"""Deploy tool (runtime, non-editable).

Order across a full deploy: gate (smoke floor -> agent tests -> capability floor,
against /src) -> swap /src->/dist (keeping /dist.prev) -> git commit -> respawn.
A failed gate aborts the swap, leaves /dist and the running agent untouched, logs
a failed-deploy step (with ``floor_cost``), and returns the gate output as the
tool observation so the agent can fix and retry.

On success the runtime logs the deploy step itself — with a synthesized
observation (the process is about to die) and deploy metadata {ref, score,
floor_cost} — *before* respawning, so ``resume_after_deploy`` replays a complete
transcript with no orphaned tool_call.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import audit


def run_deploy(config, *, run_id, step, thought, deploy_call, tokens, cost,
               message=None, respawn=True, floor_llm_factory=None) -> str:
    """Run the gate and (on pass) swap + respawn. Returns the gate output on abort."""
    root = Path(config.agent_root)
    log_path = config.log_path
    cid = deploy_call["id"]
    params = deploy_call.get("params", {})

    # --- gate: smoke floor ---------------------------------------------------
    ok, detail = _run_smoke_floor(root)
    if not ok:
        return _abort(log_path, run_id, step, thought, cid, params, tokens, cost,
                      f"deploy aborted: smoke floor failed\n{detail}", floor_cost=0.0)

    # --- gate: agent tests ---------------------------------------------------
    from . import testrunner
    tok, tdetail = testrunner.run_pytest(root / "src", root)
    if not tok:
        return _abort(log_path, run_id, step, thought, cid, params, tokens, cost,
                      f"deploy aborted: agent tests failed\n{tdetail}", floor_cost=0.0)

    # --- gate: capability floor ---------------------------------------------
    deployed_score = audit.last_deploy_score(log_path)
    verdict = _run_capability_floor(root, config, deployed_score, floor_llm_factory)
    floor_cost = float(verdict.get("floor_cost", 0.0))
    if not verdict.get("ok"):
        return _abort(log_path, run_id, step, thought, cid, params, tokens, cost,
                      f"deploy aborted: capability floor failed\n{verdict.get('detail')}",
                      floor_cost=floor_cost, score=verdict.get("score"))

    score = float(verdict.get("score", 0.0))

    # --- swap /src -> /dist (keep /dist.prev) --------------------------------
    _swap(root)
    ref = _git_commit(root, f"deploy {run_id} step {step}: {message or ''}".strip())

    # --- log the deploy step (synthesized result), then respawn --------------
    synthesized = f"deployed: /src→/dist @ {ref}"
    audit.write_step(
        log_path, run_id, step, thought,
        [{"id": cid, "tool": "deploy", "params": params, "result": synthesized, "ok": True}],
        tokens, cost, deploy={"ref": ref, "score": score, "floor_cost": floor_cost},
    )

    if not respawn:
        return synthesized  # test path: caller verifies swap + resume
    _respawn(root)  # os.execv — never returns
    return synthesized  # unreachable


# --- gate helpers ------------------------------------------------------------

def _run_smoke_floor(root: Path) -> tuple[bool, str]:
    env = _clean_env(root)
    cmd = [sys.executable, "-m", "tools.smoke_floor", str(root)]
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return (False, "smoke floor timed out")
    verdict = _last_json(proc.stdout) or {}
    if not verdict:
        return (False, (proc.stdout or "") + (proc.stderr or "") or "smoke floor: no verdict")
    return (bool(verdict.get("ok")), verdict.get("detail", ""))


def _run_capability_floor(root: Path, config, deployed_score, floor_llm_factory) -> dict:
    # Offline self-test: drive the floor with the deterministic stub.
    if floor_llm_factory is None and os.environ.get("AGENT_STUB_LLM"):
        from ._stub import make_floor_factory
        floor_llm_factory = make_floor_factory()
    if floor_llm_factory is not None:
        from . import capability_floor
        return capability_floor.run(root, config, deployed_score=deployed_score,
                                     llm_factory=floor_llm_factory)
    env = _clean_env(root)
    cmd = [sys.executable, "-m", "tools.capability_floor", str(root)]
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "score": 0.0, "floor_cost": 0.0, "detail": "capability floor timed out"}
    verdict = _last_json(proc.stdout)
    if not verdict:
        return {"ok": False, "score": 0.0, "floor_cost": 0.0,
                "detail": (proc.stdout or "") + (proc.stderr or "") or "no verdict"}
    return verdict


def _clean_env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items()}
    env["PYTHONPATH"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _last_json(text: str) -> dict | None:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _abort(log_path, run_id, step, thought, cid, params, tokens, cost, message, *,
           floor_cost, score=None) -> str:
    audit.write_step(
        log_path, run_id, step, thought,
        [{"id": cid, "tool": "deploy", "params": params, "result": message, "ok": False}],
        tokens, cost, deploy={"ref": None, "score": score, "floor_cost": floor_cost, "ok": False},
    )
    return message


# --- swap / git / respawn ----------------------------------------------------

def _swap(root: Path) -> None:
    src, dist, prev = root / "src", root / "dist", root / "dist.prev"
    if dist.exists():
        if prev.exists():
            shutil.rmtree(prev)
        shutil.move(str(dist), str(prev))
    shutil.copytree(src, dist, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def _git_commit(root: Path, message: str) -> str:
    if not shutil.which("git"):
        return "dist.prev"  # rollback falls back to the single /dist.prev step
    try:
        if not (root / ".git").exists():
            subprocess.run(["git", "init"], cwd=str(root), capture_output=True, timeout=30)
            subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, timeout=60)
        subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, timeout=60)
        subprocess.run(["git", "commit", "-m", message, "--allow-empty"],
                       cwd=str(root), capture_output=True, timeout=60)
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "dist.prev"
    except Exception:
        return "dist.prev"


def _respawn(root: Path) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable, "-m", "tools.boot", str(root)])
