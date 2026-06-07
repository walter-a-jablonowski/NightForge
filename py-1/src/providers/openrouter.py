"""OpenRouter provider adapter.

Wraps the official ``openai`` SDK pointed at OpenRouter's OpenAI-compatible
endpoint. Translates between the loop's normalized message/response shape and the
OpenAI tool-calling format, and exposes ``context_window`` + ``count_tokens`` for
the memory safety clip.

Normalized response shape (see idea-py.md -> LLM provider):
    { content: str|None, tool_calls: [{id, name, params}], tokens: {in, out}, cost: float }
"""

from __future__ import annotations

import json
import time

from tools import sandbox

BASE_URL = "https://openrouter.ai/api/v1"

# Static fallback context windows (input tokens) by model substring. Used only
# if the OpenRouter /models metadata fetch fails. Decision #3: fetch metadata
# once, fall back to this table.
_FALLBACK_WINDOWS = {
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude-3.5": 200_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "o3": 200_000,
    "gemini-2": 1_000_000,
    "llama-3": 128_000,
}
_DEFAULT_WINDOW = 128_000

_MAX_RETRIES = 4
_BACKOFF_BASE = 1.5


class OpenRouterProvider:
    def __init__(self, model: str, api_key: str | None, base_url: str | None = None, **extras):
        from openai import OpenAI

        self.model = model
        self._extras = extras
        # A placeholder lets the gate construct the adapter without a key (it never
        # calls); a real call without OPENROUTER_API_KEY will 401, as expected.
        self._client = OpenAI(base_url=base_url or BASE_URL, api_key=api_key or "no-key")
        self._window: int | None = None

    # --- normalized call -----------------------------------------------------

    def call(self, messages: list[dict], tools: list[dict] | None = None, **extras) -> dict:
        oa_messages = [_to_openai_message(m) for m in messages]
        kwargs: dict = {
            "model": self.model,
            "messages": oa_messages,
            # OpenRouter returns spend in usage.cost when usage accounting is on.
            "extra_body": {"usage": {"include": True}},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        kwargs.update(self._extras)
        kwargs.update(extras)

        resp = self._with_retry(lambda: self._client.chat.completions.create(**kwargs))
        msg = resp.choices[0].message
        tool_calls = []
        for tc in msg.tool_calls or []:
            try:
                params = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                params = {"_raw_arguments": tc.function.arguments}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "params": params})

        usage = resp.usage
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        cost = _extract_cost(usage)
        return {
            "content": msg.content,
            "tool_calls": tool_calls,
            "tokens": {"in": tin, "out": tout},
            "cost": cost,
        }

    def _with_retry(self, fn):
        from openai import APIConnectionError, APIStatusError, RateLimitError

        last = None
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except (RateLimitError, APIConnectionError) as e:
                last = e
                time.sleep(_BACKOFF_BASE ** attempt)
            except APIStatusError as e:
                if e.status_code in (500, 502, 503, 504, 529):
                    last = e
                    time.sleep(_BACKOFF_BASE ** attempt)
                else:
                    raise
        raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} retries: {last}")

    # --- safety-clip support -------------------------------------------------

    @property
    def context_window(self) -> int:
        if self._window is None:
            self._window = self._fetch_window()
        return self._window

    def _fetch_window(self) -> int:
        try:
            resp = sandbox.http_request("GET", f"{BASE_URL}/models", timeout=10.0)
            if resp.status_code == 200:
                for entry in resp.json().get("data", []):
                    if entry.get("id") == self.model:
                        cl = entry.get("context_length")
                        if cl:
                            return int(cl)
        except Exception:
            pass  # fall back to the static table
        for frag, win in _FALLBACK_WINDOWS.items():
            if frag in self.model:
                return win
        return _DEFAULT_WINDOW

    def count_tokens(self, messages: list[dict]) -> int:
        """Cheap char-based estimate (~4 chars/token) + per-message overhead.

        Deliberately not tiktoken: OpenRouter proxies many tokenizers, so an exact
        count is impossible without a network call. An estimate is all the safety
        clip needs (see idea-py.md -> LLM provider).
        """
        chars = 0
        for m in messages:
            content = m.get("content") or ""
            chars += len(content)
            for tc in m.get("tool_calls", []) or []:
                chars += len(tc.get("name", "")) + len(json.dumps(tc.get("params", {})))
        return chars // 4 + 4 * len(messages)


def _to_openai_message(m: dict) -> dict:
    role = m["role"]
    if role == "assistant" and m.get("tool_calls"):
        return {
            "role": "assistant",
            "content": m.get("content") or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc.get("params", {}))},
                }
                for tc in m["tool_calls"]
            ],
        }
    if role == "tool":
        return {"role": "tool", "tool_call_id": m["tool_call_id"], "content": m.get("content", "")}
    return {"role": role, "content": m.get("content") or ""}


def _extract_cost(usage) -> float:
    if usage is None:
        return 0.0
    cost = getattr(usage, "cost", None)
    if cost is None:
        extra = getattr(usage, "model_extra", None) or {}
        cost = extra.get("cost")
    try:
        return float(cost) if cost is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def build(model: str, api_key: str | None, **extras) -> OpenRouterProvider:
    """Factory used by the registry."""
    return OpenRouterProvider(model=model, api_key=api_key, **extras)
