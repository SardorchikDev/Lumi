"""Lumi TUI runtime and renderer."""
from __future__ import annotations

import concurrent.futures
import io
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

# ── Logging setup (file only — never pollutes the TUI) ───────────────────────
_LOG_DIR = Path.home() / ".lumi"
_LOG_DIR.mkdir(exist_ok=True)
_WORKSPACE_TRUST_FILE = _LOG_DIR / "trusted_workspaces.json"
logging.basicConfig(
    filename=str(_LOG_DIR / "lumi.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("lumi")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(dotenv_path=ROOT / ".env")

# ── CLI Modules ──────────────────────────────────────────────────────────────
from src.agents.council import LEAD_AGENTS, _get_available_agents, classify_task, council_ask
from src.chat.client_factory import make_client as make_provider_client
from src.chat.hf_client import (
    chat_stream,
    get_available_providers,
    get_client,
    get_models,
    get_provider,
    pick_startup_model,
    set_provider,
)
from src.chat.inference_controls import (
    EFFORT_LEVELS,
    apply_reasoning_effort,
    display_reasoning_effort,
    display_reasoning_indicator,
    normalize_reasoning_effort,
    provider_effort_options,
    tune_inference_request,
)
from src.chat.optimizer import (
    estimate_message_tokens,
    estimate_tokens,
    get_global_context_cache,
    get_global_telemetry,
    optimize_messages,
    route_model,
)
from src.chat.runtime import build_runtime_messages
from src.chat.streaming import StreamCancelledError, stream_once
from src.memory.conversation_store import load_resume, save_repo_autosave
from src.memory.conversation_store import (
    save as session_save,
)
from src.memory.longterm import (
    add_fact,
    build_memory_block,
    clear_facts,
    get_facts,
    get_persona_override,
    remove_fact,
)
from src.memory.short_term import ShortTermMemory
from src.prompts.builder import (
    PromptContext,
    build_dynamic_system_prompt,
    is_coding_task,
    is_file_generation_task,
    load_persona,
)
from src.tools.agentic_runtime import build_agentic_system_hint, run_tool_loop_sync
from src.tools.base import ToolContext, ToolEvent
from src.tools.search import search, search_display
from src.tui.command_groups import register_command_groups
from src.tui.controller_actions import (
    apply_path_suggestion as controller_apply_path_suggestion,
)
from src.tui.controller_actions import (
    browser_select as controller_browser_select,
)
from src.tui.controller_actions import (
    cancel_pending_file_plan as controller_cancel_pending_file_plan,
)
from src.tui.controller_actions import (
    cancel_transient_state as controller_cancel_transient_state,
)
from src.tui.controller_actions import (
    confirm_picker as controller_confirm_picker,
)
from src.tui.controller_actions import (
    consume_pending_file_plan as controller_consume_pending_file_plan,
)
from src.tui.controller_actions import (
    do_retry as controller_do_retry,
)
from src.tui.controller_actions import (
    execute_command as controller_execute_command,
)
from src.tui.controller_actions import (
    filesystem_prompt_hint as controller_filesystem_prompt_hint,
)
from src.tui.controller_actions import (
    handle_key as controller_handle_key,
)
from src.tui.controller_actions import (
    hist_nav as controller_hist_nav,
)
from src.tui.controller_actions import (
    open_picker as controller_open_picker,
)
from src.tui.controller_actions import (
    queue_filesystem_plan as controller_queue_filesystem_plan,
)
from src.tui.controller_actions import (
    record_filesystem_action as controller_record_filesystem_action,
)
from src.tui.controller_actions import (
    refresh_browser as controller_refresh_browser,
)
from src.tui.controller_actions import (
    refresh_picker as controller_refresh_picker,
)
from src.tui.controller_actions import (
    run_file_agent as controller_run_file_agent,
)
from src.tui.controller_actions import (
    run_message as controller_run_message,
)
from src.tui.controller_actions import (
    undo_last_filesystem_action as controller_undo_last_filesystem_action,
)
from src.tui.controller_actions import (
    update_slash as controller_update_slash,
)
from src.tui.input import InputHistory, read_key
from src.tui.media import (
    build_image_messages,
    generate_gemini_images,
    image_mime,
    inject_text_at_cursor,
    parse_image_request,
    parse_imagine_request,
    parse_voice_duration,
    record_voice_clip,
    resolve_media_target,
    transcribe_audio_file,
)
from src.tui.mode_registry import MODE_CLI_REGISTRY
from src.tui.mode_sessions import (
    build_mode_context_text,
    build_mode_review_card,
    fallback_mode_summary_data,
    format_mode_tldr,
    list_mode_conversations,
    parse_mode_summary_response,
    sanitize_handoff_transcript,
    save_mode_conversation,
    search_mode_conversations,
)
from src.tui.notes import LittleNotesStore
from src.tui.review_cards import file_review_card
from src.tui.session import initialize_ui_state
from src.tui.state import AgentState, Msg, PaneState, PermissionPromptState, ReviewCard, Store
from src.tui.views import OverlayView, PaneView, StarterView, TranscriptView, ViewStyle
from src.utils.autoremember import auto_extract_facts
from src.utils.claude_parity import (
    render_agents_report,
    render_files_report,
    render_tasks_report,
    render_version_report,
)
from src.utils.filesystem import (
    execute_operation_plan,
    generate_delete_plan,
    generate_file_plan,
    generate_transfer_plan,
    inspect_operation_plan,
    is_copy_request,
    is_create_request,
    is_delete_request,
    is_filesystem_request,
    is_move_request,
    is_rename_request,
    suggest_paths,
    undo_operation,
)
from src.utils.git_tools import summarize_git_state
from src.utils.intelligence import (
    detect_emotion,
    emotion_hint,
    is_complex_coding_task,
    needs_live_lookup,
    needs_plan_first,
    should_search,
)
from src.utils.permissions import (
    PermissionDecision,
    PermissionRequest,
)
from src.utils.permissions import (
    add_permission_rule as add_tool_permission_rule,
)
from src.utils.permissions import (
    evaluate_permission as evaluate_tool_permission,
)
from src.utils.permissions import (
    remove_permission_rule as remove_tool_permission_rule,
)
from src.utils.permissions import (
    render_permission_report as render_tool_permission_report,
)
from src.utils.permissions import (
    set_permission_mode as set_tool_permission_mode,
)
from src.utils.plugins import (
    approve_plugin,
    load_plugins,
    reload_plugins,
    render_permission_report,
    render_plugin_audit_report,
    render_plugin_inventory_report,
    revoke_plugin,
)
from src.utils.plugins import dispatch as plugin_dispatch
from src.utils.project_context import load_project_context
from src.utils.project_memory import memory_path as project_memory_path
from src.utils.project_memory import remember_decision as remember_project_decision
from src.utils.project_memory import render_memory_block
from src.utils.rebirth import load_rebirth_profile, rebirth_status_summary, render_rebirth_report
from src.utils.repo_profile import inspect_workspace
from src.utils.runtime_config import (
    add_context_directory,
    load_runtime_config,
    parse_runtime_config_update,
    remove_context_directory,
    render_runtime_config_report,
    reset_runtime_config,
    update_runtime_config,
)
from src.utils.system_reports import build_doctor_report, build_status_report
from src.utils.web import fetch_url
from src.utils.workbench import (
    WORKBENCH_TITLE,
    WORKBENCH_VERSION,
    coerce_workbench_job,
    create_workbench_job,
    execute_workbench,
    load_workbench_jobs,
    render_workbench_jobs_report,
    render_workbench_result,
    save_workbench_job,
    update_workbench_job,
    workbench_job_to_dict,
)

try:
    from src.utils.tools import clipboard_get, clipboard_set, get_weather, load_project, read_pdf
except Exception:
    clipboard_get = clipboard_set = get_weather = load_project = read_pdf = None

_context_cache = get_global_context_cache()
_session_telemetry = get_global_telemetry()


def _mode_display_path(path: str | Path, *, max_len: int = 52) -> str:
    text = str(Path(path).expanduser())
    home = str(Path.home())
    if text == home:
        text = "~"
    elif text.startswith(home + "/"):
        text = "~/" + text[len(home) + 1 :]
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3) :]


def _workspace_path_key(path: Path) -> str:
    return str(path.resolve())


