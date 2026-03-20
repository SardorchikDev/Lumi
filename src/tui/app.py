"""
◆ Lumi TUI — True Ultimate Edition
  Fully restored full command codebase without trimming, pristine thread-safety.
  Minimalist rounded conversation boundaries, original retro logo, perfect cursor math.
"""
from __future__ import annotations

import concurrent.futures
import io
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
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
    set_provider,
)
from src.chat.optimizer import (
    get_global_context_cache,
    get_global_telemetry,
    optimize_messages,
    route_model,
)
from src.chat.runtime import build_runtime_messages
from src.chat.streaming import stream_once
from src.memory.conversation_store import load_by_name, load_latest
from src.memory.conversation_store import (
    save as session_save,
)
from src.memory.longterm import (
    add_fact,
    build_memory_block,
    get_facts,
    get_persona_override,
)
from src.memory.short_term import ShortTermMemory
from src.prompts.builder import (
    build_system_prompt,
    is_coding_task,
    is_file_generation_task,
    load_persona,
)
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
from src.tui.notes import LittleNotesStore
from src.tui.review_cards import file_review_card
from src.tui.session import initialize_ui_state
from src.tui.state import AgentState, Msg, PaneState, ReviewCard, Store
from src.tui.views import OverlayView, PaneView, StarterView, TranscriptView, ViewStyle
from src.utils.autoremember import auto_extract_facts
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
from src.utils.intelligence import (
    detect_emotion,
    emotion_hint,
    is_complex_coding_task,
    needs_plan_first,
    should_search,
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
from src.utils.repo_profile import inspect_workspace
from src.utils.system_reports import build_doctor_report, build_status_report
from src.utils.web import fetch_url

try:
    from src.utils.tools import clipboard_get, clipboard_set, get_weather, load_project, read_pdf
except Exception:
    clipboard_get = clipboard_set = get_weather = load_project = read_pdf = None

_context_cache = get_global_context_cache()
_session_telemetry = get_global_telemetry()


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
    label: str = "◆ lumi",
) -> str:
    idx = tui.store.add(Msg("streaming", "", label))
    chunks: list[str] = []
    try:
        full = stream_once(
            client,
            model,
            messages,
            max_tokens=2048,
            temperature=0.2,
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
def _move(r, c): return f"{CSI}{r};{c}H"
def _erase_line(): return f"{CSI}2K"
def _clr_down(): return f"{CSI}J"

BG = "transparent"
BG_DARK = "#1d2230"
BG_HL = "#242a38"
BG_POP = "#181d28"
BORDER = "#31384a"
MUTED = "#6b7285"
COMMENT = "#6b7285"
FG_DIM = "#abb3c5"
FG = "#cfd6e6"
FG_HI = "#eef2ff"
BLUE = "#8fb4ff"
CYAN = "#86d3ff"
GREEN = "#9ad27a"
YELLOW = "#e3c277"
ORANGE = "#f2a97f"
RED = "#ef8b8b"
PURPLE = "#a7b7ff"
TEAL = "#78c8c8"

def B(h): return _fg(h) + _bold()
R = _reset()

SPINNER_FRAMES = list("⠋⠙⠚⠞⠦⠴⠲⠳⠓⠋")
PULSE_DOTS = ["   ", "·  ", " · ", "  ·", "···"]

def _rule(width, label=""):
    line_w = max(8, width - 4)
    if not label:
        return _fg(BORDER) + "─" * line_w + R
    plain = f" {label} "
    left = max(0, (line_w - len(plain)) // 2)
    right = max(0, line_w - len(plain) - left)
    return _fg(BORDER) + "─" * left + R + _fg(MUTED) + plain + R + _fg(BORDER) + "─" * right + R

def _popup_frame(top, left, width, title=""):
    header = _move(top, left) + _fg(BORDER) + " " + "─" * (width - 2) + " " + R
    if title:
        title_text = f" {title} "
        title_len = min(len(title_text), max(0, width - 4))
        title_text = title_text[:title_len]
        start = left + max(2, (width - title_len) // 2)
        header += _move(top, start) + _fg(MUTED) + title_text + R
    return header

def _popup_line(row, left, width, content="", tone=FG_DIM, selected=False):
    inner_w = max(0, width - 4)
    plain = content[:inner_w]
    bg = _bg(BG_HL if selected else BG_POP)
    return (
        _move(row, left)
        + _fg(BORDER) + "  " + R
        + bg + _fg(tone) + plain + " " * max(0, inner_w - len(plain)) + R
        + _fg(BORDER) + "  " + R
    )

def _rule(width, label=""):
    line_w = max(0, width - 4)
    if not label:
        return _fg(BORDER) + "─" * line_w + R
    plain = f" {label} "
    left = max(0, (line_w - len(plain)) // 2)
    right = max(0, line_w - len(plain) - left)
    return _fg(BORDER) + "─" * left + R + _fg(MUTED) + plain + R + _fg(BORDER) + "─" * right + R

PROV_NAME = {
    "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
    "mistral": "Mistral", "huggingface": "HuggingFace", "github": "GitHub Models",
    "cohere": "Cohere", "bytez": "Bytez", "cloudflare": "Cloudflare",
    "ollama": "Ollama", "council": "⚡ Council",
    "vercel": "Vercel AI", "vertex": "Vertex AI",
}
PROV_COL = {
    "gemini": CYAN, "groq": ORANGE, "openrouter": PURPLE, "mistral": RED,
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
            "/agent": "/agent fix the failing tests and keep the diff small",
            "/browse": "/browse src",
            "/file": "/file src/tui/app.py",
            "/fs": "/fs mkdir docs",
            "/git": "/git status",
            "/help": "/help",
            "/memory": "/memory",
            "/model": "/model",
            "/onboard": "/onboard",
            "/pane": "/pane pytest -q",
            "/permissions": "/permissions all",
            "/project": "/project .",
            "/rag": "/rag how does the agent patch files?",
            "/review": "/review src/chat/hf_client.py",
            "/search": "/search latest ruff rule docs",
            "/status": "/status",
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
        if name in {"/model", "/theme", "/persona", "/mode", "/offline", "/plugins", "/permissions", "/status", "/doctor", "/onboard", "/benchmark", "/quit", "/exit"}:
            return "settings"
        if name in {"/agent", "/scaffold", "/edit", "/review", "/fix", "/debug", "/improve", "/optimize", "/security", "/refactor", "/test", "/explain"}:
            return "code"
        if name in {"/search", "/web", "/image", "/data", "/pdf", "/rag", "/index"}:
            return "research"
        if name in {"/remember", "/memory", "/forget", "/save", "/load", "/sessions", "/export", "/find", "/note", "/todo"}:
            return "memory"
        if name in {"/browse", "/fs", "/file", "/project", "/shell", "/grep", "/tree", "/lint", "/fmt", "/run", "/apply", "/pane"}:
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

        starter_lines = self._build_starter_lines(chat_w)
        prompt_lines, prompt_cursor_row, prompt_cursor_col = self._prompt_bar(rows, cols, chat_w)
        prompt_height = len(prompt_lines)
        starter_rows = len(starter_lines)
        for i, line in enumerate(starter_lines, start=1):
            if i > rows:
                break
            w(_move(i, 1))
            w(_bg(BG) + _erase_line() + line + _bg(BG))

        transcript_top = 1 + starter_rows
        prompt_top = max(transcript_top, rows - prompt_height + 1)
        chat_rows = max(0, prompt_top - transcript_top)

        # Build and render chat area below the starter panel
        chat_lines = self._build_chat_lines(chat_w)
        total = len(chat_lines)
        offset = max(0, min(self.tui.scroll_offset, max(0, total - chat_rows)))
        end = total - offset
        start = max(0, end - chat_rows)
        chat_lines = chat_lines[start:end]

        while len(chat_lines) < chat_rows:
            chat_lines.insert(0, "")

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

        # Clear any rows below the transcript region and above the prompt
        for clear_row in range(transcript_top + chat_rows, prompt_top):
            w(_move(clear_row, 1) + _bg(BG) + _erase_line())

        if getattr(self.tui, "browser_visible", False): w(self._browser_popup(rows, cols))
        if self.tui.slash_visible and self.tui.slash_hits: w(self._slash_popup(rows, cols))
        if self.tui.path_visible and self.tui.path_hits: w(self._path_popup(rows, cols))
        if self.tui.picker_visible and self.tui.picker_items: w(self._picker_popup(rows, cols))
        if self.tui.notification: w(self._notification_bar(rows, cols))

        cur_col = prompt_cursor_col
        cursor_row = min(rows, prompt_cursor_row)
        w(_move(cursor_row, min(cur_col, cols - 1)))
        w(_show_cur())

        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def _build_starter_lines(self, width):
        intro = self._starter_view.build(width)
        return intro.header_lines + intro.trailing_lines

    def _build_chat_lines(self, width):
        return self._transcript_view.build(width)

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

    def _stat_info(self, chat_w):
        """Compute status string (plain + colored) for top bar."""
        tui = self.tui
        pname = PROV_NAME.get(tui.current_model if tui.current_model == "council" else get_provider(), get_provider())
        model = tui.current_model.split("/")[-1][:22]
        mem = tui.memory.get()
        if _session_telemetry.last_budget is not None:
            toks = _session_telemetry.last_budget.total_prompt_tokens
        elif len(mem) != tui._cached_tok_len:
            tui._cached_tok_count = sum(_tok(m["content"]) for m in mem)
            tui._cached_tok_len = len(mem)
            toks = tui._cached_tok_count
        else:
            toks = tui._cached_tok_count
        mode = f" {tui.response_mode}" if tui.response_mode else ""

        if tui.vessel_mode and tui.active_vessel:
            stat_str   = f"vessel {tui.active_vessel.lower()} · ~{toks:,}tk{mode}"
            stat_colored = _fg(RED) + _bold() + f"vessel {tui.active_vessel.lower()}" + R + _fg(COMMENT) + f" · ~{toks:,}tk{mode}"
        else:
            stat_str   = f"{pname} · {model} · ~{toks:,}tk{mode}"
            stat_colored = _fg(FG_DIM) + pname + R + _fg(COMMENT) + f" · {model} · ~{toks:,}tk{mode}"

        if tui.current_model == "council" and getattr(tui, "agents", None):
            names_plain, rail_segments = [], []
            for ag in tui.agents:
                ico = SPINNER_FRAMES[ag.frame % len(SPINNER_FRAMES)] if ag.st == "spin" else ("✓" if ag.st == "ok" else "✕")
                col = (CYAN if ag.lead else FG_DIM) if ag.st == "spin" else (GREEN if ag.st == "ok" else RED)
                nm  = ag.name.split()[0][:6]
                names_plain.append(nm)
                rail_segments.append(_fg(col) + ico + " " + nm + R)
            stat_str     = "Council " + " ".join(names_plain) + mode
            stat_colored = _fg(COMMENT) + "council" + _fg(FG_DIM) + " · " + _fg(FG_DIM) + "  ".join(rail_segments) + R

        return stat_str, stat_colored

    def _top_bar(self, rows, cols, chat_w):
        return _move(1, 1) + _bg(BG) + _erase_line() + _move(2, 1) + _bg(BG) + _erase_line()

    def _prompt_bar(self, rows, cols, chat_w):
        tui = self.tui
        text = tui.buf
        content_w = max(24, chat_w - 8)

        def chunk_plain(value: str) -> list[str]:
            logical = value.split("\n") or [""]
            out: list[str] = []
            for line in logical:
                if line == "":
                    out.append("")
                    continue
                start = 0
                while start < len(line):
                    out.append(line[start : start + content_w])
                    start += content_w
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
            visible_limit = 2 if (tui.multiline or "\n" in text or len(text) > content_w) else 1
            start = max(0, cursor_line - visible_limit + 1)
            visible = all_lines[start : start + visible_limit] or [""]
            cursor_row_rel = cursor_line - start

        left = " " * 2
        border = _fg(BORDER)
        lines = [left + border + "╭" + "─" * content_w + "╮" + R]
        if text:
            for segment in visible:
                lines.append(left + border + "│" + R + " " + _fg(FG_HI) + segment.ljust(content_w - 2) + R + " " + border + "│" + R)
        else:
            placeholder = "send a message"
            lines.append(left + border + "│" + R + " " + _fg(MUTED) + placeholder.ljust(content_w - 2) + R + " " + border + "│" + R)
        lines.append(left + border + "╰" + "─" * content_w + "╯" + R)

        prompt_top = rows - len(lines) + 1
        cursor_row = prompt_top + 1 + (cursor_row_rel if text else 0)
        cursor_col_abs = len(left) + 3 + cursor_col
        return lines, cursor_row, cursor_col_abs

    # kept for any external callers; delegates to the two new methods
    def _input_area(self, rows, cols, chat_w):
        prompt_lines, _cursor_row, _cursor_col = self._prompt_bar(rows, cols, chat_w)
        return self._top_bar(rows, cols, chat_w) + "".join(
            _move(rows - len(prompt_lines) + idx + 1, 1) + line
            for idx, line in enumerate(prompt_lines)
        )

    def _browser_popup(self, rows, cols):
        return self._overlay_view.browser_popup(rows, cols)

    def _slash_popup(self, rows, cols):
        return self._overlay_view.slash_popup(rows, cols)

    def _path_popup(self, rows, cols):
        return self._overlay_view.path_popup(rows, cols)

    def _picker_popup(self, rows, cols):
        return self._overlay_view.picker_popup(rows, cols)

    def _notification_bar(self, rows, cols):
        return self._overlay_view.notification_bar(rows, cols)


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
        self.browser_cwd = os.getcwd()
        self.workspace_profile = inspect_workspace(Path.cwd())

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

    def _make_system_prompt(self, coding_mode=False, file_mode=False):
        return build_system_prompt({**self.persona, **self.persona_override}, build_memory_block(), coding_mode, file_mode)

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
        with self._state_lock: self.busy = status
        self.redraw()

    def redraw(self): self.renderer.draw()

    # ── Inference / Generators  ─────────────────────────────────────────────
    def _tui_stream(self, messages, model, label="◆ lumi"):
        idx = self.store.add(Msg("streaming", "", label))
        if model == "council": return self._run_council_stream(idx, messages)

        chunks: list[str] = []
        try:
            def _on_delta(delta: str) -> None:
                chunks.append(delta)
                self.store.append(idx, delta)
                self.redraw()

            full = chat_stream(
                self.client,
                messages,
                model=model,
                max_tokens=8192,
                temperature=0.7,
                on_delta=_on_delta,
                on_status=lambda status: self._notify(status, duration=2.0),
            )
        except Exception as ex: return self._handle_stream_error(idx, ex, messages)
        self.store.finalize(idx)
        if not full:
            full = "".join(chunks)
        _session_telemetry.record_response(full)
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
                    set_provider(remaining[0]); self.client = get_client(); self.current_model = get_models(remaining[0])[0]
                    self.store.set_text(idx, "")
                    chunks: list[str] = []
                    def _on_delta(delta: str) -> None:
                        chunks.append(delta)
                        self.store.append(idx, delta)
                        self.redraw()
                    full = chat_stream(
                        self.client,
                        messages,
                        model=self.current_model,
                        max_tokens=8192,
                        temperature=0.7,
                        on_delta=_on_delta,
                        on_status=lambda status: self._notify(status, duration=2.0),
                    )
                    if not full:
                        full = "".join(chunks)
                    self.store.finalize(idx); return full
                except Exception as ex2: self.store.set_text(idx, f"⚠  {ex2}")
            else: self.store.set_text(idx, f"⚠  {ex}")
        else: self.store.set_text(idx, f"⚠  {ex}")
        self.store.finalize(idx); return f"⚠  {ex}"

    def _silent_call(self, prompt, model, max_tokens=8192):
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
            reply = self.client.chat.completions.create(
                model=routed,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
                stream=False,
            )
            usage = getattr(reply, "usage", None)
            completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
            reply = reply.choices[0].message.content.strip()
            _session_telemetry.record_response(reply, actual_tokens=completion_tokens)
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
        Execute an external AI CLI synchronously on the main thread.
        Called by the run() loop — never from a background thread.
        This is the only correct way: main thread owns the terminal.
        """
        binary = entry["binary"]
        name   = entry["name"]
        fd     = sys.stdin.fileno()

        # ── 1. Tear down Lumi's terminal state ────────────────────────────────
        # Exit alternate screen, show cursor, restore original cooked termios
        sys.stdout.write("\033[?1049l\033[?25h\033[0m")
        sys.stdout.flush()
        if self.original_termios:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, self.original_termios)
            except Exception:
                pass

        # Brief banner so the user knows what happened
        print(f"\n\033[38;2;187;154;247m◆ Entering {name}\033[0m  — exit normally to return to Lumi\n",
              flush=True)

        # ── 2. Run the CLI directly — no `script` wrapper ────────────────────
        # `script` corrupts full-TUI apps (claude, opencode, gemini, etc.)
        # We run the binary raw so it gets a clean controlling terminal.
        # Transcript capture is skipped for TUI tools; use the tool's own
        # built-in history / export if you need a log.
        exit_code = 1
        try:
            result    = subprocess.run([binary], env={**os.environ})
            exit_code = result.returncode
        except FileNotFoundError:
            print(f"\033[31m✗ {binary} not found in PATH\033[0m", flush=True)
        except KeyboardInterrupt:
            pass  # user Ctrl-C'd out of the CLI — that's fine

        # ── 3. Restore Lumi's terminal state ─────────────────────────────────
        print(f"\n\033[38;2;86;95;137m◆ Returned from {name}. Restoring Lumi…\033[0m\n",
              flush=True)
        time.sleep(0.05)

        try:
            tty.setraw(fd)
        except Exception:
            pass

        # Re-enter alternate screen, hide cursor, full repaint
        sys.stdout.write("\033[?1049h\033[?25l\033[2J")
        sys.stdout.flush()
        self.redraw()

        # ── 4. Inject return-context into memory and greet ───────────────────
        note = (f" Exit code: {exit_code}." if exit_code != 0 else "")
        sys_msg = (
            f"[SYSTEM NOTE: The user just returned from a {name} session.{note} "
            f"Warmly welcome them back and ask if they need help reviewing or continuing their work.]"
        )
        self.memory.add("system", sys_msg)

        user_msg = f"(Returned from {name}.)"
        self.store.add(Msg("user", user_msg))
        self.memory.add("user", user_msg)

        def _welcome():
            msgs = build_messages(self.system_prompt, self.memory.get())
            raw  = self._tui_stream(msgs, self.current_model)
            self.memory.add("assistant", raw)
            self.last_reply = raw
            self.turns     += 1
            self.set_busy(False)
            self.redraw()

        threading.Thread(target=_welcome, daemon=True).start()

    def run(self):
        self.persona = load_persona(); self.persona_override = get_persona_override()
        self.system_prompt = self._make_system_prompt()
        self.name = self.persona_override.get("name") or self.persona.get("name", "Lumi")

        try:
            p = get_provider(); self.current_model = get_models(p)[0]; self.client = get_client()
            self.little_notes.record_model(p, self.current_model)
        except Exception:
            log.exception("Failed to load provider/model")
            self.current_model = "unknown"; self.client = None

        self._loaded_plugins = load_plugins()
        for md_path in[Path("LUMI.md"), Path("lumi.md")]:
            if md_path.exists(): self.system_prompt += f"\n\n--- Project context (LUMI.md) ---\n{md_path.read_text().strip()}"; break

        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        self.original_termios = old
        def _cleanup(*_):
            try: termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                log.debug("Cleanup termios failed")
            sys.stdout.write(_show_cur() + _alt_off()); sys.stdout.flush()

        try: signal.signal(signal.SIGWINCH, lambda *_: self.redraw())
        except Exception:
            log.debug("SIGWINCH not supported")
        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))

        try:
            sys.stdout.write(_alt_on()); sys.stdout.flush(); tty.setraw(fd)
            with self._state_lock: self._running = True
            threading.Thread(target=self._guardian_loop, daemon=True).start()
            self.redraw()
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
            try: session_save(self.memory.get())
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
            session_save_fn=session_save,
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
    # Show a subtle toast but keep history visually empty so the splash header returns
    tui._notify("Chat cleared.")

@registry.register("/browse", "󰉋 Visual file tree explorer — navigate & inject files")
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
            icon = "󰉋" if e.is_dir() else "󰈔"
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

@registry.register("/file", "󰈔 Load a file into AI context: /file path/to/file")
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
        tui._sys(f"󰈔 Loaded `{rel}` ({line_count} lines) into context")
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

@registry.register("/load", "Load memory save string")
def cmd_load(tui: LumiTUI, arg: str):
    try:
        h = load_by_name(arg.strip()) if arg.strip() else load_latest()
        if h: tui.memory.set_history(h); tui.turns = len(h) // 2; tui._sys(f"Loaded {len(h)} messages")
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
    tui.multiline = not tui.multiline
    tui._notify(f"Multiline {'ON — Enter=newline, Ctrl+D=submit' if tui.multiline else 'OFF'}")

@registry.register("/remember", "Save a fact to long-term memory")
def cmd_rem(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /remember <fact>"); return
    n = add_fact(arg.strip()); tui.system_prompt = tui._make_system_prompt()
    tui._notify(f"Remembered fact #{n}")

@registry.register("/memory", "Show all stored long-term facts")
def cmd_mem(tui: LumiTUI, arg: str):
    f = get_facts()
    if f:
        lines = ["Long-term memory:"] + [f"  {i}. {val}" for i, val in enumerate(f, 1)]
        tui._sys("\n".join(lines))
    else: tui._sys("No facts stored. Use /remember <fact>")

@registry.register("/forget", "Remove a fact by number: /forget 3")
def cmd_forg(tui: LumiTUI, arg: str):
    f = get_facts()
    if not f: tui._err("No facts to forget"); return
    lines = ["Facts:"] + [f"  {i}. {val}" for i, val in enumerate(f, 1)]
    tui._sys("\n".join(lines) + "\n  Use: /forget <number>")

@registry.register("/short", "Next reply: be concise")
def cmd_short(tui: LumiTUI, arg: str): tui.response_mode = "short"; tui._notify("Mode: concise")
@registry.register("/detailed", "Next reply: be comprehensive")
def cmd_detailed(tui: LumiTUI, arg: str): tui.response_mode = "detailed"; tui._notify("Mode: detailed")
@registry.register("/bullets", "Next reply: bullet points only")
def cmd_bullets(tui: LumiTUI, arg: str): tui.response_mode = "bullets"; tui._notify("Mode: bullets")

# ── New utility commands ──────────────────────────────────────────────────────

@registry.register("/compact", "Toggle compact display mode")
def cmd_compact(tui: LumiTUI, arg: str): tui._compact = not tui._compact; tui._sys(f"Compact {'on' if tui._compact else 'off'}")

@registry.register("/tokens", "Show estimated token usage")
def cmd_tokens(tui: LumiTUI, arg: str):
    tui._sys(_session_telemetry.render_usage_report())

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

@registry.register("/sessions", "List saved sessions")
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

@registry.register("/plugins", "List loaded plugins")
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


@registry.register("/permissions", "Show plugin permissions: /permissions [all|plugins]")
def cmd_permissions(tui: LumiTUI, arg: str):
    scope = arg.strip().lower() or "summary"
    if scope not in {"summary", "all", "plugins"}:
        tui._err("Usage: /permissions [all|plugins]")
        return
    tui._sys(render_permission_report(scope))


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

HELP_CATEGORIES = register_command_groups(
    registry,
    build_messages=build_messages,
    read_file=_read_file,
    context_cache=_context_cache,
    get_available_providers=get_available_providers,
    log=log,
)

@registry.register("/mode", "/mode [cli]  Launch an AI coding CLI (claude, codex, gemini, opencode, aider, goose, qwen, plandex, kilo, amp, continue)")
def cmd_mode(tui: LumiTUI, arg: str):
    # ── Registry of all known AI CLI tools ────────────────────────────────────
    # Each entry: binary, display name, description, install command(s)
    CLI_REGISTRY = {
        "claude": {
            "binary":   "claude",
            "name":     "Claude Code",
            "maker":    "Anthropic",
            "desc":     "Repo-aware agentic coding — edits, refactors, git workflows",
            "install":  "npm install -g @anthropic-ai/claude-code",
            "install2": "curl -fsSL https://claude.ai/install.sh | bash",
        },
        "codex": {
            "binary":   "codex",
            "name":     "Codex CLI",
            "maker":    "OpenAI",
            "desc":     "Local agentic coding with o4-mini / GPT-5, sandboxed execution",
            "install":  "npm install -g @openai/codex",
        },
        "gemini": {
            "binary":   "gemini",
            "name":     "Gemini CLI",
            "maker":    "Google",
            "desc":     "Free tier, Gemini 2.5 Pro, repo-aware, MCP support",
            "install":  "npm install -g @google/gemini-cli",
        },
        "opencode": {
            "binary":   "opencode",
            "name":     "OpenCode",
            "maker":    "SST",
            "desc":     "75+ providers, LSP integration, multi-session, privacy-first",
            "install":  "npm install -g opencode-ai",
            "install2": "curl -fsSL https://opencode.ai/install | bash",
        },
        "aider": {
            "binary":   "aider",
            "name":     "Aider",
            "maker":    "Paul Gauthier",
            "desc":     "Git-first pair programmer, auto-commits, 130+ languages",
            "install":  "pip install aider-chat --break-system-packages",
            "install2": "pipx install aider-chat",
        },
        "goose": {
            "binary":   "goose",
            "name":     "Goose",
            "maker":    "Block (Square)",
            "desc":     "Fully autonomous agent — execute, debug, deploy; MCP native",
            "install":  "curl -fsSL https://github.com/block/goose/releases/latest/download/install.sh | bash",
        },
        "qwen": {
            "binary":   "qwen",
            "name":     "Qwen Code",
            "maker":    "Alibaba",
            "desc":     "Qwen3-Coder optimised, 1k free req/day via OAuth, 480B MoE",
            "install":  'bash -c "$(curl -fsSL https://qwen-code-assets.oss-cn-hangzhou.aliyuncs.com/installation/install-qwen.sh)"',
        },
        "plandex": {
            "binary":   "plandex",
            "name":     "Plandex",
            "maker":    "Plandex",
            "desc":     "Plan-first agent, 2M token context, multi-file structured tasks",
            "install":  "curl -sL https://plandex.ai/install.sh | bash",
        },
        "kilo": {
            "binary":   "kilo",
            "name":     "Kilo Code",
            "maker":    "Kilo-Org",
            "desc":     "500+ models, Architect/Debug/Orchestrator modes, Agent Skills, MCP native",
            "install":  "npm install -g @kilocode/cli",
        },
        "amp": {
            "binary":   "amp",
            "name":     "Amp",
            "maker":    "Sourcegraph",
            "desc":     "Unconstrained token usage, subagents, thread sharing, GPT-5 Oracle mode",
            "install":  "npm install -g @sourcegraph/amp",
            "install2": "curl -fsSL https://ampcode.com/install.sh | bash",
        },
        "continue": {
            "binary":   "cn",
            "name":     "Continue CLI",
            "maker":    "Continue.dev",
            "desc":     "Session history, resume tasks, headless/CI mode, any model via config",
            "install":  "npm install -g @continuedev/cli",
        },
    }

    # ── Helper: detect installed tools ────────────────────────────────────────
    def _installed(entry: dict) -> bool:
        return shutil.which(entry["binary"]) is not None

    # ── No arg → show status table ─────────────────────────────────────────────
    target = arg.strip().lower()

    if not target:
        lines = ["◆  AI CLI Launcher — available tools:\n"]
        for key, e in CLI_REGISTRY.items():
            status = "✓ installed" if _installed(e) else "✗ not found"
            mark   = "●" if _installed(e) else "○"
            lines.append(f"  {mark} /mode {key:<12} {e['name']:<16} [{e['maker']}]  {status}")
        lines.append("\n  Usage: /mode <name>  — suspends Lumi, launches the CLI, returns when you exit")
        lines.append("  If not installed, Lumi will show the install command.")
        tui._sys("\n".join(lines))
        tui.redraw()
        return

    # ── Validate ───────────────────────────────────────────────────────────────
    if target not in CLI_REGISTRY:
        names = ", ".join(CLI_REGISTRY.keys())
        tui._err(f"Unknown CLI: '{target}'. Choose from: {names}")
        return

    entry = CLI_REGISTRY[target]

    # ── Not installed → show install hints ────────────────────────────────────
    if not _installed(entry):
        install_hint = f"  $ {entry['install']}"
        if "install2" in entry:
            install_hint += f"\n  $ {entry['install2']}  (alternative)"
        tui._sys(
            f"◆  {entry['name']} is not installed.\n\n"
            f"  Install with:\n{install_hint}\n\n"
            f"  After installing, run /mode {target} again."
        )
        tui.redraw()
        return

    # ── Signal main loop — it will call _do_handoff() on the main thread ─────
    tui._sys(f"◆  Launching {entry['name']}…  Lumi will resume when you exit.")
    tui.redraw()
    tui._pending_handoff = entry   # consumed by run() before next key read

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
    sys.stdout.write("\033[?1049l\033[?25h")
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
    sys.stdout.write("\033[?1049h\033[?25l\033[J")
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
        provider, _model, auto_routed = resolve_media_target(
            capability="audio_transcription",
            current_provider=get_provider() if tui.current_model != "council" else "",
            current_model=tui.current_model,
            configured_providers=get_available_providers(),
            get_models_fn=get_models,
        )
        text, backend = transcribe_audio_file(audio_file)
        if not text:
            raise RuntimeError("No speech detected. Try again a little closer to the mic.")
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
