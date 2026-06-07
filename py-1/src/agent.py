"""The agent: frozen entrypoint, supervisor, ReAct loop, resume.

``main(config, llm=None)`` is the frozen runtime<->agent contract — the runtime
starts and respawns it (signature verified by the smoke floor; off-limits even
under ``improve: full``). Everything behind it (loop body, memory, providers,
tools) is agent-editable.
"""

from __future__ import annotations

from tools import audit

from . import memory as mem
from . import registry


# --- frozen entrypoint + supervisor -----------------------------------------

def main(config, llm=None):
    """Drive runs until the session is done (see idea-py.md -> Run lifecycle).

    A ``deploy`` inside ``run_agent`` replaces the process; the respawned main()
    re-enters here and the next ``run_agent`` resumes the chain from agent.log.
    """
    log_path = config.log_path
    while True:
        totals = audit.session_totals(log_path)
        if totals["cost_sum"] >= config.limits["max_cost_sum"]:
            return _halt("cumulative max_cost_sum reached", totals)
        if totals["deploys"] >= config.limits["max_deploys"]:
            return _halt("cumulative max_deploys reached", totals)

        result = run_agent(config, llm)

        if config.mode == "production":
            return result  # batch: serve the goal(s) once, then exit
        if (config.agent_root / "dist" / "production-ready").exists():
            return _halt("agent signalled production-ready", {"result": result})
        # else: dev mode continues with a fresh run


def _halt(reason: str, info: dict) -> str:
    return f"halted: {reason} ({info})"


def _user_goal(config) -> str:
    if config.mode == "dev":
        goal = (
            "Begin dev mode. Improve your implementation toward the capability "
            "checklist in your system prompt: research current best practice with "
            "web_search/web_fetch, edit your code under /src with fs_write, verify "
            "with run_tests, then deploy. Record findings and progress in "
            "/data/db (index.md, roadmap.md). When you judge yourself ready, write "
            "/dist/production-ready."
        )
    else:
        goal = "Begin. Work through the goal(s) defined in your system prompt."
    if config.instructions and config.instructions.strip():
        goal += "\n\nOperator instructions:\n" + config.instructions.strip()
    return goal


# --- one run -----------------------------------------------------------------

def run_agent(config, llm):
    log_path = config.log_path
    limits = config.limits
    run_id = audit.next_run_id(log_path)
    user_goal = _user_goal(config)

    if audit.has_history(log_path):
        memory = resume_after_deploy(config, llm)   # rebuild from the whole session
    else:
        memory = mem.new_session(config.system_prompt, user_goal)

    specs = registry.tool_specs()
    impls = registry.build_tool_impls(config)
    audit.write_header(
        log_path, run_id, config.llm.get("model", "?"), limits,
        config.system_prompt_hash, registry.TOOL_NAMES,
    )

    steps = 0
    cost = 0.0
    while steps < limits["max_steps"] and cost < limits["max_cost"]:
        steps += 1
        mem.safety_clip(memory, llm)
        response = llm.call(memory, tools=specs)
        cost += float(response.get("cost") or 0.0)
        thought = response.get("content")
        tool_calls = response.get("tool_calls") or []

        if not tool_calls:
            audit.write_step(log_path, run_id, steps, thought, [], response["tokens"], response["cost"])
            return thought or "done"

        # deploy is terminal: force it to run alone, before recording the turn,
        # so no sibling call is logged without a tool response.
        if any(c["name"] == "deploy" for c in tool_calls):
            tool_calls = [c for c in tool_calls if c["name"] == "deploy"][:1]

        memory.append({"role": "assistant", "content": thought or "", "tool_calls": tool_calls})

        calls_log = []
        deploy_logged = False
        for call in tool_calls:
            name, params, cid = call["name"], call.get("params", {}), call["id"]
            if name == "deploy":
                # Terminal: the runtime runs the gate, logs the deploy step, and
                # respawns on success (never returns). On a gate abort it returns
                # the gate output and has already logged the failed-deploy step.
                from tools import deploy as deploy_tool
                observation = deploy_tool.run_deploy(
                    config, run_id=run_id, step=steps, thought=thought,
                    deploy_call=call, tokens=response["tokens"], cost=response["cost"],
                    message=params.get("message"),
                )
                memory.append({"role": "tool", "tool_call_id": cid, "name": name, "content": observation})
                deploy_logged = True
                break
            elif name not in impls:
                observation, ok = f"unknown tool: {name}", False
            else:
                try:
                    observation, ok = impls[name](params)
                except Exception as e:  # noqa: BLE001 — funnel back to the model
                    observation, ok = f"tool error: {e}", False
            memory.append({"role": "tool", "tool_call_id": cid, "name": name, "content": observation})
            calls_log.append({"id": cid, "tool": name, "params": params, "result": observation, "ok": ok})

        if not deploy_logged:
            audit.write_step(log_path, run_id, steps, thought, calls_log, response["tokens"], response["cost"])

    return "stopped: step/cost limit reached"


def resume_after_deploy(config, llm):
    """Rebuild memory from the whole session log and apply the safety clip."""
    memory = audit.replay_memory(config.log_path, config.system_prompt, _user_goal(config))
    mem.safety_clip(memory, llm)
    return memory
