"""Central name -> adapter registry (providers, search/fetch backends, tools).

Registration is centralized here — adapters do not self-register — so under
production ``improve: tools`` (which can edit files under /src/providers and
/src/tools but not this file) the capability set is fixed *by construction*: an
allowed edit can change a capability's behaviour but never add a tool or backend.

Adding a provider/backend = one new file + one line in the relevant map here.
This module's location is part of the frozen runtime<->agent contract; the smoke
floor verifies it exists and that the configured names resolve.
"""

from __future__ import annotations

from . import agent_tools
from .providers import openrouter
from .tools.fetch import jina
from .tools.search import exa, tavily

PROVIDERS = {
    "openrouter": openrouter.build,
}

SEARCH_BACKENDS = {
    "tavily": tavily.search,
    "exa": exa.search,
}

FETCH_BACKENDS = {
    "jina": jina.fetch,
}

# Tool names the model may call (schemas live in agent_tools).
TOOL_NAMES = [
    "web_search", "web_fetch", "fs_read", "fs_list", "fs_write", "fs_delete",
    "run_tests", "install", "deploy",
]


def build_llm(config, api_key: str | None):
    """Construct the configured provider adapter (called by the runtime)."""
    name = config.llm.get("provider")
    if name not in PROVIDERS:
        raise ValueError(f"no provider adapter for {name!r}")
    extras = {k: v for k, v in config.llm.items() if k not in ("provider", "model")}
    return PROVIDERS[name](config.llm["model"], api_key, **extras)


def get_search(name: str):
    if name not in SEARCH_BACKENDS:
        raise ValueError(f"no web_search backend for {name!r}")
    return SEARCH_BACKENDS[name]


def get_fetch(name: str):
    if name not in FETCH_BACKENDS:
        raise ValueError(f"no web_fetch backend for {name!r}")
    return FETCH_BACKENDS[name]


def tool_specs() -> list[dict]:
    return agent_tools.tool_specs()


def build_tool_impls(config) -> dict:
    return agent_tools.build_tool_impls(config)
