"""Offline self-test stubs (runtime test hook — NOT part of the agent).

Activated only when ``AGENT_STUB_LLM=1`` so the full machinery (boot -> loop ->
tools -> deploy gate -> swap -> respawn -> resume) can be exercised end-to-end
without network or API keys. Production always uses the real provider adapter.
"""

from __future__ import annotations

from pathlib import Path

from . import audit


class _BaseStub:
    context_window = 200_000

    def count_tokens(self, messages):
        return sum(len(m.get("content") or "") for m in messages) // 4

    @staticmethod
    def _final(text):
        return {"content": text, "tool_calls": [], "tokens": {"in": 1, "out": 1}, "cost": 0.0}

    @staticmethod
    def _call(cid, name, params, thought=""):
        return {"content": thought,
                "tool_calls": [{"id": cid, "name": name, "params": params}],
                "tokens": {"in": 1, "out": 1}, "cost": 0.0}


class FloorStub(_BaseStub):
    """Passes the fixed capability-floor cases by reading the case prompt."""

    def call(self, messages, tools=None, **extras):
        sys_prompt = messages[0].get("content", "") if messages else ""
        if "17 * 23" in sys_prompt:
            return self._final("391")
        if "example.com" in sys_prompt:
            return self._final("The main heading on the page is: Example Domain")
        if "Python programming language" in sys_prompt:
            return self._final("The official website is https://www.python.org")
        return self._final("done")


class DemoLLM(_BaseStub):
    """Scripted main-loop driver: seed a note + deploy, then (after respawn) finish."""

    def __init__(self, config):
        self._log = config.log_path
        self._step = 0

    def call(self, messages, tools=None, **extras):
        self._step += 1
        deploys = audit.session_totals(self._log)["deploys"]
        if deploys == 0:
            if self._step == 1:
                return self._call("c1", "fs_write",
                                  {"path": "data/db/seed-note.md",
                                   "content": "# Seed note\nOffline self-test ran here.\n"},
                                  thought="Recording a seed note in /data before deploying.")
            return self._call("c2", "deploy", {"message": "offline self-test deploy"},
                              thought="Deploying the seed over /dist.")
        # after the respawn + resume
        if self._step == 1:
            return self._call("c3", "fs_write", {"path": "dist/production-ready", "content": ""},
                              thought="Resumed after deploy; signalling production-ready.")
        return self._final("Offline self-test complete.")


def make_floor_factory():
    return lambda config: FloorStub()
