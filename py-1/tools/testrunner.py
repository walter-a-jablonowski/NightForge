"""Sandboxed pytest runner (runtime).

Runs a package's ``tests/`` suite in a subprocess with secrets scrubbed from the
environment. Used by the ``run_tests`` tool and by the deploy gate's agent-tests
layer. The subprocess inherits the same OS-level fs/network restrictions as the
parent (the operator container is the real boundary — see sandbox.py).

Tests live inside the package (``src.tests`` / ``dist.tests``) and import siblings
relatively (``from .. import memory``), so the same suite is portable across the
src->dist swap.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_pytest(pkg_dir: str | Path, agent_root: str | Path, timeout: int = 300) -> tuple[bool, str]:
    pkg_dir = Path(pkg_dir)
    agent_root = Path(agent_root)
    tests_dir = pkg_dir / "tests"
    if not tests_dir.exists():
        return (True, "no tests directory — nothing to run")

    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env["PYTHONPATH"] = str(agent_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    cmd = [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--import-mode=importlib"]
    try:
        proc = subprocess.run(
            cmd, cwd=str(agent_root), env=env, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return (False, f"tests timed out after {timeout}s")
    except FileNotFoundError:
        return (False, "pytest not available in the venv")

    output = (proc.stdout or "") + (proc.stderr or "")
    # exit 0 = passed; 5 = no tests collected (treat as pass-with-note)
    if proc.returncode == 0:
        return (True, output or "all tests passed")
    if proc.returncode == 5:
        return (True, "no tests collected\n" + output)
    return (False, output or f"pytest exited {proc.returncode}")
