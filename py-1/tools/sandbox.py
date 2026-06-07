"""In-language security guards (defense-in-depth).

IMPORTANT — this is **not** the security boundary. Per idea-py.md -> Security ->
Enforcement boundary, the real boundary is OS-level: the agent is expected to run
inside an operator-provided isolated process/container (Docker Desktop / WSL2 on
Windows) with the filesystem mounted to scope and *all* egress forced through an
allowlist. Python code running with the process's privileges can reach around any
in-process guard (``ctypes``, ``__import__``, C extensions). These checks are a
defense-in-depth layer and a clear contract; they are not a substitute for the
container. See README.md -> "Run note: container requirement".

This module enforces, in-process:
  * the network egress allowlist (host + method), with the runtime User-Agent;
  * the filesystem read/write scope (with ``improve`` narrowing in production);
  * per-write size + /src disk-quota resource limits;
  * the ``<untrusted>`` wrapping of web results.

It is configured once at startup via ``configure(config)`` and is non-editable by
the agent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

# --- resource limits ---------------------------------------------------------
MAX_WRITE_BYTES = 5 * 1024 * 1024  # per-write file size cap
SRC_DISK_QUOTA = 50 * 1024 * 1024  # total bytes allowed under /src

# Methods allowed against arbitrary open-web hosts (read-only, no body).
_OPEN_WEB_METHODS = {"GET", "HEAD"}

# Static host map for shipped backends/providers. Adding a host is a
# capability-frontier change (human-extended) — the agent cannot widen this.
_PROVIDER_HOSTS = {"openrouter": {"openrouter.ai"}}
_SEARCH_HOSTS = {
    "tavily": {"api.tavily.com"},
    "exa": {"api.exa.ai"},
    "serper": {"google.serper.dev"},
}
_FETCH_HOSTS = {
    "jina": {"r.jina.ai"},
    "firecrawl": {"api.firecrawl.dev"},
    "trafilatura": set(),  # pure open-web fetcher, no configured host of its own
}
_PYPI_HOSTS = {"pypi.org", "files.pythonhosted.org"}


class SecurityError(Exception):
    """Raised when a guard rejects an operation (fed back to the model, non-fatal)."""


class _State:
    agent_root: Path | None = None
    read_excludes: list[Path] = []
    src_dir: Path | None = None
    data_dir: Path | None = None
    prod_ready: Path | None = None
    improve: str = "full"
    configured_hosts: set[str] = set()
    user_agent: str = "agent"
    _client: httpx.Client | None = None


_S = _State()


def _configured_hosts(config) -> set[str]:
    hosts: set[str] = set(_PYPI_HOSTS)
    hosts |= _PROVIDER_HOSTS.get(config.llm.get("provider", ""), set())
    base_url = config.llm.get("base_url")
    if base_url:
        h = urlparse(base_url).hostname
        if h:
            hosts.add(h)
    hosts |= _SEARCH_HOSTS.get(config.tools.get("web_search", ""), set())
    hosts |= _FETCH_HOSTS.get(config.tools.get("web_fetch", ""), set())
    return hosts


def configure(config) -> None:
    """Initialise the guards from the parsed Config. Called once at startup."""
    root = Path(config.agent_root).resolve()
    _S.agent_root = root
    _S.src_dir = (root / "src").resolve()
    _S.data_dir = (root / "data").resolve()
    _S.prod_ready = (root / "dist" / "production-ready").resolve()
    _S.improve = config.improve
    _S.read_excludes = [
        (root / ".env").resolve(),
        (root / "dev-config.yml").resolve(),
        (root / "user-config.yml").resolve(),
        (root / "tools").resolve(),  # the runtime's own files
        (root / ".venv").resolve(),
        (root / ".git").resolve(),
    ]
    _S.configured_hosts = _configured_hosts(config)
    _S.user_agent = config.user_agent


# --- filesystem scope --------------------------------------------------------

def _under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve(path: str) -> Path:
    if _S.agent_root is None:
        raise SecurityError("sandbox not configured")
    p = Path(path)
    if not p.is_absolute():
        p = _S.agent_root / p
    return p.resolve()


def check_read(path: str) -> Path:
    """Validate a read target is inside /agent and not an excluded file/dir."""
    p = _resolve(path)
    if not _under(p, _S.agent_root):
        raise SecurityError(f"read outside /agent denied: {path}")
    for ex in _S.read_excludes:
        if p == ex or _under(p, ex):
            raise SecurityError(f"read of protected path denied: {path}")
    return p


def check_write(path: str) -> Path:
    """Validate a write target against the write scope (with improve narrowing)."""
    p = _resolve(path)
    if not _under(p, _S.agent_root):
        raise SecurityError(f"write outside /agent denied: {path}")

    # /data — memory, writable in all modes regardless of improve.
    if _under(p, _S.data_dir):
        return p
    # the single allowed /dist file
    if p == _S.prod_ready:
        return p
    # /src — code, governed by improve
    if _under(p, _S.src_dir):
        if _S.improve == "off":
            raise SecurityError("improve: off — /src writes are disabled")
        if _S.improve == "tools":
            allowed_parents = [
                (_S.src_dir / "providers").resolve(),
                (_S.src_dir / "tools").resolve(),
            ]
            if not any(_under(p, ap) for ap in allowed_parents):
                raise SecurityError(
                    "improve: tools — writes restricted to existing files under "
                    "/src/providers and /src/tools"
                )
            if not p.exists():
                raise SecurityError("improve: tools — cannot create new files")
        return p
    raise SecurityError(f"write outside /src + /data scope denied: {path}")


def check_write_size(data: bytes) -> None:
    if len(data) > MAX_WRITE_BYTES:
        raise SecurityError(
            f"write exceeds per-file cap ({len(data)} > {MAX_WRITE_BYTES} bytes)"
        )


def src_disk_usage() -> int:
    if _S.src_dir is None or not _S.src_dir.exists():
        return 0
    total = 0
    for dirpath, _dirs, files in os.walk(_S.src_dir):
        for f in files:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    return total


def check_src_quota(extra: int) -> None:
    if src_disk_usage() + extra > SRC_DISK_QUOTA:
        raise SecurityError(f"/src disk quota exceeded ({SRC_DISK_QUOTA} bytes)")


# --- network egress ----------------------------------------------------------

def _client() -> httpx.Client:
    if _S._client is None:
        # Connection pooling (etiquette: reuse connections) + sane redirect cap.
        _S._client = httpx.Client(
            follow_redirects=True,
            max_redirects=5,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": _S.user_agent},
        )
    return _S._client


def http_request(
    method: str,
    url: str,
    *,
    allow_open_web: bool = False,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Guarded outbound HTTP. Enforces the egress allowlist (host + method).

    - Configured hosts (providers/backends + PyPI): any method.
    - Open web (any other host): only when ``allow_open_web`` is set, and only
      GET/HEAD with no request body — fetch can *read* a site, never *act* on it.
    The runtime User-Agent is always injected; callers cannot override it.
    """
    method = method.upper()
    host = urlparse(url).hostname or ""
    has_body = bool(kwargs.get("content") or kwargs.get("data") or kwargs.get("json"))

    if host in _S.configured_hosts:
        pass  # configured host: full methods allowed
    elif allow_open_web and method in _OPEN_WEB_METHODS and not has_body:
        pass  # open-web read: GET/HEAD, no body
    else:
        raise SecurityError(
            f"egress denied: {method} {host or url!r} "
            f"({'off-allowlist host' if host not in _S.configured_hosts else 'mutating method on open web'})"
        )

    merged = {"User-Agent": _S.user_agent}
    if headers:
        merged.update(headers)
    merged["User-Agent"] = _S.user_agent  # cannot be overridden by the caller
    return _client().request(method, url, headers=merged, **kwargs)


# --- untrusted content -------------------------------------------------------

def wrap_untrusted(source: str, content: str) -> str:
    """Wrap web results so the model treats them as data, not commands."""
    safe_source = source.replace('"', "'")
    return f'<untrusted source="{safe_source}">\n{content}\n</untrusted>'
