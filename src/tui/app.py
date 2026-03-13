"""
◆ Lumi TUI — True Ultimate Edition
  Fully restored full command codebase without trimming, pristine thread-safety.
  Minimalist rounded conversation boundaries, original retro logo, perfect cursor math.
"""
from __future__ import annotations

import concurrent.futures
import functools
import io
import json
import logging
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import textwrap
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
from src.chat.hf_client import (
    get_client, get_models, get_provider, set_provider, get_available_providers,
)
from src.memory.short_term import ShortTermMemory
from src.memory.longterm import (
    get_facts, add_fact, remove_fact, clear_facts, build_memory_block,
    get_persona_override, set_persona_override, clear_persona_override,
)
from src.memory.conversation_store import (
    save as session_save, load_latest, load_by_name, list_sessions, delete_session,
)
from src.prompts.builder import (
    load_persona, build_system_prompt, build_messages,
    is_coding_task, is_file_generation_task,
)
from src.agents.council import council_ask, _get_available_agents, LEAD_AGENTS, classify_task
from src.tools.search import search, search_display
from src.utils.web import fetch_url
from src.utils.plugins import load_plugins, get_commands, dispatch as plugin_dispatch
from src.utils.intelligence import (
    detect_emotion, emotion_hint, detect_topic,
    should_search, is_complex_coding_task, needs_plan_first,
)
from src.utils.autoremember import auto_extract_facts
from src.utils.export import export_md
from src.utils.filesystem import is_create_request, generate_file_plan, write_file_plan, format_creation_summary

try:
    from src.utils.tools import clipboard_get, clipboard_set, get_weather, load_project, read_pdf
except Exception:
    clipboard_get = clipboard_set = get_weather = load_project = read_pdf = None

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
BG_DARK = "#24283b"
BG_HL = "#292e42"
BG_POP = "#1f2335"
BORDER = "#414868"
MUTED = "#565f89"
COMMENT = "#565f89"
FG_DIM = "#a9b1d6"
FG = "#c0caf5"
FG_HI = "#cfc9c2"
BLUE = "#7aa2f7"
CYAN = "#7dcfff"
GREEN = "#9ece6a"
YELLOW = "#e0af68"
ORANGE = "#ff9e64"
RED = "#f7768e"
PURPLE = "#bb9af7"
TEAL = "#2ac3de"

def B(h): return _fg(h) + _bold()
R = _reset()

SPINNER_FRAMES = list("⠋⠙⠚⠞⠦⠴⠲⠳⠓⠋")
PULSE_DOTS = ["   ", "·  ", " · ", "  ·", "···"]

