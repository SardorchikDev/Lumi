"""Integration-style tests for the TUI controller and renderer state."""

from __future__ import annotations

from src.tui.app import LumiTUI, _strip_ansi
from src.tui.notes import LittleNotesStore
from src.tui.state import Msg


def _make_tui(tmp_path, monkeypatch) -> LumiTUI:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    tui = LumiTUI()
    notes_path = tmp_path / "little_notes.json"
    tui.little_notes = LittleNotesStore(notes_path)
    tui.recent_commands = tui.little_notes.recent_commands[:3]
    tui.recent_actions = tui.little_notes.recent_actions[:4]
    tui.current_model = "meta-llama/Llama-3.3-70B-Instruct"
    return tui


def test_starter_panel_renders_persisted_little_notes(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.little_notes.record_command("/agent")
    tui.little_notes.record_command("/help")
    tui.recent_commands = tui.little_notes.recent_commands[:3]

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "welcome to lumi" in joined
    assert "little notes" in joined
    assert "/help" in joined
    assert "/agent" in joined
    assert "say something nice" in joined
    tui._task_executor.shutdown(wait=False)


def test_chat_layout_keeps_prompt_and_transcript_separate(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(Msg("user", "hi"))
    tui.store.add(Msg("assistant", "hello back"))

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    chat = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]

    assert any("say something nice" in line for line in starter)
    assert any("welcome to lumi" in line for line in starter)
    assert any("| you" in line for line in chat)
    assert any("hello back" in line for line in chat)
    tui._task_executor.shutdown(wait=False)


def test_ctrl_g_toggles_to_prompt_only_layout(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    tui._handle_key("CTRL_G")
    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(90)]

    assert not any("welcome to lumi" in line for line in lines)
    assert any("say something nice" in line for line in lines)
    tui._task_executor.shutdown(wait=False)


def test_recent_commands_persist_across_tui_instances(tmp_path, monkeypatch):
    first = _make_tui(tmp_path, monkeypatch)
    first.redraw = lambda: None
    first._execute_command("/clear", "")

    second = _make_tui(tmp_path, monkeypatch)
    second.little_notes = LittleNotesStore(tmp_path / "little_notes.json")
    second.recent_commands = second.little_notes.recent_commands[:3]

    lines = [_strip_ansi(line) for line in second.renderer._build_starter_lines(110)]
    assert any("/clear" in line for line in lines)

    first._task_executor.shutdown(wait=False)
    second._task_executor.shutdown(wait=False)


def test_starter_panel_shows_recent_action(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.little_notes.record_action("Created 2 file(s) and 1 folder(s).")
    tui.recent_actions = tui.little_notes.recent_actions[:4]

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "recent action" in joined
    assert "Created 2 file(s) and 1 folder(s)." in joined
    tui._task_executor.shutdown(wait=False)


def test_pending_plan_changes_prompt_hint(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui._pending_file_plan = {"plan": {"operation": "delete"}, "base_dir": str(tmp_path), "inspection": {}}

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "confirm removal" in joined
    assert "y apply" in joined
    tui._task_executor.shutdown(wait=False)


def test_pending_file_plan_confirmation_creates_files_without_chat_fallback(tmp_path, monkeypatch):
    class FailingExecutor:
        def submit(self, *_args, **_kwargs):
            raise AssertionError("pending file plan should not fall through to chat execution")

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = FailingExecutor()
    tui._pending_file_plan = (
        {
            "root": "docs",
            "files": [{"path": "README.md", "content": "# hello\n"}],
        },
        str(tmp_path),
    )
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ENTER")

    assert tui._pending_file_plan is None
    assert (tmp_path / "docs").is_dir()
    assert (tmp_path / "docs" / "README.md").read_text(encoding="utf-8") == "# hello\n"
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Created" in msg.text for msg in messages)


def test_pending_delete_plan_confirmation_removes_paths_without_chat_fallback(tmp_path, monkeypatch):
    class FailingExecutor:
        def submit(self, *_args, **_kwargs):
            raise AssertionError("pending delete plan should not fall through to chat execution")

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = FailingExecutor()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# hello\n", encoding="utf-8")
    tui._pending_file_plan = (
        {
            "operation": "delete",
            "targets": [{"path": "docs", "kind": "dir"}],
        },
        str(tmp_path),
    )
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ENTER")

    assert tui._pending_file_plan is None
    assert not (tmp_path / "docs").exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Removed" in msg.text for msg in messages)


def test_path_suggestions_complete_with_tab(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    tui.buf = "delete src/a"
    tui.cur_pos = len(tui.buf)

    tui._update_slash()

    assert tui.path_visible is True
    assert "src/app.py" in tui.path_hits
    tui._handle_key("TAB")
    assert tui.buf == "delete src/app.py"
    tui._task_executor.shutdown(wait=False)


def test_undo_restores_last_filesystem_action(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._pending_file_plan = {
        "plan": {"operation": "create", "root": ".", "files": [{"path": "notes.txt", "content": "hello\n"}]},
        "base_dir": str(tmp_path),
        "inspection": {},
    }
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)
    tui._handle_key("ENTER")
    assert (tmp_path / "notes.txt").exists()

    tui._execute_command("/undo", "")

    assert not (tmp_path / "notes.txt").exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Undid filesystem action" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)
