"""Structured JSONL audit log (``agent.log``) — written by the runtime.

The agent's loop supplies step data; the runtime writes it. Because the log is
runtime-owned (the agent has no ``fs_write`` access to ``agent.log``), the
cumulative caps and the capability-floor regression bar derived from it cannot be
gamed. The log survives ``/dist`` swaps and is the source ``resume_after_deploy``
replays.

Record shapes (see idea-py.md -> Logging):
  header: {ts, run_id, kind:"header", model, limits, system_prompt_hash, tools}
  step:   {ts, run_id, step, thought, calls:[{id,tool,params,result,ok}],
           tokens:{in,out}, cost, deploy}
A ``deploy`` step also carries deploy metadata in the ``deploy`` field:
  {ref, score, floor_cost}. A failed deploy is logged as a step with
  ``deploy.ok == false`` and its ``floor_cost``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

RESULT_CAP = 8000  # observations longer than this are elided in the log


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(log_path: Path, record: dict) -> None:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_records(log_path: Path) -> list[dict]:
    if not Path(log_path).exists():
        return []
    out = []
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def next_run_id(log_path: Path) -> str:
    n = 0
    for rec in _read_records(log_path):
        if rec.get("kind") == "header":
            n += 1
    return f"r-{n + 1}"


def write_header(log_path: Path, run_id: str, model: str, limits: dict,
                 system_prompt_hash: str, tools: list[str]) -> None:
    _append(Path(log_path), {
        "ts": _now(), "run_id": run_id, "kind": "header",
        "model": model, "limits": limits,
        "system_prompt_hash": system_prompt_hash, "tools": tools,
    })


def _clip(result: str) -> str:
    if isinstance(result, str) and len(result) > RESULT_CAP:
        return result[:RESULT_CAP] + "\n[result elided — full output not stored]"
    return result


def write_step(log_path: Path, run_id: str, step: int, thought: str | None,
               calls: list[dict], tokens: dict, cost: float, deploy: dict | None = None) -> None:
    rec = {
        "ts": _now(), "run_id": run_id, "step": step,
        "thought": thought or "",
        "calls": [
            {"id": c.get("id"), "tool": c.get("tool"), "params": c.get("params", {}),
             "result": _clip(c.get("result", "")), "ok": bool(c.get("ok", True))}
            for c in calls
        ],
        "tokens": tokens, "cost": cost, "deploy": deploy,
    }
    _append(Path(log_path), rec)


# --- derived state -----------------------------------------------------------

def session_totals(log_path: Path) -> dict:
    """Cumulative session $ and deploy count, derived from the log (un-gameable)."""
    cost_sum = 0.0
    deploys = 0
    for rec in _read_records(log_path):
        if rec.get("kind") == "header":
            continue
        if "step" in rec:
            cost_sum += float(rec.get("cost") or 0.0)
            dep = rec.get("deploy")
            if dep and dep.get("ok", True) and dep.get("ref") is not None:
                deploys += 1
    return {"cost_sum": cost_sum, "deploys": deploys}


def last_deploy_score(log_path: Path) -> float | None:
    """The capability-floor score of the currently deployed /dist (or None)."""
    score = None
    for rec in _read_records(log_path):
        dep = rec.get("deploy")
        if dep and dep.get("ok", True) and dep.get("score") is not None:
            score = dep.get("score")
    return score


def replay_memory(log_path: Path, system_prompt: str, user_goal: str) -> list[dict]:
    """Rebuild session memory from the whole log (every run_id), for resume.

    Front of the transcript (system + user goal) is reconstructed from current
    config; the middle (assistant thoughts + tool calls + observations) is
    replayed from every step record, matching each result back to its call by id.
    """
    memory: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_goal},
    ]
    for rec in _read_records(log_path):
        if rec.get("kind") == "header" or "step" not in rec:
            continue
        calls = rec.get("calls", [])
        if not calls:
            continue
        memory.append({
            "role": "assistant",
            "content": rec.get("thought", ""),
            "tool_calls": [
                {"id": c.get("id"), "name": c.get("tool"), "params": c.get("params", {})}
                for c in calls
            ],
        })
        for c in calls:
            memory.append({
                "role": "tool", "tool_call_id": c.get("id"),
                "name": c.get("tool"), "content": c.get("result", ""),
            })
    return memory


def has_history(log_path: Path) -> bool:
    """True if any step has been logged (i.e. this is a respawn, not a cold boot)."""
    for rec in _read_records(log_path):
        if "step" in rec:
            return True
    return False
