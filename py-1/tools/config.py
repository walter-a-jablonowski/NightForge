"""Config parsing + the governance lock.

The runtime parses config and hands the agent a frozen ``Config`` object; the
agent never re-reads the config files itself (see idea-py.md -> Runtime <-> agent
interface). The governance keys ``llm`` / ``limits`` / ``improve`` / ``web`` /
``tools`` are taken **only** from the operator's file (``dev-config.yml`` in dev,
``user-config.yml`` in production). They are stripped from the agent-authored
``config.yml`` so the agent cannot switch its own model, lift its own cost /
deploy ceilings, widen its own ``improve`` level, or change the outbound identity
it presents.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Keys owned by the operator's config alone. Ignored if they appear in config.yml.
GOVERNANCE_KEYS = ("llm", "limits", "improve", "web", "tools")

DEFAULT_LIMITS = {
    "max_steps": 50,
    "max_cost": 5.0,
    "max_cost_sum": 50.0,
    "max_deploys": 30,
}


class ConfigError(Exception):
    """Raised on a malformed or incomplete operator config (fail fast at startup)."""


@dataclass
class Config:
    agent_root: Path
    code_dir: Path  # the active code package dir being run (dist for a normal run)
    mode: str  # "dev" | "production"
    llm: dict[str, Any]
    limits: dict[str, Any]
    improve: str  # off | tools | full  (dev mode == full)
    web: dict[str, Any]
    tools: dict[str, Any]  # {"web_search": <backend>, "web_fetch": <backend>}
    system_prompt: str
    instructions: str
    agent_settings: dict[str, Any] = field(default_factory=dict)
    # Optional redirect for agent.log — used by the smoke floor to run a real
    # loop step against a throwaway log instead of the live audit trail.
    log_path_override: Path | None = None

    @property
    def user_agent(self) -> str:
        """UA composed as ``<user_agent> (+<contact>)`` (see web.md -> Identification)."""
        name = self.web.get("user_agent", "agent")
        contact = self.web.get("contact")
        return f"{name} (+{contact})" if contact else name

    @property
    def system_prompt_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()

    @property
    def log_path(self) -> Path:
        return self.log_path_override or (self.agent_root / "agent.log")

    @property
    def data_dir(self) -> Path:
        return self.agent_root / "data"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"malformed YAML in {path.name}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a mapping at top level")
    return data


def load_config(agent_root: str | Path, code_dir: str | Path | None = None) -> Config:
    """Parse operator config + the agent's config.yml into a frozen Config.

    ``code_dir`` is the active code package directory (``dist`` for a normal run,
    ``src`` when the gate evaluates a candidate). It defaults to ``<root>/dist``.
    """
    agent_root = Path(agent_root)
    code_dir = Path(code_dir) if code_dir else agent_root / "dist"

    dev = _read_yaml(agent_root / "dev-config.yml")
    mode = dev.get("mode", "dev")
    if mode not in ("dev", "production"):
        raise ConfigError(f"mode must be 'dev' or 'production', got {mode!r}")

    if mode == "dev":
        operator = dev
        system_prompt = operator.get("systemPrompt") or ""
        instructions = operator.get("devInstructions") or ""
        improve = "full"  # dev mode has unrestricted /src edits
    else:
        operator = _read_yaml(agent_root / "user-config.yml")
        agent_md = agent_root / "AGENT.md"
        if not agent_md.exists():
            raise ConfigError("production mode requires AGENT.md (system prompt)")
        system_prompt = agent_md.read_text(encoding="utf-8")
        instructions = operator.get("prodInstructions") or ""
        improve = operator.get("improve", "tools")
        if improve not in ("off", "tools", "full"):
            raise ConfigError(f"improve must be off|tools|full, got {improve!r}")

    llm = operator.get("llm")
    if not isinstance(llm, dict) or not llm.get("provider"):
        raise ConfigError("operator config must set llm.provider")
    if not llm.get("model"):
        raise ConfigError("operator config must set llm.model")

    limits = {**DEFAULT_LIMITS, **(operator.get("limits") or {})}
    web = operator.get("web") or {}
    tools = operator.get("tools") or {"web_search": "tavily", "web_fetch": "jina"}

    # The agent's own settings (config.yml) — governance keys stripped out.
    agent_settings: dict[str, Any] = {}
    cfg_path = code_dir / "config.yml"
    if cfg_path.exists():
        raw = _read_yaml(cfg_path)
        agent_settings = {k: v for k, v in raw.items() if k not in GOVERNANCE_KEYS}

    return Config(
        agent_root=agent_root,
        code_dir=code_dir,
        mode=mode,
        llm=llm,
        limits=limits,
        improve=improve,
        web=web,
        tools=tools,
        system_prompt=system_prompt,
        instructions=instructions,
        agent_settings=agent_settings,
    )
