"""Tests for src.memory.longterm — fact memory and persona overrides."""

import json
import pathlib
from unittest.mock import patch

from src.memory.longterm import (
    _load,
    _save,
    add_fact,
    build_memory_block,
    clear_facts,
    clear_persona_override,
    get_facts,
    get_persona_override,
    remove_fact,
    set_persona_override,
)


class TestFactMemory:
    def setup_method(self):
        """Use a temp file for each test."""
        self._tmp = pathlib.Path("/tmp/lumi_test_longterm.json")
        self._patcher = patch("src.memory.longterm.MEMORY_FILE", self._tmp)
        self._patcher.start()
        # Start clean
        if self._tmp.exists():
            self._tmp.unlink()

    def teardown_method(self):
        self._patcher.stop()
        if self._tmp.exists():
            self._tmp.unlink()

    def test_load_empty(self):
        data = _load()
        assert data == {"facts": [], "persona_override": {}}

    def test_add_and_get_facts(self):
        add_fact("User prefers Python")
        add_fact("User's name is Sardor")
        facts = get_facts()
        assert len(facts) == 2
        assert "User prefers Python" in facts
        assert "User's name is Sardor" in facts

    def test_add_fact_returns_count(self):
        count = add_fact("fact one")
        assert count == 1
        count = add_fact("fact two")
        assert count == 2

    def test_add_fact_strips_whitespace(self):
        add_fact("  padded fact  ")
        facts = get_facts()
        assert facts[0] == "padded fact"

    def test_remove_fact_valid_index(self):
        add_fact("keep me")
        add_fact("remove me")
        result = remove_fact(1)
        assert result is True
        facts = get_facts()
        assert len(facts) == 1
        assert facts[0] == "keep me"

    def test_remove_fact_invalid_index(self):
        add_fact("only fact")
        result = remove_fact(5)
        assert result is False
        assert len(get_facts()) == 1

    def test_remove_fact_negative_index(self):
        add_fact("fact")
        result = remove_fact(-1)
        assert result is False

    def test_clear_facts(self):
        add_fact("fact1")
        add_fact("fact2")
        clear_facts()
        assert get_facts() == []

    def test_build_memory_block_empty(self):
        block = build_memory_block()
        assert block == ""

    def test_build_memory_block_with_facts(self):
        add_fact("Likes TypeScript")
        add_fact("Uses PostgreSQL")
        block = build_memory_block()
        assert "Likes TypeScript" in block
        assert "Uses PostgreSQL" in block
        assert "1." in block
        assert "2." in block

    def test_persistence(self):
        """Facts survive across load/save cycles."""
        add_fact("persistent fact")
        # Simulate a fresh load
        facts = get_facts()
        assert "persistent fact" in facts


class TestPersonaOverride:
    def setup_method(self):
        self._tmp = pathlib.Path("/tmp/lumi_test_longterm_persona.json")
        self._patcher = patch("src.memory.longterm.MEMORY_FILE", self._tmp)
        self._patcher.start()
        if self._tmp.exists():
            self._tmp.unlink()

    def teardown_method(self):
        self._patcher.stop()
        if self._tmp.exists():
            self._tmp.unlink()

    def test_default_persona_override_empty(self):
        override = get_persona_override()
        assert override == {}

    def test_set_and_get_persona_override(self):
        set_persona_override({"name": "Aria", "tone": "formal"})
        override = get_persona_override()
        assert override["name"] == "Aria"
        assert override["tone"] == "formal"

    def test_clear_persona_override(self):
        set_persona_override({"name": "Custom"})
        clear_persona_override()
        override = get_persona_override()
        assert override == {}

    def test_persona_and_facts_coexist(self):
        add_fact("test fact")
        set_persona_override({"name": "Test"})
        assert len(get_facts()) == 1
        assert get_persona_override()["name"] == "Test"
