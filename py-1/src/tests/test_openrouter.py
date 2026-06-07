"""OpenRouter adapter translation (normalized <-> OpenAI shape), no network."""

import json
from types import SimpleNamespace

from ..providers import openrouter


def _fake_response(content, tool_calls, cost):
    tcs = [
        SimpleNamespace(
            id=tc["id"], type="function",
            function=SimpleNamespace(name=tc["name"], arguments=json.dumps(tc["params"])),
        )
        for tc in tool_calls
    ]
    msg = SimpleNamespace(content=content, tool_calls=tcs or None)
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=3, cost=cost)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def test_call_translates_tool_calls_and_cost(monkeypatch):
    llm = openrouter.OpenRouterProvider("anthropic/claude-sonnet-4", api_key=None)

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _fake_response(
            content=None,
            tool_calls=[{"id": "call_1", "name": "fs_write", "params": {"path": "src/x.py"}}],
            cost=0.0042,
        )

    monkeypatch.setattr(llm._client.chat.completions, "create", fake_create)

    memory = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "p", "name": "t", "params": {"a": 1}}]},
        {"role": "tool", "tool_call_id": "p", "name": "t", "content": "obs"},
    ]
    out = llm.call(memory, tools=[{"type": "function", "function": {"name": "fs_write"}}])

    # normalized response shape
    assert out["content"] is None
    assert out["tool_calls"] == [{"id": "call_1", "name": "fs_write", "params": {"path": "src/x.py"}}]
    assert out["tokens"] == {"in": 12, "out": 3}
    assert abs(out["cost"] - 0.0042) < 1e-9

    # outbound translation: prior assistant tool_call became OpenAI arguments JSON;
    # tool reply carries tool_call_id; usage accounting requested.
    msgs = captured["messages"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == json.dumps({"a": 1})
    assert msgs[3]["tool_call_id"] == "p"
    assert captured["extra_body"] == {"usage": {"include": True}}


def test_call_finishes_without_tool_calls(monkeypatch):
    llm = openrouter.OpenRouterProvider("gpt-4o", api_key=None)
    monkeypatch.setattr(llm._client.chat.completions, "create",
                        lambda **k: _fake_response("final answer", [], 0.001))
    out = llm.call([{"role": "user", "content": "hi"}])
    assert out["content"] == "final answer" and out["tool_calls"] == []
