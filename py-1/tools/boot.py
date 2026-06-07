"""Runtime launcher / respawn entry (non-editable).

This is the process the user starts and that the deploy tool respawns
(``python -m tools.boot <agent_root>``). It parses config, loads secrets, builds
the configured LLM client (handing it the key), scrubs secrets from the
environment, configures the in-language guards, then hands control to the active
agent code's frozen ``main(config, llm)``.

The active code is the ``dist`` package; the agent edits ``src`` and deploys it
over ``dist``. A self-test hook (``AGENT_STUB_LLM=1``) injects an offline stub so
the whole chain can run without network or keys.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import config as cfg
from . import sandbox, secrets


def _ensure_dist(root: Path) -> None:
    """First launch: populate /dist from /src if it is missing/empty."""
    dist, src = root / "dist", root / "src"
    if not dist.exists() or not (dist / "agent.py").exists():
        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(src, dist, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def _build_llm(config):
    """Construct the LLM the loop runs against (real adapter, or offline stub)."""
    if os.environ.get("AGENT_STUB_LLM"):
        from ._stub import DemoLLM
        return DemoLLM(config)
    from dist import registry  # active code's registry
    key = secrets.get_key(config.llm.get("provider", ""))
    return registry.build_llm(config, key)


def run(root: str | Path) -> str:
    root = Path(root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _ensure_dist(root)

    config = cfg.load_config(root, code_dir=root / "dist")
    secrets.load(root)
    sandbox.configure(config)

    llm = _build_llm(config)          # needs the key — built before the scrub
    secrets.scrub()                   # remove secrets from os.environ before agent code runs

    from dist import agent            # the frozen entrypoint
    return agent.main(config, llm)


def main(argv):
    root = argv[1] if len(argv) > 1 else os.getcwd()
    try:
        result = run(root)
    except cfg.ConfigError as e:
        # Startup config error: fail fast with a clear message (idea-py.md -> Error handling).
        print(f"startup config error: {e}", file=sys.stderr)
        return 2
    print(result if isinstance(result, str) else "done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
