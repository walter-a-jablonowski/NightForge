"""Outbound HTTP etiquette helpers shared by fetch backends (see web.md).

The runtime independently enforces the egress allowlist + User-Agent; this layer
covers the backend's own responsibilities: robots.txt (Disallow / Crawl-delay)
and 429/Retry-After backoff. robots.txt is fetched through the runtime guard
(open-web GET) and parsed/cached per host. The remaining web.md rules
(X-Robots-Tag, conditional requests, sitemaps) become binding once the agent
grows a persistent URL index — deferred per web.md.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from tools import sandbox

_robots_cache: dict[str, RobotFileParser | None] = {}
_last_request: dict[str, float] = {}


class DisallowedByRobots(Exception):
    pass


def _robots_for(host_scheme: str, ua: str) -> RobotFileParser | None:
    if host_scheme in _robots_cache:
        return _robots_cache[host_scheme]
    rp: RobotFileParser | None = RobotFileParser()
    try:
        resp = sandbox.http_request(
            "GET", f"{host_scheme}/robots.txt", allow_open_web=True, timeout=10.0
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            rp = None  # no robots.txt -> allowed
    except Exception:
        rp = None
    _robots_cache[host_scheme] = rp
    return rp


def check_and_pace(url: str, user_agent: str) -> None:
    """Raise DisallowedByRobots if blocked; otherwise honor crawl-delay pacing."""
    parsed = urlparse(url)
    host_scheme = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_for(host_scheme, user_agent)
    if rp is not None and not rp.can_fetch(user_agent, url):
        raise DisallowedByRobots(f"robots.txt disallows fetching {url}")

    delay = 1.0
    if rp is not None:
        try:
            cd = rp.crawl_delay(user_agent)
            if cd:
                delay = float(cd)
        except Exception:
            pass
    last = _last_request.get(parsed.netloc)
    if last is not None:
        wait = delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(min(wait, 5.0))
    _last_request[parsed.netloc] = time.monotonic()
