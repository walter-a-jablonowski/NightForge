"""Bounded dependency installer (runtime) — a capability, not a shell.

Installs a single package from PyPI into the agent's venv via pip and pins the
resolved version into ``/src/pyproject.toml`` so the dependency set rides the
deploy (test-gated + reproducible). Default-allow for ordinary PyPI packages.

The **restricted set** crosses the capability frontier and needs human approval
(rejected here with a clear message): installing/replacing the installer or
package manager itself; any index other than the configured PyPI
(``--index-url`` / ``--extra-index-url``); and VCS / URL / local-path installs.
See app-concept-py.md -> Security -> Dependencies.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# requirement spec: name[extras]<version-constraint>, nothing else
_SPEC_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"          # package name
    r"(\[[A-Za-z0-9._,\-]+\])?"             # optional extras
    r"([<>=!~]=?[A-Za-z0-9._*\-]+)?$"        # optional single version constraint
)

_RESTRICTED = {"pip", "uv", "poetry", "setuptools", "wheel", "pipenv", "conda", "virtualenv"}


def _name_of(spec: str) -> str:
    return re.split(r"[\[<>=!~ ]", spec, 1)[0].strip().lower().replace("_", "-")


def _validate(package: str) -> str | None:
    """Return an approval-required/invalid message, or None if allowed."""
    p = package.strip()
    if not p:
        return "no package specified"
    lowered = p.lower()
    if any(tok in lowered for tok in ("://", "git+", "file:", "--index-url", "--extra-index-url")):
        return ("needs human approval: off-PyPI-index / VCS / URL / local-path installs "
                "cross the capability frontier")
    if p.startswith("-") or "/" in p or "\\" in p:
        return "needs human approval: flags and path installs are not permitted"
    if not _SPEC_RE.match(p):
        return f"invalid package spec: {package!r} (expected name[extras][==version])"
    if _name_of(p) in _RESTRICTED:
        return (f"needs human approval: {_name_of(p)!r} is an installer/package-manager "
                "package (restricted set)")
    return None


def install(package: str, agent_root: str | Path, timeout: int = 300) -> tuple[bool, str]:
    reason = _validate(package)
    if reason:
        return (False, reason)

    cmd = [sys.executable, "-m", "pip", "install", "--no-input",
           "--disable-pip-version-check", package]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return (False, f"install timed out after {timeout}s")
    if proc.returncode != 0:
        return (False, (proc.stdout or "") + (proc.stderr or ""))

    name = _name_of(package)
    version = _installed_version(name)
    pin = f"{name}=={version}" if version else package
    pinned = _pin_into_pyproject(Path(agent_root) / "src" / "pyproject.toml", name, pin)
    note = f"installed {pin}; pinned into /src/pyproject.toml" if pinned else \
           f"installed {pin}; could not update pyproject.toml (pin manually)"
    return (True, note)


def _installed_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def _pin_into_pyproject(path: Path, name: str, pin: str) -> bool:
    """Minimal pin: add/replace ``name==ver`` in [project].dependencies."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(dependencies\s*=\s*\[)(.*?)(\])", text, re.DOTALL)
    if not m:
        return False
    body = m.group(2)
    # drop any existing pin for this package, then append the new one
    body = re.sub(rf'"\s*{re.escape(name)}[^"]*"\s*,?', "", body, flags=re.IGNORECASE)
    body = body.rstrip()
    sep = "\n  "
    new_body = f"{body}{',' if body.strip() else ''}{sep}\"{pin}\",\n"
    new_text = text[: m.start(2)] + new_body + text[m.end(2):]
    path.write_text(new_text, encoding="utf-8")
    return True
