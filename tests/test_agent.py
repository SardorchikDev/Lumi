"""Unit tests for src.agents.agent."""

from pathlib import Path

import pytest

from src.agents.agent import (
    ChangeJournal,
    build_file_write_preview,
    collect_planning_context,
    compute_step_file_change,
    execute_action_step,
    inspect_repo,
    is_risky,
    make_plan,
    normalize_plan,
    run_step,
    validate_action_step,
    validate_file_write_path,
)
from src.agents.task_memory import record_run


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
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        context = collect_planning_context("inspect README.md", tmp_path)
        assert "Workspace root:" in context
        assert "Top-level entries:" in context
        assert "README.md" in context
        assert "## README.md" in context
        assert "Verification commands detected:" in context

    def test_inspect_repo_detects_entrypoints_and_verification(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n[tool.mypy]\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_smoke.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        profile = inspect_repo(tmp_path, "check main")
        assert "main.py" in profile.entrypoints
        assert "tests" in profile.verification_commands
        assert "lint" in profile.verification_commands

    def test_inspect_repo_detects_frameworks_and_config_files(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies":{"react":"^19.0.0"},"scripts":{"test":"vitest","lint":"eslint ."}}\n',
            encoding="utf-8",
        )
        (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")
        profile = inspect_repo(tmp_path, "update ui")
        assert "react" in profile.frameworks
        assert "package.json" in profile.config_files
        assert "tsconfig.json" in profile.config_files

    def test_make_plan_includes_task_memory_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("src.agents.task_memory.TASK_MEMORY_PATH", tmp_path / "task_memory.json")
        record_run("fix parser", status="completed", summary="updated parser", touched_files=["src/parser.py"])
        client = FakeClient(
            """
            [
              {"type": "action", "action": "inspect_repo", "description": "Inspect the repo"}
            ]
            """
        )
        make_plan("inspect parser", client, "fake-model", base_dir=tmp_path)
        user_message = client.calls[0]["messages"][1]["content"]
        assert "Recent agent task memory:" in user_message
        assert "Top-level entries:" in user_message

    def test_make_plan_builds_filesystem_scaffold_without_model(self, tmp_path):
        client = FakeClient("[]")
        steps = make_plan(
            "create a folder named docs and add a file named README.md inside that folder",
            client,
            "fake-model",
            base_dir=tmp_path,
        )
        assert client.calls == []
        assert [step["description"] for step in steps] == [
            "Create folder docs",
            "Create file docs/README.md",
        ]

    def test_make_plan_tracks_nested_folder_references(self, tmp_path):
        client = FakeClient("[]")
        steps = make_plan(
            "create a folder named app add a folder named components inside that folder add a file named Button.tsx inside that folder",
            client,
            "fake-model",
            base_dir=tmp_path,
        )
        assert client.calls == []
        assert [(step["type"], step.get("target") or step.get("path")) for step in steps] == [
            ("action", "app"),
            ("action", "app/components"),
            ("file_write", "app/components/Button.tsx"),
        ]


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

    def test_rejects_patch_context_without_anchors(self):
        with pytest.raises(ValueError, match="needs before_context or after_context"):
            normalize_plan([{"type": "action", "action": "patch_context", "path": "app.py", "replacement": "x"}])

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

    def test_validate_action_blocks_ambiguous_patch_context(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("start\none\nend\nstart\ntwo\nend\n", encoding="utf-8")
        ok, reason = validate_action_step(
            {
                "action": "patch_context",
                "path": "app.py",
                "before_context": "start\n",
                "after_context": "end\n",
                "replacement": "updated\n",
            },
            tmp_path,
        )
        assert ok is False
        assert "matched multiple regions" in reason

    def test_validate_action_allows_run_verify(self, tmp_path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        ok, reason = validate_action_step(
            {"action": "run_verify", "verify_kind": "tests", "target": "."},
            tmp_path,
        )
        assert ok is True
        assert reason == ""

    def test_validate_action_allows_rename_path(self, tmp_path):
        path = tmp_path / "old.txt"
        path.write_text("hello\n", encoding="utf-8")
        ok, reason = validate_action_step(
            {"action": "rename_path", "target": "old.txt", "destination": "new.txt"},
            tmp_path,
        )
        assert ok is True
        assert reason == ""


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

    def test_compute_patch_context_change(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("header\nstart\nold\nend\nfooter\n", encoding="utf-8")
        ok, reason, changed_path, content = compute_step_file_change(
            {
                "type": "action",
                "action": "patch_context",
                "path": "app.py",
                "before_context": "start\n",
                "after_context": "end\n",
                "old_block": "old\n",
                "replacement": "new\n",
            },
            tmp_path,
        )
        assert ok is True
        assert reason == "patch_context"
        assert changed_path == path
        assert content == "header\nstart\nnew\nend\nfooter\n"

    def test_compute_patch_apply_change(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        ok, reason, changed_path, content = compute_step_file_change(
            {
                "type": "action",
                "action": "patch_apply",
                "path": "app.py",
                "hunks": [
                    {"old_text": "alpha", "new_text": "one"},
                    {"old_text": "gamma", "new_text": "three"},
                ],
            },
            tmp_path,
        )
        assert ok is True
        assert reason == "patch_apply"
        assert changed_path == path
        assert content == "one\nbeta\nthree\n"


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

    def test_execute_action_search_symbols(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
        success, output = execute_action_step({"action": "search_symbols", "target": "src", "symbol": "greet"}, tmp_path)
        assert success is True
        assert "src/main.py:1:" in output

    def test_execute_action_write_yaml(self, tmp_path):
        success, output = execute_action_step(
            {"action": "write_yaml", "path": "config.yaml", "yaml_content": {"debug": True}},
            tmp_path,
        )
        assert success is True
        assert "Written YAML:" in output
        assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "debug: true\n"

    def test_execute_action_rename_path(self, tmp_path):
        path = tmp_path / "old.txt"
        path.write_text("hello\n", encoding="utf-8")
        success, output = execute_action_step(
            {"action": "rename_path", "target": "old.txt", "destination": "renamed.txt"},
            tmp_path,
        )
        assert success is True
        assert "Renamed:" in output
        assert not path.exists()
        assert (tmp_path / "renamed.txt").exists()

    def test_execute_action_run_verify(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tests").mkdir()
        (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        success, output = execute_action_step({"action": "run_verify", "verify_kind": "tests", "target": "."}, tmp_path)
        assert success is True
        assert "passed" in output

    def test_execute_action_inspect_changed_files(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        success, _ = execute_action_step({"action": "inspect_changed_files", "target": "."}, tmp_path)
        assert success is True

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

    def test_run_step_patch_context(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        path = tmp_path / "app.py"
        path.write_text("before\nalpha\nomega\nafter\n", encoding="utf-8")
        success, output = run_step(
            {
                "type": "action",
                "action": "patch_context",
                "path": "app.py",
                "before_context": "before\n",
                "after_context": "after\n",
                "old_block": "alpha\nomega\n",
                "replacement": "beta\ngamma\n",
            },
            client=None,
            model="test",
            memory=DummyMemory(),
            system_prompt="",
            yolo=True,
        )
        assert success is True
        assert "Patched file:" in output
        assert path.read_text(encoding="utf-8") == "before\nbeta\ngamma\nafter\n"

    def test_run_step_patch_apply(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        path = tmp_path / "app.py"
        path.write_text("one\ntwo\nthree\n", encoding="utf-8")
        success, output = run_step(
            {
                "type": "action",
                "action": "patch_apply",
                "path": "app.py",
                "hunks": [
                    {"old_text": "one", "new_text": "1"},
                    {"old_text": "three", "new_text": "3"},
                ],
            },
            client=None,
            model="test",
            memory=DummyMemory(),
            system_prompt="",
            yolo=True,
        )
        assert success is True
        assert "Patched file:" in output
        assert path.read_text(encoding="utf-8") == "1\ntwo\n3\n"

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
