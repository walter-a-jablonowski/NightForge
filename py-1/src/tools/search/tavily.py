"""Tavily web_search backend.

Calls the Tavily HTTP API through the runtime egress guard (configured host:
``api.tavily.com``, so the search POST is allowed). The runtime injects the
User-Agent; the key comes from the runtime secret channel, never os.environ.

Returns the normalized search shape (see idea-py.md -> Web backends):
    [ { title, url, snippet, score } ]
"""

from __future__ import annotations

from tools import sandbox, secrets

ENDPOINT = "https://api.tavily.com/search"


def search(query: str, max_results: int = 5, **extras) -> list[dict]:
    key = secrets.get_key("tavily")
    if not key:
        raise RuntimeError("TAVILY_API_KEY not configured")
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": extras.get("search_depth", "basic"),
    }
    resp = sandbox.http_request("POST", ENDPOINT, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "score": r.get("score"),
            }
        )
    return results
