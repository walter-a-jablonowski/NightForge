"""Capability-floor cases (decision #4) — fixed, objective, deterministic checks.

A handful of end-to-end tasks with code-based checks (no LLM judge). Each runs the
candidate /src against the goal and verifies the outcome. Targets are chosen for
durability:
  * arithmetic — pure loop+LLM liveness, no tools, never goes stale;
  * example.com — IANA's reserved demo page, stable "Example Domain" heading;
  * python.org — the official Python site, stable hostname in a search hit.

Each case: ``id``, ``prompt`` (the system goal), ``max_steps``, and
``check(answer, calls) -> bool`` where ``calls`` is the flattened list of tool
calls ({tool, params, result, ok}) from the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Case:
    id: str
    prompt: str
    max_steps: int
    check: Callable[[str, list[dict]], bool]


def _has_text(answer: str, *needles: str) -> bool:
    a = (answer or "").lower()
    return all(n.lower() in a for n in needles)


def _result_contains(calls: list[dict], tool: str, needle: str) -> bool:
    for c in calls:
        if c.get("tool") == tool and needle.lower() in str(c.get("result", "")).lower():
            return True
    return False


CASES = [
    Case(
        id="reasoning",
        prompt=("You are a precise calculator. Compute 17 * 23 and reply with just "
                "the final number and nothing else."),
        max_steps=3,
        check=lambda answer, calls: "391" in (answer or ""),
    ),
    Case(
        id="fetch",
        prompt=("You answer questions by fetching web pages. Use the web_fetch tool, "
                "then report the requested information concisely.\n\n"
                "Task: Fetch https://example.com/ and report the main heading shown on "
                "the page."),
        max_steps=5,
        check=lambda answer, calls: _has_text(answer, "example domain")
        or _result_contains(calls, "web_fetch", "Example Domain"),
    ),
    Case(
        id="search",
        prompt=("You answer questions by searching the web. Use the web_search tool, "
                "then report the requested URL.\n\n"
                "Task: Find the official website of the Python programming language and "
                "report its URL."),
        max_steps=5,
        check=lambda answer, calls: _has_text(answer, "python.org")
        or _result_contains(calls, "web_search", "python.org"),
    ),
]

# First deploy has no prior /dist score; the candidate must clear this minimum.
COLD_START_BAR = 2  # of len(CASES): reasoning + at least one tool case
TOLERANCE = 0  # strict >=, softened only by the single re-run of a failing case
