"""Session bootstrap helpers for the Lumi TUI runtime."""

from __future__ import annotations

import random
from typing import Any

from src.chat.cost import SessionCostTracker
from src.tui.state import PaneState, PermissionPromptState, ReviewCard

LUMI_SESSION_TIPS = [
    "Tip: Use /model to switch providers or open the picker with Ctrl+N.",
    "Tip: Use /agent to plan and execute repo-aware coding tasks.",
    "Tip: Use /image <path> [question] to inspect an image with Gemini vision.",
    "Tip: Use /voice [seconds] to record and transcribe straight into the prompt.",
    "Tip: Use /imagine <prompt> to generate images with Gemini.",
    "Tip: Ask Lumi to create, rename, move, copy, or delete files in plain language.",
    "Tip: Use /git review or /git summary to inspect your current changes.",
    "Tip: Press Esc to cancel pickers, pending reviews, and transient UI.",
    "Tip: Press Ctrl+G to hide or show the starter panel.",
    "Tip: Use /doctor to check provider setup, workspace health, and runtime status.",
    "Tip: Use /plugins inspect to review plugin trust and permissions.",
    "Tip: Use /clear to reset the current chat without leaving the TUI.",
]


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
    tui.review_card = ReviewCard()
    tui.show_starter_panel = True
    tui.starter_panel_pinned = False
    tui.shortcuts_visible = False
    tui.workspace_trust_visible = False
    tui.workspace_trust_sel = 0
    tui.permission_prompt = PermissionPromptState()
    tui.permission_prompt_active = False
    tui.permission_prompt_event = None
    tui.command_palette_visible = False
    tui.command_palette_query = ""
    tui.command_palette_hits = []
    tui.command_palette_sel = 0
    tui.todo_pane_visible = False
    tui.agent_todos = []
    tui.tool_logs = []
    tui.shell_logs = []
    tui.tool_row_index = {}
    tui.session_cost = SessionCostTracker()

    tui.little_notes = notes_store
    tui.recent_commands = tui.little_notes.recent_commands
    tui.recent_actions = tui.little_notes.recent_actions
    tui.session_tip = random.choice(LUMI_SESSION_TIPS)

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
