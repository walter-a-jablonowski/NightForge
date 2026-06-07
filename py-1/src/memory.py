"""Session memory + the runtime safety clip.

Session memory is the list of typed turns (system / user / assistant / tool)
matching the LLM SDK chat format. Rich compaction is the agent's job; this module
provides only the **safety clip** so a step can always run: when the next request
would exceed a safe fraction of the model's context window, it elides the oldest
``tool`` observations (keeping the system message, the user goal, and the most
recent turns) and leaves a marker. Eliding *content* rather than removing the
message keeps each ``tool`` reply paired with its ``assistant`` tool_call, so the
provider API never sees an orphaned call.
"""

from __future__ import annotations

SAFE_FRACTION = 0.75
ELIDED_MARKER = "[older context elided — see agent.log]"
KEEP_RECENT = 6  # most-recent turns never elided by the safety clip


def new_session(system_prompt: str, user_goal: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_goal},
    ]


def safety_clip(memory: list[dict], llm) -> list[dict]:
    """Elide oldest tool observations until under SAFE_FRACTION of the window.

    Best-effort and idempotent: returns the same list object with some ``tool``
    contents replaced by a marker. Never touches system/user/assistant turns or
    the most recent ``KEEP_RECENT`` turns.
    """
    window = getattr(llm, "context_window", None)
    if not window:
        return memory
    budget = int(window * SAFE_FRACTION)

    # Indices eligible for elision: tool messages, not in the recent tail.
    cutoff = len(memory) - KEEP_RECENT
    for i, turn in enumerate(memory):
        if llm.count_tokens(memory) <= budget:
            break
        if i >= cutoff:
            break
        if turn.get("role") == "tool" and turn.get("content") != ELIDED_MARKER:
            turn["content"] = ELIDED_MARKER
    return memory