PROV_NAME = {
    "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
    "mistral": "Mistral", "huggingface": "HuggingFace", "github": "GitHub Models",
    "cohere": "Cohere", "cloudflare": "Cloudflare", "ollama": "Ollama", "council": "⚡ Council",
}
PROV_COL = {
    "gemini": CYAN, "groq": ORANGE, "openrouter": PURPLE, "mistral": RED,
    "huggingface": YELLOW, "github": FG_HI, "cohere": GREEN,
    "cloudflare": ORANGE, "ollama": FG_DIM, "council": PURPLE,
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
    fd = sys.stdin.fileno()
    while True:
        try:
            ch = os.read(fd, 1)
            if not ch: return ""
            if ch == b"\x1b":
                r, _, _ = select.select([fd], [],[], 0.05)
                if r:
                    seq = os.read(fd, 16)
                    full = ch + seq
                    if full == b"\x1b[A": return "UP"
                    if full == b"\x1b[B": return "DOWN"
                    if full == b"\x1b[C": return "RIGHT"
                    if full == b"\x1b[D": return "LEFT"
                    if full == b"\x1b[H": return "HOME"
                    if full == b"\x1b[F": return "END"
                    if full == b"\x1b[3~": return "DELETE"
                    if full == b"\x1b[5~": return "PGUP"
                    if full == b"\x1b[6~": return "PGDN"
                    if full == b"\x1b[1;5C": return "CTRL_RIGHT"
                    if full == b"\x1b[1;5D": return "CTRL_LEFT"
                return "ESC"

            if ch in (b"\r", b"\n"): return "ENTER"
            if ch in (b"\x7f", b"\x08"): return "BACKSPACE"
            if ch == b"\x09": return "TAB"
            if ch == b"\x0c": return "CTRL_L"
            if ch == b"\x11": return "CTRL_Q"
            if ch == b"\x03": return "CTRL_C"
            if ch == b"\x0e": return "CTRL_N"
            if ch == b"\x17": return "CTRL_W"
            if ch == b"\x01": return "HOME"
            if ch == b"\x05": return "END"
            if ch == b"\x15": return "CTRL_U"
            if ch == b"\x12": return "CTRL_R"

            buf = ch
            while True:
                try: return buf.decode("utf-8")
                except UnicodeDecodeError:
                    r, _, _ = select.select([fd], [],[], 0.1)
                    if r: buf += os.read(fd, 1)
                    else: return ""
        except InterruptedError:
            continue

# ══════════════════════════════════════════════════════════════════════════════
#  Command Infrastructure
# ══════════════════════════════════════════════════════════════════════════════
class CommandRegistry:
    def __init__(self):
        self.commands = {}
    def register(self, name, desc):
        def decorator(func):
            self.commands[name] = {"func": func, "desc": desc}
            return func
        return decorator
    def get_hits(self, query):
        return [(cmd, data["desc"]) for cmd, data in self.commands.items() if query in cmd]

registry = CommandRegistry()

class Msg:
    __slots__ = ("role", "text", "ts", "label")
    def __init__(self, role, text, label=""):
        self.role, self.text, self.ts, self.label = role, text, _hm(), label

class Store:
    def __init__(self):
        self._lock, self._data = threading.Lock(),[]
    def add(self, m):
        with self._lock: self._data.append(m); return len(self._data) - 1
    def append(self, idx, chunk):
        with self._lock: self._data[idx].text += chunk
    def set_text(self, idx, text):
        with self._lock: self._data[idx].text = text
    def finalize(self, idx):
        with self._lock: 
            if self._data[idx].role == "streaming": self._data[idx].role = "assistant"
    def clear(self):
        with self._lock: self._data.clear()
    def snapshot(self):
        with self._lock: return list(self._data)

class AgentState:
    def __init__(self, aid, name, lead=False):
        self.aid, self.name, self.lead = aid, name, lead
        self.st, self.conf, self.t, self.frame = "spin", "", "", 0
    def done(self, ok, conf, t):
        self.st, self.conf, self.t = ("ok" if ok else "fail"), conf, t

# ══════════════════════════════════════════════════════════════════════════════
#  Rendering Graphics & Bounding Boxes
# ══════════════════════════════════════════════════════════════════════════════
class Renderer:
    def __init__(self, tui):
        self.tui = tui
        self._lock = threading.Lock()

    def draw(self):
        with self._lock:
            self._draw()

    def _draw(self):
        rows, cols = _term_size()
        pane_active = getattr(self.tui, "pane_active", False)
        chat_w = int(cols * 0.6) if pane_active else cols
        pane_w = cols - chat_w - 1 if pane_active else 0
        buf =[]
        w = buf.append

        w(_hide_cur())
        w(_move(1, 1))

        # Bottom 2 rows allocated specifically to rendering floating Prompt Frame exactly!
        chat_rows = rows - 2 
        chat_lines = self._build_chat_lines(chat_w)
        
        total = len(chat_lines)
        offset = max(0, min(self.tui.scroll_offset, max(0, total - chat_rows)))
        end = total - offset
        start = max(0, end - chat_rows)
        chat_lines = chat_lines[start:end]
        
        while len(chat_lines) < chat_rows:
            chat_lines.insert(0, "")

        for i in range(chat_rows):
            w(_move(i + 1, 1))
            cl = chat_lines[i] if i < len(chat_lines) else ""
            
            if pane_active:
                cl_stripped = _strip_ansi(cl)
                pad = max(0, chat_w - len(cl_stripped))
                cl_padded = cl + " " * pad
                
                pane_lines = getattr(self.tui, "pane_lines_output", [])
                p_idx = i - chat_rows + len(pane_lines)
                pane_line = pane_lines[p_idx] if p_idx >= 0 and p_idx < len(pane_lines) else ""
                pane_line_padded = pane_line.ljust(pane_w)[:pane_w]
                
                w(_bg(BG) + cl_padded + _fg(BORDER) + "│" + _fg(FG) + pane_line_padded + _bg(BG))
            else:
                w(_bg(BG) + _erase_line() + cl + _bg(BG))

        # When large overlays are visible, don't draw the bottom hint/prompt to avoid ASCII overlap
        if self.tui.picker_visible or getattr(self.tui, "browser_visible", False):
            w(_move(rows - 1, 1) + _bg(BG) + _erase_line())
            w(_move(rows, 1) + _bg(BG) + _erase_line())
        else:
            w(self._input_area(rows, cols, chat_w))

        if getattr(self.tui, "browser_visible", False): w(self._browser_popup(rows, cols))
        if self.tui.slash_visible and self.tui.slash_hits: w(self._slash_popup(rows, cols))
        if self.tui.picker_visible and self.tui.picker_items: w(self._picker_popup(rows, cols))
        if self.tui.notification: w(self._notification_bar(rows, cols))

        disp_w = chat_w - 7
        scroll = max(0, self.tui.cur_pos - disp_w + 1)
        cur_col = 5 + (self.tui.cur_pos - scroll) 
        
        # Keep inside matrix range so automatic Line feeds don't kill buffer UI natively!
        w(_move(rows, min(cur_col, cols - 1)))
        w(_show_cur())
        
        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def _build_chat_lines(self, width):
        msgs = self.tui.store.snapshot()
        lines =[]
        inner = max(30, width - 6)
        if not msgs:
            ver = "v0.3.4"

            # ── Braille ruby gem ─────────────────────────────────────────────
            P  = _fg(PURPLE)
            C  = _fg(CYAN)
            BL = _fg(BLUE)
            T  = _fg(TEAL)

            sprite = [
                (C  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (C  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⠋⠙⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (C  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⠃⠀⠀⠘⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R,  30),
                (P  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠇⠀⠀⠀⠀⠸⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (P  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (P  + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (BL + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⠀⠀⠀⠀⠀⠀⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (BL + "⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣤⣾⣶⠶⠶⠶⠶⣶⣷⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀" + R, 30),
                (BL + "⠀⠀⠀⠀⠀⢀⣠⠶⠋⠉⠀⠀⢻⣆⠀⠀⣰⡟⠀⠀⠉⠙⠶⣄⡀⠀⠀⠀⠀⠀" + R, 30),
                (T  + "⠀⠀⠀⠀⣴⠟⠁⠀⠀⠀⠀⠀⠀⠻⣦⣴⠟⠀⠀⠀⠀⠀⠀⠈⠻⣦⠀⠀⠀⠀" + R, 30),
                (T  + "⠀⠀⢀⡾⠁⠀⠀⠀⠀⠀⠀⠀⢀⣴⠟⠻⣦⡀⠀⠀⠀⠀⠀⠀⠀⠈⢷⡀⠀⠀" + R, 30),
                (T  + "⠀⢠⣿⠁⠀⠀⠀⠀⢀⣀⣤⠾⠛⠁⠀⠀⠈⠛⠷⣤⣀⡀⠀⠀⠀⠀⠈⣿⡄⠀" + R, 30),
                (T  + "⠀⠘⠛⠓⠒⠒⠛⠛⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠛⠛⠒⠒⠚⠛⠃⠀" + R, 30),
            ]
            anchor_w = 30

            sub_vis = f"lumi  {ver}"
            anchor_w = max(anchor_w, len(sub_vis))
            cpad = max(0, (width - anchor_w) // 2)

            chat_rows = _term_size()[0] - 4
            top_pad = max(2, (chat_rows - len(sprite) - 4) // 2)
            lines += [""] * top_pad

            for row_str, row_w in sprite:
                spad = (anchor_w - row_w) // 2
                lines.append(" " * cpad + " " * spad + row_str)

            lines.append("")
            wpad = (anchor_w - len(sub_vis)) // 2
            lines.append(
                " " * cpad + " " * wpad +
                B(FG_HI) + "lumi" + R +
                _fg(BORDER) + "  " + ver + R
            )

            lines += [""] * max(0, chat_rows - len(lines) - 1)
            return lines

        # Optional pinned agent plan panel (from /agent)
        if getattr(self.tui, "agent_active_objective", None) and getattr(self.tui, "agent_tasks", None):
            lines.append("")
            lines.append("  " + _fg(COMMENT) + "Agent objective: " + _fg(FG_HI) + self.tui.agent_active_objective + R)
            for idx, task in enumerate(self.tui.agent_tasks, start=1):
                bullet = "○"
                label = task.get("text", "")
                for ln in textwrap.wrap(label, inner - 6) or [label]:
                    lines.append("    " + _fg(MUTED) + bullet + " " + _fg(FG) + ln + R)
                    bullet = " "  # only first line gets the bullet
            lines.append("")

        for msg in msgs:
            if msg.role == "user":
                # Gemini-style: just indented text, no rail
                lines.append("  " + _fg(FG_DIM) + "you  " + _fg(COMMENT) + msg.ts + R)
                for ln in textwrap.wrap(msg.text, inner) or [msg.text]:
                    lines.append("  " + _fg(FG_HI) + ln + R)
                lines.append("")

            elif msg.role in ("assistant", "streaming"):
                label = msg.label or "◆ Lumi"
                is_stream = msg.role == "streaming"
                t_now = time.time()
                # Animated streaming cursor block
                if is_stream:
                    blink_on = int(t_now * 4) % 2 == 0
                    cursor = (" " + _fg(CYAN) + ("▋" if blink_on else " ") + R)
                else:
                    cursor = ""

                if self.tui.vessel_mode and self.tui.active_vessel:
                    rail_col = RED
                    hdr_col = B(RED)
                    if "vessel" not in label:
                        label = f"◈ Vessel [{self.tui.active_vessel}]"
                else:
                    rail_col = PURPLE
                    hdr_col = B(PURPLE)

                a_pre = "  "
                # Header: minimal label + faint timestamp
                lines.append(
                    "  " +
                    hdr_col + label + R +
                    "  " + _fg(COMMENT) + msg.ts + R
                )
                raw_lines = msg.text.split("\n") if msg.text else [""]
                
                in_code = False
                code_w = min(inner - 2, 92)
                lpre = a_pre
                
                for ln in raw_lines:
                    if ln.startswith("```"):
                        if not in_code:
                            in_code = True
                            code_lang = ln[3:].strip()
                            lt = f" {code_lang}" if code_lang else " code"
                            lang_badge = _fg(CYAN) + _bold() + lt + R
                            bar_fill = "─" * max(0, code_w - len(lt) - 1)
                            lines.append(
                                lpre +
                                _fg(BORDER) + "╭" + _fg(TEAL) + "─" + R +
                                lang_badge +
                                _fg(BORDER) + " " + bar_fill + "╮" + R
                            )
                            _code_lineno = [0]  # mutable counter
                        else:
                            in_code = False
                            bar_fill = "─" * max(0, code_w)
                            lines.append(
                                lpre + _fg(BORDER) + "╰" + bar_fill + "╯" + R
                            )
                        continue
                        
                    if in_code:
                        _code_lineno[0] += 1
                        lineno_str = _fg(BORDER) + f"{_code_lineno[0]:>3} " + R
                        mcc = code_w - 6
                        for sl in (textwrap.wrap(ln, mcc) if len(ln) > mcc else [ln]) or [""]:
                            hi = _syntax_hi(sl)
                            pad = max(0, mcc - _visible_len(sl))
                            lines.append(
                                lpre + _bg(BG_DARK) + lineno_str +
                                hi + _bg(BG_DARK) + " " * pad + R
                            )
                            lineno_str = _fg(BORDER) + "    " + R  # continuation lines no number
                        continue
                        
                    # Standard Markdown Formatting inside AI Bubbles
                    if re.match(r"^#{1,6} ", ln):
                        lvl = len(ln) - len(ln.lstrip("#"))
                        col =[BLUE, CYAN, TEAL, FG_HI, FG, FG_DIM][min(lvl - 1, 5)]
                        lines.append(lpre) # Extra padding above headers
                        txt = ln.lstrip("# ")
                        lines.append(lpre + _fg(col) + _bold() + txt + R)
                        
                    elif ln.startswith("> "):
                        body = ln[2:]
                        lines.append(lpre + _fg(TEAL) + "▍" + _italic() + _fg(FG_DIM) + " " + body + R)
                    elif re.match(r"^[-*•] ", ln):
                        body = ln[2:]
                        lines.append(lpre + _fg(CYAN) + "  ◦ " + _fg(FG) + body + R)
                    elif re.match(r"^\d+\. ", ln):
                        m = re.match(r'^(\d+)\. (.*)', ln)
                        if m:
                            num, body = m.group(1), m.group(2)
                            lines.append(lpre + _fg(PURPLE) + _bold() + f"  {num}." + R + " " + _fg(FG) + body + R)
                        else:
                            lines.append(lpre + _fg(FG) + ln + R)
                    elif ln.strip() == "":
                        lines.append(lpre)
                    else:
                        rendered = self._inline(ln)
                        if len(_strip_ansi(ln)) <= inner:
                            lines.append(lpre + rendered + R)
                        else:
                            for wl in (textwrap.wrap(_strip_ansi(ln), inner) or [ln]):
                                lines.append(lpre + _fg(FG) + wl + R)
                                
                if in_code: lines.append(lpre + _bg(BG_DARK) + _fg(RED) + "[STREAM PAUSED]" + " " * (code_w - 15) + R)
                if cursor: lines[-1] += cursor
                    
                lines.append("")

            elif msg.role == "system":
                for sln in msg.text.split("\n"):
                    for wl in (textwrap.wrap(sln, inner) if sln.strip() else [""]):
                        lines.append("  " + _fg(TEAL) + wl + R)
                lines.append("")

            elif msg.role == "error":
                lines.append("  " + _fg(RED) + "⚠  " + msg.text + R)
                lines.append("")

        return lines

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

    def _input_area(self, rows, cols, chat_w):
        tui = self.tui
        pname = PROV_NAME.get(tui.current_model if tui.current_model == "council" else get_provider(), get_provider())
        model = tui.current_model.split("/")[-1][:22]
        mem = tui.memory.get()
        if len(mem) != tui._cached_tok_len:
            tui._cached_tok_count = sum(_tok(m["content"]) for m in mem)
            tui._cached_tok_len = len(mem)
        toks = tui._cached_tok_count

        mode = f" {tui.response_mode}" if tui.response_mode else ""

        if tui.vessel_mode and tui.active_vessel:
            stat_str = f" ⬡ VESSEL [{tui.active_vessel.upper()}] · ~{toks:,}tk{mode} "
            stat_colored = _fg(RED) + _bold() + f"⬡ VESSEL [{tui.active_vessel.upper()}]" + R + _fg(COMMENT) + f" · ~{toks:,}tk{mode}"
        else:
            stat_str = f" {pname} · {model} · ~{toks:,}tk{mode} "
            stat_colored = _fg(FG_DIM) + f"{pname}" + R + _fg(COMMENT) + f" · {model} · ~{toks:,}tk{mode}"

        # Council agent rail (animated) in status when active
        if tui.current_model == "council" and getattr(tui, "agents", None):
            names_plain = []
            rail_segments = []
            for ag in tui.agents:
                if ag.st == "spin":
                    ico = SPINNER_FRAMES[ag.frame % len(SPINNER_FRAMES)]
                    col = CYAN if ag.lead else FG_DIM
                elif ag.st == "ok":
                    ico = "✓"
                    col = GREEN
                else:
                    ico = "✕"
                    col = RED
                nm = ag.name.split()[0][:6]
                names_plain.append(nm)
                rail_segments.append(_fg(col) + ico + " " + nm + R)
            stat_str = " Council " + " ".join(names_plain) + mode
            stat_colored = (
                _fg(COMMENT)
                + "Council "
                + _fg(FG_DIM)
                + " | "
                + _fg(FG)
                + "  ".join(rail_segments)
                + R
            )

        # Top line: hint on the left, model/status on the right
        hint_plain = "  /help · Tab · Ctrl+R · Ctrl+Q"
        hint_colored = (
            _fg(BORDER) + "  " +
            _fg(MUTED) + "/help · Tab · Ctrl+R · Ctrl+Q" +
            R
        )

        hint_len = _visible_len(hint_plain)
        stat_len = _visible_len(stat_str)
        total_needed = hint_len + stat_len + 4

        if total_needed <= chat_w:
            space_between = max(1, chat_w - hint_len - stat_len - 2)
            gap = min(space_between, 16)
            top_line = " " + hint_colored + " " * gap + stat_colored
        else:
            # If the terminal is very narrow, fall back to just right-aligned status
            top_w = max(0, chat_w - stat_len - 2)
            top_line = " " * top_w + stat_colored + " "

        top = _move(rows - 1, 1) + _bg(BG) + _erase_line() + top_line + R

        # Prompt chevron
        t_now = time.time()
        if tui.busy:
            frame = int(t_now * 10) % len(SPINNER_FRAMES)
            sym  = _fg(CYAN) + SPINNER_FRAMES[frame] + " " + R
            hint = _fg(MUTED) + _italic() + "thinking" + PULSE_DOTS[int(t_now * 2) % len(PULSE_DOTS)] + R
        else:
            sym  = _fg(BLUE) + _bold() + "❯ " + R
            hint = ""

        txt = tui.buf
        disp_w = chat_w - 7
        scroll = max(0, tui.cur_pos - disp_w + 1)
        shown = txt[scroll:scroll + disp_w]

        bot = _move(rows, 1) + _bg(BG) + _erase_line() + "  " + sym + _fg(FG_HI) + shown + hint + R

        return top + bot

    def _browser_popup(self, rows, cols):
        tui = getattr(self, "tui", None)
        if not tui: return ""
        
        items = tui.browser_items; sel = tui.browser_sel
        pop_w = min(60, cols - 6); pop_h = min(20, rows - 6)
        left = max(2, (cols - pop_w) // 2); top = max(2, (rows - pop_h) // 2)
        
        # Display window
        disp_items = []
        if items:
            total = len(items)
            start = max(0, min(sel - pop_h // 2, total - pop_h + 2))
            disp_items = items[start:start + pop_h - 2]
            
            # Recalculate local selection index
            local_sel = sel - start
        else:
            local_sel = -1
            
        out = [_move(top, left) + _fg(BORDER) + "╭" + "─" * (pop_w - 2) + "╮" + R]
        
        # Header (shows CWD)
        cwd = tui.browser_cwd
        if len(cwd) > pop_w - 6: cwd = "..." + cwd[-(pop_w - 9):]
        pad = max(0, pop_w - 4 - len(cwd))
        out.append(_move(top + 1, left) + _fg(BORDER) + "│ " + _fg(BLUE) + cwd + " " * pad + _fg(BORDER) + " │" + R)
        out.append(_move(top + 2, left) + _fg(BORDER) + "├" + "─" * (pop_w - 2) + "┤" + R)
        
        row = top + 3
        for i, item in enumerate(disp_items):
            itype, iname, ipath = item
            is_sel = (i == local_sel)
            bg_ = _bg(BG_HL) if is_sel else _bg(BG)
            
            if iname == "..":
                icon = "󰜄"; color = _fg(MUTED); name_color = _fg(FG_HI) if is_sel else _fg(FG)
            elif itype == "dir":
                icon = "󰉋"; color = _fg(BLUE); name_color = _fg(FG_HI) if is_sel else _fg(FG)
            else:
                icon = "󰈔"; color = _fg(FG_DIM); name_color = _fg(FG_HI) if is_sel else _fg(MUTED)
                
            disp_name = iname[:pop_w - 10]
            sp = max(0, pop_w - 4 - len(disp_name) - 2)
            pointer = "› " if is_sel else "  "
            out.append(
                _move(row, left)
                + _bg(BG)
                + _fg(BORDER) + "│ "
                + bg_
                + color + icon + " "
                + name_color + pointer + disp_name
                + " " * max(0, sp - 2) + R
                + _fg(BORDER) + " │" + R
            )
            row += 1
            
        # Empty space padding if list is short
        while row < top + pop_h - 1:
            out.append(_move(row, left) + _fg(BORDER) + "│ " + " " * (pop_w - 4) + " │" + R)
            row += 1
            
        out.append(_move(row, left) + _fg(BORDER) + "├" + "─" * (pop_w - 2) + "┤" + R)
        row += 1
        bot_txt = "Esc Close  ·  ↑↓ Move  ·  Enter/→ Open  ·  ← Back"
        out.append(_move(row, left) + _fg(BORDER) + "│ " + _fg(COMMENT) + bot_txt + " " * max(0, pop_w - 4 - len(bot_txt)) + _fg(BORDER) + " │" + R)
        row += 1
        out.append(_move(row, left) + _fg(BORDER) + "╰" + "─" * (pop_w - 2) + "╯" + R)
        
        return "".join(out)

    def _slash_popup(self, rows, cols):
        hits = self.tui.slash_hits; sel = self.tui.slash_sel; pop_w = min(58, cols - 4)
        n = min(len(hits), 10); top = rows - 2 - n - 2; left = max(2, (cols - pop_w) // 2)
        out = [_move(top, left) + _fg(BORDER) + "╭" + "─" * (pop_w - 2) + "╮" + R]
        for i, (cmd, desc) in enumerate(hits[:10]):
            is_sel = (i == sel)
            cc = _fg(CYAN) + _bold() if is_sel else _fg(BLUE)
            dc = _fg(FG_HI) if is_sel else _fg(MUTED)
            bg_ = _bg(BG_HL) if is_sel else _bg(BG)
            d_cmd = f"{cmd[:15]:<16}"
            d_desc = desc[:max(0, pop_w - 26)]
            pad2 = max(0, pop_w - 22 - len(d_desc))
            pointer = "› " if is_sel else "  "
            out.append(
                _move(top + 1 + i, left)
                + _fg(BORDER) + "│ "
                + bg_ + cc + pointer + d_cmd + R
                + bg_ + dc + d_desc + " " * pad2 + R
                + _fg(BORDER) + " │" + R
            )
        out.append(_move(top + 1 + n, left) + _fg(BORDER) + "╰" + "─" * (pop_w - 2) + "╯" + R)
        return "".join(out)

    def _picker_popup(self, rows, cols):
        items = self.tui.picker_items; sel = self.tui.picker_sel
        pop_w = min(64, cols - 4)
        left = max(2, (cols - pop_w) // 2); top = max(2, (rows - len(items) - 5) // 2)
        out = [_move(top, left) + _fg(BORDER) + "╭" + "─" * (pop_w - 2) + "╮" + R]
        header_txt = " model · provider"
        tp = max(0, pop_w - 2 - len(header_txt))
        out.append(
            _move(top + 1, left) +
            _fg(BORDER) + "│" +
            _fg(MUTED) + header_txt + " " * tp +
            _fg(BORDER) + "│" + R
        )
        out.append(_move(top + 2, left) + _fg(BORDER) + "├" + "─" * (pop_w - 2) + "┤" + R)
        row = top + 3
        for i, (kind, value, label) in enumerate(items):
            if kind == "header":
                lbl = label[:pop_w - 6]
                sp = max(0, pop_w - 4 - len(lbl))
                out.append(
                    _move(row, left) + _fg(BORDER) + "│ " +
                    _fg(COMMENT) + lbl + " " * sp +
                    _fg(BORDER) + " │" + R
                )
            else:
                is_sel = (i == sel)
                dot = "●" if is_sel else "○"
                bg_ = _bg(BG_HL) if is_sel else _bg(BG)
                lc = B(CYAN) if is_sel else _fg(FG_DIM)
                vcol = PROV_COL.get(value, FG) if kind == "provider" else FG
                lbl = label[: pop_w - 12]
                pp = max(0, pop_w - 8 - len(lbl))
                pointer = "› " if is_sel else "  "
                out.append(
                    _move(row, left)
                    + _fg(BORDER) + "│ "
                    + bg_ + lc + pointer + dot + " "
                    + _fg(vcol if is_sel else FG_DIM) + lbl
                    + " " * pp + R
                    + _fg(BORDER) + " │" + R
                )
            row += 1
        out.append(_move(row, left) + _fg(BORDER) + "├" + "─" * (pop_w - 2) + "┤" + R)
        row += 1
        bot_txt = "Esc Close  ·  ↑↓ Navigate  ·  Enter Mount"
        out.append(
            _move(row, left) + _fg(BORDER) + "│ " +
            _fg(MUTED) + bot_txt + " " * max(0, pop_w - 4 - len(bot_txt)) +
            _fg(BORDER) + " │" + R
        )
        row += 1
        out.append(_move(row, left) + _fg(BORDER) + "╰" + "─" * (pop_w - 2) + "╯" + R)
        return "".join(out)

    def _notification_bar(self, rows, cols):
        msg = self.tui.notification
        inner = msg[:max(0, cols - 12)]
        left = max(1, cols - len(inner) - 8)
        return (
            _move(rows - 3, left) +
            _fg(BORDER) + "╭─ " + _fg(CYAN) + "◆ " + _fg(FG_HI) + inner +
            _fg(BORDER) + " ─╮" + R
        )


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
        self._input_hist = self._load_history()
        self._hist_idx = -1; self._hist_draft = ""

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

        self._loaded_plugins =[]; self.renderer = Renderer(self)
        self.original_termios = None
        self.pane_active = False
        self.pane_lines_output = []
        
        # ── Browser Mode ──────────────────────────────────────────────────────
        self.browser_visible = False
        self.browser_cwd = os.getcwd()
        self.browser_items = []
        self.browser_sel = 0

    def _make_system_prompt(self, coding_mode=False, file_mode=False):
        return build_system_prompt({**self.persona, **self.persona_override}, build_memory_block(), coding_mode, file_mode)

    def _sys(self, text): self.store.add(Msg("system", text))
    def _err(self, text): self.store.add(Msg("error", str(text)))
    
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
        try:
            entries = list(os.scandir(self.browser_cwd))
            dirs = sorted([e for e in entries if e.is_dir()], key=lambda e: e.name.lower())
            files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name.lower())
            
            self.browser_items = []
            if self.browser_cwd != "/":
                self.browser_items.append(("dir", "..", os.path.dirname(self.browser_cwd)))
                
            for d in dirs: self.browser_items.append(("dir", d.name, d.path))
            for f in files: self.browser_items.append(("file", f.name, f.path))
            self.browser_sel = max(0, min(self.browser_sel, len(self.browser_items) - 1))
        except Exception as e:
            self._err(f"Browser error: {e}")
            self.browser_items = []

    def _browser_select(self):
        if not self.browser_items: return
        sel = self.browser_sel
        if sel < 0 or sel >= len(self.browser_items): return
        itype, iname, ipath = self.browser_items[sel]
        
        if itype == "dir":
            # Navigate into the directory
            self.browser_cwd = ipath
            self.browser_sel = 0
            self._refresh_browser()
            self.redraw()
        else:
            # File selected — inject into context, close the browser
            self.browser_visible = False
            self._notify(f"󰈔 Loaded: {iname}")
            threading.Thread(
                target=self._execute_command,
                args=("/file", ipath),
                daemon=True
            ).start()

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

        full = ""
        try:
            for chunk in self.client.chat.completions.create(model=model, messages=messages, max_tokens=8192, temperature=0.7, stream=True):
                if not chunk.choices: continue
                d = chunk.choices[0].delta.content
                if d:
                    full += d; self.store.append(idx, d); self.redraw()
        except Exception as ex: return self._handle_stream_error(idx, ex, messages)
        self.store.finalize(idx); return full

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
        if refined: self.store.set_text(idx, refined or full)
        self.store.finalize(idx); return refined or full

    def _handle_stream_error(self, idx, ex, messages):
        msg = str(ex)
        if any(x in msg for x in ("429", "RESOURCE_EXHAUSTED", "quota", "limit: 0")):
            remaining = [p for p in get_available_providers() if p != get_provider()]
            if remaining:
                self._sys(f"Quota hit — switching to {remaining[0]}")
                try:
                    set_provider(remaining[0]); self.client = get_client(); self.current_model = get_models(remaining[0])[0]
                    self.store.set_text(idx, "")
                    full = ""
                    for chunk in self.client.chat.completions.create(model=self.current_model, messages=messages, max_tokens=8192, temperature=0.7, stream=True):
                        if not chunk.choices: continue
                        d = chunk.choices[0].delta.content
                        if d: full += d; self.store.append(idx, d); self.redraw()
                    self.store.finalize(idx); return full
                except Exception as ex2: self.store.set_text(idx, f"⚠  {ex2}")
            else: self.store.set_text(idx, f"⚠  {ex}")
        else: self.store.set_text(idx, f"⚠  {ex}")
        self.store.finalize(idx); return f"⚠  {ex}"

    def _silent_call(self, prompt, model, max_tokens=8192):
        try: return self.client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.3, stream=False).choices[0].message.content.strip()
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
    def run(self):
        self.persona = load_persona(); self.persona_override = get_persona_override()
        self.system_prompt = self._make_system_prompt()
        self.name = self.persona_override.get("name") or self.persona.get("name", "Lumi")

        try:
            p = get_provider(); self.current_model = get_models(p)[0]; self.client = get_client()
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
        if not key: return
        if key == "ESC":
            if getattr(self, "browser_visible", False): self.browser_visible = False; self.redraw(); return
            if self.slash_visible: self.slash_visible = False
            elif self.picker_visible: self.picker_visible = False
            return
        if key in ("CTRL_Q", "CTRL_C"):
            with self._state_lock: self._running = False
            return
        if key == "CTRL_N":
            if not self.slash_visible: self._open_picker()
            return
        if key == "CTRL_L":
            self.memory.clear(); self.store.clear(); self.agents.clear()
            self.last_msg = self.last_reply = self.prev_reply = None
            self.turns = 0; self.set_busy(False); self.buf = ""; self.cur_pos = self.scroll_offset = 0
            self.slash_visible = self.picker_visible = False
            self._sys("Chat cleared."); return
        if key == "CTRL_R":
            if not (self._active_task and not self._active_task.done()):
                self._active_task = self._task_executor.submit(self._do_retry)
            return
        if key == "CTRL_U": self.buf = ""; self.cur_pos = 0; self.slash_visible = False; return

        if key == "UP":
            if getattr(self, "browser_visible", False):
                self.browser_sel = max(0, self.browser_sel - 1); self.redraw(); return
            if self.slash_visible: self.slash_sel = max(0, self.slash_sel - 1)
            elif self.picker_visible:
                new = self.picker_sel - 1
                while new >= 0 and self.picker_items[new][0] == "header": new -= 1
                if new >= 0: self.picker_sel = new
            elif not self.buf: self.scroll_offset += 3
            else: self._hist_nav(-1)
            return
        if key == "DOWN":
            if getattr(self, "browser_visible", False):
                self.browser_sel = min(len(self.browser_items) - 1, self.browser_sel + 1); self.redraw(); return
            if self.slash_visible: self.slash_sel = min(len(self.slash_hits) - 1, self.slash_sel + 1)
            elif self.picker_visible:
                new = self.picker_sel + 1
                while new < len(self.picker_items) and self.picker_items[new][0] == "header": new += 1
                if new < len(self.picker_items): self.picker_sel = new
            elif not self.buf: self.scroll_offset = max(0, self.scroll_offset - 3)
            else: self._hist_nav(1)
            return

        if key == "PGUP": rows, _ = _term_size(); self.scroll_offset += max(1, rows - 6); return
        if key == "PGDN": rows, _ = _term_size(); self.scroll_offset = max(0, self.scroll_offset - max(1, rows - 6)); return
        if key == "TAB":
            if self.slash_visible and self.slash_hits:
                cmd = self.slash_hits[self.slash_sel][0]; self.buf = cmd + " "
                self.cur_pos = len(self.buf); self.slash_visible = False
            return

        if key == "ENTER":
            if getattr(self, "browser_visible", False): self._browser_select(); return
            if self.picker_visible: self._confirm_picker(); return
            if self.slash_visible and self.slash_hits:
                cmd = self.slash_hits[self.slash_sel][0]
                self.slash_visible = False; self.buf = ""; self.cur_pos = 0
                self._execute_command(cmd, ""); return
            text = self.buf.strip(); self.buf = ""; self.cur_pos = 0; self.slash_visible = False; self._hist_idx = -1
            if text and not self.busy:
                if text not in (self._input_hist[-1:] or [""]):
                    self._input_hist.append(text)
                    self._save_history_entry(text)
                if text.startswith("/"):
                    parts = text.split(None, 1)
                    self._execute_command(parts[0].lower(), parts[1] if len(parts) > 1 else "")
                else:
                    if self._active_task and not self._active_task.done():
                        self._err("Still busy — wait for the current reply.")
                    else:
                        self._active_task = self._task_executor.submit(self._run_message, text)
            return

        if key == "BACKSPACE":
            if getattr(self, "browser_visible", False):
                parent = os.path.dirname(self.browser_cwd)
                if parent != self.browser_cwd:
                    self.browser_sel = 0; self.browser_cwd = parent; self._refresh_browser(); self.redraw()
                return
            if self.cur_pos > 0:
                self.buf = self.buf[:self.cur_pos - 1] + self.buf[self.cur_pos:]; self.cur_pos -= 1
            self._update_slash(); return
        if key == "DELETE":
            if self.cur_pos < len(self.buf): self.buf = self.buf[:self.cur_pos] + self.buf[self.cur_pos + 1:]
            return
        if key == "CTRL_W":
            if self.cur_pos > 0:
                t = self.buf[:self.cur_pos].rstrip(); idx = t.rfind(" ")
                keep = t[:idx + 1] if idx >= 0 else ""; self.buf = keep + self.buf[self.cur_pos:]; self.cur_pos = len(keep)
            self._update_slash(); return

        if key == "CTRL_RIGHT":
            i = self.cur_pos
            while i < len(self.buf) and self.buf[i] == " ": i += 1
            while i < len(self.buf) and self.buf[i] != " ": i += 1
            self.cur_pos = i; return
        if key == "CTRL_LEFT":
            i = self.cur_pos
            while i > 0 and self.buf[i - 1] == " ": i -= 1
            while i > 0 and self.buf[i - 1] != " ": i -= 1
            self.cur_pos = i; return
        if key == "LEFT":
            if getattr(self, "browser_visible", False):
                parent = os.path.dirname(self.browser_cwd)
                if parent != self.browser_cwd:
                    self.browser_sel = 0; self.browser_cwd = parent; self._refresh_browser(); self.redraw()
                return
            self.cur_pos = max(0, self.cur_pos - 1); return
        if key == "RIGHT":
            if getattr(self, "browser_visible", False): self._browser_select(); return
            self.cur_pos = min(len(self.buf), self.cur_pos + 1); return
        if key == "HOME": self.cur_pos = 0; return
        if key == "END": self.cur_pos = len(self.buf); return

        if len(key) == 1 and (key.isprintable() or ord(key) > 127):
            self.buf = self.buf[:self.cur_pos] + key + self.buf[self.cur_pos:]; self.cur_pos += 1; self._update_slash()

    def _update_slash(self):
        if self.buf.startswith("/"):
            q = self.buf.lower(); self.slash_hits = registry.get_hits(q); self.slash_sel = 0; self.slash_visible = bool(self.slash_hits)
        else: self.slash_visible = False

    def _load_history(self) -> list:
        try:
            if self._hist_file.exists():
                lines = self._hist_file.read_text(encoding="utf-8").splitlines()
                return [l for l in lines if l.strip()][-500:]
        except Exception:
            log.exception("Failed to load history")
        return []

    def _save_history_entry(self, text: str):
        try:
            with self._hist_file.open("a", encoding="utf-8") as f:
                f.write(text.replace("\n", " ") + "\n")
        except Exception:
            log.exception("Failed to save history entry")

    def _hist_nav(self, direction):
        if not self._input_hist: return
        if self._hist_idx == -1: self._hist_draft = self.buf
        new = self._hist_idx + direction
        if new < -1 or new >= len(self._input_hist): return
        self._hist_idx = new; self.buf = (self._hist_draft if new == -1 else self._input_hist[-(new + 1)]); self.cur_pos = len(self.buf)

    # ── Master LLM Task Query Send Operation Routing  ───────────────────────
    def _run_message(self, user_input):
        self.set_busy(True); self.scroll_offset = 0

        _is_code = is_complex_coding_task(user_input) or is_coding_task(user_input)
        _is_files = is_file_generation_task(user_input)
        sp = self._make_system_prompt(coding_mode=_is_code, file_mode=_is_files)

        if needs_plan_first(user_input) and _is_files:
            sp += "\n\n[INSTRUCTION: Output a brief one-paragraph plan. Then write each file completely.]"
        if is_create_request(user_input): self._run_file_agent(user_input, sp); return

        emotion = detect_emotion(user_input); augmented = user_input
        if emotion: hint = emotion_hint(emotion); augmented = (hint + augmented) if hint else augmented
        
        if self.response_mode == "short": augmented += "\n\n[Reply concisely — 2-3 sentences max.]"
        elif self.response_mode == "detailed": augmented += "\n\n[Reply in detail — be thorough and comprehensive.]"
        elif self.response_mode == "bullets": augmented += "\n\n[Reply using bullet points only.]"
        self.response_mode = None

        if should_search(user_input):
            self._sys("◆  searching the web…"); self.redraw()
            try:
                results_text = search(user_input, fetch_top=True)
                if results_text and not results_text.startswith("[No"):
                    augmented = f"{augmented}\n\n[Web search results:]\n{results_text}\n[Use the above to inform your answer. Cite sources.]"
                    self._sys("◆  found web results")
            except Exception:
                log.exception("Web search failed")

        cmd = user_input.split()[0] if user_input.startswith("/") else None
        if cmd:
            handled, plug_result = plugin_dispatch(cmd, user_input.split(None, 1)[1] if len(user_input.split(None, 1)) > 1 else "", client=self.client, model=self.current_model, memory=self.memory, system_prompt=sp, name=self.name)
            if handled:
                if plug_result: self._sys(plug_result)
                self.set_busy(False); return

        if len(self.memory.get()) > 15 and self.turns % 10 == 0 and self.turns > 0:
            def _compress():
                try:
                    snapshot = self.memory.get()[:-4]
                    if not snapshot: return
                    m = self.current_model if self.current_model != "council" else get_models(get_provider())[0]
                    summ = self._silent_call(
                        "Summarize this conversation briefly:\n\n" +
                        "\n".join(f"{x['role']}: {x['content'][:200]}" for x in snapshot), m, 200
                    )
                    if summ:
                        # Lock before mutating shared history
                        with self._state_lock:
                            self.memory._history = (
                                [{"role": "system", "content": f"[Summary]: {summ}"}]
                                + self.memory._history[-4:]
                            )
                            self._cached_tok_len = -1  # invalidate token cache
                        log.debug("Memory compressed to summary + last 4 messages")
                except Exception:
                    log.exception("Memory compression failed")
            self._task_executor.submit(_compress)

        self.last_msg = user_input
        self.store.add(Msg("user", user_input)); self.memory.add("user", augmented)
        messages = build_messages(sp, self.memory.get())
        self.redraw()

        raw_reply = self._tui_stream(messages, self.current_model)
        self.memory._history[-1] = {"role": "user", "content": user_input}
        self.memory.add("assistant", raw_reply)
        
        self.prev_reply = self.last_reply; self.last_reply = raw_reply
        self.turns += 1; self.set_busy(False)

        if self.turns % 5 == 0:
            self._task_executor.submit(lambda: session_save(self.memory.get()))
        if self.turns % 8 == 0:
            def _bg_remember():
                try:
                    if auto_extract_facts(self.client, self.current_model, self.memory.get()):
                        with self._state_lock:
                            self.system_prompt = self._make_system_prompt()
                        log.debug("Auto-remember: system prompt updated")
                except Exception:
                    log.exception("Auto-remember failed")
            self._task_executor.submit(_bg_remember)

    def _run_file_agent(self, user_input, sp):
        self._sys("◆  generating file plan…"); self.redraw()
        try:
            _fs_model = self.current_model
            if _fs_model == "council": _fs_model = get_models(get_provider())[0]
            plan = generate_file_plan(user_input, self.client, _fs_model)
        except Exception as e: self._err(f"File plan failed: {e}"); self.set_busy(False); return
        if not plan: self._err("Couldn't generate a file plan."); self.set_busy(False); return

        root = plan.get("root", "."); files = plan.get("files",[]); home = os.path.expanduser("~")
        lines = [f"File plan → {home}"]; lines.append(f"  📁 {root}/") if root and root != "." else None
        for f in files: lines.append(f"  📄 {f.get('path', '')}")
        lines.append(""); lines.append("Type 'yes' to create, anything else to cancel.")
        
        self._sys("\n".join(lines)); self.set_busy(False); self._pending_file_plan = (plan, home)

    def _do_retry(self):
        if self.busy: return
        for m in reversed(self.memory.get()):
            if m["role"] == "user":
                text = m["content"]; self.memory._history = self.memory._history[:-2] if len(self.memory._history) >= 2 else[]
                self.turns = max(0, self.turns - 1); self.set_busy(True)
                self.store.add(Msg("user", text)); self.memory.add("user", text)
                
                msgs = build_messages(self.system_prompt, self.memory.get())
                raw = self._tui_stream(msgs, self.current_model)
                self.memory._history[-1] = {"role": "user", "content": text}; self.memory.add("assistant", raw)
                self.prev_reply = self.last_reply; self.last_reply = raw; self.turns += 1; self.set_busy(False); return
        self._err("Nothing to retry.")

    def _open_picker(self):
        items =[]
        try:
            avail = get_available_providers(); models = get_models(get_provider()) if self.current_model not in ("council", "unknown") else[]
            items.append(("header", "", "Providers"))
            for p in avail: items.append(("provider", p, PROV_NAME.get(p, p)))
            if len(avail) >= 2: items.append(("provider", "council", "⚡ Council"))
            if models:
                items.append(("header", "", f"Models ({PROV_NAME.get(get_provider(), get_provider())})"))
                for m in models[:16]: items.append(("model", m, m.split("/")[-1]))
        except Exception:
            log.exception("Picker open failed")
        self.picker_items = items; self.picker_sel = 0; self.picker_visible = True

    def _confirm_picker(self):
        if not self.picker_items: self.picker_visible = False; return
        kind, value, label = self.picker_items[self.picker_sel]
        if kind == "header": return
        if kind == "provider":
            if value == "council": self.current_model = "council"
            else:
                try:
                    set_provider(value); self.client = get_client(); ms = get_models(value); self.current_model = ms[0] if ms else ""; self._open_picker(); return
                except Exception:
                    log.exception("Provider switch failed")
            self._sys(f"Provider → {PROV_NAME.get(self.current_model, self.current_model)}")
        elif kind == "model": self.current_model = value; self._notify(f"Model → {value.split('/')[-1]}")
        self.picker_visible = False

    def _execute_command(self, cmd, arg):
        if cmd in registry.commands: registry.commands[cmd]["func"](self, arg)
        else:
            handled, plug_result = plugin_dispatch(cmd, arg, client=self.client, model=self.current_model, memory=self.memory, system_prompt=self.system_prompt, name=self.name)
            if handled:
                if plug_result: self._sys(plug_result)
            else: self._err(f"Unknown command: {cmd}  (try /help)")


# ══════════════════════════════════════════════════════════════════════════════
#  Commands / Utilities Massive Implementation Restoration List
# ══════════════════════════════════════════════════════════════════════════════
def bg_task(func):
    """Decorator that runs a command in the TUI's thread pool instead of spawning bare threads."""
    def wrapper(tui: "LumiTUI", arg: str):
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
    if not parts or parts[0] in {"help", "?"}:
        usage = [
            "Filesystem tools:",
            "  /fs ls [path]              - list directory contents",
            "  /fs cat <file>             - show file contents (truncated)",
            "  /fs mkdir <dir>            - create directory (parents ok)",
            "  /fs mv <src> <dst>         - move/rename file",
            "  /fs rm <file> --force      - delete file (no directories)",
            "  /fs write <file> [text]    - overwrite file with text or last reply code",
            "  /fs append <file> [text]   - append text or last reply code",
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
        target = _path(rest[0])
        try:
            target.mkdir(parents=True, exist_ok=True)
            tui._notify(f"Created directory: {target}")
        except Exception as e:
            tui._err(str(e))
        return

    if sub == "mv":
        if len(rest) != 2:
            tui._err("Usage: /fs mv <src> <dst>")
            return
        src, dst = _path(rest[0]), _path(rest[1])
        if not src.exists():
            tui._err(f"Not found: {src}")
            return
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            tui._notify(f"Moved: {src.name} → {dst}")
        except Exception as e:
            tui._err(str(e))
        return

    if sub == "rm":
        if not rest:
            tui._err("Usage: /fs rm <file> --force")
            return
        target = _path(rest[0])
        force = "--force" in rest[1:]
        if not target.exists():
            tui._err(f"Not found: {target}")
            return
        if target.is_dir():
            tui._err("Refusing to delete directories. Use /shell for rm -r.")
            return
        if any(part.startswith(".git") for part in target.parts):
            tui._err("Refusing to touch .git content for safety.")
            return
        if not force:
            tui._err("Add --force to confirm: /fs rm <file> --force")
            return
        try:
            target.unlink()
            tui._notify(f"Deleted: {target}")
        except Exception as e:
            tui._err(str(e))
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
        target = _path(rest[0])
        if len(rest) >= 2:
            content = " ".join(rest[1:])
        else:
            content = _code_from_last_reply()
            if not content:
                tui._err("No text provided and no last reply to use.")
                return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if sub == "write":
                target.write_text(content, encoding="utf-8")
                tui._notify(f"Wrote file: {target}")
            else:
                with target.open("a", encoding="utf-8") as f:
                    if target.stat().st_size > 0:
                        f.write("\n")
                    f.write(content)
                tui._notify(f"Appended to: {target}")
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
        # Inject into memory as a user-facing system note
        tui._sys(f"󰈔 Loaded `{rel}` ({line_count} lines) into context")
        # Also push into the conversation memory so the LLM can see it
        snippet = f"<file path=\"{rel}\">\n{content}\n</file>"
        tui.memory.add("user", snippet)
    except Exception as e:
        tui._err(f"Failed to read {path}: {e}")

@registry.register("/council", "All agents run together")
def cmd_council(tui: LumiTUI, arg: str): tui.current_model = "council"; tui._sys("⚡ Council mode — all agents in parallel")

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
        if h: tui.memory._history = h; tui.turns = len(h) // 2; tui._sys(f"Loaded {len(h)} messages")
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
    tui.memory._history[-1] = {"role": "user", "content": "Tell me more."}; tui.memory.add("assistant", raw)
    tui.prev_reply = tui.last_reply; tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/undo", "Pop the latest history branch")
def cmd_undo(tui: LumiTUI, arg: str):
    if len(tui.memory._history) >= 2:
        tui.memory._history = tui.memory._history[:-2]
        tui.turns = max(0, tui.turns - 1)
        tui._sys("Last exchange removed from LLM Memory Tree.")
    else: tui._err("Nothing to undo.")

@registry.register("/rewrite", "Alternative generation run")
@bg_task
def cmd_rewrite(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("No block loaded!"); return
    tui.set_busy(True); tui.memory.add("user", "[Rewrite the previous context totally differently.]")
    msgs = build_messages(tui.system_prompt, tui.memory.get()); raw = tui._tui_stream(msgs, tui.current_model)
    tui.memory._history[-1] = {"role": "user", "content": "Rewrite completely differently."}
    tui.memory.add("assistant", raw); tui.prev_reply = tui.last_reply; tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/tl;dr", "One sentence summarize response")
@bg_task
def cmd_tldr(tui: LumiTUI, arg: str):
    if not tui.last_reply: tui._err("Nothing returned yet."); return
    tui.set_busy(True); m = tui.current_model if tui.current_model != "council" else get_models(get_provider())[0]
    s = tui._silent_call(f"Summarize this in exactly ONE minimal sentence (under 16 words): {tui.last_reply}", m, 60)
    if s: tui._sys(f"tl;dr: {s}")
    tui.set_busy(False)

@registry.register("/fix", "Fix pipeline code traces directly")
@bg_task
def cmd_fix(tui: LumiTUI, arg: str):
    if not arg or not tui.last_reply: tui._err("Requires Exception error copy format context code"); return
    tui.set_busy(True)
    msg = f"Im crashing with stack trace error: ```{arg}``` context was previously:\n{tui.last_reply}\n1. Clarify Root cause\n2. Rewrite entire codeblock fix directly.\n3. Defenses?"
    tui.memory.add("user", msg); raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get()), tui.current_model, f"◆ {tui.name}  [fix]")
    tui.memory._history[-1] = {"role": "user", "content": f"/fix: {arg[:100]}"}; tui.memory.add("assistant", raw)
    tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

@registry.register("/search", "Internet browser fetching context tools")
@bg_task
def cmd_search(tui: LumiTUI, arg: str):
    if not arg: tui._err("Search needs keywords via CLI space."); return
    tui.set_busy(True); tui._sys(f"◆  Searching Internet Servers... => [ {arg} ]")
    try:
        results, _ = search_display(arg); lines = [f"Result Headers Found for => {arg}", ""]
        for i, r in enumerate(results, 1): lines.append(f" {i}. {r['title']}\n    - {r['url']}")
        tui._sys("\n".join(lines)); ctx = search(arg, fetch_top=True)
        tui.memory.add("user", f"Auto Search Tool results fetched internally to system parameters [query={arg}]\nData block:\n{ctx}\nAnalyze directly the main details and print clear structured insights.")
        raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get()), tui.current_model, f"◆ {tui.name}  [WWW Net Context Load Complete]")
        tui.memory._history[-1] = {"role": "user", "content": f"Search requested info on [ {arg} ]"}
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
    tui.memory.add("user", f"Fetched external raw web link ({url}):\n{content}\n---\nRespond instruction: {q}")
    raw = tui._tui_stream(build_messages(tui.system_prompt, tui.memory.get()), tui.current_model, f"◆ {tui.name} [WWW Node parser]")
    tui.memory._history[-1] = {"role": "user", "content": f"Scan web dom target details[URL_HIDDEN]: {q}"}; tui.memory.add("assistant", raw)
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
    tui.memory._history[-1] = {"role": "user", "content": "Generational System Comment AutoDocs Code Map Layout."}
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
    tui.memory._history[-1] = {"role": "user", "content": "Applied Code PEP Typings Map Refactor Run!"}; tui.memory.add("assistant", raw); tui.last_reply = raw; tui.turns += 1; tui.set_busy(False)

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
    msgs = tui.memory.get()
    total = sum(max(1, int(len(m["content"].split()) * 1.35)) for m in msgs)
    tui._sys(f"Estimated tokens: ~{total:,}  ({len(msgs)} messages)")

@registry.register("/context", "Show context window breakdown")
def cmd_context(tui: LumiTUI, arg: str):
    msgs = tui.memory.get()
    sys_t = sum(max(1, int(len(m["content"].split()) * 1.35)) for m in msgs if m["role"] == "system")
    usr_t = sum(max(1, int(len(m["content"].split()) * 1.35)) for m in msgs if m["role"] == "user")
    ast_t = sum(max(1, int(len(m["content"].split()) * 1.35)) for m in msgs if m["role"] == "assistant")
    tui._sys(f"Context breakdown:\n  System: ~{sys_t:,}tk\n  User:   ~{usr_t:,}tk\n  AI:     ~{ast_t:,}tk\n  Total:  ~{sys_t + usr_t + ast_t:,}tk")

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
    sdir = Path("data/sessions")
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
        prompt = f"Rewrite and improve this file. Return ONLY the new file content:\n\n```\n{content}\n```"
        msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
        reply = tui._tui_stream(msgs, tui.current_model, f"editing {path.name}")
        tui.last_reply = reply; tui.set_busy(False)
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
    if not arg.strip(): tui._err("Usage: /image <path> [question]"); return
    tui._sys("Vision requires multimodal model — use Gemini provider")

@registry.register("/data", "Analyze CSV/JSON: /data stats.csv")
def cmd_data(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /data <file.csv|file.json>"); return
    path = Path(arg.strip()).expanduser()
    if not path.is_file(): tui._err(f"Not found: {path}"); return
    content = path.read_text(errors="replace")[:8000]
    def _go():
        tui.set_busy(True)
        prompt = f"Analyze this data ({path.name}). Give summary stats, patterns, insights:\n\n```\n{content}\n```"
        msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
        reply = tui._tui_stream(msgs, tui.current_model, f"analyzing {path.name}")
        tui.last_reply = reply; tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/agent", "Plan a multi-step agent workflow")
def cmd_agent(tui: LumiTUI, arg: str):
    objective = arg.strip()
    if not objective:
        tui._err("Usage: /agent <objective>"); return

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
    todo_file = Path("data/todos.json")
    todo_file.parent.mkdir(parents=True, exist_ok=True)
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
    note_file = Path("data/notes.json")
    note_file.parent.mkdir(parents=True, exist_ok=True)
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
    if not tui._loaded_plugins: tui._sys("No plugins loaded. Drop .py files in ~/Lumi/plugins/"); return
    tui._sys("Loaded plugins:\n" + "\n".join(f"  {p}" for p in tui._loaded_plugins))

@registry.register("/comment", "Add inline comments to file")
def cmd_comment(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /comment <filepath>"); return
    path = Path(arg.strip()).expanduser()
    if not path.is_file(): tui._err(f"Not found: {path}"); return
    content = path.read_text(errors="replace")
    def _go():
        tui.set_busy(True)
        prompt = f"Add clear inline comments to this code. Return ONLY the commented code:\n\n```\n{content}\n```"
        msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
        reply = tui._tui_stream(msgs, tui.current_model, f"commenting {path.name}")
        tui.last_reply = reply; tui.set_busy(False)
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/git", "Git: /git status|log|diff|commit|push|pull|branch")
def cmd_git(tui: LumiTUI, arg: str):
    sub = arg.strip().split()[0] if arg.strip() else "status"
    cmd_map = {"status": ["git", "status", "-sb"], "log": ["git", "log", "--oneline", "--graph", "-15"],
               "diff": ["git", "diff", "--stat"], "branch": ["git", "branch", "-a"],
               "push": ["git", "push"], "pull": ["git", "pull"]}
    if sub == "commit":
        diff = subprocess.run(["git", "diff", "--cached", "--stat"], capture_output=True, text=True).stdout
        if not diff.strip(): diff = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True).stdout
        if not diff.strip(): tui._err("No changes to commit"); return
        def _go():
            tui.set_busy(True)
            prompt = f"Generate a concise commit message for:\n{diff}\nReturn ONLY the message."
            msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
            reply = tui._tui_stream(msgs, tui.current_model, "git commit")
            tui.last_reply = reply; tui.set_busy(False)
        threading.Thread(target=_go, daemon=True).start(); return
    if sub == "commit-confirm":
        subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
        if tui.last_reply:
            msg = tui.last_reply.strip().strip("`").strip()
            r = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
            tui._sys(r.stdout.strip() or r.stderr.strip()); return
        tui._err("Run /git commit first"); return
    if sub in cmd_map:
        r = subprocess.run(cmd_map[sub], capture_output=True, text=True)
        tui._sys(r.stdout.strip() or r.stderr.strip() or "(no output)")
    else: tui._sys("Usage: /git status|log|diff|commit|commit-confirm|push|pull|branch")

@registry.register("/pdf", "Load PDF text into context")
def cmd_pdf(tui: LumiTUI, arg: str):
    if not arg.strip(): tui._err("Usage: /pdf <path.pdf>"); return
    tui._sys("PDF loading requires PyPDF2 — pip install PyPDF2")

@registry.register("/project", "Load entire project into context")
def cmd_project(tui: LumiTUI, arg: str):
    target = Path(arg.strip() or ".").expanduser()
    if not target.is_dir(): tui._err(f"Not a directory: {target}"); return
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".md", ".toml", ".yaml", ".yml", ".json", ".sh"}
    files = [f for f in target.rglob("*") if f.is_file() and f.suffix in exts and ".git" not in str(f) and "node_modules" not in str(f)][:30]
    if not files: tui._sys("No recognizable source files found"); return
    content_parts = []
    for f in files:
        try: content_parts.append(f"<file path=\"{f}\">\n{f.read_text(errors='replace')[:3000]}\n</file>")
        except Exception: pass
    tui.memory.add("user", "\n\n".join(content_parts))
    tui._sys(f"Loaded {len(files)} files from {target} into context")

# ── Help (redesigned) ────────────────────────────────────────────────────────

HELP_CATEGORIES = {
    "💬 Chat": ["/clear", "/retry", "/redo", "/undo", "/more", "/rewrite", "/tl;dr", "/summarize", "/translate", "/short", "/detailed", "/bullets", "/multi"],
    "🔧 Code": ["/fix", "/debug", "/explain", "/review", "/improve", "/optimize", "/security", "/refactor", "/test", "/docs", "/types", "/comment", "/run", "/edit"],
    "📁 Files": ["/file", "/browse", "/find", "/grep", "/tree", "/project", "/fs"],
    "🔀 Git": ["/git", "/pr", "/changelog", "/standup", "/readme"],
    "🌐 Web": ["/search", "/web", "/image", "/data"],
    "🧠 Memory": ["/remember", "/memory", "/forget", "/save", "/load", "/sessions", "/export", "/tokens", "/context"],
    "🛠️ Tools": ["/shell", "/scaffold", "/lint", "/fmt", "/todo", "/note", "/draft", "/weather", "/timer", "/copy", "/paste", "/diff", "/pdf"],
    "⚙️ System": ["/model", "/council", "/mode", "/offline", "/godmode", "/pane", "/apply", "/index", "/rag", "/voice", "/persona", "/sys", "/plugins", "/compact", "/help", "/exit"],
}

@registry.register("/help", "Show all commands organized by category")
def cmd_help(tui: LumiTUI, arg: str):
    lines = []
    for cat, cmds in HELP_CATEGORIES.items():
        lines.append(f"\n  {cat}")
        for c in cmds:
            data = registry.commands.get(c)
            if data:
                desc = data["desc"][:52]
                lines.append(f"    {c:<16} {desc}")
    lines.append(f"\n  {len(registry.commands)} commands available. Tab to autocomplete.")
    lines.append(f"\n  Shortcuts: Ctrl+N=model picker | Ctrl+L=clear | Ctrl+R=retry | Tab=complete")
    tui._sys("\n".join(lines))

# ── Batch 2 Commands ──────────────────────────────────────────────────────────────

@registry.register("/fix", "Diagnose error and fix it")
def cmd_fix(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /fix <error message>"); return
    def _go():
        tui.set_busy(True)
        ctx = f"\n\nContext:\n{tui.last_reply}" if tui.last_reply else ""
        msg = (f"I'm getting this error:\n\n```\n{arg}\n```{ctx}\n\n"
               "1. What's causing it\n2. The exact fix\n3. How to avoid it next time")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [fix]")
        tui.memory._history[-1] = {"role": "user", "content": f"/fix: {arg[:200]}"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/debug", "Deep debug with root cause + test")
def cmd_debug(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        error = arg or "the issue in the last message"
        ctx = f"\n\nLast reply:\n{tui.last_reply}" if tui.last_reply else ""
        msg = (f"Deep debug:\n\n```\n{error}\n```{ctx}\n\n"
               "1. Root cause\n2. Stack trace explanation\n"
               "3. Step-by-step fix\n4. Regression test\n5. Alternative approaches")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [debug]")
        tui.memory._history[-1] = {"role": "user", "content": f"/debug: {error[:200]}"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/improve", "Improve code quality and readability")
def cmd_improve(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"File: `{Path(target).name}`\n\n```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to improve. Pass a file path or ask something first."); tui.set_busy(False); return
        msg = (f"Improve this code. Fix bugs, improve readability, add error handling, "
               f"clean up style. Output the COMPLETE improved version:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [improve]")
        tui.memory._history[-1] = {"role": "user", "content": "/improve"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/optimize", "Performance optimize with before/after")
def cmd_optimize(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to optimize."); tui.set_busy(False); return
        msg = (f"Optimize for performance. Find bottlenecks, improve algorithmic complexity, "
               f"show before/after with estimates:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [optimize]")
        tui.memory._history[-1] = {"role": "user", "content": "/optimize"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/security", "Security audit with severity ratings")
def cmd_security(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to audit."); tui.set_busy(False); return
        msg = (f"Security audit. Find: injection, auth issues, data exposure, input validation gaps, "
               f"hardcoded secrets. Rate each critical/high/medium/low:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [security]")
        tui.memory._history[-1] = {"role": "user", "content": "/security"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/refactor", "Refactor with SOLID principles")
def cmd_refactor(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to refactor."); tui.set_busy(False); return
        msg = (f"Refactor using SOLID principles and design patterns. Reduce duplication, improve abstractions. "
               f"Output the complete refactored version with a brief explanation:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [refactor]")
        tui.memory._history[-1] = {"role": "user", "content": "/refactor"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/test", "Generate pytest unit tests")
def cmd_test(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to test."); tui.set_busy(False); return
        msg = (f"Write comprehensive pytest unit tests. Cover: happy path, edge cases, errors, "
               f"boundary conditions. Include fixtures and mocks where needed:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [tests]")
        tui.memory._history[-1] = {"role": "user", "content": "/test"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/explain", "Explain code line by line")
def cmd_explain(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"File `{Path(target).name}`:\n\n```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to explain."); tui.set_busy(False); return
        msg = f"Explain this code line by line. Walk through every function, why it's written that way, and what a developer needs to understand:\n\n{content}"
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [explain]")
        tui.memory._history[-1] = {"role": "user", "content": "/explain"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/review", "Full code review with specifics")
def cmd_review(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        target = arg.strip() if arg.strip() else None
        if target and Path(target).expanduser().exists():
            try: content = f"File `{Path(target).name}`:\n\n```\n{_read_file(target)}\n```"
            except Exception as e: tui._err(str(e)); tui.set_busy(False); return
        elif tui.last_reply: content = tui.last_reply
        else: tui._err("Nothing to review."); tui.set_busy(False); return
        msg = (f"Thorough code review. Cover: correctness, edge cases, performance, security, "
               f"readability, maintainability. Be specific with line numbers and variable names:\n\n{content}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [review]")
        tui.memory._history[-1] = {"role": "user", "content": "/review"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/scaffold", "Generate complete project scaffold")
def cmd_scaffold(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /scaffold <type>  e.g. fastapi, react, cli, flask"); return
    def _go():
        tui.set_busy(True)
        msg = (f"Generate a complete, production-ready {arg} project scaffold. "
               f"Full file contents — no placeholders, no TODOs. Include: folder structure, "
               f"requirements/package.json, entry point, routes/components, README, .gitignore, tests.")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [scaffold: {arg}]")
        tui.memory._history[-1] = {"role": "user", "content": f"/scaffold: {arg}"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/readme", "Generate README for project/path")
def cmd_readme(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        path = arg.strip() if arg.strip() else "."
        r = subprocess.run(
            f"find {path} -maxdepth 2 -type f -not -path '*/.git/*' -not -path '*/__pycache__/*' | head -40",
            shell=True, capture_output=True, text=True)
        struct = r.stdout.strip()
        main_code = ""
        for fname in ["main.py", "app.py", "index.js", "src/main.py"]:
            fp = Path(path) / fname
            if fp.exists():
                try: main_code = f"\n\n{fname}:\n```\n{fp.read_text()[:2000]}\n```"
                except Exception:
                    log.debug("Could not read main file for readme")
                break
        msg = (f"Generate a comprehensive README.md.\n\nFiles:\n{struct}{main_code}\n\n"
               f"Include: title, description, features, installation, usage, API docs, contributing, license.")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [README]")
        tui.memory._history[-1] = {"role": "user", "content": "[readme]"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/pr", "Write PR description from git diff")
def cmd_pr(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        r1 = subprocess.run("git diff origin/HEAD...HEAD", shell=True, capture_output=True, text=True)
        r2 = subprocess.run("git log origin/HEAD...HEAD --oneline", shell=True, capture_output=True, text=True)
        diff = r1.stdout.strip(); log = r2.stdout.strip()
        if not diff:
            r1 = subprocess.run("git diff HEAD~1 HEAD", shell=True, capture_output=True, text=True)
            r2 = subprocess.run("git log HEAD~1..HEAD --oneline", shell=True, capture_output=True, text=True)
            diff = r1.stdout.strip(); log = r2.stdout.strip()
        if not diff and not log:
            tui._err("No diff found. Commit something first."); tui.set_busy(False); return
        msg = (f"Write a GitHub PR description.\n\nCommits:\n{log}\n\nDiff:\n{diff[:3000]}\n\n"
               f"Include: Title, What changed, Why, How to test. Use Markdown.")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [PR]")
        tui.memory._history[-1] = {"role": "user", "content": "[pr]"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/changelog", "Generate CHANGELOG from git log")
def cmd_changelog(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        r = subprocess.run("git log --oneline -60", shell=True, capture_output=True, text=True)
        log = r.stdout.strip()
        if not log: tui._err("No git history found."); tui.set_busy(False); return
        msg = f"Generate a CHANGELOG from these git commits. Group by: Added, Changed, Fixed, Removed. Use Markdown:\n\n{log}"
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [CHANGELOG]")
        tui.memory._history[-1] = {"role": "user", "content": "[changelog]"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/standup", "Daily standup from git + todos")
def cmd_standup(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        r = subprocess.run("git log --oneline --since='24 hours ago'", shell=True, capture_output=True, text=True)
        log = r.stdout.strip() or "No commits in the last 24 hours"
        try:
            from src.utils.todo import todo_list as _tlist
            todos = [t for t in _tlist() if not t.get("done")]
            todo_txt = "\n".join(f"- {t['text']}" for t in todos[:10]) or "No pending todos"
        except Exception:
            log.debug("Could not read todo file")
            todo_txt = "No pending todos"
        msg = (f"Generate a short daily standup (Yesterday / Today / Blockers).\n\n"
               f"Recent commits:\n{log}\n\nPending todos:\n{todo_txt}")
        tui.memory.add("user", msg)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [standup]")
        tui.memory._history[-1] = {"role": "user", "content": "[standup]"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/grep", "Search codebase for pattern")
def cmd_grep(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /grep <pattern> [path]"); return
    parts = arg.split(None, 1); pattern = parts[0]; path = parts[1] if len(parts) > 1 else "."
    r = subprocess.run(
        ["grep", "-rn",
         "--include=*.py", "--include=*.js", "--include=*.ts",
         "--include=*.go", "--include=*.rs", "--include=*.md",
         pattern, path],
        capture_output=True, text=True)
    out = r.stdout.strip()
    tui.store.add(Msg("shell", out[:3000] if out else "No matches found.", f"grep -rn '{pattern}' {path}"))

@registry.register("/tree", "Directory tree view")
def cmd_tree(tui: LumiTUI, arg: str):
    path = arg.strip() if arg.strip() else "."
    if shutil.which("tree"):
        r = subprocess.run(
            ["tree", path, "-L", "3", "--noreport",
             "-I", "__pycache__|*.pyc|.git|node_modules|.venv|venv"],
            capture_output=True, text=True)
        out = r.stdout.strip()
    else:
        lines = [path + "/"]
        def _t(p, prefix="", depth=0):
            if depth > 3: return
            try: entries = sorted(Path(p).iterdir(), key=lambda x: (x.is_file(), x.name))
            except Exception:
                log.debug("Timer parse failed")
                return
            for i, e in enumerate(entries):
                if e.name in (".git", "__pycache__", "node_modules", ".venv", "venv"): continue
                conn = "└── " if i == len(entries)-1 else "├── "
                lines.append(prefix + conn + e.name + ("/" if e.is_dir() else ""))
                if e.is_dir(): _t(e, prefix + ("    " if i == len(entries)-1 else "│   "), depth+1)
        _t(path); out = "\n".join(lines[:80])
    tui.store.add(Msg("shell", out, f"tree {path}"))

@registry.register("/lint", "Lint with ruff or flake8")
def cmd_lint(tui: LumiTUI, arg: str):
    path = arg.strip() if arg.strip() else "."
    if shutil.which("ruff"):
        r = subprocess.run(["ruff", "check", path, "--output-format=concise"], capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
    elif shutil.which("flake8"):
        r = subprocess.run(["flake8", path, "--max-line-length=120"], capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
    else:
        tui._err("ruff or flake8 not installed. Run: pip install ruff"); return
    tui.store.add(Msg("shell", out if out else "✓ No lint errors.", f"lint {path}"))

@registry.register("/fmt", "Format with black or prettier")
def cmd_fmt(tui: LumiTUI, arg: str):
    path = arg.strip() if arg.strip() else "."
    if shutil.which("black"):
        r = subprocess.run(["black", path, "--quiet"], capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        tui.store.add(Msg("shell", out if out else "✓ Formatted.", f"black {path}"))
    elif shutil.which("prettier"):
        r = subprocess.run(f"prettier --write {path} 2>&1 | tail -5", shell=True, capture_output=True, text=True)
        tui.store.add(Msg("shell", r.stdout.strip() or "✓ Formatted.", f"prettier {path}"))
    else:
        tui._err("black or prettier not found. Run: pip install black")

@registry.register("/redo", "Regenerate with different approach")
def cmd_redo(tui: LumiTUI, arg: str):
    if not tui.last_msg: tui._err("Nothing to redo."); return
    def _go():
        tui.set_busy(True)
        alt = arg.strip()
        q = (f"{tui.last_msg}\n\n[This time: {alt}]" if alt
             else f"{tui.last_msg}\n\n[Rephrase — different approach, same quality.]")
        if len(tui.memory._history) >= 2:
            tui.memory._history = tui.memory._history[:-2]
            tui.turns = max(0, tui.turns - 1)
        tui.store.add(Msg("user", f"↺ redo{' — '+alt if alt else ''}"))
        tui.memory.add("user", q)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model)
        tui.memory._history[-1] = {"role": "user", "content": tui.last_msg}
        tui.memory.add("assistant", raw)
        tui.prev_reply = tui.last_reply; tui.last_reply = raw
        tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/translate", "Translate last reply to a language")
def cmd_translate(tui: LumiTUI, arg: str):
    if not arg: tui._err("Usage: /translate <language>"); return
    if not tui.last_reply: tui._err("No reply to translate yet."); return
    def _go():
        tui.set_busy(True)
        q = f"Translate your last response into {arg}. Output only the translation."
        tui.memory.add("user", q)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [→ {arg}]")
        tui.memory._history[-1] = {"role": "user", "content": f"Translate to {arg}"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

@registry.register("/summarize", "Summarize the conversation")
def cmd_summarize(tui: LumiTUI, arg: str):
    def _go():
        tui.set_busy(True)
        q = "Summarize our conversation so far in concise bullet points."
        tui.memory.add("user", q)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [summarize]")
        tui.memory._history[-1] = {"role": "user", "content": q}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw; tui.turns += 1; tui.set_busy(False); tui.redraw()
    threading.Thread(target=_go, daemon=True).start()

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

    # ── PTY handoff ────────────────────────────────────────────────────────────
    binary   = entry["binary"]
    log_file = f".{binary}_raw.log"
    dest_file = f"{binary}_session.txt"

    def _handoff():
        tui.set_busy(True)
        tui._sys(f"◆  Launching {entry['name']}… Lumi will resume when you exit.")
        tui.redraw()
        time.sleep(0.3)  # let the sys message render

        # Phase 1 — suspend TUI, restore normal terminal
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        if hasattr(tui, "original_termios") and tui.original_termios:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, tui.original_termios)
            except Exception:
                pass

        print(f"\n  ◆ Entering {entry['name']} — exit normally to return to Lumi\n")

        # Phase 2 — run inside `script` for transcript capture
        try:
            subprocess.run(
                f"script -q -c '{binary}' {log_file}",
                shell=True,
                env={**os.environ},   # pass full env (API keys etc.)
            )
        except Exception:
            pass

        # Phase 3 — clean & save transcript
        if os.path.exists(log_file):
            try:
                raw = Path(log_file).read_text(errors="replace")
                clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b.', '', raw)
                clean = re.sub(r'\r\n|\r', '\n', clean).strip()
                header = (
                    f"==== {entry['name'].upper()} SESSION | "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====\n"
                )
                with open(dest_file, "a", encoding="utf-8") as f:
                    f.write(header + clean + "\n\n")
                os.remove(log_file)
            except Exception:
                pass

        # Phase 4 — restore Lumi TUI
        try:
            tty.setraw(sys.stdin.fileno())
        except Exception:
            pass
        sys.stdout.write("\033[?1049h\033[?25l\033[J")
        sys.stdout.flush()
        tui.redraw()

        # Phase 5 — inject context & welcome back
        transcript_note = (
            f" The session transcript was saved to '{dest_file}'."
            if os.path.exists(dest_file) else ""
        )
        sys_msg = (
            f"[SYSTEM NOTE: The user just returned from a {entry['name']} CLI session.{transcript_note} "
            f"Warmly welcome them back. If a transcript exists, offer to review it for context, bugs, or next steps.]"
        )
        tui.memory.add("system", sys_msg)

        user_msg = f"(I have returned from {entry['name']}. Greet me back and mention {dest_file} if it exists.)"
        tui.store.add(Msg("user", user_msg))
        tui.memory.add("user", user_msg)

        def _stream_welcome():
            msgs = build_messages(tui.system_prompt, tui.memory.get())
            raw = tui._tui_stream(msgs, tui.current_model)
            tui.memory.add("assistant", raw)
            tui.last_reply = raw
            tui.turns += 1
            tui.set_busy(False)
            tui.redraw()

        threading.Thread(target=_stream_welcome, daemon=True).start()

    threading.Thread(target=_handoff, daemon=True).start()

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
        tui.pane_active = False
        tui.redraw()
        return
        
    tui.pane_active = True
    tui.pane_lines_output = []
    
    def _read_pane():
        proc = subprocess.Popen(arg, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(proc.stdout.readline, ""):
            if not getattr(tui, "_running", True) or not tui.pane_active:
                proc.terminate()
                break
            tui.pane_lines_output.append(line.rstrip('\n')[:120]) # Limit width
            if len(tui.pane_lines_output) > 100:
                tui.pane_lines_output = tui.pane_lines_output[-100:]
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
            
        prompt = f"{context}\n\nBased on the codebase above, answer this: {arg}"
        tui.memory.add("user", prompt)
        
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [RAG]")
        tui.memory._history[-1] = {"role": "user", "content": f"/rag {arg}"}
        tui.memory.add("assistant", raw)
        tui.last_reply = raw
        tui.turns += 1
    except Exception as e:
        tui._err(f"RAG search failed: {e}")
    tui.set_busy(False)

@registry.register("/voice", "Record 5s of voice and transcribe")
@bg_task
def cmd_voice(tui: LumiTUI, arg: str):
    tui.set_busy(True)
    tui._sys("◆  Listening for 5 seconds... Speak now!")
    try:
        from src.tools.voice import record_audio, transcribe_audio_hf
        audio_file = record_audio(duration=5)
        tui._sys("◆  Transcribing...")
        text = transcribe_audio_hf(audio_file)
        
        # Inject the transcribed text directly into the user's input buffer
        tui.buf = text
        tui.cur_pos = len(text)
        tui._sys(f"Transcribed: '{text}' (Press Enter to send)")
    except Exception as e:
        tui._err(f"Voice failed: {e}")
    tui.set_busy(False)

# ── Entry System Level ─────────────────────────────────────────────────────────────
def launch(): LumiTUI().run()

if __name__ == "__main__": launch()
