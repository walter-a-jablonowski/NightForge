"""Secret injection + environment scrub.

Adapters never read ``.env`` or ``os.environ`` themselves. The runtime loads
secrets here, hands the configured LLM client its key (the client arrives
pre-built — see boot.py), exposes web-backend keys through the controlled
``get_key`` channel (by the ``<BACKEND>_API_KEY`` convention), and then **scrubs
secrets from the environment** so ``/src`` code cannot read ``.env`` out of
``os.environ`` (closing the bypass around the ``fs_read`` ``.env`` exclusion).

In-language scrubbing is defense-in-depth, not the boundary (see sandbox.py).
"""

from __future__ import annotations

import os
from pathlib import Path

_STORE: dict[str, str] = {}
_loaded = False


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val in ("", "..."):  # placeholder in .env.sample
            continue
        out[key] = val
    return out


def load(agent_root: str | Path) -> None:
    """Load .env (and any *_API_KEY already in the environment) into the store."""
    global _loaded
    _STORE.clear()
    # Pre-existing environment keys (e.g. CI-provided) are honoured too.
    for k, v in os.environ.items():
        if k.endswith("_API_KEY") and v:
            _STORE[k] = v
    env_path = Path(agent_root) / ".env"
    if env_path.exists():
        _STORE.update(_parse_env(env_path.read_text(encoding="utf-8")))
    _loaded = True


def scrub() -> None:
    """Remove secrets from os.environ before agent code runs."""
    for k in list(os.environ.keys()):
        if k.endswith("_API_KEY") or k in _STORE:
            os.environ.pop(k, None)


def get_key(backend: str) -> str | None:
    """Return the key for a backend/provider by the ``<BACKEND>_API_KEY`` convention.

    ``backend`` may be the bare name ("tavily") or the full env name
    ("TAVILY_API_KEY"); case-insensitive on the bare name.
    """
    if not _loaded:
        raise RuntimeError("secrets.load() not called")
    name = backend if backend.endswith("_API_KEY") else f"{backend.upper()}_API_KEY"
    return _STORE.get(name)
