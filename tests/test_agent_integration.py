"""Integration-style tests for run_agent()."""

from __future__ import annotations

import pytest

from src.agents.agent import run_agent


def _set_task_memory(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.agents.task_memory.TASK_MEMORY_PATH", tmp_path / "task_memory.json")


class DummyMemory:
    def __init__(self):
        self.messages = []

    def get(self):
        return self.messages

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})


class SequenceClient:
    def __init__(self, responses):
        self.responses = list(responses)
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
        content = self.responses.pop(0)
        return type(
            "Response",
            (),
            {"choices": [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]},
        )()


def test_run_agent_executes_grounded_plan(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    client = SequenceClient(
        [
            """
            [
              {"type": "action", "action": "read_file", "target": "README.md", "description": "Inspect the README"},
              {"type": "file_write", "path": "notes.txt", "content": "done\\n", "description": "Write notes"},
              {"type": "action", "action": "list_dir", "target": ".", "description": "List files"}
            ]
            """
        ]
    )
    summary = run_agent("inspect repo and write notes", client, "fake-model", DummyMemory(), "system", yolo=True)
    captured = capsys.readouterr().out
    assert "Plan  (3 steps)" in captured
    assert "Summary" in captured
    assert "Write notes" in captured
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "done\n"
    assert summary.startswith("Agent completed 3/3 steps")


def test_run_agent_rolls_back_on_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    path = tmp_path / "app.py"
    path.write_text("old\n", encoding="utf-8")
    (tmp_path / "test_fail.py").write_text("def test_fail():\n    assert False\n", encoding="utf-8")
    client = SequenceClient(
        [
            """
            [
              {"type": "file_write", "path": "app.py", "content": "new\\n", "description": "Overwrite app"},
              {"type": "action", "action": "run_tests", "target": "test_fail.py", "description": "Run failing tests"}
            ]
            """
        ]
    )
    answers = iter([True, True])
    monkeypatch.setattr("src.agents.agent.confirm", lambda prompt: next(answers))

    summary = run_agent("break and rollback", client, "fake-model", DummyMemory(), "system", yolo=False)
    captured = capsys.readouterr().out
    assert "rollback completed" in captured
    assert path.read_text(encoding="utf-8") == "old\n"
    assert "Rolled back 1 change(s)." in summary


def test_run_agent_reports_preflight_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    client = SequenceClient(
        [
            """
            [
              {"type": "action", "action": "read_file", "target": "missing.txt", "description": "Read a missing file"}
            ]
            """
        ]
    )
    summary = run_agent("search repo", client, "fake-model", DummyMemory(), "system", yolo=True)
    assert summary.startswith("Plan rejected during preflight:")


def test_run_agent_surfaces_make_plan_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    client = SequenceClient(["not json at all"])
    summary = run_agent("do something", client, "fake-model", DummyMemory(), "system", yolo=True)
    assert summary.startswith("Could not generate plan:")


def test_run_agent_auto_appends_verification_for_mutations(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    client = SequenceClient(
        [
            """
            [
              {"type": "file_write", "path": "notes.txt", "content": "done\\n", "description": "Write notes"}
            ]
            """
        ]
    )
    summary = run_agent("write notes", client, "fake-model", DummyMemory(), "system", yolo=True)
    captured = capsys.readouterr().out
    assert "Plan  (2 steps)" in captured
    assert "Verify the workspace after changes" in captured
    assert summary.startswith("Agent completed")


def test_run_agent_executes_context_anchored_patch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    path = tmp_path / "app.py"
    path.write_text("before\nold\nafter\n", encoding="utf-8")
    client = SequenceClient(
        [
            """
            [
              {
                "type": "action",
                "action": "patch_context",
                "path": "app.py",
                "before_context": "before\\n",
                "after_context": "after\\n",
                "old_block": "old\\n",
                "replacement": "new\\n",
                "description": "Patch the anchored block"
              }
            ]
            """
        ]
    )
    summary = run_agent("update the anchored block", client, "fake-model", DummyMemory(), "system", yolo=True)
    assert summary.startswith("Agent completed")
    assert path.read_text(encoding="utf-8") == "before\nnew\nafter\n"


def test_run_agent_uses_recovery_plan(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 1) == 3\n",
        encoding="utf-8",
    )
    client = SequenceClient(
        [
            """
            [
              {"type": "action", "action": "run_tests", "target": "test_calc.py", "description": "Run targeted tests"}
            ]
            """,
            """
            [
              {
                "type": "action",
                "action": "patch_file",
                "path": "calc.py",
                "old_text": "return a - b",
                "new_text": "return a + b",
                "description": "Fix the calculation"
              }
            ]
            """,
        ]
    )
    summary = run_agent("fix failing tests in review", client, "fake-model", DummyMemory(), "system", yolo=True)
    assert "Recovery used." in summary
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


def test_run_agent_review_only_skips_mutations(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    client = SequenceClient(
        [
            """
            [
              {"type": "file_write", "path": "notes.txt", "content": "done\\n", "description": "Write notes"}
            ]
            """
        ]
    )
    summary = run_agent("review only: write notes", client, "fake-model", DummyMemory(), "system", yolo=True)
    assert summary.startswith("Review-only plan generated")
    assert not (tmp_path / "notes.txt").exists()


def test_run_agent_scaffolds_nested_filesystem_from_plain_language(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_task_memory(monkeypatch, tmp_path)
    client = SequenceClient([])
    summary = run_agent(
        "create a folder named src add a file named main.py inside that folder create a folder named utils inside that folder",
        client,
        "fake-model",
        DummyMemory(),
        "system",
        yolo=True,
    )
    assert client.calls == []
    assert summary.startswith("Agent completed 3/3 steps")
    assert (tmp_path / "src").is_dir()
    assert (tmp_path / "src" / "main.py").read_text(encoding="utf-8") == ""
    assert (tmp_path / "src" / "utils").is_dir()