def _load_workspace_trust_paths() -> set[str]:
    try:
        data = json.loads(_WORKSPACE_TRUST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {
        _workspace_path_key(Path(item))
        for item in data
        if isinstance(item, str) and item.strip()
    }


def _save_workspace_trust_paths(paths: set[str]) -> None:
    payload = sorted(path for path in paths if path)
    _WORKSPACE_TRUST_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _mode_detect_binary_version(entry: dict[str, object], binary_path: str) -> str:
    version_args = entry.get("version_args") or [["--version"], ["version"], ["-V"]]
    for args in version_args:
        try:
            result = subprocess.run(
                [binary_path, *list(args)],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            continue
        output = (result.stdout or result.stderr or "").strip()
        if output:
            return output.splitlines()[0][:120]
    return ""


def _mode_binary_info(entry: dict[str, object]) -> dict[str, str | bool]:
    binary = str(entry["binary"])
    binary_path = shutil.which(binary)
    if not binary_path:
        return {
            "installed": False,
            "binary": binary,
            "binary_path": "",
            "version": "",
            "reason": "",
        }
    if Path(binary_path).name != binary:
        return {
            "installed": False,
            "binary": binary,
            "binary_path": str(Path(binary_path).resolve()),
            "version": "",
            "reason": f"Resolved `{binary_path}` but expected executable name `{binary}`.",
        }
    return {
        "installed": True,
        "binary": binary,
        "binary_path": str(Path(binary_path).resolve()),
        "version": _mode_detect_binary_version(entry, binary_path),
        "reason": "",
    }


def _mode_recent_lines(cli_name: str, *, limit: int = 3) -> list[str]:
    records = list_mode_conversations(cli_name, limit=limit)
    lines: list[str] = []
    for record in records:
        summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
        tldr = str(summary.get("tldr", "")).strip() or "No TL;DR available."
        stamp = Path(str(record.get("path", ""))).stem or str(record.get("date", "")).strip() or "unknown"
        lines.append(f"  - {stamp} · {tldr[:96]}")
    return lines


def _mode_memory_note(record: dict[str, object]) -> str:
    summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
    parts = [f"[Mode session: {record.get('name', record.get('cli', 'external CLI'))}]"]
    if summary.get("tldr"):
        parts.append(f"TL;DR: {summary['tldr']}")
    for label in ("files", "commands", "decisions", "next_steps"):
        values = summary.get(label)
        if isinstance(values, list) and values:
            parts.append(f"{label}: " + "; ".join(str(item) for item in values[:4]))
    if record.get("path"):
        parts.append(f"Saved transcript: {record['path']}")
    return " ".join(parts)


def _index_mode_record(record: dict[str, object]) -> None:
    path = str(record.get("path", "")).strip()
    label = f"{record.get('name', record.get('cli', 'mode'))} {Path(path).name}" if path else str(record.get("name", "mode"))
    key = f"mode:{record.get('cli', 'unknown')}:{Path(path).stem}" if path else f"mode:{record.get('cli', 'unknown')}"
    _context_cache.remember_text(key, label, build_mode_context_text(record), kind="mode")


def _build_mode_conversation_lines(
    records: list[dict[str, object]],
    *,
    cli_name: str | None = None,
    query: str = "",
) -> tuple[str, str, list[str]]:
    title = "mode conversations"
    subtitle_parts: list[str] = []
    if cli_name:
        subtitle_parts.append(cli_name)
    if query:
        subtitle_parts.append(f"search: {query}")
    subtitle = "  ·  ".join(subtitle_parts)
    lines: list[str] = []
    for index, record in enumerate(records[:10], 1):
        summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
        stamp = Path(str(record.get("path", ""))).stem or str(record.get("date", "")).strip() or "unknown"
        tldr = str(summary.get("tldr", "")).strip() or "No TL;DR available."
        lines.append(f"{index}. {record.get('name', record.get('cli', '?'))} · {stamp}")
        meta = [
            _mode_display_path(str(record.get("cwd", "?"))),
            f"{record.get('duration_seconds', '?')}s",
        ]
        if record.get("git_branch"):
            meta.append(str(record["git_branch"]))
        lines.append("   " + " · ".join(meta))
        lines.append("   " + tldr[:104])
        next_steps = summary.get("next_steps")
        if isinstance(next_steps, list) and next_steps:
            lines.append("   next: " + str(next_steps[0])[:98])
        lines.append("")
    if lines and not lines[-1].strip():
        lines.pop()
    return title, subtitle, lines


def build_messages(system_prompt: str, history: list[dict[str, str]], *, model: str = "") -> list[dict[str, str]]:
    return build_runtime_messages(
        system_prompt,
        history,
        model=model,
        get_provider_fn=get_provider,
        get_models_fn=get_models,
        context_cache=_context_cache,
        telemetry=_session_telemetry,
        search_markers=("fetched external raw web link", "auto search tool results"),
        file_markers=("loaded file", "<file path=", "cached for retrieval"),
        include_coding_detector=True,
    )


def _stream_direct_completion(
    tui: LumiTUI,
    *,
    client,
    messages: list[dict[str, object]],
    model: str,
    label: str = "lumi",
) -> str:
    idx = tui.store.add(Msg("streaming", "", label))
    chunks: list[str] = []
    effort = normalize_reasoning_effort(getattr(tui, "reasoning_effort", "medium"))
    tuned_messages = apply_reasoning_effort(messages, effort)
    tuned_max_tokens, tuned_temperature = tune_inference_request(2048, 0.2, effort)
    try:
        full = stream_once(
            client,
            model,
            tuned_messages,
            max_tokens=tuned_max_tokens,
            temperature=tuned_temperature,
            on_delta=lambda delta: (
                chunks.append(delta),
                tui.store.append(idx, delta),
                tui.redraw(),
            ),
        )
    except Exception as ex:
        tui.store.set_text(idx, f"⚠  {ex}")
        tui.store.finalize(idx)
        return f"⚠  {ex}"
    tui.store.finalize(idx)
    if not full:
        full = "".join(chunks).strip()
    _session_telemetry.record_response(full)
    return full

# ══════════════════════════════════════════════════════════════════════════════
#  ANSI Colors & Deep Tokyo Night Math
# ══════════════════════════════════════════════════════════════════════════════
ESC = "\033"
CSI = ESC + "["

def _fg(h):
    h = h.lstrip("#")
    return f"{CSI}38;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"

def _bg(h):
    if h == "transparent": return f"{CSI}49m"
    h = h.lstrip("#")
    return f"{CSI}48;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"

def _bold(): return f"{CSI}1m"
def _italic(): return f"{CSI}3m"
def _reset(): return f"{CSI}0m"
def _hide_cur(): return f"{ESC}[?25l"
def _show_cur(): return f"{ESC}[?25h"
def _alt_on(): return f"{ESC}[?1049h"
def _alt_off(): return f"{ESC}[?1049l"
def _alt_scroll_on(): return f"{ESC}[?1007h"
def _alt_scroll_off(): return f"{ESC}[?1007l"
def _paste_on(): return f"{ESC}[?2004h"
def _paste_off(): return f"{ESC}[?2004l"
def _move(r, c): return f"{CSI}{r};{c}H"
def _erase_line(): return f"{CSI}2K"
def _clr_down(): return f"{CSI}J"

BG = "transparent"
BG_DARK = "#111418"
BG_HL = "#20252d"
BG_POP = "#171b21"
BORDER = "#2b313c"
MUTED = "#7a8392"
COMMENT = "#7a8392"
FG_DIM = "#b4bcc8"
FG = "#d7dce4"
FG_HI = "#f3f5f7"
BLUE = "#a5b8d1"
CYAN = "#aabed5"
GREEN = "#a8c2a1"
YELLOW = "#d6c6a1"
ORANGE = "#b4bcc8"
RED = "#d1a2a2"
PURPLE = "#b8bfd6"
TEAL = "#9cbeb7"

def B(h): return _fg(h) + _bold()
R = _reset()

SPINNER_FRAMES = list("⠋⠙⠚⠞⠦⠴⠲⠳⠓⠋")
PULSE_DOTS = ["   ", "·  ", " · ", "  ·", "···"]

def _rule(width, label=""):
    line_w = max(8, width)
    if not label:
        return _fg(BORDER) + "─" * line_w + R
    plain = f" {label} "
    left = max(0, (line_w - len(plain)) // 2)
    right = max(0, line_w - len(plain) - left)
    return _fg(BORDER) + "─" * left + R + _fg(MUTED) + plain + R + _fg(BORDER) + "─" * right + R

def _popup_frame(top, left, width, title=""):
    inner_w = max(0, width - 2)
    label = title.strip()[: max(0, inner_w - 2)]
    if label:
        plain = f"{label} " + "─" * max(0, inner_w - len(label) - 1)
    else:
        plain = "─" * inner_w
    return _move(top, 1) + _bg(BG) + _erase_line() + _move(top, left) + _fg(MUTED) + " " + plain[:inner_w].ljust(inner_w) + " " + R

def _popup_line(row, left, width, content="", tone=FG_DIM, selected=False):
    inner_w = max(0, width - 2)
    plain = content[:inner_w]
    return (
        _move(row, 1)
        + _bg(BG)
        + _erase_line()
        + _move(row, left)
        + (_bold() if selected else "")
        + _fg(tone)
        + " "
        + plain
        + " " * max(0, inner_w - len(plain))
        + " "
        + R
    )

def _rule(width, label=""):
    line_w = max(0, width)
    if not label:
        return _fg(BORDER) + "─" * line_w + R
    plain = f" {label} "
    left = max(0, (line_w - len(plain)) // 2)
    right = max(0, line_w - len(plain) - left)
    return _fg(BORDER) + "─" * left + R + _fg(MUTED) + plain + R + _fg(BORDER) + "─" * right + R

PROV_NAME = {
    "claude": "Claude", "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
    "mistral": "Mistral", "huggingface": "HuggingFace", "github": "GitHub Models",
    "cohere": "Cohere", "bytez": "Bytez", "cloudflare": "Cloudflare",
    "ollama": "Ollama", "council": "⚡ Council",
    "vercel": "Vercel AI", "vertex": "Vertex AI",
}
PROV_COL = {
    "claude": ORANGE, "gemini": CYAN, "groq": ORANGE, "openrouter": PURPLE, "mistral": RED,
    "huggingface": YELLOW, "github": FG_HI, "cohere": GREEN,
    "bytez": TEAL, "cloudflare": ORANGE, "ollama": FG_DIM, "council": PURPLE,
    "vercel": TEAL, "vertex": BLUE,
}

def _hm(): return datetime.now().strftime("%H:%M")
def _tok(t): return max(1, int(len(t.split()) * 1.35))
def _strip_ansi(s): return re.sub(r'\033\[[^a-zA-Z]*[a-zA-Z]|\033\].*?\007|\033.', '', s)
def _visible_len(s): return len(_strip_ansi(s))

def _term_size():
    s = shutil.get_terminal_size((120, 36))
    return max(s.lines, 24), max(s.columns, 80)

def _read_file(path: str) -> str:
    return Path(path).expanduser().read_text(errors="replace")

_KW = r'\b(def|class|return|import|from|if|elif|else|for|while|in|not|and|or|True|False|None|try|except|with|as|pass|break|continue|raise|yield|lambda|async|await|int|float|void|char|bool|double|auto|const|static|public|private|protected|virtual|override|namespace|using|std|cout|cin|cerr|endl|vector|string|map|set|list|new|delete|this)\b'
# Pre-compiled once — never rebuilt per line
_SYNTAX_RE = re.compile(
    rf'(?P<str>"[^"]*"|\'[^\']*\')|(?P<com>//.*|#.*)|(?P<num>\b\d+\b)|(?P<kw>{_KW})|(?P<ws>\s+)|(?P<other>.)'
)

def _syntax_hi(line):
    out = ""
    tokens = _SYNTAX_RE.finditer(line)
    for t in tokens:
        g = t.lastgroup
        if g == 'str': out += _fg(YELLOW) + t.group() + R
        elif g == 'com': out += _fg(COMMENT) + _italic() + t.group() + R
        elif g == 'num': out += _fg(ORANGE) + t.group() + R
        elif g == 'kw': out += _fg(PURPLE) + _bold() + t.group() + R
        else:
            txt = t.group()
            out += _fg(CYAN) + txt if g == 'other' and txt in '{}[]().:=+*-/<>!&|' else _fg(FG_HI) + txt
            out += R if g == 'other' else ""
    return out + R

# ══════════════════════════════════════════════════════════════════════════════
#  Robust OS Controls (UTF-8 Compatible / Resize Handling)
# ══════════════════════════════════════════════════════════════════════════════
def _read_key():
    return read_key(sys.stdin.fileno())

# ══════════════════════════════════════════════════════════════════════════════
#  Command Infrastructure
# ══════════════════════════════════════════════════════════════════════════════
class CommandRegistry:
    def __init__(self):
        self.commands = {}
        self.examples = {
            "/add-dir": "/add-dir ../shared-lib",
            "/agent": "/agent fix the failing tests and keep the diff small",
            "/browse": "/browse src",
            "/config": "/config set effort high",
            "/files": "/files auth routing",
            "/file": "/file src/tui/app.py",
            "/fs": "/fs mkdir docs",
            "/git": "/git status",
            "/help": "/help",
            "/hooks": "/hooks inspect",
            "/memory": "/memory",
            "/model": "/model",
            "/onboard": "/onboard",
            "/pane": "/pane pytest -q",
            "/permissions": "/permissions all",
            "/logs": "/logs",
            "/project": "/project .",
            "/rag": "/rag how does the agent patch files?",
            "/review": "/review src/chat/hf_client.py",
            "/search": "/search latest ruff rule docs",
            "/skills": "/skills inspect release",
            "/status": "/status",
            "/tasks": "/tasks",
            "/version": "/version",
        }
    def register(self, name, desc, aliases=None):
        def decorator(func):
            self.commands[name] = {
                "func": func,
                "desc": desc,
                "category": self._infer_category(name),
                "aliases": tuple(aliases or ()),
            }
            for alias in aliases or ():
                self.commands[alias] = {
                    "func": func,
                    "desc": f"{desc} (alias)",
                    "category": self._infer_category(name),
                    "aliases": (),
                }
            return func
        return decorator

    @staticmethod
    def _subsequence_score(query: str, text: str) -> int | None:
        if not query:
            return 0
        pos = -1
        score = 0
        for char in query:
            next_pos = text.find(char, pos + 1)
            if next_pos == -1:
                return None
            score += next_pos - pos
            pos = next_pos
        return score

    def _infer_category(self, name):
        if name in {"/model", "/theme", "/persona", "/mode", "/offline", "/plugins", "/plugin", "/permissions", "/config", "/status", "/doctor", "/onboard", "/benchmark", "/hooks", "/brief", "/fast", "/effort", "/version", "/logs", "/quit", "/exit"}:
            return "settings"
        if name in {"/agent", "/agents", "/tasks", "/jobs", "/build", "/learn", "/ship", "/fixci", "/scaffold", "/edit", "/review", "/fix", "/debug", "/improve", "/optimize", "/security", "/refactor", "/test", "/explain"}:
            return "code"
        if name in {"/search", "/web", "/image", "/data", "/pdf", "/rag", "/index"}:
            return "research"
        if name in {"/remember", "/memory", "/forget", "/save", "/load", "/resume", "/sessions", "/session", "/export", "/find", "/note", "/todo", "/skills"}:
            return "memory"
        if name in {"/browse", "/fs", "/files", "/add-dir", "/file", "/project", "/shell", "/grep", "/tree", "/lint", "/fmt", "/run", "/apply", "/pane", "/ide"}:
            return "workspace"
        return "chat"

    def get_hits(self, query):
        q = query.lower().strip()
        needle = q[1:] if q.startswith("/") else q
        hits = []
        seen = set()
        for cmd, data in self.commands.items():
            if cmd in seen:
                continue
            cmd_lower = cmd.lower()
            alias_matches = " ".join(alias.lower() for alias in data.get("aliases", ()))
            desc_lower = data["desc"].lower()
            haystack = " ".join([cmd_lower, cmd_lower.lstrip("/"), desc_lower, alias_matches]).strip()
            score: tuple[int, int, str] | None = None
            if not needle:
                score = (0, 0, cmd_lower)
            elif cmd_lower.startswith(q) or cmd_lower.lstrip("/").startswith(needle):
                score = (0, len(cmd_lower), cmd_lower)
            elif needle in cmd_lower or needle in desc_lower or needle in alias_matches:
                score = (1, len(cmd_lower), cmd_lower)
            else:
                fuzzy = self._subsequence_score(needle, haystack)
                if fuzzy is not None:
                    score = (2, fuzzy, cmd_lower)
            if score is None:
                continue
            hits.append(
                (
                    score,
                    cmd,
                    data["desc"],
                    data.get("category", "chat"),
                    self.examples.get(cmd, ""),
                )
            )
            seen.add(cmd)
        hits.sort(key=lambda item: item[0])
        return [(cmd, desc, category, example) for _score, cmd, desc, category, example in hits[:12]]

registry = CommandRegistry()

# ══════════════════════════════════════════════════════════════════════════════
#  Rendering Graphics & Bounding Boxes
# ══════════════════════════════════════════════════════════════════════════════
class Renderer:
    def __init__(self, tui):
        self.tui = tui
        self._lock = threading.Lock()
        self._starter_cache_key = None
        self._starter_cache_lines: list[str] = []
        self._chat_cache_key = None
        self._chat_cache_lines: list[str] = []
        style = ViewStyle(
            fg_fn=_fg,
            bg_fn=_bg,
            bold=_bold,
            italic=_italic,
            reset=R,
            bg_value=BG,
            bg_pop_value=BG_POP,
            bg_hl_value=BG_HL,
            border=BORDER,
            muted=MUTED,
            comment=COMMENT,
            fg_dim=FG_DIM,
            fg=FG,
            fg_hi=FG_HI,
            cyan=CYAN,
            red=RED,
            teal=TEAL,
            orange=ORANGE,
        )
        self._starter_view = StarterView(
            tui,
            style,
            provider_resolver=self._active_provider_key,
            provider_label=lambda provider: PROV_NAME.get(provider, provider),
            spinner_frames=SPINNER_FRAMES,
        )
        self._transcript_view = TranscriptView(
            tui,
            style,
            inline_renderer=self._inline,
            syntax_highlighter=_syntax_hi,
            strip_ansi=_strip_ansi,
            visible_len=_visible_len,
        )
        self._pane_view = PaneView(
            tui,
            style,
            strip_ansi=_strip_ansi,
        )
        self._overlay_view = OverlayView(
            tui,
            style,
            popup_frame=_popup_frame,
            popup_line=_popup_line,
            move=_move,
            strip_ansi=_strip_ansi,
        )

    def _active_provider_key(self) -> str:
        if self.tui.current_model == "council":
            return "council"
        try:
            return get_provider()
        except Exception:
            return "huggingface"

    def draw(self):
        with self._lock:
            self._draw()

    def _draw(self):
        rows, cols = _term_size()
        pane_state = getattr(self.tui, "pane", None)
        pane_active = bool(getattr(self.tui, "pane_active", False) or getattr(pane_state, "active", False))
        chat_w = int(cols * 0.6) if pane_active else cols
        pane_w = cols - chat_w - 1 if pane_active else 0
        buf =[]
        w = buf.append

        w(_hide_cur())
        for clear_row in range(1, rows + 1):
            w(_move(clear_row, 1) + _bg(BG) + _erase_line())

        starter_lines = self._build_starter_lines(chat_w)
        prompt_lines, prompt_cursor_row, prompt_cursor_col = self._prompt_bar(rows, cols, chat_w)
        starter_rows = len(starter_lines)
        prompt_height = len(prompt_lines)
        chat_lines = self._build_chat_lines(chat_w)
        total = len(chat_lines)
        transcript_top = self._transcript_top(starter_rows, total)
        prompt_top = self._prompt_top(rows, transcript_top, prompt_height, total)
        self.tui._last_prompt_top = prompt_top
        self.tui._last_prompt_height = prompt_height

        starter_top = 1
        for i, line in enumerate(starter_lines, start=starter_top):
            if i > rows:
                break
            w(_move(i, 1))
            w(_bg(BG) + _erase_line() + line + _bg(BG))

        for idx, line in enumerate(prompt_lines, start=prompt_top):
            if idx > rows:
                break
            w(_move(idx, 1))
            if pane_active:
                prompt_stripped = _strip_ansi(line)
                pad = max(0, chat_w - len(prompt_stripped))
                divider = _fg(BORDER) + "│" + R
                blank_pane = " " * max(0, pane_w)
                w(_bg(BG) + line + " " * pad + divider + blank_pane + _bg(BG))
            else:
                w(_bg(BG) + _erase_line() + line + _bg(BG))

        transcript_bottom = min(rows, prompt_top - 1)
        chat_rows = max(0, transcript_bottom - transcript_top + 1)

        offset = max(0, min(self.tui.scroll_offset, max(0, total - chat_rows)))
        end = total - offset
        start = max(0, end - chat_rows)
        chat_lines = chat_lines[start:end]

        pane_lines = self._build_pane_lines(pane_w, chat_rows) if pane_active else []

        for i in range(chat_rows):
            w(_move(i + transcript_top, 1))
            cl = chat_lines[i] if i < len(chat_lines) else ""

            if pane_active:
                cl_stripped = _strip_ansi(cl)
                pad = max(0, chat_w - len(cl_stripped))
                cl_padded = cl + " " * pad
                pane_line = pane_lines[i] if i < len(pane_lines) else ""

                divider = _fg(BORDER) + "│" + R
                w(_bg(BG) + cl_padded + divider + pane_line + _bg(BG))
            else:
                w(_bg(BG) + _erase_line() + cl + _bg(BG))

        if getattr(self.tui, "browser_visible", False): w(self._browser_popup(rows, chat_w))
        if self.tui.slash_visible and self.tui.slash_hits: w(self._slash_popup(rows, chat_w))
        if self.tui.path_visible and self.tui.path_hits: w(self._path_popup(rows, chat_w))
        if self.tui.picker_visible and self.tui.picker_items: w(self._picker_popup(rows, chat_w))
        if getattr(self.tui, "command_palette_visible", False): w(self._command_palette_popup(rows, chat_w))
        if getattr(self.tui, "shortcuts_visible", False): w(self._shortcuts_popup(rows, chat_w))
        if getattr(self.tui, "workspace_trust_visible", False): w(self._workspace_trust_popup(rows, cols))
        if getattr(self.tui, "permission_prompt_active", False): w(self._permission_popup(rows, cols))
        if self.tui.notification: w(self._notification_bar(rows, cols))

        cur_col = prompt_cursor_col
        cursor_row = min(rows, self._prompt_cursor_row(rows, prompt_height, prompt_top, prompt_cursor_row))
        w(_move(cursor_row, min(cur_col, cols - 1)))
        w(_show_cur())

        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def _build_starter_lines(self, width):
        review_card = getattr(self.tui, "review_card", None)
        pending_plan = getattr(self.tui, "_pending_file_plan", None)
        cache_key = (
            width,
            bool(getattr(self.tui, "show_starter_panel", True)),
            bool(getattr(self.tui, "starter_panel_pinned", False)),
            str(getattr(self.tui, "current_model", "")),
            self._active_provider_key(),
            str(Path.cwd().resolve()),
            str(getattr(self.tui, "session_tip", "") or ""),
            tuple(getattr(self.tui, "recent_actions", []) or []),
            tuple(getattr(self.tui, "recent_commands", []) or []),
            bool(getattr(review_card, "active", False)),
            str(getattr(review_card, "title", "") or ""),
            repr(pending_plan) if pending_plan else "",
        )
        if cache_key == self._starter_cache_key:
            return list(self._starter_cache_lines)
        intro = self._starter_view.build(width)
        lines = intro.header_lines + intro.trailing_lines
        self._starter_cache_key = cache_key
        self._starter_cache_lines = list(lines)
        return list(lines)

    def _build_chat_lines(self, width):
        snapshot = self.tui.store.snapshot()
        streaming = any(msg.role == "streaming" for msg in snapshot)
        agent_tasks = tuple(
            (str(item.get("text", "")), bool(item.get("done", False)), str(item.get("status", "")))
            for item in (getattr(self.tui, "agent_tasks", None) or [])
        )
        cache_key = (
            width,
            int(getattr(self.tui.store, "version", 0)),
            bool(getattr(self.tui, "vessel_mode", False)),
            str(getattr(self.tui, "active_vessel", "") or ""),
            str(getattr(self.tui, "agent_active_objective", "") or ""),
            agent_tasks,
        )
        if not streaming and cache_key == self._chat_cache_key:
            return list(self._chat_cache_lines)
        lines = self._transcript_view.build(width)
        if not streaming:
            self._chat_cache_key = cache_key
            self._chat_cache_lines = list(lines)
        return list(lines)

    def _transcript_top(self, starter_rows, chat_line_count):
        return 1 + max(0, starter_rows) + (1 if starter_rows > 0 and chat_line_count > 0 else 0)

    def _prompt_top(self, rows, transcript_top, prompt_height, chat_line_count):
        min_top = max(1, transcript_top)
        max_top = max(min_top, rows - prompt_height + 1)
        ideal_top = min_top + max(0, chat_line_count)
        return min(max_top, ideal_top)

    def _prompt_cursor_row(self, rows, prompt_height, prompt_top, prompt_cursor_row):
        return prompt_top + max(0, prompt_cursor_row - 1)

    def _build_pane_lines(self, width, height):
        return self._pane_view.build(width, height)

    def _inline(self, text):
        out = ""
        i = 0
        while i < len(text):
            if text[i:i+2] == "**" and "**" in text[i+2:]:
                end = text.index("**", i + 2)
                out += _bold() + _fg(FG_HI) + text[i+2:end] + R + _fg(FG)
                i = end + 2
            elif text[i] == "*" and i+1 < len(text) and text[i+1] != "*" and "*" in text[i+1:]:
                end = text.index("*", i + 1)
                out += _italic() + _fg(FG_DIM) + text[i+1:end] + R + _fg(FG)
                i = end + 1
            elif text[i] == "`" and "`" in text[i+1:]:
                end = text.index("`", i + 1)
                out += _bg(BG_DARK) + _fg(CYAN) + " " + text[i+1:end] + " " + R + _fg(FG)
                i = end + 1
            else:
                out += _fg(FG) + text[i]
                i += 1
        return out

    def _mode_hint(self):
        parts = []
        if self.tui.multiline:
            parts.append("multiline")
        if self.tui.response_mode:
            parts.append(self.tui.response_mode)
        if self.tui.vessel_mode and self.tui.active_vessel:
            parts.append(f"vessel {self.tui.active_vessel}")
        return " · ".join(parts)

    def _cwd_display(self, max_len=28):
        cwd = str(Path.cwd().resolve())
        home = str(Path.home())
        if cwd == home:
            display = "~"
        elif cwd.startswith(home + "/"):
            display = "~/" + cwd[len(home) + 1 :]
        else:
            display = cwd
        if len(display) <= max_len:
            return display
        return "..." + display[-(max_len - 3) :]

    def _branch_display(self) -> str:
        profile = getattr(self.tui, "workspace_profile", None)
        branch = getattr(profile, "git_branch", "") if profile is not None else ""
        branch = branch or getattr(self.tui, "_git_branch", "") or ""
        return branch or "-"

    def _stat_info(self, chat_w):
        """Compute status string (plain + colored) for top bar."""
        tui = self.tui
        pname = PROV_NAME.get(tui.current_model if tui.current_model == "council" else get_provider(), get_provider())
        model = tui.current_model.split("/")[-1][:28]
        cwd = self._cwd_display()

        if tui.vessel_mode and tui.active_vessel:
            stat_str = f"vessel {tui.active_vessel.lower()} · 100% left · {cwd}"
            stat_colored = (
                _fg(RED) + _bold() + f"vessel {tui.active_vessel.lower()}" + R
                + _fg(COMMENT) + f" · 100% left · {cwd}" + R
            )
        else:
            stat_str = f"{pname} · {model} · 100% left · {cwd}"
            stat_colored = (
                _fg(FG_DIM) + pname + R
                + _fg(COMMENT) + " · " + R
                + _fg(FG_HI) + model + R
                + _fg(COMMENT) + f" · 100% left · {cwd}" + R
            )

        if tui.current_model == "council" and getattr(tui, "agents", None):
            names_plain, rail_segments = [], []
            for ag in tui.agents:
                ico = SPINNER_FRAMES[ag.frame % len(SPINNER_FRAMES)] if ag.st == "spin" else ("✓" if ag.st == "ok" else "✕")
                col = (CYAN if ag.lead else FG_DIM) if ag.st == "spin" else (GREEN if ag.st == "ok" else RED)
                nm  = ag.name.split()[0][:6]
                names_plain.append(nm)
                rail_segments.append(_fg(col) + ico + " " + nm + R)
            stat_str     = "Council " + " ".join(names_plain) + " · 100% left · " + cwd
            stat_colored = _fg(COMMENT) + "council" + _fg(FG_DIM) + " · " + _fg(FG_DIM) + "  ".join(rail_segments) + R

        return stat_str, stat_colored

    def _top_bar(self, rows, cols, chat_w):
        return _move(1, 1) + _bg(BG) + _erase_line() + _move(2, 1) + _bg(BG) + _erase_line()

    def _prompt_placeholder(self, chat_w: int) -> str:
        profile = getattr(self.tui, "workspace_profile", None)
        if int(getattr(self.tui, "turns", 0) or 0) == 0 and profile is None:
            placeholder = "inspect this repo and tell me how it works"
        else:
            practical: list[str] = []
            serious: list[str] = []
            funny: list[str] = []
            if profile is None:
                practical.extend(
                    [
                        "inspect this repo and tell me how it works",
                        "find the main entrypoint and explain it",
                        "map the architecture and point out the risky parts",
                        "show me where the real logic starts",
                    ]
                )
                serious.extend(
                    [
                        "show me the subsystem I need to understand before editing",
                        "trace the startup path and explain the handoffs",
                        "identify the most fragile part of this repo",
                    ]
                )
                funny.extend(
                    [
                        "tell me which file looks innocent but definitely is not",
                        "find the part of this repo that is quietly cursed",
                        "show me the file most likely to waste my afternoon",
                    ]
                )
            elif getattr(profile, "changed_files", ()):
                practical.extend(
                    [
                        "review the current changes and find issues",
                        "summarize what changed and what looks risky",
                        "trace the changed files and explain the impact",
                    ]
                )
                serious.extend(
                    [
                        "check the diff for regressions and edge cases",
                        "identify the highest-risk change before we merge anything",
                        "show me which edit is most likely to break prod",
                    ]
                )
                funny.extend(
                    [
                        "find the bug hiding in the latest changes",
                        "tell me which edit is acting confident for no reason",
                        "show me the diff line that is about to start drama",
                    ]
                )
            elif getattr(profile, "verification_commands", {}):
                practical.extend(
                    [
                        "run the tests and fix the failures",
                        "add tests for the riskiest edge cases",
                        "trace the failing path and patch it cleanly",
                    ]
                )
                serious.extend(
                    [
                        "find the brittle path before we edit anything",
                        "tell me what will break first if we touch auth",
                        "pin down the failure before we change code",
                    ]
                )
                funny.extend(
                    [
                        "find the test that is about to ruin my day",
                        "show me which failure is screaming the loudest",
                        "tell me which test file woke up angry today",
                    ]
                )
            elif getattr(profile, "frameworks", ()):
                framework = str(profile.frameworks[0])
                practical.extend(
                    [
                        f"explain the {framework} architecture in this repo",
                        f"show me the core {framework} flow from entrypoint to output",
                        "map the important files before we change anything",
                    ]
                )
                serious.extend(
                    [
                        "tell me where the complexity is hiding",
                        "find the hottest path in this codebase",
                        "show me the subsystem with the most coupling",
                    ]
                )
                funny.extend(
                    [
                        "show me the part of this stack I will regret touching",
                        "tell me which layer is pretending to be simple",
                        "find the file that thinks it is the whole framework",
                    ]
                )
            else:
                practical.extend(
                    [
                        "find where this symbol is used",
                        "trace the startup path and explain it",
                        "show me the fastest way to understand this project",
                    ]
                )
                serious.extend(
                    [
                        "show me the highest-risk part of this repo",
                        "identify the subsystem most likely to cause regressions",
                        "find dead code or weird leftovers",
                    ]
                )
                funny.extend(
                    [
                        "tell me what this codebase is pretending to be organized about",
                        "show me the file that definitely needs an explanation",
                        "find the weirdest thing still surviving in this repo",
                    ]
                )
            seed = (
                int(getattr(self.tui, "turns", 0) or 0) * 7
                + len(getattr(self.tui, "recent_commands", []) or [])
                + len(getattr(self.tui, "recent_actions", []) or [])
                + len(str(Path.cwd().resolve()))
            )
            tone_pools = [pool for pool in (practical, serious, funny) if pool]
            chosen_pool = tone_pools[seed % len(tone_pools)]
            item_index = (seed // max(1, len(tone_pools))) % len(chosen_pool)
            placeholder = chosen_pool[item_index]
        max_len = max(12, chat_w - 4)
        if len(placeholder) > max_len:
            placeholder = placeholder[: max_len - 1].rstrip() + "…"
        return placeholder

    def _prompt_bar(self, rows, cols, chat_w):
        tui = self.tui
        text = tui.buf
        rail_w = max(20, chat_w)
        text_w = max(10, rail_w - 2)

        def chunk_plain(value: str) -> list[str]:
            logical = value.split("\n") or [""]
            out: list[str] = []
            for line in logical:
                if line == "":
                    out.append("")
                    continue
                start = 0
                while start < len(line):
                    out.append(line[start : start + text_w])
                    start += text_w
            return out or [""]

        if not text:
            visible = [""]
            cursor_row_rel = 0
            cursor_col = 0
        else:
            cursor_before = text[: tui.cur_pos]
            all_lines = chunk_plain(text)
            cursor_lines = chunk_plain(cursor_before)
            cursor_line = max(0, len(cursor_lines) - 1)
            cursor_col = len(cursor_lines[-1]) if cursor_lines else 0
            visible_limit = 3 if (tui.multiline or "\n" in text or len(text) > text_w) else 1
            start = max(0, cursor_line - visible_limit + 1)
            visible = all_lines[start : start + visible_limit] or [""]
            cursor_row_rel = cursor_line - start

        pending_label, pending_hint = tui.filesystem_prompt_hint()

        content_rows: list[tuple[str, str, str]] = []
        if text:
            for idx, segment in enumerate(visible):
                marker = "› " if idx == 0 else "  "
                tone = FG_HI if idx == 0 else FG
                content_rows.append((marker, tone, segment))
        elif tui.busy:
            frame = int(time.time() * 10) % len(SPINNER_FRAMES)
            content_rows.append((SPINNER_FRAMES[frame] + " ", MUTED, "thinking"))
        elif pending_label:
            pending_text = pending_label + (f" · {pending_hint}" if pending_hint else "")
            content_rows.append(("? ", CYAN, pending_text[:text_w]))
        else:
            content_rows.append(("› ", MUTED, self._prompt_placeholder(chat_w)[:text_w]))

        effort = normalize_reasoning_effort(getattr(tui, "reasoning_effort", "medium"))
        effort_label = display_reasoning_effort(effort, short=True)
        effort_icon = display_reasoning_indicator(effort)
        footer_left = "? for shortcuts"
        footer_right_plain = f"{effort_icon} {effort_label} · /effort"
        gap = max(2, chat_w - len(footer_left) - len(footer_right_plain))
        footer_line = (
            _fg(MUTED)
            + footer_left
            + R
            + " " * gap
            + _fg(COMMENT)
            + footer_right_plain
            + R
        )

        lines = [_rule(chat_w)]
        for marker, tone, segment in content_rows:
            marker_color = CYAN if (tui.busy or pending_label) and marker.strip() else FG_HI
            lines.append(
                _fg(marker_color)
                + marker
                + R
                + _fg(tone)
                + segment[:text_w]
                + R
            )
        lines.append(_rule(chat_w))
        lines.append(footer_line)

        cursor_row = 2 + (cursor_row_rel if text else 0)
        active_marker = content_rows[min(cursor_row_rel if text else 0, len(content_rows) - 1)][0]
        cursor_col_abs = len(active_marker) + 1 + cursor_col
        return lines, cursor_row, cursor_col_abs

    # kept for any external callers; delegates to the two new methods
    def _input_area(self, rows, cols, chat_w):
        prompt_lines, _cursor_row, _cursor_col = self._prompt_bar(rows, cols, chat_w)
        starter_rows = len(self._build_starter_lines(chat_w))
        chat_lines = self._build_chat_lines(chat_w)
        prompt_top = self._prompt_top(
            rows,
            self._transcript_top(starter_rows, len(chat_lines)),
            len(prompt_lines),
            len(chat_lines),
        )
        return self._top_bar(rows, cols, chat_w) + "".join(
            _move(prompt_top + idx, 1) + line
            for idx, line in enumerate(prompt_lines)
        )

    def _browser_popup(self, rows, chat_w):
        return self._overlay_view.browser_popup(rows, chat_w)

    def _slash_popup(self, rows, chat_w):
        return self._overlay_view.slash_popup(rows, chat_w)

    def _path_popup(self, rows, chat_w):
        return self._overlay_view.path_popup(rows, chat_w)

    def _picker_popup(self, rows, chat_w):
        return self._overlay_view.picker_popup(rows, chat_w)

    def _shortcuts_popup(self, rows, chat_w):
        return self._overlay_view.shortcuts_popup(rows, chat_w)

    def _command_palette_popup(self, rows, chat_w):
        return self._overlay_view.command_palette_popup(rows, chat_w)

    def _notification_bar(self, rows, cols):
        return self._overlay_view.notification_bar(rows, cols)

    def _workspace_trust_popup(self, rows, cols):
        return self._overlay_view.workspace_trust_popup(rows, cols)

    def _permission_popup(self, rows, cols):
        return self._overlay_view.permission_popup(rows, cols)


# ══════════════════════════════════════════════════════════════════════════════
#  Controller & Input Lifecycle  (TUI Controller Engine Hub Main Event Sync loop)
# ══════════════════════════════════════════════════════════════════════════════
class LumiTUI:
    def __init__(self):
        self._state_lock = threading.Lock()
        self._task_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="lumi")
        self._active_task: concurrent.futures.Future | None = None
        self.store = Store(); self.agents =[]
        self._cached_tok_count: int = 0
        self._cached_tok_len: int = 0   # len(memory) when last computed
        self.buf = ""; self.cur_pos = 0; self.scroll_offset = 0
        self.slash_hits =[]; self.slash_sel = 0; self.slash_visible = False
        self.picker_items =[]; self.picker_sel = 0; self.picker_visible = False
        self.notification = ""; self._notif_timer = None; self._running = False
        self._hist_file = _LOG_DIR / "history"
        self.history = InputHistory(self._hist_file)

        self.memory = ShortTermMemory(max_turns=20); self.persona = {}
        self.persona_override = {}; self.system_prompt = ""; self.client = None
        self.current_model = "unknown"; self.name = "Lumi"
        self.turns = 0; self.last_msg = None; self.last_reply = None
        self.prev_reply = None; self.response_mode = None
        self.multiline = False; self._compact = False; self.busy = False
        self.brief_mode = False; self.fast_mode = False
        self.reasoning_effort = "medium"
        self._last_prompt_top = 1
        self._last_prompt_height = 1
        self._stop_requested = threading.Event()
        self._git_branch = self._read_git_branch(Path.cwd())
        self._startup_warmed = False
        self._startup_warm_thread: threading.Thread | None = None
        self._cached_project_context: tuple[Path | None, float | None, str] = (None, None, "")
        self._cached_project_memory: tuple[Path | None, float | None, str] = (None, None, "")
        self.workbench_jobs = [workbench_job_to_dict(job) for job in load_workbench_jobs(Path.cwd(), limit=12)]
        self._workbench_job_seq = 0
        for item in self.workbench_jobs:
            match = re.match(r"^wb-(\d+)$", str(item.get("id", "")))
            if match:
                self._workbench_job_seq = max(self._workbench_job_seq, int(match.group(1)))

        # Agent planning state (for /agent plans)
        self.agent_active_objective = None
        self.agent_tasks = []

        # ── Vessel Mode ───────────────────────────────────────────────────────
        self.vessel_mode   = False   # True when acting as a pure AI conduit
        self.active_vessel = None    # "gemini" | "qwen" | "opencode" | None
        self._pending_handoff = None # set by /mode; consumed by main loop

        self._loaded_plugins =[]; self.renderer = Renderer(self)
        self.original_termios = None
        initialize_ui_state(
            self,
            history=self.history,
            notes_store=LittleNotesStore(),
        )
        self.runtime_config = load_runtime_config(Path.cwd())
        self._apply_runtime_config(self.runtime_config)
        self.browser_cwd = os.getcwd()
        self.workspace_profile = None
        self.workspace_trust_visible = self._should_prompt_workspace_trust()

    @staticmethod
    def _read_git_branch(base_dir: Path) -> str:
        head_file = base_dir / ".git" / "HEAD"
        try:
            raw = head_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
        if raw.startswith("ref: "):
            return raw.rsplit("/", 1)[-1].strip()
        return raw[:7]

    def _apply_runtime_config(self, config) -> None:
        self.runtime_config = config
        self.multiline = bool(config.multiline)
        self._compact = bool(config.compact_mode)
        self.brief_mode = bool(config.brief_mode)
        self.fast_mode = bool(config.fast_mode)
        self.live_lookup_enabled = bool(getattr(config, "live_lookup", True))
        self.reasoning_effort = "low" if self.fast_mode else normalize_reasoning_effort(config.reasoning_effort)

    def _sync_runtime_config(self, **updates):
        config = update_runtime_config(Path.cwd(), **updates)
        self._apply_runtime_config(config)
        self.workspace_profile = inspect_workspace(Path.cwd())
        self._git_branch = getattr(self.workspace_profile, "git_branch", "") or self._git_branch
        return config

    def set_pane(
        self,
        *,
        title: str,
        lines: list[str] | None = None,
        subtitle: str = "",
        footer: str = "",
        close_on_escape: bool = False,
    ) -> None:
        self.pane = PaneState(
            active=True,
            title=title,
            subtitle=subtitle,
            lines=list(lines or []),
            footer=footer,
            close_on_escape=close_on_escape,
        )
        self.pane_active = True
        self.pane_lines_output = self.pane.content()

    def clear_pane(self) -> None:
        self.pane = PaneState()
        self.pane_active = False
        self.pane_lines_output = []

    def set_review_card(
        self,
        *,
        title: str,
        summary_lines: list[str] | None = None,
        preview_lines: list[str] | None = None,
        footer: str = "",
    ) -> None:
        self.review_card = ReviewCard(
            active=True,
            title=title,
            summary_lines=list(summary_lines or []),
            preview_lines=list(preview_lines or []),
            footer=footer,
        )

    def clear_review_card(self) -> None:
        self.review_card = ReviewCard()

    def _workbench_model(self) -> str:
        if self.current_model != "council":
            return self.current_model
        provider = get_provider()
        models = get_models(provider)
        return pick_startup_model(provider, models) if models else self.current_model

    def _workbench_pane_lines(self) -> list[str]:
        report = render_workbench_jobs_report(Path.cwd(), live_jobs=self.workbench_jobs, limit=8)
        lines = report.splitlines()[1:]
        return lines or ["No workbench jobs yet."]

    def _workbench_pane_visible(self) -> bool:
        pane = getattr(self, "pane", None)
        if not self.pane_active or pane is None:
            return False
        return bool(getattr(pane, "active", False) and getattr(pane, "title", "") == "workbench jobs")

    def _refresh_workbench_pane(self, *, force: bool = False) -> None:
        if not force and not self._workbench_pane_visible():
            self.redraw()
            return
        self.set_pane(
            title="workbench jobs",
            subtitle=WORKBENCH_TITLE,
            lines=self._workbench_pane_lines(),
            footer="Esc close  ·  /pane close  ·  /jobs",
            close_on_escape=True,
        )
        self.redraw()

    def launch_workbench(self, mode: str, objective: str, *, dry_run: bool = False, show_pane: bool = False) -> str:
        self._workbench_job_seq += 1
        job_id = f"wb-{self._workbench_job_seq}"
        base_dir = Path.cwd().resolve()
        client = self.client
        model = self._workbench_model()
        system_prompt = self.system_prompt
        memory = self.memory
        job_record = create_workbench_job(mode, objective, base_dir=base_dir, dry_run=dry_run, job_id=job_id)
        job = workbench_job_to_dict(job_record)
        self.workbench_jobs.insert(0, job)
        save_workbench_job(job_record)
        self.agent_active_objective = f"{mode}: {objective}"
        self.agent_tasks = [{"text": "profiling workspace", "status": "queued"}]
        self._refresh_workbench_pane(force=show_pane)

        def _update_job(*, status: str | None = None, stage: str | None = None, summary: str | None = None, risk: str | None = None) -> None:
            with self._state_lock:
                for item in self.workbench_jobs:
                    if item.get("id") != job_id:
                        continue
                    if status is not None:
                        item["status"] = status
                    if stage is not None:
                        item["stage"] = stage
                        self.agent_tasks = [{"text": stage, "status": status or str(item.get("status", "running"))}]
                    if summary is not None:
                        item["summary"] = summary
                    if risk is not None:
                        item["risk"] = risk
                    current_record = coerce_workbench_job(item, base_dir=base_dir) or job_record
                    record = update_workbench_job(
                        current_record,
                        status=str(item.get("status", "queued")),
                        stage=str(item.get("stage", "queued")),
                        summary=str(item.get("summary", "")),
                        risk=str(item.get("risk", "")),
                        touched_files=tuple(str(value) for value in item.get("touched_files", []) if str(value).strip()),
                        failed_checks=tuple(str(value) for value in item.get("failed_checks", []) if str(value).strip()),
                        log_excerpt=str(item.get("log_excerpt", "")),
                    )
                    save_workbench_job(record)
                    break
            self._refresh_workbench_pane()

        def _progress(stage: str) -> None:
            _update_job(status="running", stage=stage)

        def _go() -> None:
            try:
                _update_job(status="running", stage="profiling workspace")
                result = execute_workbench(
                    mode,
                    objective,
                    client=client,
                    model=model,
                    memory=memory,
                    system_prompt=system_prompt,
                    base_dir=base_dir,
                    dry_run=dry_run,
                    progress_cb=_progress,
                )
            except Exception as exc:
                job["log_excerpt"] = str(exc)
                _update_job(status="failed", stage="failed", summary=str(exc))
                self._err(f"{mode} failed: {exc}")
                self._notify(f"{mode} failed")
            else:
                job["touched_files"] = list(getattr(result, "touched_files", ()) or ())
                job["failed_checks"] = list(getattr(result, "failed_checks", ()) or ())
                job["log_excerpt"] = str(getattr(result, "execution_log", "") or "")
                _update_job(
                    status="done",
                    stage="artifacts ready",
                    summary=result.summary,
                    risk=result.risk_level,
                )
                self._sys(render_workbench_result(result))
                self._notify(f"{mode} ready")
            finally:
                self.agent_active_objective = None
                self.agent_tasks = []
                self.redraw()

        threading.Thread(target=_go, daemon=True).start()
        return job_id

    def _should_prompt_workspace_trust(self) -> bool:
        cwd = Path.cwd().resolve()
        if cwd != Path.home().resolve():
            return False
        return _workspace_path_key(cwd) not in _load_workspace_trust_paths()

    def show_workspace_trust_prompt(self) -> None:
        self.workspace_trust_sel = 0
        self.workspace_trust_visible = True

    def accept_workspace_trust(self) -> None:
        trusted = _load_workspace_trust_paths()
        trusted.add(_workspace_path_key(Path.cwd()))
        _save_workspace_trust_paths(trusted)
        self.workspace_trust_sel = 0
        self.workspace_trust_visible = False
        self._notify("Workspace trusted")

    def decline_workspace_trust(self) -> None:
        self.workspace_trust_sel = 1
        self.workspace_trust_visible = False
        with self._state_lock:
            self._running = False

    def _project_context_block(self) -> str:
        path, cached_mtime, cached_text = self._cached_project_context
        context_path, context_text = load_project_context(Path.cwd())
        current_mtime = None
        if context_path is not None:
            try:
                current_mtime = context_path.stat().st_mtime
            except OSError:
                current_mtime = None
        if path == context_path and cached_mtime == current_mtime:
            return cached_text
        self._cached_project_context = (context_path, current_mtime, context_text)
        return context_text

    def _project_memory_block(self) -> str:
        path = project_memory_path(Path.cwd())
        current_mtime = None
        if path.exists():
            try:
                current_mtime = path.stat().st_mtime
            except OSError:
                current_mtime = None
        cached_path, cached_mtime, cached_text = self._cached_project_memory
        if cached_path == path and cached_mtime == current_mtime and cached_text:
            return cached_text
        block = render_memory_block(Path.cwd())
        self._cached_project_memory = (path, current_mtime, block)
        return block

    def _bootstrap_system_prompt(self) -> str:
        prompt_context = PromptContext(
            date=datetime.now().strftime("%Y-%m-%d"),
            cwd=str(Path.cwd().resolve()),
            git_branch=self._git_branch,
            extra_rules=(build_agentic_system_hint(live_lookup=self.live_lookup_enabled),),
        )
        return build_dynamic_system_prompt(
            {**self.persona, **self.persona_override},
            context=prompt_context,
        )

    def _make_system_prompt(self, coding_mode=False, file_mode=False):
        project_context = self._project_context_block()
        active_files: list[tuple[str, str]] = []
        for doc in _context_cache.recent_documents(limit=5):
            if doc.kind not in {"file", "project-file"}:
                continue
            active_files.append((doc.label, doc.content[:1800]))
        todos = tuple(getattr(self, "agent_todos", []) or [])
        prompt_context = PromptContext(
            date=datetime.now().strftime("%Y-%m-%d"),
            cwd=str(Path.cwd().resolve()),
            git_branch=str(getattr(self.workspace_profile, "git_branch", "") or self._git_branch or ""),
            project_context=project_context,
            git_status=summarize_git_state(Path.cwd()),
            memory_block=build_memory_block(),
            active_files=tuple(active_files),
            recent_tool_results=tuple(str(item) for item in getattr(self, "tool_logs", [])[-5:]),
            todos=todos,
            extra_rules=(build_agentic_system_hint(live_lookup=self.live_lookup_enabled), self._project_memory_block()),
        )
        return build_dynamic_system_prompt(
            {**self.persona, **self.persona_override},
            context=prompt_context,
            coding_mode=coding_mode,
            file_mode=file_mode,
        )

    def _system_prompt_for_turn(self, *, user_input: str, coding_mode: bool = False, file_mode: bool = False) -> str:
        early_turn = int(getattr(self, "turns", 0) or 0) == 0
        lightweight_ok = (
            early_turn
            and not getattr(self, "_startup_warmed", False)
            and not coding_mode
            and not file_mode
            and not str(user_input or "").lstrip().startswith("/")
        )
        if lightweight_ok:
            return self.system_prompt or self._bootstrap_system_prompt()
        return self._make_system_prompt(coding_mode=coding_mode, file_mode=file_mode)

    def _warm_start_background(self) -> None:
        if self._startup_warm_thread and self._startup_warm_thread.is_alive():
            return

        def _go() -> None:
            try:
                self.workspace_profile = inspect_workspace(Path.cwd())
                self._git_branch = getattr(self.workspace_profile, "git_branch", "") or self._git_branch
            except Exception:
                log.exception("Failed to inspect workspace during warm startup")
            try:
                self.system_prompt = self._make_system_prompt()
            except Exception:
                log.exception("Failed to rebuild system prompt during warm startup")
            finally:
                self._startup_warmed = True
                self.redraw()
            try:
                self._loaded_plugins = load_plugins()
            except Exception:
                log.exception("Failed to load plugins during warm startup")
            try:
                for record in list_mode_conversations(limit=40):
                    _index_mode_record(record)
            except Exception:
                log.exception("Failed to index saved mode conversations during warm startup")

        self._startup_warm_thread = threading.Thread(target=_go, daemon=True)
        self._startup_warm_thread.start()

    def _sys(self, text): self.store.add(Msg("system", text))
    def _err(self, text): self.store.add(Msg("error", str(text)))

    def filesystem_prompt_hint(self) -> tuple[str, str]:
        return controller_filesystem_prompt_hint(self)

    def _cancel_pending_file_plan(self) -> bool:
        return controller_cancel_pending_file_plan(self)

    def _cancel_transient_state(self) -> bool:
        return controller_cancel_transient_state(self)

    def _record_filesystem_action(self, summary: str, undo_record: dict | None = None) -> None:
        controller_record_filesystem_action(self, summary, undo_record)

    def _undo_last_filesystem_action(self) -> bool:
        return controller_undo_last_filesystem_action(self, undo_operation)

    def _notify(self, msg, duration=2.5):
        with self._state_lock: self.notification = msg
        self.redraw()
        if self._notif_timer: self._notif_timer.cancel()
        def _clear():
            with self._state_lock: self.notification = ""
            self.redraw()
        t = threading.Timer(duration, _clear); t.daemon = True; t.start()
        self._notif_timer = t

    def request_stop(self) -> None:
        if not self.busy:
            return
        if not self._stop_requested.is_set():
            self._stop_requested.set()
            self._notify("Stopping…", duration=1.2)

    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    def _refresh_command_palette(self) -> None:
        query = str(getattr(self, "command_palette_query", "") or "").strip().lower()
        seen_values: set[str] = set()
        prompt_hits: list[dict[str, str]] = []
        for entry in reversed(self.history.entries[-12:]):
            if query and query not in entry.lower():
                continue
            value = entry.strip()
            if not value or value in seen_values:
                continue
            prompt_hits.append(
                {
                    "kind": "prompt",
                    "label": value[:18],
                    "desc": value[:56],
                    "value": value,
                    "example": value,
                }
            )
            seen_values.add(value)
            if len(prompt_hits) >= 4:
                break

        command_hits: list[dict[str, str]] = []
        command_limit = max(4, 12 - len(prompt_hits))
        for cmd, desc, _category, example in registry.get_hits(query):
            value = cmd
            if value in seen_values:
                continue
            command_hits.append(
                {
                    "kind": "command",
                    "label": cmd,
                    "desc": desc,
                    "value": value,
                    "example": example,
                }
            )
            seen_values.add(value)
            if len(command_hits) >= command_limit:
                break

        hits = [*command_hits, *prompt_hits][:12]

        self.command_palette_hits = hits[:12]
        if self.command_palette_hits:
            self.command_palette_sel = max(0, min(self.command_palette_sel, len(self.command_palette_hits) - 1))
        else:
            self.command_palette_sel = 0

    def _toggle_command_palette(self) -> None:
        self.command_palette_visible = not bool(getattr(self, "command_palette_visible", False))
        if self.command_palette_visible:
            self.command_palette_query = ""
            self.command_palette_sel = 0
            self._refresh_command_palette()
        else:
            self.command_palette_query = ""
            self.command_palette_hits = []
            self.command_palette_sel = 0
        self.redraw()

    def _submit_prompt_text(self, text: str) -> None:
        clean = str(text or "").strip()
        if self._pending_file_plan is not None and not self.busy and not clean:
            self._consume_pending_file_plan("")
            return
        if not clean or self.busy:
            return
        if self._consume_pending_file_plan(clean):
            return
        self.history.append(clean)
        if clean.startswith("/"):
            parts = clean.split(None, 1)
            self._execute_command(parts[0].lower(), parts[1] if len(parts) > 1 else "")
            return
        if self._active_task and not self._active_task.done():
            self._err("Still busy — wait for the current reply.")
            return
        self._active_task = self._task_executor.submit(self._run_message, clean)

    def _run_command_palette_selection(self) -> None:
        if not self.command_palette_hits:
            return
        item = self.command_palette_hits[self.command_palette_sel]
        value = str(item.get("value") or "").strip()
        kind = str(item.get("kind") or "command")
        self.command_palette_visible = False
        self.command_palette_query = ""
        self.command_palette_hits = []
        self.command_palette_sel = 0
        if not value:
            self.redraw()
            return
        if kind == "command":
            example = str(item.get("example") or "")
            if "<" in example or "[" in example:
                self.buf = f"{value} "
                self.cur_pos = len(self.buf)
                self.redraw()
                return
            self._submit_prompt_text(value)
            return
        self._submit_prompt_text(value)

    def _set_agent_todos(self, todos: list[dict[str, str]]) -> None:
        self.agent_todos = list(todos)
        if self.todo_pane_visible:
            self._refresh_todo_pane()

    def _refresh_todo_pane(self) -> None:
        if not self.todo_pane_visible:
            return
        lines = ["No active TODOs."]
        if self.agent_todos:
            icon_map = {
                "pending": "○",
                "in progress": "●",
                "in_progress": "●",
                "done": "✓",
                "failed": "✗",
            }
            lines = []
            for item in self.agent_todos:
                status = str(item.get("status") or "pending").lower()
                icon = icon_map.get(status, "○")
                priority = str(item.get("priority") or "medium")
                lines.append(f"{icon} {item.get('task', '')} [{priority}]")
        self.set_pane(
            title="todo",
            subtitle=WORKBENCH_TITLE,
            lines=lines,
            footer="Esc close  ·  Ctrl+T hide",
            close_on_escape=True,
        )

    def _toggle_todo_pane(self) -> None:
        self.todo_pane_visible = not bool(getattr(self, "todo_pane_visible", False))
        if self.todo_pane_visible:
            self._refresh_todo_pane()
        elif getattr(self, "pane_active", False) and getattr(getattr(self, "pane", None), "title", "") == "todo":
            self.clear_pane()

    def _tool_event(self, event: ToolEvent) -> None:
        payload = dict(event.input_data or {})
        summary_target = str(
            payload.get("path")
            or payload.get("command")
            or payload.get("pattern")
            or payload.get("message")
            or ""
        ).strip()
        label = f"{event.name}  {summary_target[:42]}".strip()
        row_key = f"{event.name}:{summary_target}"
        if event.status == "running":
            row_index = self.store.add(Msg("tool", "", label=label, meta={"status": "running"}))
            self.tool_row_index[row_key] = row_index
            self.tool_logs.append(f"{event.name}: running {summary_target}".strip())
        else:
            status = "✓" if event.ok else "✗"
            text = f"{status} {event.duration_ms}ms"
            row_index = self.tool_row_index.pop(row_key, None)
            meta = {
                "status": event.status,
                "ok": event.ok,
                "duration_ms": event.duration_ms,
                "result": event.result,
            }
            if row_index is not None:
                self.store.update(row_index, role="tool", text=text, label=label, meta=meta)
            else:
                self.store.add(Msg("tool", text, label=label, meta=meta))
            self.tool_logs.append(f"{event.name}: {status} {summary_target} {text}".strip())
            self.tool_logs = self.tool_logs[-20:]
        self.redraw()

    def _shell_output(self, chunk: str) -> None:
        text = chunk[:160]
        self.shell_logs.append(text)
        self.shell_logs = self.shell_logs[-120:]
        if getattr(self, "pane_active", False) and getattr(getattr(self, "pane", None), "title", "") == "workbench jobs":
            if self.pane.lines is None:
                self.pane.lines = []
            self.pane.lines.append(text)
            self.pane.lines = self.pane.lines[-120:]
            self.pane_lines_output = self.pane.content()
            self.redraw()

    def _request_tool_permission(self, request: PermissionRequest) -> PermissionDecision:
        prompt = PermissionPromptState(
            active=True,
            tool_name=request.tool_name,
            display=request.display,
            rule_hint=request.value,
            selected=0,
        )
        event = threading.Event()
        self.permission_prompt = prompt
        self.permission_prompt_active = True
        self.permission_prompt_event = {"event": event, "decision": None, "request": request}
        self.redraw()
        event.wait()
        payload = self.permission_prompt_event or {}
        decision = payload.get("decision")
        self.permission_prompt = PermissionPromptState()
        self.permission_prompt_active = False
        self.permission_prompt_event = None
        self.redraw()
        return decision or PermissionDecision(False, "requires approval")

    def _approve_pending_permission(self, mode: str) -> None:
        payload = self.permission_prompt_event or {}
        request = payload.get("request")
        event = payload.get("event")
        if request is None or event is None:
            return
        if mode == "allow_always":
            add_tool_permission_rule("allow", f"{request.tool_name}:{request.value}", base_dir=Path.cwd())
            decision = PermissionDecision(True, "allowed by user", matched_rule=f"{request.tool_name}:{request.value}")
        elif mode == "allow_once":
            decision = PermissionDecision(True, "allowed by user")
        else:
            decision = PermissionDecision(False, "denied by user")
        payload["decision"] = decision
        event.set()

    def _resolve_tool_permission(self, request: PermissionRequest) -> PermissionDecision:
        if request.tool_name in {"web_search", "weather_lookup", "time_lookup"}:
            return PermissionDecision(True, "allowed read-only live lookup")
        decision = evaluate_tool_permission(
            request.tool_name,
            request.value,
            base_dir=Path.cwd(),
            display=request.display,
        )
        if decision.allowed or decision.reason != "requires approval":
            return decision
        return self._request_tool_permission(request)

    def _refresh_browser(self):
        controller_refresh_browser(self)

    def _browser_select(self):
        controller_browser_select(self)

    def _capture(self, fn, *args, **kwargs):
        buf = io.StringIO(); result = None
        try:
            with redirect_stdout(buf): result = fn(*args, **kwargs)
        except Exception as e: self._err(str(e))
        out = buf.getvalue().strip()
        if out and _strip_ansi(out): self._sys(_strip_ansi(out))
        return result

    def set_busy(self, status):
        with self._state_lock:
            self.busy = status
            if status:
                self._stop_requested.clear()
        self.redraw()

    def redraw(self): self.renderer.draw()

    def _chat_stream_with_stop(self, **kwargs):
        try:
            return chat_stream(**kwargs, should_stop=self.stop_requested)
        except TypeError as exc:
            if "should_stop" not in str(exc):
                raise
            return chat_stream(**kwargs)

    # ── Inference / Generators  ─────────────────────────────────────────────
    def _tui_stream(self, messages, model, label="lumi"):
        idx = self.store.add(Msg("streaming", "", label))
        if model == "council": return self._run_council_stream(idx, messages)

        chunks: list[str] = []
        effort = normalize_reasoning_effort(getattr(self, "reasoning_effort", "medium"))
        tuned_messages = apply_reasoning_effort(messages, effort)
        try:
            provider = get_provider()
        except Exception:
            provider = ""
        request_options = provider_effort_options(provider, effort)
        tuned_max_tokens = int(request_options.get("max_tokens", 2048))
        tuned_temperature = float(request_options.get("temperature", 0.45))
        last_user = next((str(item.get("content") or "") for item in reversed(tuned_messages) if str(item.get("role")) == "user"), "")
        tool_loop_markers = (
            " edit ", " fix ", " refactor ", " grep ", " diff ", " commit ", " tests", " pytest",
            " shell", " directory", " folder", " file ", ".py", ".ts", ".js", ".rs", ".go",
            " git ", " run ", " todo", "/build", "/fixci",
        )
        normalized_prompt = f" {last_user.lower().strip()} "
        use_tool_loop = bool(
            provider
            and model != "council"
            and (
                any(token in normalized_prompt for token in tool_loop_markers)
                or (self.live_lookup_enabled and needs_live_lookup(last_user))
            )
        )
        try:
            if use_tool_loop:
                context = ToolContext(
                    base_dir=Path.cwd(),
                    permission_resolver=lambda request: self._resolve_tool_permission(request),
                    event_sink=self._tool_event,
                    todo_getter=lambda: list(getattr(self, "agent_todos", [])),
                    todo_setter=self._set_agent_todos,
                    shell_output_sink=self._shell_output,
                    stop_checker=self.stop_requested,
                )
                result = run_tool_loop_sync(
                    self.client,
                    provider,
                    model,
                    tuned_messages,
                    context,
                    effort_options=request_options,
                )
                self.store.set_text(idx, result.text)
                self.store.finalize(idx)
                _session_telemetry.record_response(result.text, actual_tokens=result.output_tokens)
                self.session_cost.record(
                    provider=provider,
                    model=model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                if self.agent_todos and self.todo_pane_visible:
                    self._refresh_todo_pane()
                return result.text

            def _on_delta(delta: str) -> None:
                if self.stop_requested():
                    raise StreamCancelledError("Stopped by user.")
                chunks.append(delta)
                self.store.append(idx, delta)
                self.redraw()

            full = self._chat_stream_with_stop(
                client=self.client,
                messages=tuned_messages,
                model=model,
                max_tokens=tuned_max_tokens,
                temperature=tuned_temperature,
                on_delta=_on_delta,
                on_status=lambda status: self._notify(status, duration=2.0),
            )
        except StreamCancelledError:
            full = "".join(chunks).strip()
            if full:
                self.store.set_text(idx, full)
                self.store.finalize(idx)
            else:
                self.store.update(idx, role="system", text="Stopped.")
            self._notify("Stopped", duration=1.2)
            return full
        except Exception as ex: return self._handle_stream_error(idx, ex, messages)
        self.store.finalize(idx)
        if not full:
            full = "".join(chunks)
        _session_telemetry.record_response(full)
        self.session_cost.record(
            provider=provider,
            model=model,
            input_tokens=estimate_message_tokens(tuned_messages),
            output_tokens=estimate_tokens(full),
        )
        return full

    def _run_council_stream(self, idx, messages):
        avail = _get_available_agents()
        user_q = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        lead_id = LEAD_AGENTS.get(classify_task(user_q), "gemini")

        with self._state_lock: self.agents = [AgentState(a["id"], a["name"], a["id"] == lead_id) for a in avail]

        def _cb(aid, ok, conf, t):
            for ag in self.agents:
                if ag.aid == aid: ag.done(ok, conf, t)
            self.redraw()

        def _spin():
            frame = 0
            while self.busy:
                for ag in self.agents: ag.frame = frame
                self.redraw(); frame = (frame + 1) % len(SPINNER_FRAMES); time.sleep(0.08)

        threading.Thread(target=_spin, daemon=True).start()

        full = refined = ""
        try:
            for chunk in council_ask(messages, user_q, stream=True, debate=True, refine=True, silent=True, agent_callback=_cb):
                if chunk.startswith("\n\n__STATS__\n"): continue
                if chunk.startswith("\n\n__REFINED__\n\n"): refined = chunk[len("\n\n__REFINED__\n\n"):]; continue
                full += chunk; self.store.append(idx, chunk); self.redraw()
        except Exception as ex:
            log.exception("Council stream failed")
            self.store.set_text(idx, f"⚠  {ex}"); self.store.finalize(idx); return f"⚠  {ex}"
        final = refined or full
        if refined: self.store.set_text(idx, final)
        self.store.finalize(idx)
        _session_telemetry.record_response(final)
        return final

    def _handle_stream_error(self, idx, ex, messages):
        msg = str(ex)
        if any(x in msg for x in ("429", "RESOURCE_EXHAUSTED", "quota", "limit: 0")):
            remaining = [p for p in get_available_providers() if p != get_provider()]
            if remaining:
                self._sys(f"Quota hit — switching to {remaining[0]}")
                try:
                    set_provider(remaining[0]); self.client = get_client(); self.current_model = pick_startup_model(remaining[0], get_models(remaining[0]))
                    self.store.set_text(idx, "")
                    chunks: list[str] = []
                    effort = normalize_reasoning_effort(getattr(self, "reasoning_effort", "medium"))
                    tuned_messages = apply_reasoning_effort(messages, effort)
                    tuned_max_tokens, tuned_temperature = tune_inference_request(2048, 0.45, effort)
                    def _on_delta(delta: str) -> None:
                        if self.stop_requested():
                            raise StreamCancelledError("Stopped by user.")
                        chunks.append(delta)
                        self.store.append(idx, delta)
                        self.redraw()
                    full = self._chat_stream_with_stop(
                        client=self.client,
                        messages=tuned_messages,
                        model=self.current_model,
                        max_tokens=tuned_max_tokens,
                        temperature=tuned_temperature,
                        on_delta=_on_delta,
                        on_status=lambda status: self._notify(status, duration=2.0),
                    )
                    if not full:
                        full = "".join(chunks)
                    self.store.finalize(idx); return full
                except StreamCancelledError:
                    full = "".join(chunks).strip()
                    if full:
                        self.store.set_text(idx, full)
                        self.store.finalize(idx)
                    else:
                        self.store.update(idx, role="system", text="Stopped.")
                    self._notify("Stopped", duration=1.2)
                    return full
                except Exception as ex2: self.store.set_text(idx, f"⚠  {ex2}")
            else: self.store.set_text(idx, f"⚠  {ex}")
        else: self.store.set_text(idx, f"⚠  {ex}")
        self.store.finalize(idx); return f"⚠  {ex}"

    def _silent_call(self, prompt, model, max_tokens=1024):
        try:
            provider = get_provider()
            routed = route_model(model, get_models(provider), "summary", provider=provider)
            messages = optimize_messages(
                [{"role": "system", "content": "You are Lumi. Return only the requested result."}, {"role": "user", "content": prompt}],
                routed,
                mode="summary",
                provider=provider,
                context_cache=_context_cache,
                telemetry=_session_telemetry,
            )
            effort = normalize_reasoning_effort(getattr(self, "reasoning_effort", "medium"))
            tuned_messages = apply_reasoning_effort(messages, effort)
            request_options = provider_effort_options(provider, effort, max_tokens=max_tokens, temperature=0.3)
            tuned_max_tokens = int(request_options.pop("max_tokens"))
            tuned_temperature = float(request_options.pop("temperature"))
            reply = self.client.chat.completions.create(
                model=routed,
                messages=tuned_messages,
                max_tokens=tuned_max_tokens,
                temperature=tuned_temperature,
                stream=False,
                **request_options,
            )
            usage = getattr(reply, "usage", None)
            completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
            reply = reply.choices[0].message.content.strip()
            _session_telemetry.record_response(reply, actual_tokens=completion_tokens)
            self.session_cost.record(
                provider=provider,
                model=routed,
                input_tokens=estimate_message_tokens(tuned_messages),
                output_tokens=int(completion_tokens or estimate_tokens(reply)),
            )
            return reply
        except Exception:
            log.exception("Silent call failed")
            return ""

    def _guardian_loop(self):
        """Background code-quality watcher. Off by default; enable with /guardian on.
        Uses a 5-minute interval and only runs when guardian_enabled is set."""
        INTERVAL = 300  # 5 minutes — not every 30 seconds
        while getattr(self, "_running", True):
            # Sleep in short chunks so we respond quickly to shutdown
            for _ in range(INTERVAL):
                if not getattr(self, "_running", True):
                    return
                time.sleep(1)

            if not getattr(self, "guardian_enabled", False):
                continue  # opt-in only

            msgs = []
            try:
                if shutil.which("ruff"):
                    r = subprocess.run(
                        ["ruff", "check", ".", "--output-format=concise"],
                        capture_output=True, text=True, timeout=30
                    )
                    if r.returncode != 0:
                        msgs.append("ruff errors")
                if shutil.which("pytest"):
                    r = subprocess.run(
                        ["pytest", "-q", "--tb=no", "-x"],
                        capture_output=True, text=True, timeout=60
                    )
                    if r.returncode != 0:
                        msgs.append("pytest failing")
            except Exception:
                log.exception("Guardian check failed")

            if msgs:
                self._notify(f"⚠ Guardian: {', '.join(msgs)}")

    # ── Application Main loop Thread setup / cleanup & Event bindings ───────
    def _do_handoff(self, entry: dict):
        """
        Execute an external AI CLI synchronously on the main thread and
        capture the session under conversations/<cli>/ when possible.
        """
        binary = str(entry["binary"])
        cli_key = str(entry.get("key", binary))
        name = str(entry["name"])
        binary_path = str(entry.get("binary_path") or shutil.which(binary) or binary)
        binary_version = str(entry.get("binary_version") or "")
        launch_cmd = list(entry.get("launch_cmd") or [binary_path])
        fd = sys.stdin.fileno()
        capture_path: Path | None = None
        transcript = ""
        captured = False
        started_at_dt = datetime.now()
        started_at = started_at_dt.isoformat(timespec="seconds")
        workspace_profile = inspect_workspace(Path.cwd())
        git_branch = workspace_profile.git_branch or ""

        # ── 1. Tear down Lumi's terminal state ────────────────────────────────
        sys.stdout.write(_paste_off() + _alt_scroll_off() + _show_cur() + _alt_off() + _reset())
        sys.stdout.flush()
        if self.original_termios:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, self.original_termios)
            except Exception:
                pass

        # Brief banner so the user knows what happened
        print(
            f"\n\033[38;2;187;154;247m◆ Entering {name}\033[0m  — exit normally to return to Lumi\n",
            flush=True,
        )

        # ── 2. Run the CLI, capturing a typescript when possible ─────────────
        exit_code = 1
        try:
            script_bin = shutil.which("script")
            if script_bin:
                with tempfile.NamedTemporaryFile(
                    prefix=f"lumi_{cli_key}_",
                    suffix=".typescript",
                    delete=False,
                ) as handle:
                    capture_path = Path(handle.name)
                result = subprocess.run(
                    [script_bin, "-qefc", shlex.join(launch_cmd), str(capture_path)],
                    env={**os.environ},
                    cwd=os.getcwd(),
                )
            else:
                result = subprocess.run(launch_cmd, env={**os.environ}, cwd=os.getcwd())
            exit_code = result.returncode
        except FileNotFoundError:
            print(f"\033[31m✗ {binary} not found in PATH\033[0m", flush=True)
        except KeyboardInterrupt:
            pass  # user Ctrl-C'd out of the CLI — that's fine
        finally:
            if capture_path and capture_path.exists():
                try:
                    transcript = sanitize_handoff_transcript(capture_path.read_text(encoding="utf-8", errors="replace"))
                    captured = bool(transcript.strip())
                except Exception:
                    log.exception("Failed to read captured handoff transcript")
                try:
                    capture_path.unlink(missing_ok=True)
                except Exception:
                    log.debug("Failed to clean temporary handoff capture")
        ended_at_dt = datetime.now()
        ended_at = ended_at_dt.isoformat(timespec="seconds")
        duration_seconds = max(0.0, (ended_at_dt - started_at_dt).total_seconds())

        # ── 3. Restore Lumi's terminal state ─────────────────────────────────
        print(
            f"\n\033[38;2;86;95;137m◆ Returned from {name}. Restoring Lumi…\033[0m\n",
            flush=True,
        )
        time.sleep(0.05)

        try:
            tty.setraw(fd)
        except Exception:
            pass

        # Re-enter alternate screen, hide cursor, full repaint
        sys.stdout.write(_alt_on() + _alt_scroll_on() + _paste_on() + _hide_cur() + "\033[2J")
        sys.stdout.flush()
        self.redraw()

        user_msg = f"(Returned from {name}.)"
        self.store.add(Msg("user", user_msg))
        self.memory.add("user", user_msg)

        def _welcome():
            summary_data: dict[str, object] = {}
            saved_path: Path | None = None
            record: dict[str, object] | None = None
            if transcript:
                summary_prompt = (
                    f"You are summarizing a {name} terminal session for Lumi.\n"
                    "Return strict JSON only with keys:\n"
                    '{"tldr":"", "files":[], "commands":[], "decisions":[], "next_steps":[]}\n'
                    "Rules:\n"
                    "- keep `tldr` to one or two sentences\n"
                    "- only include files actually mentioned\n"
                    "- keep each list short and high-signal\n"
                    "- if unsure, omit instead of guessing\n\n"
                    f"Transcript:\n{transcript[-20000:]}"
                )
                try:
                    summary_raw = self._silent_call(summary_prompt, self.current_model, max_tokens=360).strip()
                    summary_data = parse_mode_summary_response(summary_raw, name, transcript)
                except Exception:
                    log.exception("External CLI summary generation failed")
            if not summary_data:
                fallback_seed = transcript or f"{name} exited with code {exit_code}. No transcript was captured."
                summary_data = fallback_mode_summary_data(name, fallback_seed)
                if not transcript:
                    exit_note = f" Exit code: {exit_code}." if exit_code != 0 else ""
                    summary_data["tldr"] = (
                        f"Returned from {name}.{exit_note} No transcript was captured."
                    ).strip()
            try:
                saved_path = save_mode_conversation(
                    cli_name=cli_key,
                    display_name=name,
                    transcript=transcript,
                    summary=summary_data,
                    exit_code=exit_code,
                    cwd=os.getcwd(),
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration_seconds,
                    git_branch=git_branch,
                    binary=binary,
                    binary_path=binary_path,
                    binary_version=binary_version,
                    captured=captured,
                )
            except Exception:
                log.exception("Failed to save external CLI conversation")

            record = {
                "cli": cli_key,
                "name": name,
                "cwd": os.getcwd(),
                "git_branch": git_branch,
                "binary": binary,
                "binary_path": binary_path,
                "binary_version": binary_version,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_seconds": round(duration_seconds, 2),
                "exit_code": exit_code,
                "captured": captured,
                "summary": summary_data,
                "transcript": transcript,
            }
            if saved_path:
                record["path"] = str(saved_path)
                record["date"] = ended_at_dt.strftime("%Y-%m-%d %H:%M")
                self.store.add(Msg("system", f"Saved {name} conversation → {saved_path}"))
            else:
                record["date"] = ended_at_dt.strftime("%Y-%m-%d %H:%M")

            try:
                _index_mode_record(record)
            except Exception:
                log.exception("Failed to index external CLI conversation in context cache")

            system_note = _mode_memory_note(record)
            self.memory.add("system", system_note)
            if saved_path:
                self.set_review_card(**build_mode_review_card(record))
            raw = format_mode_tldr(summary_data, name)
            self.store.add(Msg("assistant", raw))
            self.memory.add("assistant", raw)
            self.last_reply = raw
            self.turns += 1
            self.set_busy(False)
            self.redraw()

        threading.Thread(target=_welcome, daemon=True).start()

    def run(self):
        self.persona = load_persona(); self.persona_override = get_persona_override()
        self.system_prompt = self._bootstrap_system_prompt()
        self.name = self.persona_override.get("name") or self.persona.get("name", "Lumi")

        try:
            p = get_provider(); self.current_model = pick_startup_model(p, get_models(p)); self.client = get_client()
            self.little_notes.record_model(p, self.current_model)
        except Exception:
            log.exception("Failed to load provider/model")
            self.current_model = "unknown"; self.client = None

        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        self.original_termios = old
        def _cleanup(*_):
            try: termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                log.debug("Cleanup termios failed")
            sys.stdout.write(_paste_off() + _alt_scroll_off() + _show_cur() + _alt_off()); sys.stdout.flush()

        try: signal.signal(signal.SIGWINCH, lambda *_: self.redraw())
        except Exception:
            log.debug("SIGWINCH not supported")
        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))

        try:
            sys.stdout.write(_alt_on() + _alt_scroll_on() + _paste_on()); sys.stdout.flush(); tty.setraw(fd)
            with self._state_lock: self._running = True
            threading.Thread(target=self._guardian_loop, daemon=True).start()
            self.redraw()
            self._warm_start_background()
            while self._running:
                # ── Consume a pending /mode handoff on the main thread ────────
                # Must happen here — main thread owns stdin and termios.
                if self._pending_handoff is not None:
                    entry, self._pending_handoff = self._pending_handoff, None
                    self._do_handoff(entry)
                    continue
                key = _read_key()
                self._handle_key(key)
                self.redraw()
        except KeyboardInterrupt: pass
        finally:
            try:
                save_repo_autosave(self.memory.get(), base_dir=Path.cwd())
                session_save(self.memory.get())
            except Exception:
                log.exception("Session save failed")
            try:
                self._task_executor.shutdown(wait=False)
            except Exception:
                pass
            _cleanup()
            log.info("Lumi exited cleanly")

    def _handle_key(self, key):
        controller_handle_key(
            self,
            key,
            term_size_fn=_term_size,
            registry=registry,
            suggest_paths_fn=suggest_paths,
        )

    def _update_slash(self):
        controller_update_slash(self, registry=registry, suggest_paths_fn=suggest_paths)

    def _load_history(self) -> list:
        return self.history.entries

    def _save_history_entry(self, text: str):
        try:
            self.history.append(text)
        except Exception:
            log.exception("Failed to save history entry")

    def _hist_nav(self, direction):
        controller_hist_nav(self, direction, registry=registry, suggest_paths_fn=suggest_paths)

    def _apply_path_suggestion(self, suggestion: str) -> None:
        controller_apply_path_suggestion(
            self,
            suggestion,
            registry=registry,
            suggest_paths_fn=suggest_paths,
        )

    # ── Master LLM Task Query Send Operation Routing  ───────────────────────
    def _autosave_history(self, history):
        save_repo_autosave(history, base_dir=Path.cwd())
        if self.turns and self.turns % 5 == 0:
            session_save(history)

    def _run_message(self, user_input):
        controller_run_message(
            self,
            user_input,
            is_complex_coding_task_fn=is_complex_coding_task,
            is_coding_task_fn=is_coding_task,
            is_file_generation_task_fn=is_file_generation_task,
            needs_plan_first_fn=needs_plan_first,
            is_filesystem_request_fn=is_filesystem_request,
            detect_emotion_fn=detect_emotion,
            emotion_hint_fn=emotion_hint,
            should_search_fn=should_search,
            search_fn=search,
            plugin_dispatch_fn=plugin_dispatch,
            get_provider_fn=get_provider,
            get_models_fn=get_models,
            session_save_fn=self._autosave_history,
            auto_extract_facts_fn=auto_extract_facts,
            build_messages_fn=build_messages,
            log=log,
        )

    def _run_file_agent(self, user_input, sp):
        controller_run_file_agent(
            self,
            user_input,
            generate_delete_plan_fn=generate_delete_plan,
            generate_transfer_plan_fn=generate_transfer_plan,
            generate_file_plan_fn=generate_file_plan,
            is_delete_request_fn=is_delete_request,
            is_move_request_fn=is_move_request,
            is_copy_request_fn=is_copy_request,
            is_rename_request_fn=is_rename_request,
            is_create_request_fn=is_create_request,
            get_provider_fn=get_provider,
            get_models_fn=get_models,
        )

    def _queue_filesystem_plan(self, plan: dict, *, base_dir: str | Path, label: str) -> bool:
        return controller_queue_filesystem_plan(
            self,
            plan,
            base_dir=base_dir,
            label=label,
            inspect_operation_plan_fn=inspect_operation_plan,
        )

    def _consume_pending_file_plan(self, text: str) -> bool:
        return controller_consume_pending_file_plan(
            self,
            text,
            execute_operation_plan_fn=execute_operation_plan,
        )

    def _do_retry(self):
        controller_do_retry(self, build_messages_fn=build_messages)

    def _open_picker(self):
        controller_open_picker(
            self,
            get_available_providers_fn=get_available_providers,
            get_provider_fn=get_provider,
            get_models_fn=get_models,
            provider_names=PROV_NAME,
            log=log,
        )

    def _confirm_picker(self):
        controller_confirm_picker(
            self,
            get_available_providers_fn=get_available_providers,
            set_provider_fn=set_provider,
            get_client_fn=get_client,
            get_models_fn=get_models,
            get_provider_fn=get_provider,
            provider_names=PROV_NAME,
            log=log,
        )

    def _refresh_picker(self):
        controller_refresh_picker(
            self,
            get_available_providers_fn=get_available_providers,
            get_provider_fn=get_provider,
            get_models_fn=get_models,
            provider_names=PROV_NAME,
            log=log,
        )

    def _execute_command(self, cmd, arg):
        controller_execute_command(
            self,
            cmd,
            arg,
            registry=registry,
            plugin_dispatch_fn=plugin_dispatch,
            build_messages_fn=build_messages,
            session_save_fn=self._autosave_history,
            auto_extract_facts_fn=auto_extract_facts,
            log=log,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Commands / Utilities Massive Implementation Restoration List
# ══════════════════════════════════════════════════════════════════════════════
def bg_task(func):
    """Decorator that runs a command in the TUI's thread pool instead of spawning bare threads."""
    def wrapper(tui: LumiTUI, arg: str):
        tui._task_executor.submit(func, tui, arg)
    return wrapper

@registry.register("/clear", "Clear conversation")
def cmd_clear(tui: LumiTUI, arg: str):
    tui.memory.clear(); tui.store.clear(); tui.agents.clear()
    tui.last_msg = tui.last_reply = tui.prev_reply = None
    tui.turns = 0
    tui.set_busy(False)
    try:
        save_repo_autosave([], base_dir=Path.cwd())
    except Exception:
        log.exception("Repo autosave clear failed")
    # Show a subtle toast but keep history visually empty so the splash header returns
    tui._notify("Chat cleared.")

@registry.register("/browse", "Visual file tree explorer - navigate and inject files")
def cmd_browse(tui: LumiTUI, arg: str):
    tui.browser_cwd = os.path.abspath(arg.strip()) if arg.strip() else os.getcwd()
    tui.browser_sel = 0
    tui._refresh_browser()
    tui.browser_visible = True
    tui.redraw()

@registry.register("/fs", "Filesystem tools: ls/cat/write/rm/mv/mkdir")
def cmd_fs(tui: LumiTUI, arg: str):
    parts = arg.strip().split()
    workspace = Path.cwd().resolve()
    if not parts or parts[0] in {"help", "?"}:
        usage = [
            "Filesystem tools:",
            "  /fs ls [path]              - list directory contents",
            "  /fs cat <file>             - show file contents (truncated)",
            "  /fs mkdir <dir>            - queue directory creation with preview",
            "  /fs mv <src> <dst>         - queue move/rename with preview",
            "  /fs rm <path>              - queue file or folder removal with preview",
            "  /fs write <file> [text]    - queue overwrite with diff preview",
            "  /fs append <file> [text]   - queue append as a previewed overwrite",
        ]
        tui._sys("\n".join(usage))
        return

    sub = parts[0].lower()
    rest = parts[1:]

    def _path(p):
        return Path(p).expanduser().resolve()

    if sub == "ls":
        target = _path(rest[0]) if rest else Path(".").resolve()
        if not target.exists():
            tui._err(f"Not found: {target}")
            return
        if target.is_file():
            size = target.stat().st_size
            tui._sys(f"{target}  ({size} bytes)")
            return
        try:
            entries = sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception as e:
            tui._err(str(e))
            return
        lines = [f"Directory: {target}"]
        for e in entries[:200]:
            icon = "[D]" if e.is_dir() else "[F]"
            suffix = "/" if e.is_dir() else ""
            lines.append(f"  {icon} {e.name}{suffix}")
        if len(entries) > 200:
            lines.append(f"  … {len(entries) - 200} more")
        tui._sys("\n".join(lines))
        return

    if sub == "cat":
        if not rest:
            tui._err("Usage: /fs cat <file>")
            return
        target = _path(rest[0])
        if not target.is_file():
            tui._err(f"Not a file: {target}")
            return
        try:
            text = target.read_text(errors="replace")
        except Exception as e:
            tui._err(str(e))
            return
        max_len = 4000
        body = text if len(text) <= max_len else text[:max_len] + "\n…(truncated)…"
        tui._sys(f"{target}:\n```text\n{body}\n```")
        return

    if sub == "mkdir":
        if not rest:
            tui._err("Usage: /fs mkdir <dir>")
            return
        plan = {"operation": "create", "root": rest[0], "files": []}
        tui._queue_filesystem_plan(plan, base_dir=workspace, label="Filesystem plan")
        return

    if sub == "mv":
        if len(rest) != 2:
            tui._err("Usage: /fs mv <src> <dst>")
            return
        plan = {
            "operation": "move",
            "items": [{"source": rest[0], "destination": rest[1], "link": "to"}],
        }
        tui._queue_filesystem_plan(plan, base_dir=workspace, label="Transfer plan")
        return

    if sub == "rm":
        if not rest:
            tui._err("Usage: /fs rm <path>")
            return
        target = _path(rest[0])
        kind = "dir" if target.exists() and target.is_dir() else "path"
        plan = {"operation": "delete", "targets": [{"path": rest[0], "kind": kind}]}
        tui._queue_filesystem_plan(plan, base_dir=workspace, label="Removal plan")
        return

    def _code_from_last_reply():
        if not tui.last_reply:
            return None
        blocks = re.findall(r"```[a-zA-Z0-9_+\\-]*\\n(.*?)```", tui.last_reply, re.DOTALL)
        if blocks:
            return blocks[-1].strip()
        return tui.last_reply.strip()

    if sub in {"write", "append"}:
        if not rest:
            tui._err(f"Usage: /fs {sub} <file> [text]")
            return
        target_arg = rest[0]
        target = _path(target_arg)
        if len(rest) >= 2:
            content = " ".join(rest[1:])
        else:
            content = _code_from_last_reply()
            if not content:
                tui._err("No text provided and no last reply to use.")
                return
        if target.exists() and target.is_dir():
            tui._err(f"Not a file: {target}")
            return
        try:
            if sub == "append" and target.exists():
                existing = target.read_text(encoding="utf-8", errors="replace")
                joiner = "\n" if existing and not existing.endswith("\n") else ""
                content = existing + joiner + content
            plan = {
                "operation": "create",
                "root": ".",
                "files": [{"path": target_arg, "content": content}],
            }
            tui._queue_filesystem_plan(plan, base_dir=workspace, label="Filesystem plan")
        except Exception as e:
            tui._err(str(e))
        return

    tui._err("Unknown /fs subcommand. Use /fs help.")

@registry.register("/file", "Load a file into AI context: /file path/to/file")
def cmd_file(tui: LumiTUI, arg: str):
    if not arg.strip():
        tui._sys("Usage: /file <path>  — e.g. /file src/main.py")
        return
    path = Path(arg.strip()).expanduser()
    if not path.exists():
        tui._err(f"File not found: {path}")
        return
    if not path.is_file():
        tui._err(f"Not a file: {path}  (use /browse to explore directories)")
        return
    try:
        content = path.read_text(errors="replace")
        rel = str(path)
        line_count = content.count("\n") + 1
        tui._sys(f"Loaded `{rel}` ({line_count} lines) into context")
        _context_cache.remember_file(rel, content)
        tui.memory.add("user", f"[loaded file: {rel}] Cached for retrieval.")
    except Exception as e:
        tui._err(f"Failed to read {path}: {e}")

@registry.register("/council", "All agents run together")
def cmd_council(tui: LumiTUI, arg: str):
    tui.current_model = "council"
    tui.little_notes.record_model("council", "council")
    tui._sys("⚡ Council mode — all agents in parallel")

@registry.register("/exit", "Quit app")
def cmd_exit(tui: LumiTUI, arg: str):
    with tui._state_lock: tui._running = False

@registry.register("/model", "Switch API provider/model")
def cmd_model(tui: LumiTUI, arg: str): tui._open_picker()

@registry.register("/save", "Save current memory block")
def cmd_save(tui: LumiTUI, arg: str):
    try: p = session_save(tui.memory.get(), arg.strip() if arg else ""); tui._notify(f"Saved → {Path(p).name}" if p else "Saved")
    except Exception as e: tui._err(str(e))

@registry.register("/load", "Load repo autosave or named session", aliases=["/resume"])
def cmd_load(tui: LumiTUI, arg: str):
    try:
        h = load_resume(arg.strip(), base_dir=Path.cwd())
        if h:
            tui.memory.set_history(h)
            tui.turns = len(h) // 2
            save_repo_autosave(h, base_dir=Path.cwd())
            tui._sys(f"Loaded {len(h)} messages")
        else: tui._err("No saved session found.")
    except Exception as e: tui._err(str(e))

@registry.register("/retry", "Retry last prompt")
def cmd_retry(tui: LumiTUI, arg: str):
    if not (tui._active_task and not tui._active_task.done()):
        tui._active_task = tui._task_executor.submit(tui._do_retry)

@registry.register("/more", "Expand upon previous details")
@bg_task
def cmd_more(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("Nothing to expand on yet."); return
    tui.set_busy(True); tui.memory.add("user", "[User wants more detail on the last response.]")
    msgs = build_messages(tui.system_prompt, tui.memory.get()); raw = tui._tui_stream(msgs, tui.current_model)
    tui.memory.replace_last("user", "Tell me more."); tui.memory.add("assistant", raw)
    tui.prev_reply = tui.last_reply; tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/undo", "Undo last filesystem action or pop the latest chat branch")
def cmd_undo(tui: LumiTUI, arg: str):
    mode = arg.strip().lower()
    if mode in {"fs", "file", "files"} or (not mode and tui._last_filesystem_undo):
        try:
            if tui._undo_last_filesystem_action():
                return
        except Exception as exc:
            tui._err(f"Filesystem undo failed: {exc}")
            return
    if tui.memory.remove_last_exchange():
        tui.turns = max(0, tui.turns - 1)
        tui._sys("Last exchange removed from LLM Memory Tree.")
    else: tui._err("Nothing to undo.")

@registry.register("/rewrite", "Alternative generation run")
@bg_task
def cmd_rewrite(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("No block loaded!"); return
    tui.set_busy(True); tui.memory.add("user", "[Rewrite the previous context totally differently.]")
    msgs = build_messages(tui.system_prompt, tui.memory.get()); raw = tui._tui_stream(msgs, tui.current_model)
    tui.memory.replace_last("user", "Rewrite completely differently.")
    tui.memory.add("assistant", raw); tui.prev_reply = tui.last_reply; tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/tl;dr", "One sentence summarize response")
@bg_task
def cmd_tldr(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("Nothing returned yet."); return
    tui.set_busy(True); m = tui.current_model if tui.current_model != "council" else get_models(get_provider())[0]
    s = tui._silent_call(f"Summarize this in exactly ONE minimal sentence (under 16 words): {tui.last_reply}", m, 60)
    if s: tui._sys(f"tl;dr: {s}")
    tui.set_busy(False)

@registry.register("/search", "Internet browser fetching context tools")
@bg_task
def cmd_search(tui: LumiTUI, arg: str):
    if not arg: tui._err("Search needs keywords via CLI space."); return
    lowered = arg.strip().lower()
    if lowered.startswith(("mode ", "mode:")):
        query_text = arg.split(":", 1)[1].strip() if ":" in arg[:5] else arg.split(None, 1)[1].strip()
        cli_name = None
        query_parts = query_text.split()
        if query_parts and query_parts[0].lower() in MODE_CLI_REGISTRY:
            cli_name = query_parts[0].lower()
            query_text = " ".join(query_parts[1:]).strip()
        records = search_mode_conversations(query_text, cli_name, limit=8) if query_text else list_mode_conversations(cli_name, limit=8)
        for record in records:
            _index_mode_record(record)
        if not records:
            tui._sys("No saved mode conversations matched that search.")
            return
        lines = ["Mode session search results", ""]
        for index, record in enumerate(records, 1):
            summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
            lines.append(f" {index}. {record.get('name', record.get('cli', '?'))}")
            lines.append(f"    - {Path(str(record.get('path', ''))).name or 'unsaved'}")
            lines.append(f"    - {str(summary.get('tldr', 'No TL;DR available.'))[:108]}")
        tui._sys("\n".join(lines))
        tui.memory.add(
            "system",
            f"[mode search] Loaded {len(records)} saved external CLI conversations into retrieval context."
        )
        return
    tui.set_busy(True); tui._sys(f"◆  Searching Internet Servers... => [ {arg} ]")
    try:
        results, _ = search_display(arg); lines = [f"Result Headers Found for => {arg}", ""]
        for i, r in enumerate(results, 1): lines.append(f" {i}. {r['title']}\n    - {r['url']}")
        tui._sys("\n".join(lines)); ctx = search(arg, fetch_top=True)
        _context_cache.remember_text(f"search:{arg}", arg, ctx, kind="search")
        tui.memory.add("user", f"[search: {arg}] Cached search results. Analyze the main details and print clear structured insights.")
        raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get(), model=tui.current_model), tui.current_model, f"◆ {tui.name}  [WWW Net Context Load Complete]")
        tui.memory.replace_last("user", f"Search requested info on [ {arg} ]")
        tui.memory.add("assistant", raw); tui.last_reply = raw; tui.turns += 1
    except Exception as e: tui._err(str(e))
    tui.set_busy(False)

@registry.register("/web", "Scrape link exact content DOM")
@bg_task
def cmd_web(tui: LumiTUI, arg: str):
    if not arg: tui._err("/web [link] [Optional Question Analysis Target...]"); return
    tui.set_busy(True); parts = arg.split(None, 1); url = parts[0]; q = parts[1] if len(parts) > 1 else "Brief summarize."
    tui._sys(f"◆  Connecting fetching HTML target payload @ [{url}]"); content = fetch_url(url)
    if content.startswith(("HTTP", "Fetch", "Could not")): tui._err(content); tui.set_busy(False); return
    _context_cache.remember_text(f"web:{url}", url, content, kind="web")
    tui.memory.add("user", f"[web: {url}] Cached fetched page. Instruction: {q}")
    raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get(), model=tui.current_model), tui.current_model, f"◆ {tui.name} [WWW Node parser]")
    tui.memory.replace_last("user", f"Scan web dom target details[URL_HIDDEN]: {q}"); tui.memory.add("assistant", raw)
    tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/shell", "OS Subprocess system layer execution map handler terminal link!")
def cmd_shell(tui: LumiTUI, arg: str):
    if not arg: tui._err("Fatal. Command payload param lacking via CLI pipeline."); return
    try:
        r = subprocess.run(arg, shell=True, capture_output=True, text=True, timeout=20)
        out = (r.stdout + ("\n" + r.stderr if r.stderr else "")).strip()
        tui.store.add(Msg("system", out[:3000] if out else " [Code Status code Success // Terminal Empty Return]", arg))
    except Exception as e: tui._err(f"Shell subprocess Exception Timeout / Fault [{str(e)}]")

@registry.register("/find", "Local Unix find tools linked wrapper!")
def cmd_find(tui: LumiTUI, arg: str):
    r = subprocess.run(f"find . -name '*{arg}*' -not -path './.git/*' 2>/dev/null | head -30", shell=True, capture_output=True, text=True)
    tui.store.add(Msg("system", r.stdout.strip() if r.stdout else "Fail code query map unhit matching pattern regex", "Directory File Index Finder..."))

@registry.register("/docs", "Create auto comments markdown code layout files")
@bg_task
def cmd_docs(tui: LumiTUI, arg: str):
    target = arg.strip(); tui.set_busy(True)
    if target and Path(target).exists(): content = _read_file(target)
    elif tui.last_reply: content = tui.last_reply
    else: tui._err("A valid File arg param, or active reply target missing"); tui.set_busy(False); return
    tui.memory.add("user", f"Generate massive doc blocks via format params to the script file contents accurately:\n{content}")
    raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get()), tui.current_model, f"◆ {tui.name}  [Document Generator Routine Started...]")
    tui.memory.replace_last("user", "Generational System Comment AutoDocs Code Map Layout.")
    tui.memory.add("assistant", raw); tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/types", "PEP typing annotations rewrite format generator block tool")
