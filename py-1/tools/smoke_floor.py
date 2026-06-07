"""Smoke floor — the fixed liveness gate (runtime, non-editable).

Runs against the candidate ``src`` package in a fresh subprocess (so the live
``dist`` process's imports are untouched and a broken candidate can't crash the
runtime). Asserts that a deploy never respawns an agent that can't even start:

  1. ``src`` imports with no errors (agent, registry, configured adapters).
  2. config parses and the configured provider/search/fetch names resolve to
     adapter files that exist.
  3. the tool registry builds with valid JSON schemas.
  4. the resolved provider adapter exposes ``context_window`` + ``count_tokens``
     (the memory safety clip relies on them).
  5. one loop step runs end-to-end against a stubbed LLM (no network).
  6. the frozen interface holds: ``main(config, llm=None)`` signature + registry
     location.
  7. backend lock: when self-built backends are disallowed, no backend file
     beyond the shipped manifest is present.

Invoked as ``python -m tools.smoke_floor <agent_root>``; prints a JSON verdict
``{"ok": bool, "detail": str}`` on the last stdout line.
"""

from __future__ import annotations

import inspect
import json
import sys
import tempfile
from pathlib import Path


class _StubLLM:
    """No-network LLM: drives one tool call, then finishes."""
    context_window = 200_000

    def __init__(self):
        self._n = 0

    def count_tokens(self, messages):
        return sum(len(m.get("content") or "") for m in messages) // 4

    def call(self, messages, tools=None, **extras):
        self._n += 1
        if self._n == 1:
            return {
                "content": "smoke: listing /data",
                "tool_calls": [{"id": "c1", "name": "fs_list", "params": {"path": "data"}}],
                "tokens": {"in": 1, "out": 1}, "cost": 0.0,
            }
        return {"content": "smoke done", "tool_calls": [], "tokens": {"in": 1, "out": 1}, "cost": 0.0}


def run(agent_root: str) -> tuple[bool, str]:
    root = Path(agent_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from tools import config as cfg
    from tools import sandbox, secrets

    # (2) config parses, names resolve to existing adapter files
    try:
        config = cfg.load_config(root, code_dir=root / "src")
    except cfg.ConfigError as e:
        return (False, f"config error: {e}")

    sandbox.configure(config)
    secrets.load(root)
    secrets.scrub()

    # (1) candidate imports
    try:
        import src.agent as agent
        import src.registry as registry
        import src.memory as memory
    except Exception as e:  # noqa: BLE001
        return (False, f"import error: {e!r}")

    # (6) frozen interface: main signature + registry location
    sig = inspect.signature(agent.main)
    params = list(sig.parameters)
    if params[:2] != ["config", "llm"]:
        return (False, f"frozen entrypoint changed: main{sig}")
    if not (root / "src" / "registry.py").exists():
        return (False, "registry.py missing from /src")

    # (2 cont.) provider/search/fetch names resolve
    prov = config.llm.get("provider")
    if prov not in registry.PROVIDERS:
        return (False, f"provider {prov!r} has no adapter")
    if config.tools.get("web_search") not in registry.SEARCH_BACKENDS:
        return (False, f"web_search backend {config.tools.get('web_search')!r} has no adapter")
    if config.tools.get("web_fetch") not in registry.FETCH_BACKENDS:
        return (False, f"web_fetch backend {config.tools.get('web_fetch')!r} has no adapter")

    # (3) tool registry builds with valid schemas
    specs = registry.tool_specs()
    names = set()
    for s in specs:
        if s.get("type") != "function" or "function" not in s:
            return (False, f"bad tool spec: {s}")
        f = s["function"]
        if not f.get("name") or "parameters" not in f or f["parameters"].get("type") != "object":
            return (False, f"bad tool schema: {f.get('name')}")
        names.add(f["name"])
    if "deploy" not in names:
        return (False, "deploy tool missing from registry")
    registry.build_tool_impls(config)

    # (4) provider adapter exposes context_window + count_tokens (without invoking
    #     context_window, which would hit the network)
    llm_real = registry.build_llm(config, api_key=None)
    if not isinstance(type(llm_real).context_window, property):
        return (False, "provider adapter missing context_window property")
    if not callable(getattr(llm_real, "count_tokens", None)):
        return (False, "provider adapter missing count_tokens")

    # (7) backend lock
    ok, detail = _check_backend_lock(root, config)
    if not ok:
        return (False, detail)

    # (5) one loop step end-to-end against the stub, on a throwaway log
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as tf:
        tmp_log = Path(tf.name)
    config.log_path_override = tmp_log
    try:
        result = agent.run_agent(config, _StubLLM())
    except Exception as e:  # noqa: BLE001
        return (False, f"loop step failed under stub: {e!r}")
    finally:
        tmp_log.unlink(missing_ok=True)
    if not isinstance(result, str):
        return (False, f"run_agent returned non-string: {result!r}")

    return (True, "smoke floor passed")


def _check_backend_lock(root: Path, config) -> tuple[bool, str]:
    # Lock active in dev when allow_self_built_backends is off, or in production
    # when improve != full.
    if config.mode == "dev":
        locked = not config.web.get("allow_self_built_backends", True)
    else:
        locked = config.improve != "full"
    if not locked:
        return (True, "")
    manifest = json.loads((root / "tools" / "shipped_backends.json").read_text(encoding="utf-8"))
    checks = [
        (root / "src" / "providers", manifest["providers"]),
        (root / "src" / "tools" / "search", manifest["search"]),
        (root / "src" / "tools" / "fetch", manifest["fetch"]),
    ]
    for d, allowed in checks:
        if not d.exists():
            continue
        for f in d.glob("*.py"):
            stem = f.stem
            if stem in ("__init__", "etiquette"):
                continue
            if stem not in allowed:
                return (False, f"backend lock: {f.relative_to(root)} not in shipped manifest")
    return (True, "")


def main(argv):
    root = argv[1] if len(argv) > 1 else "."
    try:
        ok, detail = run(root)
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"smoke floor crashed: {e!r}"
    print(json.dumps({"ok": ok, "detail": detail}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
