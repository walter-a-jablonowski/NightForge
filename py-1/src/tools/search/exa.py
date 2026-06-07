"""Exa web_search backend (secondary).

Calls the Exa HTTP API through the runtime egress guard (configured host:
``api.exa.ai``). The key comes from the runtime secret channel (EXA_API_KEY),
never os.environ. Returns the normalized search shape:
    [ { title, url, snippet, score } ]
"""

from __future__ import annotations

from tools import sandbox, secrets

ENDPOINT = "https://api.exa.ai/search"


def search(query: str, max_results: int = 5, **extras) -> list[dict]:
    key = secrets.get_key("exa")
    if not key:
        raise RuntimeError("EXA_API_KEY not configured")
    payload = {
        "query": query,
        "numResults": max_results,
        "contents": {"highlights": {"numSentences": 2}},
    }
    resp = sandbox.http_request(
        "POST", ENDPOINT, json=payload, headers={"x-api-key": key}, timeout=30.0
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("results", []):
        highlights = r.get("highlights") or []
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (highlights[0] if highlights else r.get("text", "") or ""),
                "score": r.get("score"),
            }
        )
    return results
