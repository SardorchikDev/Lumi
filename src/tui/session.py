"""Session bootstrap helpers for the Lumi TUI runtime."""

from __future__ import annotations

from typing import Any

from src.tui.state import PaneState


def initialize_ui_state(
    tui: Any,
    *,
    history,
    notes_store,
) -> None:
    tui.history = history
    tui._pending_file_plan = None
    tui._last_filesystem_undo = None

    tui.pane_active = False
    tui.pane_lines_output = []
    tui.pane = PaneState()
    tui.show_starter_panel = True

    tui.little_notes = notes_store
    tui.recent_commands = tui.little_notes.recent_commands
    tui.recent_actions = tui.little_notes.recent_actions

    tui.path_hits = []
    tui.path_sel = 0
    tui.path_visible = False
    tui._path_span = (0, 0)
    tui.picker_query = ""
    tui.picker_stage = "providers"
    tui.picker_provider_key = ""
    tui.picker_preview_lines = []
    tui.picker_empty_message = ""
    tui.picker_provider_names = {}
    tui.picker_health_by_key = {}

    tui.browser_visible = False
    tui.browser_cwd = "."
    tui.browser_items = []
    tui.browser_sel = 0
