"""Jina Reader web_fetch backend.

Jina Reader (``https://r.jina.ai/<url>``) fetches a page and returns clean
markdown. The request to ``r.jina.ai`` is a configured host; the target URL is
robots-checked first (open-web GET via the runtime guard). A JINA_API_KEY is
optional (raises rate limits) and comes from the runtime secret channel.

Returns the normalized fetch shape (see idea-py.md -> Web backends):
    { content, content_type, status }
"""

from __future__ import annotations

import time

from tools import sandbox, secrets

from ..etiquette import DisallowedByRobots, check_and_pace

PREFIX = "https://r.jina.ai/"
_MAX_RETRIES = 3


def fetch(url: str, **extras) -> dict:
    # Honor robots.txt for the *target* host before asking Jina to fetch it.
    ua = sandbox._S.user_agent  # runtime-composed UA (read-only)
    try:
        check_and_pace(url, ua)
    except DisallowedByRobots as e:
        return {"content": str(e), "content_type": "text", "status": 403}

    headers = {"Accept": "text/markdown"}
    key = secrets.get_key("jina")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    last_status = 0
    for attempt in range(_MAX_RETRIES):
        resp = sandbox.http_request("GET", PREFIX + url, headers=headers, timeout=60.0)
        last_status = resp.status_code
        if resp.status_code == 429:  # back off, honor Retry-After
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if (retry_after or "").isdigit() else 2.0 * (attempt + 1)
            time.sleep(min(delay, 10.0))
            continue
        if resp.status_code == 200:
            return {"content": resp.text, "content_type": "markdown", "status": 200}
        break
    return {"content": f"fetch failed (status {last_status})", "content_type": "text", "status": last_status}
