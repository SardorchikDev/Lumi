"""Tests for src.memory.short_term — ShortTermMemory."""

from src.memory.short_term import ShortTermMemory


class TestShortTermMemory:
    def test_init_default_max_turns(self):
        mem = ShortTermMemory()
        assert mem.max_turns == 20
        assert len(mem) == 0

    def test_init_custom_max_turns(self):
        mem = ShortTermMemory(max_turns=5)
        assert mem.max_turns == 5

    def test_add_and_get(self):
        mem = ShortTermMemory()
        mem.add("user", "hello")
        mem.add("assistant", "hi there")
        history = mem.get()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

    def test_len(self):
        mem = ShortTermMemory()
        assert len(mem) == 0
        mem.add("user", "msg1")
        assert len(mem) == 1
        mem.add("assistant", "msg2")
        assert len(mem) == 2

    def test_clear(self):
        mem = ShortTermMemory()
        mem.add("user", "hello")
        mem.add("assistant", "world")
        mem.clear()
        assert len(mem) == 0
        assert mem.get() == []

    def test_truncation_at_max_turns(self):
        mem = ShortTermMemory(max_turns=3)
        # max_turns=3 means keep last 6 messages (3 turns * 2 messages each)
        for i in range(10):
            mem.add("user", f"msg-{i}")
        # After adding 10 messages with max_turns=3, should keep last 6
        history = mem.get()
        assert len(history) == 6
        assert history[0]["content"] == "msg-4"
        assert history[-1]["content"] == "msg-9"

    def test_get_returns_list_copy_reference(self):
        """Verify get() returns the internal list (not a copy)."""
        mem = ShortTermMemory()
        mem.add("user", "test")
        history = mem.get()
        assert history is mem._history

    def test_add_preserves_role_and_content(self):
        mem = ShortTermMemory()
        mem.add("system", "you are helpful")
        result = mem.get()
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "you are helpful"

    def test_empty_content(self):
        mem = ShortTermMemory()
        mem.add("user", "")
        assert len(mem) == 1
        assert mem.get()[0]["content"] == ""
