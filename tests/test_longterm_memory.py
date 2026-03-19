"""Tests for src.memory.longterm — fact memory, persona overrides, and episodes."""

import json
import pathlib
import sqlite3
from unittest.mock import patch

import numpy as np
import pytest

from src.memory.longterm import (
    _load,
    add_fact,
    auto_summarize_and_save,
    build_memory_block,
    clear_facts,
    clear_persona_override,
    get_facts,
    get_persona_override,
    get_related_episodes,
    memory_stats,
    remove_fact,
    save_episode,
    search_facts,
    set_persona_override,
    update_fact,
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

    def test_add_fact_dedupes_case_insensitively(self):
        add_fact("User prefers Python")
        count = add_fact("user prefers python")
        assert count == 1
        assert get_facts() == ["User prefers Python"]

    def test_update_fact_rewrites_existing_value(self):
        add_fact("old fact")
        assert update_fact(0, "new fact") is True
        assert get_facts() == ["new fact"]

    def test_search_facts_ranks_matching_entries(self):
        add_fact("User prefers Python")
        add_fact("User likes TypeScript")
        add_fact("Favorite editor is Neovim")
        matches = search_facts("python user")
        assert matches[0] == "User prefers Python"
        assert "User likes TypeScript" in matches

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

    def test_memory_stats_reports_fact_and_persona_counts(self):
        add_fact("test fact")
        set_persona_override({"name": "Test", "tone": "formal"})
        stats = memory_stats()
        assert stats["facts"] == 1
        assert stats["persona_override_keys"] == 2
        assert stats["episodes"] == 0


class TestEpisodes:
    def setup_method(self):
        self._db = pathlib.Path("/tmp/lumi_test_episodes.sqlite3")
        self._legacy = pathlib.Path("/tmp/lumi_test_episodes.pkl")
        self._db.unlink(missing_ok=True)
        self._legacy.unlink(missing_ok=True)
        self._db_patcher = patch("src.memory.longterm.EPISODIC_DB_PATH", self._db)
        self._legacy_patcher = patch("src.memory.longterm.LEGACY_EPISODIC_DB_PATH", self._legacy)
        self._db_patcher.start()
        self._legacy_patcher.start()

    def teardown_method(self):
        self._db_patcher.stop()
        self._legacy_patcher.stop()
        self._db.unlink(missing_ok=True)
        self._legacy.unlink(missing_ok=True)

    def test_save_episode_uses_sqlite_store(self):
        save_episode("Finished refactor", np.array([0.1, 0.9], dtype=np.float32))
        assert self._db.exists()
        with sqlite3.connect(self._db) as conn:
            rows = conn.execute("SELECT summary, vector_json FROM episodes").fetchall()
        assert rows[0][0] == "Finished refactor"
        assert json.loads(rows[0][1]) == pytest.approx([0.1, 0.9])

    def test_get_related_episodes_scores_sqlite_entries(self, monkeypatch):
        save_episode("Refactored parser", np.array([1.0, 0.0], dtype=np.float32))
        save_episode("Improved tests", np.array([0.0, 1.0], dtype=np.float32))
        monkeypatch.setattr("src.tools.rag.get_embedding", lambda query, client: [1.0, 0.0])
        monkeypatch.setattr("src.tools.rag.cosine_similarity", lambda a, b: float(np.dot(a, b)))
        assert get_related_episodes("parser", object()) == ["Refactored parser", "Improved tests"]

    def test_auto_summarize_and_save_logs_instead_of_printing(self, monkeypatch, capsys):
        history = [{"role": "user", "content": f"line {idx}"} for idx in range(6)]
        fake_client = type(
            "Client",
            (),
            {
                "chat": type(
                    "Chat",
                    (),
                    {
                        "completions": type(
                            "Completions",
                            (),
                            {
                                "create": staticmethod(
                                    lambda **kwargs: type(
                                        "Resp",
                                        (),
                                        {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "summary"})()})()]},
                                    )()
                                )
                            },
                        )()
                    },
                )()
            },
        )()
        monkeypatch.setattr("src.tools.rag.get_embedding_client", lambda: object())
        monkeypatch.setattr("src.tools.rag.get_embedding", lambda text, client: [0.2, 0.8])
        auto_summarize_and_save(history, fake_client, "model")
        assert capsys.readouterr().out == ""
        assert self._db.exists()
