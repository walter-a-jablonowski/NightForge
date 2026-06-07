"""Capability floor — the end-to-end regression gate (runtime, non-editable).

Runs the candidate /src against the fixed floor cases (floor_cases.py) with real
LLM calls and acts as a regression gate: the candidate must score >= the
currently deployed /dist (recorded in agent.log, un-gameable). On the first
deploy there is no prior score, so the candidate must clear the cold-start bar.
A single failing case is re-run once before it can block a deploy.

The floor's spend is **runtime overhead** (``floor_cost``), recorded on the
deploy step record / failed-deploy entry and NOT charged to the agent's budget.

Two invocation paths, one ``run()``:
  * real deploy — invoked as ``python -m tools.capability_floor <root>``; builds
    the real LLM from the secret channel and prints a JSON verdict;
  * tests / boot-check — called in-process with an ``llm_factory`` that injects a
    deterministic stub, so the gate + swap + respawn cycle is verifiable offline.
"""

from __future__ import annotations

import json
import sys
import tempfile
from copy import copy
from pathlib import Path

from . import audit, floor_cases


def _run_case(root: Path, config, case, llm) -> tuple[bool, float]:
    """Run one case against the candidate; return (passed, cost)."""
    import src.agent as agent

    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as tf:
        tmp_log = Path(tf.name)
    try:
        case_cfg = copy(config)
        case_cfg.mode = "production"
        case_cfg.system_prompt = case.prompt
        case_cfg.instructions = ""
        case_cfg.limits = {**config.limits, "max_steps": case.max_steps, "max_cost": 1.0}
        case_cfg.log_path_override = tmp_log

        answer = agent.run_agent(case_cfg, llm)
        calls = _flatten_calls(tmp_log)
        cost = audit.session_totals(tmp_log)["cost_sum"]
        try:
            passed = bool(case.check(answer, calls))
        except Exception:
            passed = False
        return (passed, cost)
    finally:
        tmp_log.unlink(missing_ok=True)


def _flatten_calls(log_path: Path) -> list[dict]:
    calls = []
    for rec in audit._read_records(log_path):
        for c in rec.get("calls", []) or []:
            calls.append(c)
    return calls


def run(root, config, deployed_score=None, llm_factory=None) -> dict:
    root = Path(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if llm_factory is not None:
        llm = llm_factory(config)
    else:
        from src import registry
        from tools import secrets
        key = secrets.get_key(config.llm.get("provider", ""))
        if not key:
            return {"ok": False, "score": 0.0, "floor_cost": 0.0,
                    "detail": f"capability floor needs an API key for provider "
                              f"{config.llm.get('provider')!r} (set it in .env)"}
        llm = registry.build_llm(config, key)

    floor_cost = 0.0
    results: dict[str, bool] = {}
    for case in floor_cases.CASES:
        passed, cost = _run_case(root, config, case, llm)
        floor_cost += cost
        if not passed:  # re-run a single failing case once before trusting the failure
            passed2, cost2 = _run_case(root, config, case, llm)
            floor_cost += cost2
            passed = passed or passed2
        results[case.id] = passed

    score = float(sum(1 for v in results.values() if v))

    if deployed_score is None:
        bar = floor_cases.COLD_START_BAR
        ok = score >= bar
        detail = f"cold-start: score {score:.0f}/{len(floor_cases.CASES)} vs bar {bar} | {results}"
    else:
        ok = score >= (deployed_score - floor_cases.TOLERANCE)
        detail = f"regression: score {score:.0f} vs deployed {deployed_score:.0f} | {results}"

    return {"ok": ok, "score": score, "floor_cost": floor_cost, "detail": detail}


def main(argv):
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools import config as cfg
    from tools import sandbox, secrets

    config = cfg.load_config(root, code_dir=root / "src")
    sandbox.configure(config)
    secrets.load(root)
    secrets.scrub()  # clears os.environ; the secret _STORE survives for get_key()
    deployed = audit.last_deploy_score(config.log_path)
    verdict = run(root, config, deployed_score=deployed)
    print(json.dumps(verdict))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
