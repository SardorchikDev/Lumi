"""Tests for src.memory.conversation_store — session save/load."""

import json
import pathlib
from unittest.mock import patch

from src.memory.conversation_store import (
    _slug,
    delete_session,
    list_sessions,
    load_by_name,
    load_latest,
    load_repo_autosave,
    load_resume,
    save,
    save_repo_autosave,
)


class TestSlug:
    def test_basic_slug(self):
        assert _slug("My Feature Branch") == "my-feature-branch"

    def test_special_characters(self):
        result = _slug("test@#$%^&*!")
        assert "@" not in result
        assert "#" not in result

    def test_truncation(self):
        long_name = "a" * 100
        result = _slug(long_name)
        assert len(result) <= 40

    def test_empty_string(self):
        result = _slug("")
        assert result == ""

    def test_whitespace_stripped(self):
        result = _slug("  padded  ")
        assert result == "padded"


class TestConversationStore:
    def setup_method(self):
        self._tmp_dir = pathlib.Path("/tmp/lumi_test_sessions")
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._patcher = patch("src.memory.conversation_store.SESSIONS_DIR", self._tmp_dir)
        self._patcher.start()
        # Clean up any existing test files
        for f in self._tmp_dir.glob("*.json"):
            f.unlink()

    def teardown_method(self):
        self._patcher.stop()
        for f in sorted(self._tmp_dir.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                f.rmdir()
        if self._tmp_dir.exists():
            self._tmp_dir.rmdir()

    def test_save_returns_path(self):
        history = [{"role": "user", "content": "hello"}]
        path = save(history)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_with_name(self):
        history = [{"role": "user", "content": "test"}]
        path = save(history, name="my-session")
        assert "my-session" in path.stem

    def test_save_and_load_latest(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        save(history)
        loaded = load_latest()
        assert len(loaded) == 2
        assert loaded[0]["content"] == "hello"

    def test_load_latest_empty(self):
        result = load_latest()
        assert result == []

    def test_load_by_name(self):
        history = [{"role": "user", "content": "named session"}]
        save(history, name="unique-test")
        loaded = load_by_name("unique-test")
        assert len(loaded) == 1
        assert loaded[0]["content"] == "named session"

    def test_load_by_name_not_found(self):
        result = load_by_name("nonexistent")
        assert result == []

    def test_list_sessions(self):
        save([{"role": "user", "content": "one"}], name="sess1")
        save([{"role": "user", "content": "two"}], name="sess2")
        sessions = list_sessions()
        assert len(sessions) == 2
        assert all("name" in s for s in sessions)
        assert all("date" in s for s in sessions)
        assert all("msgs" in s for s in sessions)

    def test_list_sessions_empty(self):
        sessions = list_sessions()
        assert sessions == []

    def test_delete_session(self):
        save([{"role": "user", "content": "delete me"}], name="deleteme")
        result = delete_session("deleteme")
        assert result is True
        assert load_by_name("deleteme") == []

    def test_delete_session_not_found(self):
        result = delete_session("nonexistent")
        assert result is False

    def test_save_content_structure(self):
        """Verify the JSON structure of saved files."""
        history = [{"role": "user", "content": "test"}]
        path = save(history, name="struct-test")
        data = json.loads(path.read_text())
        assert "name" in data
        assert "date" in data
        assert "messages" in data
        assert data["messages"] == history

    def test_repo_autosave_round_trip(self, tmp_path):
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        history = [{"role": "user", "content": "repo chat"}]

        path = save_repo_autosave(history, base_dir=workspace)

        assert path.exists()
        assert load_repo_autosave(workspace) == history

    def test_repo_autosave_uses_repo_root_for_nested_paths(self, tmp_path):
        workspace = tmp_path / "repo"
        nested = workspace / "src" / "pkg"
        nested.mkdir(parents=True)
        (workspace / ".git").mkdir()
        history = [{"role": "assistant", "content": "same repo"}]

        save_repo_autosave(history, base_dir=nested)

        assert load_repo_autosave(workspace) == history
        assert load_repo_autosave(nested) == history

    def test_load_resume_prefers_repo_autosave(self, tmp_path):
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        repo_history = [{"role": "user", "content": "repo autosave"}]
        global_history = [{"role": "user", "content": "global latest"}]

        save(global_history, name="other-session")
        save_repo_autosave(repo_history, base_dir=workspace)

        assert load_resume(base_dir=workspace) == repo_history

    def test_load_resume_falls_back_to_latest_snapshot(self, tmp_path):
        workspace = tmp_path / "repo"
        workspace.mkdir()
        latest_history = [{"role": "user", "content": "latest snapshot"}]

        save(latest_history, name="fallback-session")

        assert load_resume(base_dir=workspace) == latest_history
