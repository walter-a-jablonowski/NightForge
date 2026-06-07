"""Session memory + safety-clip behaviour."""

from .. import memory as mem


class FakeLLM:
    context_window = 100  # tiny window to force clipping

    def count_tokens(self, messages):
        return sum(len(m.get("content") or "") for m in messages) // 4


def test_new_session_shape():
    m = mem.new_session("SYS", "GOAL")
    assert m[0] == {"role": "system", "content": "SYS"}
    assert m[1] == {"role": "user", "content": "GOAL"}


def test_safety_clip_elides_old_tool_observations():
    big = "x" * 4000  # ~1000 tokens each, well over the 75-token budget
    m = [{"role": "system", "content": "S"}, {"role": "user", "content": "G"}]
    # 6 assistant/tool exchanges — older ones fall outside the protected tail.
    for i in range(6):
        m.append({"role": "assistant", "content": "",
                  "tool_calls": [{"id": str(i), "name": "t", "params": {}}]})
        m.append({"role": "tool", "tool_call_id": str(i), "name": "t", "content": big})

    mem.safety_clip(m, FakeLLM())

    # The oldest tool observation (index 3) is elided; system/user untouched; the
    # most recent KEEP_RECENT turns are preserved verbatim.
    assert m[3]["content"] == mem.ELIDED_MARKER
    assert m[0]["content"] == "S" and m[1]["content"] == "G"
    assert m[-1]["content"] == big  # most-recent tool obs preserved


def test_safety_clip_noop_without_window():
    class NoWindow:
        context_window = None
    m = mem.new_session("S", "G")
    assert mem.safety_clip(m, NoWindow()) is m
