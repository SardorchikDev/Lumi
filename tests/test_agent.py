"""Unit tests for src.agents.agent."""

from pathlib import Path

import pytest

from src.agents.agent import (
    ChangeJournal,
    build_file_write_preview,
    collect_planning_context,
    compute_step_file_change,
    execute_action_step,
    is_risky,
    make_plan,
    normalize_plan,
    run_step,
    validate_action_step,
    validate_file_write_path,
)


class DummyMemory:
    def __init__(self):
        self.messages = []

    def get(self):
        return self.messages

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})


class FakeResponse:
    def __init__(self, content):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []
        self.chat = type(
            "Chat",
            (),
            {
                "completions": type(
                    "Completions",
                    (),
                    {"create": self._create},
                )()
            },
        )()

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.content)


class TestPlanningContext:
    def test_collects_workspace_facts(self, tmp_path):
        (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        context = collect_planning_context("inspect README.md", tmp_path)
        assert "Workspace root:" in context
        assert "Top-level entries:" in context
        assert "README.md" in context
        assert "## README.md" in context


class TestRisk:
    def test_explicit_risky_flag(self):
        assert is_risky({"risky": True, "description": "anything"}) is True

    def test_keyword_based_risky_detection(self):
        assert is_risky({"description": "deploy the service"}) is True
        assert is_risky({"action": "run_tests", "description": "verify changes"}) is False


class TestPlanNormalization:
    def test_rewrites_legacy_shell_step(self):
        steps = normalize_plan(
            [{"type": "shell", "description": "Run tests", "command": "pytest"}]
        )
        assert steps[0]["type"] == "action"
        assert steps[0]["action"] == "run_tests"

    def test_rewrites_vague_ai_task(self):
        steps = normalize_plan(
            [{"type": "ai_task", "description": "Read file pyproject.toml"}]
        )
        assert steps[0]["type"] == "action"
        assert steps[0]["action"] == "read_file"

    def test_rejects_all_ai_task_plan(self):
        with pytest.raises(ValueError, match="all steps were ai_task"):
            normalize_plan(
                [
                    {"type": "ai_task", "prompt": "think"},
                    {"type": "ai_task", "prompt": "think more"},
                ]
            )

    def test_rejects_patch_lines_without_bounds(self):
        with pytest.raises(ValueError, match="missing line bounds"):
            normalize_plan([{"type": "action", "action": "patch_lines", "path": "app.py", "replacement": "x"}])

    def test_make_plan_includes_context_and_normalizes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
        client = FakeClient(
            """
            [
              {"id": 7, "type": "shell", "description": "Run tests for this project", "command": "pytest"}
            ]
            """
        )
        steps = make_plan("test the project", client, "fake-model")
        assert steps[0]["action"] == "run_tests"
        user_message = client.calls[0]["messages"][1]["content"]
        assert "Workspace context:" in user_message
        assert "README.md" in user_message


class TestValidation:
    def test_validate_file_write_path_allows_workspace_relative_path(self, tmp_path):
        ok, reason = validate_file_write_path("notes/todo.md", tmp_path)
        assert ok is True
        assert reason == ""

    def test_validate_file_write_path_blocks_escape(self, tmp_path):
        ok, reason = validate_file_write_path("../outside.txt", tmp_path)
        assert ok is False
        assert "must stay inside the current workspace" in reason

    def test_validate_action_allows_write_json(self, tmp_path):
        ok, reason = validate_action_step(
            {"action": "write_json", "path": "config.json", "json_content": {"debug": True}},
            tmp_path,
        )
        assert ok is True
        assert reason == ""

    def test_validate_action_blocks_search_without_query(self, tmp_path):
        ok, reason = validate_action_step({"action": "search_code", "target": "."}, tmp_path)
        assert ok is False
        assert "requires a query" in reason

    def test_validate_action_blocks_ambiguous_patch_file(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("foo\nfoo\n", encoding="utf-8")
        ok, reason = validate_action_step(
            {"action": "patch_file", "path": "app.py", "old_text": "foo", "new_text": "bar"},
            tmp_path,
        )
        assert ok is False
        assert "ambiguous" in reason

    def test_validate_action_blocks_patch_lines_conflict(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("a\nb\nc\n", encoding="utf-8")
        ok, reason = validate_action_step(
            {
                "action": "patch_lines",
                "path": "app.py",
                "start_line": 2,
                "end_line": 2,
                "old_block": "x\n",
                "replacement": "y\n",
            },
            tmp_path,
        )
        assert ok is False
        assert "old_block does not match" in reason


class TestFileChangeComputation:
    def test_compute_file_write_change(self, tmp_path):
        ok, reason, path, content = compute_step_file_change(
            {"type": "file_write", "path": "docs/readme.txt", "content": "hello"},
            tmp_path,
        )
        assert ok is True
        assert reason == "file_write"
        assert path == tmp_path / "docs" / "readme.txt"
        assert content == "hello"

    def test_compute_patch_lines_change(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("a\nb\nc\n", encoding="utf-8")
        ok, reason, changed_path, content = compute_step_file_change(
            {
                "type": "action",
                "action": "patch_lines",
                "path": "app.py",
                "start_line": 2,
                "end_line": 2,
                "old_block": "b\n",
                "replacement": "beta\n",
            },
            tmp_path,
        )
        assert ok is True
        assert reason == "patch_lines"
        assert changed_path == path
        assert content == "a\nbeta\nc\n"


class TestPreview:
    def test_returns_empty_for_new_file(self, tmp_path):
        assert build_file_write_preview(tmp_path / "new.txt", "hello") == ""

    def test_returns_no_changes_marker(self, tmp_path):
        path = tmp_path / "same.txt"
        path.write_text("hello\n", encoding="utf-8")
        assert build_file_write_preview(path, "hello\n") == "[No changes]"

    def test_returns_unified_diff_for_changed_file(self, tmp_path):
        path = tmp_path / "config.txt"
        path.write_text("old\nvalue\n", encoding="utf-8")
        preview = build_file_write_preview(path, "new\nvalue\n")
        assert "--- config.txt (current)" in preview
        assert "+++ config.txt (agent)" in preview
        assert "-old" in preview
        assert "+new" in preview


class TestExecution:
    def test_execute_action_run_tests(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        success, output = execute_action_step({"action": "run_tests", "target": "test_sample.py"}, tmp_path)
        assert success is True
        assert "1 passed" in output

    def test_execute_action_search_code(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        success, output = execute_action_step({"action": "search_code", "target": "src", "query": "greet"}, tmp_path)
        assert success is True
        assert "src/main.py:1:" in output

    def test_run_step_patch_file(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        path = tmp_path / "app.py"
        path.write_text("print('hello')\n", encoding="utf-8")
        success, output = run_step(
            {
                "type": "action",
                "action": "patch_file",
                "path": "app.py",
                "old_text": "hello",
                "new_text": "world",
            },
            client=None,
            model="test",
            memory=DummyMemory(),
            system_prompt="",
            yolo=True,
        )
        assert success is True
        assert "Patched file:" in output
        assert path.read_text(encoding="utf-8") == "print('world')\n"

    def test_run_step_patch_lines_prints_preview_before_confirm(self, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        path = tmp_path / "app.py"
        path.write_text("a\nb\nc\n", encoding="utf-8")
        monkeypatch.setattr("src.agents.agent.confirm", lambda prompt: False)

        success, output = run_step(
            {
                "type": "action",
                "action": "patch_lines",
                "path": "app.py",
                "start_line": 2,
                "end_line": 2,
                "old_block": "b\n",
                "replacement": "beta\n",
                "risky": True,
            },
            client=None,
            model="test",
            memory=DummyMemory(),
            system_prompt="",
            yolo=False,
        )
        captured = capsys.readouterr().out
        assert success is False
        assert output == "Skipped by user"
        assert "diff preview for" in captured
        assert "-b" in captured
        assert "+beta" in captured
        assert path.read_text(encoding="utf-8") == "a\nb\nc\n"

    def test_run_step_legacy_shell_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        success, output = run_step(
            {"type": "shell", "command": "echo hello"},
            client=None,
            model="test",
            memory=DummyMemory(),
            system_prompt="",
            yolo=True,
        )
        assert success is False
        assert "Legacy shell steps are disabled" in output


class TestJournal:
    def test_rolls_back_file_changes(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("old\n", encoding="utf-8")
        journal = ChangeJournal()
        journal.record_file(path)
        path.write_text("new\n", encoding="utf-8")
        rolled_back = journal.rollback()
        assert str(path) in rolled_back
        assert path.read_text(encoding="utf-8") == "old\n"

    def test_rolls_back_created_file(self, tmp_path):
        path = tmp_path / "new.txt"
        journal = ChangeJournal()
        journal.record_file(path)
        path.write_text("hello\n", encoding="utf-8")
        journal.rollback()
        assert not path.exists()