@bg_task
def cmd_types(tui: LumiTUI, arg: str):
    target = arg.strip(); tui.set_busy(True)
    if target and Path(target).exists(): content = _read_file(target)
    elif tui.last_reply: content = tui.last_reply
    else: tui._err("Types parameter missing! Active text memory nil void zero context state loaded!"); tui.set_busy(False); return
    tui.memory.add("user", f"Parse format TypeHint TypeChecker mypy style to all structure object values directly safely accurately!\n```\n{content}\n```")
    raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get()), tui.current_model, f"◆ {tui.name}  [Statically Type Analysis Typing routine...]")
    tui.memory.replace_last("user", "Applied Code PEP Typings Map Refactor Run!"); tui.memory.add("assistant", raw); tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/multi", "Toggle multiline input mode")
def cmd_multi(tui: LumiTUI, arg: str):
    tui._sync_runtime_config(multiline=not tui.multiline)
    tui._notify(f"Multiline {'ON — Enter=newline, Ctrl+D=submit' if tui.multiline else 'OFF'}")

@registry.register("/remember", "Save a fact to long-term memory")
def cmd_rem(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /remember <fact>"); return
    fact = " ".join(arg.strip().split())
    n = add_fact(fact)
    remember_project_decision(fact, base_dir=Path.cwd())
    tui.system_prompt = tui._make_system_prompt()
    tui._sys(f"Remembered fact #{n}: {fact}")

@registry.register("/memory", "Show all stored long-term facts")
def cmd_mem(tui: LumiTUI, arg: str):
    f = get_facts()
    if f:
        lines = ["Long-term memory:"] + [f"  {i}. {val}" for i, val in enumerate(f, 1)]
        lines.append("")
        lines.append("Use /forget <number> to remove one fact or /forget all to clear everything.")
        tui._sys("\n".join(lines))
    else: tui._sys("No facts stored. Use /remember <fact>")

@registry.register("/forget", "Remove a fact by number: /forget 3")
def cmd_forg(tui: LumiTUI, arg: str):
    f = get_facts()
    if not f: tui._err("No facts to forget"); return
    target = arg.strip().lower()
    if not target:
        lines = ["Facts:"] + [f"  {i}. {val}" for i, val in enumerate(f, 1)]
        tui._sys("\n".join(lines) + "\n  Use: /forget <number>  or  /forget all")
        return
    if target == "all":
        clear_facts()
        tui.system_prompt = tui._make_system_prompt()
        tui._sys("Cleared all remembered facts.")
        return
    try:
        index = int(target) - 1
    except ValueError:
        tui._err("Usage: /forget <number>  or  /forget all")
        return
    if not (0 <= index < len(f)):
        tui._err(f"Fact #{index + 1} does not exist.")
        return
    removed = f[index]
    if not remove_fact(index):
        tui._err(f"Failed to forget fact #{index + 1}.")
        return
    tui.system_prompt = tui._make_system_prompt()
    tui._sys(f"Forgot fact #{index + 1}: {removed}")

@registry.register("/short", "Next reply: be concise")
def cmd_short(tui: LumiTUI, arg: str): tui.response_mode = "short"; tui._notify("Mode: concise")
@registry.register("/detailed", "Next reply: be comprehensive")
def cmd_detailed(tui: LumiTUI, arg: str): tui.response_mode = "detailed"; tui._notify("Mode: detailed")
@registry.register("/bullets", "Next reply: bullet points only")
def cmd_bullets(tui: LumiTUI, arg: str): tui.response_mode = "bullets"; tui._notify("Mode: bullets")
@registry.register("/effort", "Set reasoning effort: low | medium | high | ehigh | max")
def cmd_effort(tui: LumiTUI, arg: str):
    raw = arg.strip().lower()
    if not raw:
        current = normalize_reasoning_effort(getattr(tui, "reasoning_effort", "medium"))
        try:
            next_value = EFFORT_LEVELS[(EFFORT_LEVELS.index(current) + 1) % len(EFFORT_LEVELS)]
        except ValueError:
            next_value = "medium"
        tui._sync_runtime_config(reasoning_effort=next_value, fast_mode=False)
        tui._notify(f"Effort: {display_reasoning_effort(next_value)}")
        return
    if raw in {"status", "show"}:
        tui._sys(f"Reasoning effort: {display_reasoning_effort(getattr(tui, 'reasoning_effort', 'medium'))}")
        return
    normalized = normalize_reasoning_effort(raw)
    if raw not in EFFORT_LEVELS and raw not in {
        "extra high",
        "extra-high",
        "extra_high",
        "max",
        "maximum",
        "xhigh",
        "very high",
        "very-high",
        "very_high",
    }:
        tui._err("Usage: /effort [low|medium|high|ehigh|max|status]")
        return
    tui._sync_runtime_config(reasoning_effort=normalized, fast_mode=False)
    tui._notify(f"Effort: {display_reasoning_effort(normalized)}")

# ── New utility commands ──────────────────────────────────────────────────────

@registry.register("/compact", "Toggle compact display mode")
def cmd_compact(tui: LumiTUI, arg: str):
    tui._sync_runtime_config(compact_mode=not tui._compact)
    tui._sys(f"Compact {'on' if tui._compact else 'off'}")


@registry.register("/brief", "Toggle brief output mode")
def cmd_brief(tui: LumiTUI, arg: str):
    raw = arg.strip().lower()
    if raw in {"", "toggle"}:
        tui._sync_runtime_config(brief_mode=not tui.brief_mode)
    else:
        try:
            tui._sync_runtime_config(**parse_runtime_config_update("brief", raw))
        except ValueError as exc:
            tui._err(str(exc))
            return
    tui._notify(f"Brief {'on' if tui.brief_mode else 'off'}")


@registry.register("/fast", "Toggle fast mode")
def cmd_fast(tui: LumiTUI, arg: str):
    raw = arg.strip().lower()
    if raw in {"", "toggle"}:
        tui._sync_runtime_config(fast_mode=not tui.fast_mode)
    else:
        try:
            tui._sync_runtime_config(**parse_runtime_config_update("fast", raw))
        except ValueError as exc:
            tui._err(str(exc))
            return
    tui._notify(f"Fast {'on' if tui.fast_mode else 'off'}")


@registry.register("/config", "Show or update runtime settings")
def cmd_config(tui: LumiTUI, arg: str):
    raw = arg.strip()
    if not raw or raw.lower() in {"show", "list"}:
        tui._sys(
            render_runtime_config_report(
                base_dir=Path.cwd(),
                provider=get_provider(),
                model=tui.current_model,
                compact_mode=tui._compact,
                multiline=tui.multiline,
                reasoning_effort=tui.reasoning_effort,
                brief_mode=tui.brief_mode,
                fast_mode=tui.fast_mode,
            )
        )
        return
    parts = raw.split(maxsplit=2)
    if len(parts) == 1 and parts[0].lower() == "reset":
        config = reset_runtime_config(Path.cwd())
        tui._apply_runtime_config(config)
        tui.workspace_profile = inspect_workspace(Path.cwd())
        tui._notify("Config reset")
        return
    if len(parts) == 3 and parts[0].lower() == "set":
        try:
            updates = parse_runtime_config_update(parts[1], parts[2])
            tui._sync_runtime_config(**updates)
        except ValueError as exc:
            tui._err(str(exc))
            return
        tui._notify(f"Config updated: {parts[1]}")
        return
    tui._err("Usage: /config [show|reset|set <key> <value>]")


@registry.register("/add-dir", "Add or remove extra workspace context directories")
def cmd_add_dir(tui: LumiTUI, arg: str):
    raw = arg.strip()
    if not raw or raw.lower() == "list":
        config = load_runtime_config(Path.cwd())
        lines = ["Context directories:"]
        if config.extra_dirs:
            lines.extend(f"  - {item}" for item in config.extra_dirs)
        else:
            lines.append("  - none")
        tui._sys("\n".join(lines))
        return
    parts = raw.split(maxsplit=1)
    action = parts[0].lower()
    target = parts[1].strip() if len(parts) > 1 else ""
    try:
        if action in {"remove", "rm", "del"}:
            if not target:
                tui._err("Usage: /add-dir remove <path>")
                return
            config, removed = remove_context_directory(target, base_dir=Path.cwd())
            tui._apply_runtime_config(config)
            tui.workspace_profile = inspect_workspace(Path.cwd())
            tui._notify(f"Removed context dir: {removed}")
            return
        config, added = add_context_directory(raw, base_dir=Path.cwd())
    except ValueError as exc:
        tui._err(str(exc))
        return
    tui._apply_runtime_config(config)
    tui.workspace_profile = inspect_workspace(Path.cwd())
    tui._notify(f"Added context dir: {added}")


@registry.register("/files", "Show workspace files, hotspots, and context directories")
def cmd_files(tui: LumiTUI, arg: str):
    tui.set_pane(
        title="files",
        subtitle=WORKBENCH_TITLE,
        lines=render_files_report(Path.cwd(), task=arg.strip()).splitlines(),
        footer="Esc close  ·  /add-dir <path>  ·  /files <task>",
        close_on_escape=True,
    )
    tui.redraw()


@registry.register("/tasks", "Show active and recent workbench tasks")
def cmd_tasks(tui: LumiTUI, arg: str):
    lines = render_tasks_report(Path.cwd()).splitlines()
    if tui.workbench_jobs:
        lines.extend(["", "Live jobs"])
        for item in tui.workbench_jobs[:6]:
            lines.append(f"  - [{item.get('status', '?')}] {item.get('mode', 'job')} · {item.get('objective', '')}")
    tui.set_pane(
        title="tasks",
        subtitle=WORKBENCH_TITLE,
        lines=lines,
        footer="Esc close  ·  /jobs",
        close_on_escape=True,
    )
    tui.redraw()


@registry.register("/agents", "Show active objective and available agents")
def cmd_agents(tui: LumiTUI, arg: str):
    tui.set_pane(
        title="agents",
        subtitle=WORKBENCH_TITLE,
        lines=render_agents_report(
            base_dir=Path.cwd(),
            active_objective=tui.agent_active_objective or "",
            active_tasks=tui.agent_tasks,
        ).splitlines(),
        footer="Esc close  ·  /agent <objective>  ·  /council",
        close_on_escape=True,
    )
    tui.redraw()


@registry.register("/version", "Show Lumi version and runtime info")
def cmd_version(tui: LumiTUI, arg: str):
    tui._sys(render_version_report(version=WORKBENCH_VERSION, provider=get_provider(), model=tui.current_model))

@registry.register("/tokens", "Show token usage and session cost", aliases=["/cost"])
def cmd_tokens(tui: LumiTUI, arg: str):
    tui._sys(_session_telemetry.render_usage_report() + "\n\n" + tui.session_cost.render_report())

@registry.register("/context", "Show context window breakdown")
def cmd_context(tui: LumiTUI, arg: str):
    tui._sys(_session_telemetry.render_context_report())

@registry.register("/export", "Export chat as Markdown file")
def cmd_export(tui: LumiTUI, arg: str):
    msgs = tui.store.snapshot()
    if not msgs: tui._sys("Nothing to export"); return
    fname = arg.strip() or f"lumi_chat_{int(time.time())}.md"
    lines = ["# Lumi Chat Export\n"]
    for m in msgs:
        if m.role == "user": lines.append(f"**You** ({m.ts}):\n{m.text}\n")
        elif m.role in ("assistant",): lines.append(f"**Lumi** ({m.ts}):\n{m.text}\n")
        elif m.role == "system": lines.append(f"*System: {m.text}*\n")
    Path(fname).write_text("\n".join(lines)); tui._sys(f"Exported to {fname}")

@registry.register("/copy", "Copy last AI reply to clipboard")
def cmd_copy(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("No reply to copy"); return
    try:
        subprocess.run(["xclip", "-selection", "clipboard"], input=tui.last_reply.encode(), check=True)
        tui._sys("Copied to clipboard")
    except Exception:
        try:
            subprocess.run(["xsel", "--clipboard", "--input"], input=tui.last_reply.encode(), check=True)
            tui._sys("Copied to clipboard")
        except Exception: tui._err("Install xclip or xsel for clipboard support")

@registry.register("/paste", "Paste clipboard as message")
def cmd_paste(tui: LumiTUI, arg: str):
    try:
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip(): tui.buf = r.stdout.strip(); tui.cur_pos = len(tui.buf)
        else: tui._err("Clipboard empty")
    except Exception:
        try:
            r = subprocess.run(["xsel", "--clipboard", "--output"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip(): tui.buf = r.stdout.strip(); tui.cur_pos = len(tui.buf)
            else: tui._err("Clipboard empty")
        except Exception: tui._err("Install xclip or xsel")

@registry.register("/diff", "Diff current vs previous AI reply")
def cmd_diff(tui: LumiTUI, arg: str):
    if not tui.last_reply or not tui.prev_reply: tui._err("Need 2+ replies for diff"); return
    import difflib
    d = difflib.unified_diff(tui.prev_reply.splitlines(), tui.last_reply.splitlines(), lineterm="", fromfile="previous", tofile="current")
    tui._sys("\n".join(d) or "No differences found")

@registry.register("/persona", "Change persona: /persona tone=formal")
def cmd_persona(tui: LumiTUI, arg: str):
    if not arg or arg.strip() == "reset":
        tui.persona_override = {}; tui.system_prompt = tui._make_system_prompt(); tui._sys("Persona reset"); return
    if "=" in arg:
        k, v = arg.split("=", 1); tui.persona_override[k.strip()] = v.strip()
        tui.system_prompt = tui._make_system_prompt(); tui._sys(f"Persona: {k.strip()} = {v.strip()}")
    else: tui._err("Usage: /persona key=value  or  /persona reset")

@registry.register("/sys", "Show current system prompt")
def cmd_sys(tui: LumiTUI, arg: str): tui._sys(f"System prompt ({len(tui.system_prompt)} chars):\n{tui.system_prompt[:500]}...")

@registry.register("/sessions", "List saved sessions", aliases=["/session"])
def cmd_sessions(tui: LumiTUI, arg: str):
    from src.config import SESSIONS_DIR
    sdir = SESSIONS_DIR
    if not sdir.exists(): tui._sys("No sessions saved yet"); return
    files = sorted(sdir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files: tui._sys("No sessions saved yet"); return
    lines = ["Saved sessions:"] + [f"  {f.stem}" for f in files[:20]]
    tui._sys("\n".join(lines))

@registry.register("/edit", "AI-rewrite a file: /edit src/main.py")
def cmd_edit(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /edit <filepath>"); return
    path = Path(arg.strip()).expanduser()
    if not path.is_file(): tui._err(f"Not a file: {path}"); return
    content = path.read_text(errors="replace")
    def _go():
        tui.set_busy(True)
        card = file_review_card(path, mode="edit")
        tui.set_review_card(
            title=str(card["title"]),
            summary_lines=list(card["summary_lines"]),
            preview_lines=list(card["preview_lines"]),
            footer=str(card["footer"]),
        )
        try:
            prompt = f"Rewrite and improve this file. Return ONLY the new file content:\n\n```\n{content}\n```"
            msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
            reply = tui._tui_stream(msgs, tui.current_model, f"editing {path.name}")
            tui.last_reply = reply
        finally:
            tui.clear_review_card()
            tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/run", "Execute last code block from AI reply")
def cmd_run(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("No reply with code to run"); return
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", tui.last_reply, re.DOTALL)
    if not blocks: tui._err("No code block found"); return
    code = blocks[-1].strip()
    def _go():
        tui.set_busy(True)
        try:
            r = subprocess.run(["python3", "-c", code], capture_output=True, text=True, timeout=30)
            out = r.stdout.strip() or r.stderr.strip() or "(no output)"
            tui._sys(f"Exit {r.returncode}:\n{out[:2000]}")
        except subprocess.TimeoutExpired: tui._err("Execution timed out (30s)")
        except Exception as e: tui._err(str(e))
        tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/image", "Vision: describe or query image")
def cmd_image(tui: LumiTUI, arg: str):
    parsed = parse_image_request(arg)
    if not parsed:
        tui._err("Usage: /image <path> [question]"); return
    path, question = parsed
    if not path.is_file():
        tui._err(f"Not found: {path}"); return
    if not image_mime(path):
        tui._err(f"Not an image: {path}"); return

    def _go():
        tui.set_busy(True)
        try:
            current_provider = get_provider()
        except Exception:
            current_provider = ""
        try:
            provider, model, auto_routed = resolve_media_target(
                capability="vision",
                current_provider=current_provider,
                current_model=tui.current_model,
                configured_providers=get_available_providers(),
                get_models_fn=get_models,
            )
            client = make_provider_client(provider)
            if auto_routed:
                tui._sys(f"Using {PROV_NAME.get(provider, provider)} vision via {model}.")
            messages = build_image_messages(question, path)
            reply = _stream_direct_completion(tui, client=client, messages=messages, model=model)
            if not reply.startswith("⚠"):
                tui.last_reply = reply
                tui.turns += 1
        except Exception as ex:
            tui._err(str(ex))
        finally:
            tui.set_busy(False)

    threading.Thread(target=_go, daemon=True).start()


@registry.register("/imagine", "Generate or edit an image with Nano Banana")
def cmd_imagine(tui: LumiTUI, arg: str):
    parsed = parse_imagine_request(arg)
    if not parsed:
        tui._err("Usage: /imagine <prompt>  or  /imagine <image-path> <prompt>")
        return
    source_image, prompt = parsed
    if source_image is not None:
        if not source_image.is_file():
            tui._err(f"Not found: {source_image}")
            return
        if not image_mime(source_image):
            tui._err(f"Not an image: {source_image}")
            return
    if not prompt.strip():
        tui._err("Image generation needs a prompt.")
        return

    def _go():
        tui.set_busy(True)
        try:
            current_provider = get_provider()
        except Exception:
            current_provider = ""
        try:
            provider, model, auto_routed = resolve_media_target(
                capability="image_generation",
                current_provider=current_provider,
                current_model=tui.current_model,
                configured_providers=get_available_providers(),
                get_models_fn=get_models,
            )
            if provider != "gemini":
                raise RuntimeError("Image generation currently uses Gemini models only.")
            if auto_routed:
                tui._sys(f"Using {PROV_NAME.get(provider, provider)} image generation via {model}.")
            saved_paths, message = generate_gemini_images(
                prompt,
                source_image=source_image,
                model=model,
            )
            lines = []
            if source_image is not None:
                lines.append(f"Edited image from {source_image}")
            else:
                lines.append("Generated image with Nano Banana")
            if message:
                lines.append(message)
            for path in saved_paths:
                lines.append(f"Saved image → {path}")
            summary = "\n".join(lines)
            tui._sys(summary)
            tui.last_reply = summary
            tui.recent_actions = tui.little_notes.record_action(
                f"Generated {len(saved_paths)} image(s) with {model}."
            )[:4]
        except Exception as ex:
            tui._err(str(ex))
        finally:
            tui.set_busy(False)

    threading.Thread(target=_go, daemon=True).start()

@registry.register("/data", "Analyze CSV/JSON: /data stats.csv")
def cmd_data(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /data <file.csv|file.json>"); return
    path = Path(arg.strip()).expanduser()
    if not path.is_file(): tui._err(f"Not found: {path}"); return
    content = path.read_text(errors="replace")[:8000]
    def _go():
        tui.set_busy(True)
        _context_cache.remember_text(f"data:{path}", path.name, content, kind="data")
        prompt = f"[data: {path.name}] Cached data snapshot. Give summary stats, patterns, insights."
        msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
        msgs = optimize_messages(
            msgs,
            tui.current_model,
            mode="code",
            provider=get_provider(),
            context_cache=_context_cache,
            telemetry=_session_telemetry,
        )
        reply = tui._tui_stream(msgs, tui.current_model, f"analyzing {path.name}")
        tui.last_reply = reply; tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/agent", "Plan a multi-step agent workflow")
def cmd_agent(tui: LumiTUI, arg: str):
    objective = arg.strip()
    if not objective:
        tui._err("Usage: /agent <objective>"); return
    tui.little_notes.record_agent_task(objective)

    def _go():
        tui.set_busy(True)
        tui._sys(f"◆ Planning agent steps for: {objective}")
        try:
            model = tui.current_model if tui.current_model != "council" else get_models(get_provider())[0]
        except Exception:
            model = tui.current_model

        prompt = (
            "You are a planning module for an autonomous developer agent.\n"
            f"Objective: {objective}\n\n"
            "Return a concise numbered list of 3–8 concrete steps.\n"
            "Each step must fit on one line and start with a number and a period, e.g. `1. ...`.\n"
            "Do NOT add explanations before or after the list."
        )
        plan_text = tui._silent_call(prompt, model, max_tokens=256)
        if not plan_text:
            tui._err("Agent planning failed."); tui.set_busy(False); return

        steps = []
        for line in plan_text.splitlines():
            m = re.match(r'^\s*\d+\.\s+(.*\S)\s*$', line)
            if m:
                steps.append(m.group(1))
        if not steps:
            steps = [s.strip() for s in plan_text.split("\n") if s.strip()][:5]

        tui.agent_active_objective = objective
        tui.agent_tasks = [{"text": s, "status": "pending"} for s in steps]

        summary_lines = ["Agent plan:", ""] + [f"  {i+1}. {s}" for i, s in enumerate(steps)]
        tui._sys("\n".join(summary_lines))
        tui.set_busy(False)
        tui.redraw()

    threading.Thread(target=_go, daemon=True).start()

@registry.register("/draft", "Draft email, Slack msg, or text")
def cmd_draft(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /draft <what to write>"); return
    def _go():
        tui.set_busy(True)
        prompt = f"Draft a professional message. Be clear and concise:\n\n{arg}"
        msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
        reply = tui._tui_stream(msgs, tui.current_model, "drafting")
        tui.last_reply = reply; tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/todo", "Todo list: /todo add|list|done|rm")
def cmd_todo(tui: LumiTUI, arg: str):
    from src.config import MEMORY_DIR
    todo_file = MEMORY_DIR / "todos.json"
    try: todos = json.loads(todo_file.read_text()) if todo_file.exists() else []
    except Exception: todos = []
    parts = arg.strip().split(None, 1) if arg.strip() else ["list"]
    cmd = parts[0].lower(); rest = parts[1] if len(parts) > 1 else ""
    if cmd == "add" and rest:
        todos.append({"text": rest, "done": False}); todo_file.write_text(json.dumps(todos))
        tui._sys(f"Added: {rest}")
    elif cmd == "list":
        if not todos: tui._sys("No todos — /todo add <task>"); return
        lines = ["Todos:"] + [f"  {'✓' if t['done'] else '○'} {i+1}. {t['text']}" for i, t in enumerate(todos)]
        tui._sys("\n".join(lines))
    elif cmd == "done" and rest.isdigit():
        idx = int(rest) - 1
        if 0 <= idx < len(todos): todos[idx]["done"] = True; todo_file.write_text(json.dumps(todos)); tui._sys(f"Done: {todos[idx]['text']}")
        else: tui._err("Invalid todo number")
    elif cmd == "rm" and rest.isdigit():
        idx = int(rest) - 1
        if 0 <= idx < len(todos): removed = todos.pop(idx); todo_file.write_text(json.dumps(todos)); tui._sys(f"Removed: {removed['text']}")
        else: tui._err("Invalid todo number")
    else: tui._sys("Usage: /todo add|list|done|rm")

@registry.register("/note", "Notes: /note add|list|search")
def cmd_note(tui: LumiTUI, arg: str):
    from src.config import MEMORY_DIR
    note_file = MEMORY_DIR / "notes.json"
    try: notes = json.loads(note_file.read_text()) if note_file.exists() else []
    except Exception: notes = []
    parts = arg.strip().split(None, 1) if arg.strip() else ["list"]
    cmd = parts[0].lower(); rest = parts[1] if len(parts) > 1 else ""
    if cmd == "add" and rest:
        notes.append({"text": rest, "ts": time.strftime("%Y-%m-%d %H:%M")}); note_file.write_text(json.dumps(notes))
        tui._sys(f"Note saved ({len(notes)} total)")
    elif cmd == "list":
        if not notes: tui._sys("No notes — /note add <text>"); return
        lines = ["Notes:"] + [f"  {i+1}. [{n['ts']}] {n['text'][:80]}" for i, n in enumerate(notes[-20:])]
        tui._sys("\n".join(lines))
    elif cmd == "search" and rest:
        hits = [n for n in notes if rest.lower() in n["text"].lower()]
        if hits: tui._sys("\n".join([f"  [{n['ts']}] {n['text'][:80]}" for n in hits]))
        else: tui._sys("No matching notes")
    else: tui._sys("Usage: /note add|list|search <query>")

@registry.register("/weather", "Current weather: /weather <location>")
def cmd_weather(tui: LumiTUI, arg: str):
    loc = arg.strip() or "auto"
    try:
        url = f"https://wttr.in/{loc}?format=%l:+%C+%t+%w+%h"
        with urllib.request.urlopen(url, timeout=5) as r: tui._sys(r.read().decode().strip())
    except Exception: tui._err("Weather fetch failed")

@registry.register("/timer", "Countdown timer: /timer 5m")
def cmd_timer(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /timer 25m or /timer 90s"); return
    unit = arg.strip()[-1]; num = arg.strip()[:-1]
    if not num.isdigit(): tui._err("Usage: /timer 25m or /timer 90s"); return
    secs = int(num) * (60 if unit == "m" else 1)
    tui._sys(f"Timer set: {secs}s")
    def _tick():
        time.sleep(secs); tui._notify(f"Timer done! ({arg.strip()})", 10)
    threading.Thread(target=_tick, daemon=True).start()

@registry.register("/plugins", "List loaded plugins", aliases=["/plugin"])
def cmd_plugins(tui: LumiTUI, arg: str):
    parts = arg.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    target = parts[1].strip() if len(parts) > 1 else ""

    if sub == "audit":
        tui._sys(render_plugin_audit_report())
        return
    if sub in {"approve", "trust"}:
        if not target:
            tui._err("Usage: /plugins approve <name>")
            return
        ok, message = approve_plugin(target)
        if ok:
            tui._loaded_plugins = reload_plugins()
            tui._sys(message)
        else:
            tui._err(message)
        return
    if sub in {"revoke", "untrust"}:
        if not target:
            tui._err("Usage: /plugins revoke <name>")
            return
        ok, message = revoke_plugin(target)
        if ok:
            tui._loaded_plugins = reload_plugins()
            tui._sys(message)
        else:
            tui._err(message)
        return
    if sub == "reload":
        tui._loaded_plugins = reload_plugins()
        tui._sys(
            "Reloaded plugins."
            if tui._loaded_plugins
            else "Reloaded plugin inventory. No trusted plugins are currently loaded."
        )
        return
    if sub == "pending":
        tui._sys(render_plugin_inventory_report("pending"))
        return
    if sub in {"inspect", "details", "verbose"}:
        tui._sys(render_plugin_inventory_report("inspect"))
        return

    tui._sys(render_plugin_inventory_report("summary"))


@registry.register("/reload-plugins", "Reload trusted plugins")
def cmd_reload_plugins(tui: LumiTUI, arg: str):
    tui._execute_command("/plugins", "reload")


@registry.register("/logs", "Show recent tool and shell logs")
def cmd_logs(tui: LumiTUI, arg: str):
    lines = ["Recent tool logs"]
    if tui.tool_logs:
        lines.extend(f"  - {item}" for item in tui.tool_logs[-12:])
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Recent shell output")
    if tui.shell_logs:
        lines.extend(f"  {item}" for item in tui.shell_logs[-20:])
    else:
        lines.append("  - none")
    tui.set_pane(
        title="logs",
        subtitle=WORKBENCH_TITLE,
        lines=lines,
        footer="Esc close  ·  /logs",
        close_on_escape=True,
    )
    tui.redraw()


@registry.register("/permissions", "Show or update tool permissions")
def cmd_permissions(tui: LumiTUI, arg: str):
    raw = arg.strip()
    if not raw or raw.lower() in {"show", "summary"}:
        tui._sys(render_tool_permission_report(base_dir=Path.cwd()))
        return
    parts = raw.split(maxsplit=2)
    sub = parts[0].lower()
    if sub == "plugins":
        tui._sys(render_permission_report("plugins"))
        return
    if sub == "all":
        tui._sys(render_tool_permission_report(base_dir=Path.cwd()) + "\n\n" + render_permission_report("all"))
        return
    if sub == "mode" and len(parts) >= 2:
        mode = parts[1].lower()
        if mode not in {"ask", "auto", "strict"}:
            tui._err("Usage: /permissions mode <ask|auto|strict>")
            return
        set_tool_permission_mode(mode, base_dir=Path.cwd())
        tui._notify(f"Permissions mode → {mode}")
        return
    if sub in {"add", "rm"} and len(parts) >= 3:
        kind_and_rule = parts[1:]
        if len(kind_and_rule) != 2:
            tui._err(f"Usage: /permissions {sub} <allow|deny> \"tool:pattern\"")
            return
        kind = kind_and_rule[0].lower()
        rule = kind_and_rule[1].strip()
        try:
            if sub == "add":
                add_tool_permission_rule(kind, rule, base_dir=Path.cwd())
                tui._notify(f"Permission added: {kind}")
            else:
                remove_tool_permission_rule(kind, rule, base_dir=Path.cwd())
                tui._notify(f"Permission removed: {kind}")
        except ValueError as exc:
            tui._err(str(exc))
        return
    tui._err("Usage: /permissions [all|plugins|mode <ask|auto|strict>|add <allow|deny> \"tool:pattern\"|rm <allow|deny> \"tool:pattern\"]")


@registry.register("/status", "Show Lumi session and workspace status")
def cmd_status(tui: LumiTUI, arg: str):
    try:
        provider = get_provider()
    except Exception:
        provider = ""
    report = build_status_report(
        base_dir=Path.cwd(),
        provider=provider,
        model=tui.current_model,
        session_turns=tui.turns,
        short_term_stats=tui.memory.stats(),
        recent_commands=tui.recent_commands,
    )
    tui._sys(report)


@registry.register("/doctor", "Check Lumi setup and workspace health")
def cmd_doctor(tui: LumiTUI, arg: str):
    try:
        provider = get_provider()
    except Exception:
        provider = ""
    try:
        configured = get_available_providers()
    except Exception:
        configured = []
    report = build_doctor_report(
        base_dir=Path.cwd(),
        provider=provider,
        model=tui.current_model,
        configured_providers=configured,
    )
    tui._sys(report)


@registry.register("/rebirth", "Rebirth profile capability report and toggles")
def cmd_rebirth(tui: LumiTUI, arg: str):
    sub = arg.strip().lower()

    if sub in {"", "status", "report"}:
        tui._sys(render_rebirth_report())
        return

    profile = load_rebirth_profile()
    defaults = profile.get("defaults", {}) if isinstance(profile.get("defaults"), dict) else {}

    if sub in {"on", "enable", "apply"}:
        mode = str(defaults.get("response_mode", "detailed")).strip() or "detailed"
        if mode in {"short", "detailed", "bullets"}:
            tui.response_mode = mode
        tui._compact = bool(defaults.get("compact", False))
        tui.guardian_enabled = bool(defaults.get("guardian_enabled", True))
        tui._sys(
            f"Rebirth profile enabled ({rebirth_status_summary()}). "
            f"response={tui.response_mode or 'default'}, compact={'on' if tui._compact else 'off'}, "
            f"guardian={'on' if tui.guardian_enabled else 'off'}."
        )
        tui._notify("Rebirth profile enabled")
        return

    if sub in {"off", "disable"}:
        tui.guardian_enabled = False
        tui.response_mode = None
        tui._sys("Rebirth profile disabled (guardian off, response mode reset).")
        tui._notify("Rebirth profile disabled")
        return

    tui._err("Usage: /rebirth [status|on|off]")

HELP_CATEGORIES = register_command_groups(
    registry,
    build_messages=build_messages,
    read_file=_read_file,
    context_cache=_context_cache,
    get_available_providers=get_available_providers,
    log=log,
)

@registry.register("/mode", "/mode vessel <name>  Launch an external AI coding CLI and import the session back into Lumi")
def cmd_mode(tui: LumiTUI, arg: str):
    parts = arg.strip().split()
    lowered = [part.lower() for part in parts]
    target = lowered[0] if lowered else ""

    if not target:
        lines = ["◆  AI CLI Launcher — available tools:\n"]
        for key, entry in MODE_CLI_REGISTRY.items():
            info = _mode_binary_info(entry)
            status = "✓ installed" if info["installed"] else "✗ not found"
            mark = "●" if info["installed"] else "○"
            version = f" · {info['version']}" if info["version"] else ""
            lines.append(
                f"  {mark} /mode vessel {key:<8} {str(entry['name']):<16} [{entry['maker']}]  {status}{version}"
            )
        recent = list_mode_conversations(limit=5)
        if recent:
            lines.append("\n  Recent saved vessel sessions:")
            for record in recent:
                summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
                lines.append(
                    f"  - {record.get('cli', '?')} · {Path(str(record.get('path', ''))).stem} · {str(summary.get('tldr', 'No TL;DR available.'))[:80]}"
                )
        lines.append("\n  Usage: /mode vessel <name>")
        lines.append("  Browse saved sessions: /mode conversations [cli] [query]")
        tui._sys("\n".join(lines))
        tui.redraw()
        return

    if target == "conversations":
        rest = lowered[1:]
        cli_name = None
        if rest and rest[0] in MODE_CLI_REGISTRY:
            cli_name = rest[0]
            rest = rest[1:]
        query = " ".join(parts[1 + (1 if cli_name else 0) :]).strip()
        records = (
            search_mode_conversations(query, cli_name, limit=10)
            if query
            else list_mode_conversations(cli_name, limit=10)
        )
        for record in records:
            _index_mode_record(record)
        title, subtitle, lines = _build_mode_conversation_lines(records, cli_name=cli_name, query=query)
        if not lines:
            lines = ["No saved mode conversations found yet.", "", "Run /mode vessel <cli> and exit that CLI to create one."]
        tui.set_pane(
            title=title,
            subtitle=subtitle,
            lines=lines,
            footer="Esc close  ·  /mode conversations [cli] [query]",
            close_on_escape=True,
        )
        tui.redraw()
        return

    if target == "vessel":
        if len(lowered) < 2:
            tui._err("Usage: /mode vessel <name>")
            return
        target = lowered[1]

    if target not in MODE_CLI_REGISTRY:
        names = ", ".join(MODE_CLI_REGISTRY.keys())
        tui._err(f"Unknown CLI: '{target}'. Choose from: {names}")
        return

    entry = dict(MODE_CLI_REGISTRY[target])
    info = _mode_binary_info(entry)
    if not info["installed"]:
        install_lines = [f"◆  {entry['name']} is not installed."]
        if info["reason"]:
            install_lines.append(f"\n  validation: {info['reason']}")
        install_lines.append("\n  Install with:")
        for command in entry.get("installs", []):
            install_lines.append(f"  $ {command}")
        install_lines.append(f"\n  Verify with:\n  $ {entry['verify']}")
        install_lines.append(f"\n  Auth/setup:\n  {entry['auth']}")
        install_lines.append(f"\n  After installing, run /mode vessel {target} again.")
        tui._sys("\n".join(str(line) for line in install_lines))
        return

    recent_lines = _mode_recent_lines(target, limit=3)
    launch_lines = [f"◆  Launching {entry['name']}…  Lumi will resume when you exit."]
    if info["version"]:
        launch_lines.append(f"  detected: {info['version']}")
    if info["binary_path"]:
        launch_lines.append(f"  binary: {_mode_display_path(str(info['binary_path']))}")
    if recent_lines:
        launch_lines.append("")
        launch_lines.append("  Recent saved sessions:")
        launch_lines.extend(recent_lines)

    tui.vessel_mode = False
    tui.active_vessel = None
    tui.system_prompt = tui._make_system_prompt()
    tui._sys("\n".join(launch_lines))
    tui.redraw()
    tui._pending_handoff = {
        **entry,
        "key": target,
        "binary_path": str(info["binary_path"]),
        "binary_version": str(info["version"]),
        "launch_cmd": [str(info["binary_path"])],
    }

@registry.register("/guardian", "Toggle background code-quality watcher (ruff + pytest)")
def cmd_guardian(tui: LumiTUI, arg: str):
    tui.guardian_enabled = not getattr(tui, "guardian_enabled", False)
    state = "on" if tui.guardian_enabled else "off"
    tui._sys(f"◆  Guardian {state} — runs ruff + pytest every 5 min")

@registry.register("/offline", "Enter air-gapped privacy mode via Ollama")
def cmd_offline(tui: LumiTUI, arg: str):
    try:
        models = get_models("ollama")
        if not models:
            tui._err("Ollama is not running or no models found! Ensure ollama is active.")
            return

        set_provider("ollama")
        tui.client = get_client()
        tui.current_model = models[0]

        tui._sys(f"◆  [OFFLINE] Privacy Mode ON. Cloud disconnected. Local: {tui.current_model}")
        tui._notify(f"Offline Mode: {tui.current_model}")
    except Exception as e:
        tui._err(f"Offline switch failed: {e}")

@registry.register("/godmode", "Agentic autonomous workflow loop")
def cmd_godmode(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /godmode <objective>"); return

    def _go():
        tui.set_busy(True)
        tui._sys(f"◆  Entering God Mode. Objective: {arg}")

        prompt = (f"GOD MODE OBJECTIVE: {arg}\n"
                  "You act autonomously. Respond STRICTLY in one of three formats:\n\n"
                  "To run a shell command:\n"
                  "[CMD] <bash command>\n\n"
                  "To edit or create a file (write full file context):\n"
                  "[EDIT] <file_path>\n"
                  "<Content...>\n"
                  "[ENDEDIT]\n\n"
                  "To finish the task successfully:\n"
                  "[DONE]\n\n"
                  "Only do ONE action per message. The system will reply with feedback.")

        tui.memory.add("user", prompt)

        loop = 0
        while getattr(tui, "_running", True) and loop < 15:
            loop += 1
            msgs = build_messages(tui.system_prompt, tui.memory.get())
            raw = tui._tui_stream(msgs, tui.current_model, f"◆ God Mode [Loop {loop}]")
            tui.memory.add("assistant", raw)
            tui.last_reply = raw
            tui.turns += 1

            if "[DONE]" in raw:
                tui._sys("◆  God Mode successfully completed the objective.")
                break

            cmd_match = re.search(r'\[CMD\]\s*(.+)', raw)
            edit_match = re.search(r'\[EDIT\]\s*([^ \n]+)\n(.*?)(?:\[ENDEDIT\]|$)', raw, re.DOTALL)

            feedback = ""
            if cmd_match:
                command = cmd_match.group(1).strip()
                tui._sys(f"◆  Executing: {command}")
                try:
                    r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
                    feedback = f"Exit code {r.returncode}\nSTDOUT:\n{r.stdout[:2000]}\nSTDERR:\n{r.stderr[:2000]}"
                except Exception as e:
                    feedback = f"Execution failed: {e}"
            elif edit_match:
                fpath = edit_match.group(1).strip()
                content = edit_match.group(2)
                tui._sys(f"◆  Writing file: {fpath}")
                try:
                    Path(fpath).parent.mkdir(parents=True, exist_ok=True)
                    Path(fpath).write_text(content, encoding='utf-8')
                    feedback = f"File {fpath} successfully updated."
                except Exception as e:
                    feedback = f"Write failed: {e}"
            else:
                feedback = "No valid [CMD], [EDIT], or [DONE] block found. Format must be exact. Only one action allowed. Do not output markdown code blocks around commands."

            tui.memory.add("user", f"System Feedback:\n{feedback}")
            tui.redraw()  # no sleep — just loop immediately

        tui.set_busy(False)
        tui.redraw()

    threading.Thread(target=_go, daemon=True).start()

@registry.register("/pane", "Launch a command in a side pane")
def cmd_pane(tui: LumiTUI, arg: str):
    if not arg or arg.strip() == "close":
        tui.clear_pane()
        tui.redraw()
        return

    tui.set_pane(
        title="live command",
        subtitle=arg.strip(),
        lines=[],
        footer="Esc close  ·  /pane close",
        close_on_escape=True,
    )

    def _read_pane():
        proc = subprocess.Popen(arg, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if tui.pane.lines is None:
            tui.pane.lines = []
        for line in iter(proc.stdout.readline, ""):
            if not getattr(tui, "_running", True) or not tui.pane_active:
                proc.terminate()
                break
            tui.pane.lines.append(line.rstrip("\n")[:160])
            tui.pane.lines = tui.pane.lines[-140:]
            tui.pane_lines_output = tui.pane.content()
            tui.redraw()
        exit_code = proc.wait()
        if tui.pane_active:
            tui.pane.footer = f"command finished  ·  exit {exit_code}  ·  /pane close"
            tui.redraw()

    threading.Thread(target=_read_pane, daemon=True).start()
    tui.redraw()

@registry.register("/apply", "Interactively apply code blocks from last LLM reply")
def cmd_apply(tui: LumiTUI, arg: str):
    if not tui.last_reply:
        tui._err("No LLM reply to apply.")
        return

    # Find markdown code blocks
    blocks = re.findall(r'```[a-zA-Z]*\n(.*?)```', tui.last_reply, re.DOTALL)
    if not blocks:
        tui._err("No markdown code blocks found in the last reply.")
        return

    target_file = arg.strip()
    if not target_file:
        tui._err("Usage: /apply <filename>")
        return

    code = blocks[0].strip() # Take the first code block

    # Temporarily exit TUI to use blocking shell input
    sys.stdout.write(_paste_off() + _alt_scroll_off() + _show_cur() + _alt_off())
    sys.stdout.flush()
    if hasattr(tui, 'original_termios') and tui.original_termios:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, tui.original_termios)

    print(f"\n\033[1;36m=== PROPOSED CHANGE FOR {target_file} ===\033[0m\n")
    print(code[:1000] + ("...\n[TRUNCATED]" if len(code) > 1000 else ""))
    print(f"\n\033[1;33mApply this code to {target_file}? [y/N]\033[0m ", end="")
    sys.stdout.flush()

    try:
        ans = input().strip().lower()
    except Exception:
        log.debug("apply input failed")
        ans = "n"

    if ans == "y":
        try:
            Path(target_file).parent.mkdir(parents=True, exist_ok=True)
            Path(target_file).write_text(code + "\n", encoding='utf-8')
            tui._sys(f"◆  Applied changes to {target_file}")
        except Exception as e:
            tui._err(f"Failed to write {target_file}: {e}")
    else:
        tui._sys(f"◆  Skipped applying to {target_file}")

    # Restore TUI
    tty.setraw(sys.stdin.fileno())
    sys.stdout.write(_alt_on() + _alt_scroll_on() + _paste_on() + _hide_cur() + "\033[J")
    sys.stdout.flush()
    tui.redraw()

@registry.register("/index", "Build local semantic codebase RAG index")
@bg_task
def cmd_index(tui: LumiTUI, arg: str):
    tui.set_busy(True)
    tui._sys("◆  Indexing local repository for RAG... (this may take a moment)")
    try:
        from src.tools.rag import build_index
        count = build_index(".")
        tui._sys(f"◆  Successfully indexed {count} files natively via SQLite.")
    except Exception as e:
        tui._err(f"Indexing failed: {e}")
    tui.set_busy(False)

@registry.register("/rag", "Query the local codebase index")
@bg_task
def cmd_rag(tui: LumiTUI, arg: str):
    if not arg:
        tui._err("Usage: /rag <question>")
        return

    tui.set_busy(True)
    try:
        from src.tools.rag import search_index
        results = search_index(arg, limit=3)
        if not results:
            tui._err("No results found or index not built. Run /index first.")
            tui.set_busy(False)
            return

        context = "Here are the top relevant files from the local index:\n\n"
        for filepath, content in results:
            context += f"--- {filepath} ---\n{content}\n\n"
            _context_cache.remember_text(f"rag:{filepath}", filepath, content, kind="rag")

        prompt = f"[rag: {arg}] Use the cached index results to answer the question."
        tui.memory.add("user", prompt)

        msgs = build_messages(tui.system_prompt, tui.memory.get(), model=tui.current_model)
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [RAG]")
        tui.memory.replace_last("user", f"/rag {arg}")
        tui.memory.add("assistant", raw)
        tui.last_reply = raw
        tui.turns += 1
    except Exception as e:
        tui._err(f"RAG search failed: {e}")
    tui.set_busy(False)

@registry.register("/voice", "Record 5s of voice and transcribe")
@bg_task
def cmd_voice(tui: LumiTUI, arg: str):
    audio_file = None
    tui.set_busy(True)
    try:
        seconds = parse_voice_duration(arg)
        tui._sys(f"◆  Listening for {seconds} second{'s' if seconds != 1 else ''}... Speak now!")
        audio_file = record_voice_clip(seconds)
        if not audio_file:
            raise RuntimeError("No recorder found. Install arecord, sox, or ffmpeg.")
        tui._sys("◆  Transcribing...")
        text, backend = transcribe_audio_file(audio_file)
        if not text:
            raise RuntimeError("No speech detected. Try again a little closer to the mic.")
        provider, _model, auto_routed = resolve_media_target(
            capability="audio_transcription",
            current_provider=get_provider() if tui.current_model != "council" else "",
            current_model=tui.current_model,
            configured_providers=get_available_providers(),
            get_models_fn=get_models,
        )
        tui.buf, tui.cur_pos = inject_text_at_cursor(tui.buf, tui.cur_pos, text)
        label = backend
        if auto_routed:
            label += f" via {PROV_NAME.get(provider, provider)}"
        tui._sys(f"Transcribed via {label}: '{text}'")
    except Exception as e:
        tui._err(f"Voice failed: {e}")
    finally:
        if audio_file:
            try:
                Path(audio_file).unlink(missing_ok=True)
            except OSError:
                pass
        tui.set_busy(False)

# ── Entry System Level ─────────────────────────────────────────────────────────────
def launch(): LumiTUI().run()

if __name__ == "__main__": launch()
