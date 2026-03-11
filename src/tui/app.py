"""
◆ Lumi — Pure Python TUI  v3.0
   Zero dependencies. ANSI + termios. Tokyo Night.
   Built by SardorchikDev. Upgraded to the moon.
"""
from __future__ import annotations

import os, sys, tty, termios, threading, signal, textwrap, re, time, json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# ══════════════════════════════════════════════════════════════════════════════
#  ANSI helpers
# ══════════════════════════════════════════════════════════════════════════════

ESC = "\033"
CSI = ESC + "["

def _fg(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"{CSI}38;2;{r};{g};{b}m"

def _bg(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"{CSI}48;2;{r};{g};{b}m"

def _bold()      -> str: return f"{CSI}1m"
def _italic()    -> str: return f"{CSI}3m"
def _reset()     -> str: return f"{CSI}0m"
def _hide_cur()  -> str: return f"{ESC}[?25l"
def _show_cur()  -> str: return f"{ESC}[?25h"
def _alt_on()    -> str: return f"{ESC}[?1049h"
def _alt_off()   -> str: return f"{ESC}[?1049l"
def _move(r,c)   -> str: return f"{CSI}{r};{c}H"
def _erase_line()-> str: return f"{CSI}2K"
def _clr_down()  -> str: return f"{CSI}J"

# ── Tokyo Night ───────────────────────────────────────────────────────────────
BG       = "#1a1b26"
BG_DARK  = "#16161e"
BG_HL    = "#1f2335"
BG_POP   = "#24283b"
BORDER   = "#29294a"
MUTED    = "#3b3f5e"
COMMENT  = "#565f89"
FG_DIM   = "#737aa2"
FG       = "#a9b1d6"
FG_HI    = "#c0caf5"
BLUE     = "#7aa2f7"
CYAN     = "#7dcfff"
GREEN    = "#9ece6a"
YELLOW   = "#e0af68"
ORANGE   = "#ff9e64"
RED      = "#f7768e"
PURPLE   = "#bb9af7"
TEAL     = "#2ac3de"
PINK     = "#ff007c"

def P(hex_c): return _fg(hex_c)
def B(hex_c): return _fg(hex_c) + _bold()
def PB(hex_c, bg_c): return _bg(bg_c) + _fg(hex_c) + _bold()
R = _reset

SPINNER_FRAMES = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

AGENT_COL = {
    "gemini": CYAN, "groq": ORANGE, "openrouter": PURPLE,
    "mistral": RED, "hf": YELLOW, "github": FG_HI,
    "cohere": GREEN, "cloudflare": ORANGE,
}
PROV_NAME = {
    "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
    "mistral": "Mistral", "huggingface": "HuggingFace",
    "github": "GitHub Models", "cohere": "Cohere",
    "cloudflare": "Cloudflare AI", "ollama": "Ollama", "council": "⚡ Council",
}
PROV_COL = {
    "gemini": CYAN, "groq": ORANGE, "openrouter": PURPLE,
    "mistral": RED, "huggingface": YELLOW, "github": FG_HI,
    "cohere": GREEN, "cloudflare": ORANGE, "ollama": FG_DIM, "council": PURPLE,
}

SLASH_CMDS = [
    ("/council",  "all agents in parallel"),
    ("/model",    "switch model / provider"),
    ("/clear",    "clear conversation"),
    ("/retry",    "retry last message"),
    ("/web",      "/web <query>  search the web"),
    ("/save",     "save chat to file"),
    ("/export",   "export chat as markdown"),
    ("/copy",     "copy last response to clipboard"),
    ("/tokens",   "show token usage"),
    ("/sys",      "show current system prompt"),
    ("/agent",    "autonomous agent mode"),
    ("/session",  "list & resume sessions"),
    ("/help",     "show all commands"),
    ("/exit",     "quit lumi"),
]

def _hm() -> str: return datetime.now().strftime("%H:%M")
def _ts() -> str: return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _tok(t: str) -> int:
    return max(1, int(len(t.split()) * 1.35))

def _term_size() -> tuple[int, int]:
    import shutil
    s = shutil.get_terminal_size((120, 36))
    return s.lines, s.columns

def _strip_ansi(s: str) -> str:
    return re.sub(r'\033\[[^a-zA-Z]*[a-zA-Z]|\033\].*?\007|\033.', '', s)

def _visible_len(s: str) -> int:
    return len(_strip_ansi(s))

def _clipboard_copy(text: str) -> bool:
    """Try to copy to clipboard using system tools."""
    import subprocess
    for cmd in [["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
                ["pbcopy"]]:
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            p.communicate(text.encode())
            if p.returncode == 0:
                return True
        except FileNotFoundError:
            continue
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  Raw terminal input
# ══════════════════════════════════════════════════════════════════════════════

def _read_key() -> str:
    fd  = sys.stdin.fileno()
    ch  = os.read(fd, 1)
    if ch == b"\x1b":
        import select
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            seq = os.read(fd, 16)
            full = ch + seq
            if full == b"\x1b[A":    return "UP"
            if full == b"\x1b[B":    return "DOWN"
            if full == b"\x1b[C":    return "RIGHT"
            if full == b"\x1b[D":    return "LEFT"
            if full == b"\x1b[H":    return "HOME"
            if full == b"\x1b[F":    return "END"
            if full == b"\x1b[3~":   return "DELETE"
            if full == b"\x1b[5~":   return "PGUP"
            if full == b"\x1b[6~":   return "PGDN"
            if full == b"\x1b[1;5C": return "CTRL_RIGHT"
            if full == b"\x1b[1;5D": return "CTRL_LEFT"
            if full == b"\x1b\x7f":  return "CTRL_BACKSPACE"
        return "ESC"
    if ch == b"\r" or ch == b"\n":  return "ENTER"
    if ch == b"\x7f":               return "BACKSPACE"
    if ch == b"\x08":               return "BACKSPACE"
    if ch == b"\x09":               return "TAB"
    if ch == b"\x0c":               return "CTRL_L"
    # NOTE: \x0d is CR = Enter in raw mode — do NOT also map it to CTRL_M
    #       Use \x0e (Ctrl+N) for model picker instead
    if ch == b"\x11":               return "CTRL_Q"
    if ch == b"\x03":               return "CTRL_C"
    if ch == b"\x0b":               return "CTRL_K"
    if ch == b"\x0e":               return "CTRL_N"   # model picker (Ctrl+N)
    if ch == b"\x17":               return "CTRL_W"   # delete word
    if ch == b"\x01":               return "HOME"     # Ctrl+A
    if ch == b"\x05":               return "END"      # Ctrl+E
    if ch == b"\x15":               return "CTRL_U"   # clear line
    if ch == b"\x10":               return "HIST_UP"  # Ctrl+P  history up
    if ch == b"\x0e":               return "HIST_DN"  # Ctrl+O  history down (fallback, same as CTRL_N handled above)
    if ch == b"\x12":               return "CTRL_R"   # retry
    try:
        decoded = ch.decode("utf-8")
        # handle multi-byte UTF-8
        if ord(decoded) >= 0x80:
            # continuation bytes might follow
            return decoded
        return decoded
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  Message model
# ══════════════════════════════════════════════════════════════════════════════

class Msg:
    __slots__ = ("role", "text", "ts", "label")
    def __init__(self, role: str, text: str, label: str = ""):
        self.role  = role     # user | assistant | streaming | system | error
        self.text  = text
        self.ts    = _hm()
        self.label = label


class Store:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: list[Msg] = []

    def add(self, m: Msg) -> int:
        with self._lock:
            self._data.append(m)
            return len(self._data) - 1

    def append(self, idx: int, chunk: str) -> None:
        with self._lock:
            self._data[idx].text += chunk

    def set_text(self, idx: int, text: str) -> None:
        """Replace entire text of a message (used for refined council output)."""
        with self._lock:
            self._data[idx].text = text

    def finalize(self, idx: int) -> None:
        with self._lock:
            self._data[idx].role = "assistant"

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def snapshot(self) -> list[Msg]:
        with self._lock:
            return list(self._data)

    def last_assistant(self) -> str:
        with self._lock:
            for m in reversed(self._data):
                if m.role == "assistant":
                    return m.text
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  Syntax highlighter
# ══════════════════════════════════════════════════════════════════════════════

_KW = {
    "def","class","return","import","from","if","elif","else","for","while",
    "in","not","and","or","True","False","None","try","except","with","as",
    "pass","break","continue","raise","yield","lambda","async","await",
    "const","let","var","function","new","typeof","instanceof","this",
    "self","super","static","public","private","protected","void","int",
    "str","bool","list","dict","tuple","set","type","None",
}

def _syntax_hi(line: str) -> str:
    """Lightweight syntax highlight for a single code line."""
    out = []
    for tok in re.split(r'(\s+|[(){}\[\],.:;=+\-*/<>!&|#"\'`@])', line):
        if not tok:
            continue
        if tok.strip() in _KW:
            out.append(_fg(PURPLE) + _bold() + tok + R() + _fg(GREEN))
        elif re.match(r'^\d+(\.\d+)?$', tok):
            out.append(_fg(ORANGE) + tok + _fg(GREEN))
        elif tok.startswith('"') or tok.startswith("'"):
            out.append(_fg(YELLOW) + tok + _fg(GREEN))
        elif tok.startswith("#") or tok.startswith("//"):
            out.append(_fg(COMMENT) + _italic() + tok + R())
            break  # rest of line is a comment
        else:
            out.append(tok)
    return "".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  Renderer
# ══════════════════════════════════════════════════════════════════════════════

class Renderer:
    def __init__(self, tui: "LumiTUI"):
        self.tui   = tui
        self._lock = threading.Lock()

    def draw(self) -> None:
        with self._lock:
            self._draw()

    def _draw(self) -> None:
        rows, cols = _term_size()
        chat_w     = cols
        buf: list[str] = []
        w = buf.append

        w(_hide_cur())
        w(_move(1, 1))
        w(self._title_bar(cols))

        # ── sidebar ───────────────────────────────────────────────────────────
        sb_w = 28
        # Only show sidebar when council is active or always?
        # Show always if terminal wide enough
        show_sb = cols >= 100 and (self.tui.agents or self.tui.prov == "council")
        if show_sb:
            chat_w = cols - sb_w - 1
            self._draw_sidebar(buf, rows, cols, chat_w, sb_w)

        # ── chat ──────────────────────────────────────────────────────────────
        chat_rows  = rows - 4
        chat_lines = self._build_chat_lines(chat_w)
        total      = len(chat_lines)
        offset     = max(0, min(self.tui.scroll_offset, max(0, total - chat_rows)))
        end        = total - offset
        start      = max(0, end - chat_rows)
        chat_lines = chat_lines[start:end]
        while len(chat_lines) < chat_rows:
            chat_lines.insert(0, "")

        for i in range(chat_rows):
            row_n = i + 2
            w(_move(row_n, 1))
            cl  = chat_lines[i] if i < len(chat_lines) else ""
            vis = _visible_len(cl)
            pad = max(0, chat_w - vis)
            w(_bg(BG) + cl + _bg(BG) + " " * pad)

        # ── input ─────────────────────────────────────────────────────────────
        w(self._input_area(rows, cols, chat_w))

        # ── popups ────────────────────────────────────────────────────────────
        if self.tui.slash_visible and self.tui.slash_hits:
            w(self._slash_popup(rows, cols, chat_w))
        if self.tui.picker_visible and self.tui.picker_items:
            w(self._picker_popup(rows, cols))
        if self.tui.notification:
            w(self._notification(rows, cols))

        # ── cursor ────────────────────────────────────────────────────────────
        disp_w  = chat_w - 6
        scroll  = max(0, self.tui.cur_pos - disp_w + 1)
        cur_col = 5 + (self.tui.cur_pos - scroll)
        w(_move(rows - 1, min(cur_col, cols - 1)))
        w(_show_cur())

        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    # ── title bar ─────────────────────────────────────────────────────────────

    def _title_bar(self, cols: int) -> str:
        tui   = self.tui
        pcol  = PROV_COL.get(tui.prov, PURPLE)
        pname = PROV_NAME.get(tui.prov, tui.prov)
        model = tui.model.split("/")[-1][:28]
        toks  = sum(_tok(m["content"]) for m in tui.history)

        left = (
            _bg(BG_DARK) + B(PURPLE) + " ◆ " + R() +
            _bg(BG_DARK) + _bold() + _fg(FG_HI) + "Lumi AI" + R() +
            _bg(BG_DARK) + _fg(BORDER) + "  ─  " + R() +
            _bg(BG_DARK) + _fg(COMMENT) + "terminal assistant" + R()
        )
        right = (
            _bg(BG_DARK) + _fg(MUTED) + f"~{toks:,}tk " + R() +
            _bg(BG_DARK) + _fg(COMMENT) + pname + R() +
            _bg(BG_DARK) + _fg(BORDER) + " / " + R() +
            _bg(BG_DARK) + _fg(pcol) + model + R() +
            _bg(BG_DARK) + " "
        )

        lv = _visible_len(left)
        rv = _visible_len(right)

        scroll_ind = ""
        if tui.scroll_offset > 0:
            scroll_ind = _bg(BG_DARK) + _fg(YELLOW) + f" ↑{tui.scroll_offset} " + R()
        si_v = _visible_len(scroll_ind)
        gap  = max(1, cols - lv - rv - si_v)

        return (
            _move(1, 1) +
            left +
            _bg(BG_DARK) + " " * gap +
            scroll_ind +
            right +
            _bg(BG) + R()
        )

    # ── sidebar (council agents) ──────────────────────────────────────────────

    def _draw_sidebar(self, buf, rows, cols, chat_w, sb_w):
        x = chat_w + 2

        def sb(row, content=""):
            buf.append(_move(row, x) + _bg(BG_DARK) + _erase_line() + content + R())

        # divider
        for r in range(2, rows - 3):
            buf.append(_move(r, chat_w + 1) + _bg(BG_DARK) + _fg(BORDER) + "│" + R())

        r = 2
        sb(r, _bg(BG_HL) + B(COMMENT) + " ◆ Council" + R()); r += 1
        sb(r); r += 1

        for ag in self.tui.agents:
            if r >= rows - 4: break
            if ag.st == "spin":
                icon = _fg(YELLOW) + SPINNER_FRAMES[ag.frame]
            elif ag.st == "ok":
                icon = _fg(GREEN) + "✓"
            else:
                icon = _fg(RED) + "✗"
            acol = _fg(AGENT_COL.get(ag.aid, FG))
            star = _fg(YELLOW) + " ★" if ag.lead else ""
            if ag.st == "ok" and ag.conf:
                meta = _fg(COMMENT) + f" {ag.conf}/10·{ag.t}s"
            elif ag.st == "spin":
                meta = _fg(MUTED) + " …"
            else:
                meta = ""
            sb(r, f" {R()}{icon} {acol}{ag.name}{R()}{star}{meta}"); r += 1

        sb(r); r += 1
        sb(r, _bg(BG_HL) + B(COMMENT) + " ◆ Keys" + R()); r += 1
        kb = [
            (BLUE, "Ctrl+N", FG_DIM, "model picker"),
            (BLUE, "Ctrl+L", FG_DIM, "clear"),
            (BLUE, "Ctrl+R", FG_DIM, "retry"),
            (BLUE, "Ctrl+W", FG_DIM, "delete word"),
            (BLUE, "PgUp",   FG_DIM, "scroll"),
            (BLUE, "/",      FG_DIM, "commands"),
        ]
        for kc, key, vc, val in kb:
            if r >= rows - 3: break
            sb(r, f" {_fg(kc)}{key:<8}{_fg(vc)}{val}"); r += 1

        # fill rest
        while r < rows - 3:
            sb(r); r += 1

    # ── chat lines ────────────────────────────────────────────────────────────

    def _build_chat_lines(self, width: int) -> list[str]:
        msgs  = self.tui.store.snapshot()
        lines: list[str] = []
        inner = max(20, width - 4)

        if not msgs:
            lines += [""] * 3
            lines.append("  " + B(PURPLE) + "◆  Lumi AI" + R())
            lines.append("")
            lines.append(
                "  " + _fg(MUTED) + "Type anything to start.  " +
                _fg(BLUE) + "/" + _fg(MUTED) + " for commands." + R()
            )
            lines.append("")
            lines.append("  " + _fg(MUTED) + "↑↓  scroll   ·   PgUp/PgDn  page   ·   Ctrl+N  model" + R())
            return lines

        for msg in msgs:
            lines.append("")
            if msg.role == "user":
                lines.append(
                    "  " + B(BLUE) + "you" +
                    "  " + _fg(COMMENT) + msg.ts + R()
                )
                for ln in textwrap.wrap(msg.text, inner) or [msg.text]:
                    lines.append("  " + _fg(FG_HI) + ln + R())
                lines.append("")

            elif msg.role in ("assistant", "streaming"):
                label  = msg.label or "◆ lumi"
                cursor = (" " + _fg(CYAN) + "▊" + R()) if msg.role == "streaming" else ""
                lines.append(
                    "  " + B(PURPLE) + label +
                    "  " + _fg(COMMENT) + msg.ts + R()
                )
                raw_lines = msg.text.split("\n") if msg.text else [""]
                in_code   = False
                code_lang = ""
                code_w    = min(inner, 88)

                for ln in raw_lines:
                    if ln.startswith("```"):
                        if not in_code:
                            in_code   = True
                            code_lang = ln[3:].strip()
                            lang_tag  = _fg(BLUE) + _bold() + code_lang + R() if code_lang else ""
                            bar_fill  = "─" * max(0, code_w - 4 - len(code_lang))
                            lines.append(
                                "  " + _bg(BG_DARK) + _fg(MUTED) + "┌─ " +
                                lang_tag + _bg(BG_DARK) + _fg(MUTED) + bar_fill + "┐" + R()
                            )
                        else:
                            in_code = False
                            lines.append(
                                "  " + _bg(BG_DARK) + _fg(MUTED) +
                                "└" + "─" * (code_w - 2) + "┘" + R()
                            )
                        continue

                    if in_code:
                        max_cc = code_w - 4
                        sub = textwrap.wrap(ln, max_cc) if len(ln) > max_cc else [ln]
                        if not sub: sub = [""]
                        for sl in sub:
                            hi  = _syntax_hi(sl)
                            pad = max(0, max_cc - len(sl))
                            lines.append(
                                "  " + _bg(BG_DARK) + _fg(MUTED) + "│ " +
                                _fg(GREEN) + hi + R() +
                                _bg(BG_DARK) + " " * pad +
                                _fg(MUTED) + " │" + R()
                            )
                    elif re.match(r"^#{1,6} ", ln):
                        level = len(ln) - len(ln.lstrip("#"))
                        text  = ln.lstrip("# ")
                        col   = [BLUE, CYAN, TEAL, FG_HI, FG, FG_DIM][min(level-1, 5)]
                        lines.append("  " + _fg(col) + _bold() + text + R())
                    elif ln.startswith("> "):
                        lines.append(
                            "  " + _fg(MUTED) + "▎" + _italic() + _fg(FG_DIM) +
                            ln[2:] + R()
                        )
                    elif re.match(r"^[-*•] ", ln):
                        lines.append(
                            "  " + _fg(PURPLE) + " •" + _fg(FG) +
                            " " + ln[2:] + R()
                        )
                    elif re.match(r"^\d+\. ", ln):
                        m2  = re.match(r"^(\d+\.\s)", ln)
                        num = m2.group(1) if m2 else ""
                        rest = ln[len(num):]
                        lines.append("  " + _fg(PURPLE) + " " + num + _fg(FG) + rest + R())
                    elif re.match(r"^---+$", ln.strip()):
                        lines.append("  " + _fg(MUTED) + "─" * min(inner, 60) + R())
                    elif re.match(r"^\*\*(.+)\*\*$", ln.strip()):
                        inner_text = re.match(r"^\*\*(.+)\*\*$", ln.strip()).group(1)
                        lines.append("  " + _bold() + _fg(FG_HI) + inner_text + R())
                    elif ln.strip() == "":
                        lines.append("")
                    else:
                        # inline `code`, **bold**, *italic*
                        rendered = self._render_inline(ln)
                        for wl in (textwrap.wrap(_strip_ansi(ln), inner) or [ln]):
                            # use rendered version for single lines, wrapped for long
                            if len(_strip_ansi(ln)) <= inner:
                                lines.append("  " + rendered + R())
                                break
                            else:
                                lines.append("  " + _fg(FG) + wl + R())

                if cursor:
                    lines.append("  " + cursor + R())
                lines.append("")

            elif msg.role == "system":
                for sln in msg.text.split("\n"):
                    wrapped = textwrap.wrap(sln, inner) if sln.strip() else [""]
                    for wl in wrapped:
                        lines.append("  " + _fg(TEAL) + wl + R())

            elif msg.role == "error":
                lines.append("  " + _fg(RED) + _bold() + "⚠  " + R() + _fg(RED) + msg.text + R())
                lines.append("")

        return lines

    def _render_inline(self, text: str) -> str:
        """Render inline markdown: `code`, **bold**, *italic*, ~~strike~~"""
        out = ""
        i   = 0
        while i < len(text):
            if text[i:i+2] == "**" and "**" in text[i+2:]:
                end = text.index("**", i+2)
                out += _bold() + _fg(FG_HI) + text[i+2:end] + R() + _fg(FG)
                i    = end + 2
            elif text[i] == "*" and i+1 < len(text) and text[i+1] != "*" and "*" in text[i+1:]:
                end = text.index("*", i+1)
                out += _italic() + _fg(FG_DIM) + text[i+1:end] + R() + _fg(FG)
                i    = end + 1
            elif text[i] == "`" and "`" in text[i+1:]:
                end = text.index("`", i+1)
                out += _bg(BG_DARK) + _fg(CYAN) + " " + text[i+1:end] + " " + R() + _fg(FG)
                i    = end + 1
            else:
                out += _fg(FG) + text[i]
                i   += 1
        return out

    # ── input area ────────────────────────────────────────────────────────────

    def _input_area(self, rows: int, cols: int, chat_w: int) -> str:
        tui    = self.tui
        sep    = (
            _move(rows - 2, 1) +
            _bg(BG) + _fg(MUTED) + " " + "─" * (chat_w - 2) + " " + R()
        )
        if tui.busy:
            symbol = _fg(YELLOW) + "⠿" + R()
            hint   = _fg(MUTED) + "  generating…" + R()
        else:
            symbol = _fg(COMMENT) + "›" + R()
            hint   = ""

        txt    = tui.buf
        disp_w = chat_w - 6
        scroll = max(0, tui.cur_pos - disp_w + 1)
        shown  = txt[scroll: scroll + disp_w]

        input_line = (
            _move(rows - 1, 1) +
            _bg(BG) + "  " + symbol + " " +
            _bg(BG) + _fg(FG_HI) + shown +
            _bg(BG) + " " * max(0, disp_w - len(shown)) +
            hint + R()
        )
        empty = (_move(rows, 1) + _bg(BG) + " " * cols + R())
        return sep + input_line + empty

    # ── slash popup ───────────────────────────────────────────────────────────

    def _slash_popup(self, rows: int, cols: int, chat_w: int) -> str:
        hits  = self.tui.slash_hits
        sel   = self.tui.slash_sel
        pop_w = min(64, chat_w - 4)
        n     = min(len(hits), 10)
        top   = rows - 2 - n - 3
        left  = max(1, (cols - pop_w) // 2)

        out = []
        out.append(
            _move(top, left) +
            _bg(BG_DARK) + _fg(MUTED) + "┌" + "─" * (pop_w - 2) + "┐" + R()
        )
        header = "  / commands   Tab=complete  Enter=run  Esc=close"
        pad    = max(0, pop_w - 2 - len(header))
        out.append(
            _move(top + 1, left) +
            _bg(BG_DARK) + _fg(MUTED) + "│" +
            _bg(BG_DARK) + _fg(COMMENT) + header + " " * pad + R() +
            _bg(BG_DARK) + _fg(MUTED) + "│" + R()
        )
        for i, (cmd, desc) in enumerate(hits[:10]):
            bg_  = _bg(BG_HL) if i == sel else _bg(BG_DARK)
            cc   = _fg(CYAN) + _bold() if i == sel else _fg(BLUE)
            dc   = _fg(FG)   if i == sel else _fg(MUTED)
            line = f" {cmd:<18}{desc}"
            pad2 = max(0, pop_w - 2 - len(line))
            out.append(
                _move(top + 2 + i, left) +
                _bg(BG_DARK) + _fg(MUTED) + "│" +
                bg_ + cc + f" {cmd:<18}" + R() + bg_ + dc + desc + " " * pad2 + R() +
                _bg(BG_DARK) + _fg(MUTED) + "│" + R()
            )
        bot = top + 2 + n
        out.append(
            _move(bot, left) +
            _bg(BG_DARK) + _fg(MUTED) + "└" + "─" * (pop_w - 2) + "┘" + R()
        )
        return "".join(out)

    # ── model picker ─────────────────────────────────────────────────────────

    def _picker_popup(self, rows: int, cols: int) -> str:
        items = self.tui.picker_items
        sel   = self.tui.picker_sel
        pop_w = 66
        left  = max(3, (cols - pop_w) // 2)
        out   = []
        top   = 3

        out.append(
            _move(top, left) +
            _bg(BG_POP) + _fg(PURPLE) + "┌" + "─" * (pop_w - 2) + "┐" + R()
        )
        title = "  ◆  LUMI  —  Model & Provider"
        tp    = max(0, pop_w - 2 - len(title))
        out.append(
            _move(top+1, left) +
            _bg(BG_POP) + _fg(PURPLE) + "│" +
            B(PURPLE) + title + " " * tp + R() +
            _bg(BG_POP) + _fg(PURPLE) + "│" + R()
        )

        row = top + 2
        for i, (kind, value, label) in enumerate(items):
            if kind == "header":
                sp = max(0, pop_w - 2 - len(label) - 2)
                out.append(
                    _move(row, left) +
                    _bg(BG_POP) + _fg(PURPLE) + "│" +
                    _bg(BG_HL) + B(COMMENT) + "  " + label + " " * sp + R() +
                    _bg(BG_POP) + _fg(PURPLE) + "│" + R()
                )
            else:
                is_sel = i == sel
                dot    = "●" if is_sel else "○"
                bg_    = _bg(BG_HL) if is_sel else _bg(BG_POP)
                lc     = B(CYAN) + " " if is_sel else _fg(FG_DIM)
                # show provider color dot
                vcol   = PROV_COL.get(value, FG) if kind == "provider" else FG
                vcolstr = _fg(vcol) if is_sel else _fg(FG_DIM)
                line   = f"  {dot}  {label}"
                pp     = max(0, pop_w - 2 - len(line))
                out.append(
                    _move(row, left) +
                    _bg(BG_POP) + _fg(PURPLE) + "│" +
                    bg_ + lc + _fg(MUTED) + f"  {dot}  " + vcolstr + label + " " * pp + R() +
                    _bg(BG_POP) + _fg(PURPLE) + "│" + R()
                )
            row += 1

        hint = "  Esc close   ·   ↑↓ navigate   ·   Enter select"
        hp   = max(0, pop_w - 2 - len(hint))
        out.append(
            _move(row, left) +
            _bg(BG_POP) + _fg(PURPLE) + "│" +
            _bg(BG_POP) + _fg(COMMENT) + hint + " " * hp + R() +
            _bg(BG_POP) + _fg(PURPLE) + "│" + R()
        )
        row += 1
        out.append(
            _move(row, left) +
            _bg(BG_POP) + _fg(PURPLE) + "└" + "─" * (pop_w - 2) + "┘" + R()
        )
        return "".join(out)

    # ── notification toast ────────────────────────────────────────────────────

    def _notification(self, rows: int, cols: int) -> str:
        msg   = self.tui.notification
        pop_w = min(len(msg) + 6, cols - 4)
        left  = max(1, cols - pop_w - 2)
        row   = rows - 5
        return (
            _move(row, left) +
            _bg(BG_POP) + _fg(CYAN) + " ◆ " + _fg(FG_HI) + msg + " " + R()
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Agent state
# ══════════════════════════════════════════════════════════════════════════════

class AgentState:
    def __init__(self, aid: str, name: str, lead: bool = False):
        self.aid   = aid
        self.name  = name
        self.lead  = lead
        self.st    = "spin"
        self.conf  = ""
        self.t     = ""
        self.frame = 0

    def done(self, ok: bool, conf: str, t: str) -> None:
        self.st, self.conf, self.t = ("ok" if ok else "fail"), conf, t


# ══════════════════════════════════════════════════════════════════════════════
#  Main TUI
# ══════════════════════════════════════════════════════════════════════════════

class LumiTUI:

    def __init__(self):
        self.store    = Store()
        self.history: list[dict] = []
        self.prov     = "unknown"
        self.model    = "unknown"
        self.busy     = False
        self.sysprompt = "You are Lumi, a helpful AI assistant."

        # input
        self.buf:     str = ""
        self.cur_pos: int = 0

        # input history (previous messages sent this session)
        self._input_history: list[str] = []
        self._hist_idx: int = -1        # -1 = current draft
        self._hist_draft: str = ""      # saved draft while browsing history

        # council
        self.agents: list[AgentState] = []

        # slash menu
        self.slash_hits:    list[tuple] = []
        self.slash_sel:     int         = 0
        self.slash_visible: bool        = False

        # model picker
        self.picker_items:   list[tuple] = []
        self.picker_sel:     int         = 0
        self.picker_visible: bool        = False

        # scroll
        self.scroll_offset: int = 0

        # notification toast
        self.notification:   str  = ""
        self._notif_timer         = None

        self.renderer   = Renderer(self)
        self._running   = False

    # ── notify toast ──────────────────────────────────────────────────────────

    def _notify(self, msg: str, duration: float = 2.5) -> None:
        self.notification = msg
        self.redraw()
        if self._notif_timer:
            self._notif_timer.cancel()
        def _clear():
            self.notification = ""
            self.redraw()
        self._notif_timer = threading.Timer(duration, _clear)
        self._notif_timer.daemon = True
        self._notif_timer.start()

    # ── draw ──────────────────────────────────────────────────────────────────

    def redraw(self) -> None:
        self.renderer.draw()

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        from src.chat.hf_client import get_provider, get_models
        from src.prompts.builder import build_system_prompt

        try:
            p = get_provider()
            m = get_models(p)[0] if p != "council" else "council"
        except Exception:
            p, m = "unknown", "unknown"
        self.prov, self.model = p, m

        try:
            self.sysprompt = build_system_prompt()
        except Exception:
            pass

        fd  = sys.stdin.fileno()
        old = termios.tcgetattr(fd)

        def _cleanup(*_):
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass
            sys.stdout.write(_show_cur() + _alt_off())
            sys.stdout.flush()

        # resize handler
        def _resize(*_):
            self.redraw()

        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))
        try:
            signal.signal(signal.SIGWINCH, _resize)
        except (AttributeError, OSError):
            pass  # SIGWINCH not on all platforms

        try:
            sys.stdout.write(_alt_on())
            sys.stdout.flush()
            tty.setraw(fd)
            self._running = True
            self.redraw()

            while self._running:
                key = _read_key()
                self._handle_key(key)
                self.redraw()

        except KeyboardInterrupt:
            pass
        finally:
            _cleanup()

    # ── key handler ───────────────────────────────────────────────────────────

    def _handle_key(self, key: str) -> None:
        # ── ESC ───────────────────────────────────────────────────────────────
        if key == "ESC":
            if self.slash_visible:    self.slash_visible = False
            elif self.picker_visible: self.picker_visible = False
            return

        # ── quit ──────────────────────────────────────────────────────────────
        if key in ("CTRL_Q", "CTRL_C"):
            self._running = False
            return

        # ── model picker ──────────────────────────────────────────────────────
        if key in ("CTRL_N", "CTRL_K"):
            if not self.slash_visible:
                self._open_picker()
            return

        # ── clear ─────────────────────────────────────────────────────────────
        if key == "CTRL_L":
            self.store.clear()
            self.history.clear()
            self.agents.clear()
            self.busy = False
            self.buf = ""
            self.cur_pos = 0
            self.scroll_offset = 0
            self.slash_visible  = False
            self.picker_visible = False
            self._sys_msg("Chat cleared.")
            return

        # ── retry last message ────────────────────────────────────────────────
        if key == "CTRL_R":
            self._do_retry()
            return

        # ── clear line (Ctrl+U) ───────────────────────────────────────────────
        if key == "CTRL_U":
            self.buf = ""
            self.cur_pos = 0
            self.slash_visible = False
            return

        # ── navigation in menus ───────────────────────────────────────────────
        if key == "UP":
            if self.slash_visible:
                self.slash_sel = max(0, self.slash_sel - 1)
            elif self.picker_visible:
                new = self.picker_sel - 1
                while new >= 0 and self.picker_items[new][0] == "header":
                    new -= 1
                if new >= 0:
                    self.picker_sel = new
            elif not self.buf:
                self.scroll_offset += 3
            else:
                # input history up
                self._hist_navigate(-1)
            return

        if key == "DOWN":
            if self.slash_visible:
                self.slash_sel = min(len(self.slash_hits) - 1, self.slash_sel + 1)
            elif self.picker_visible:
                new = self.picker_sel + 1
                while new < len(self.picker_items) and self.picker_items[new][0] == "header":
                    new += 1
                if new < len(self.picker_items):
                    self.picker_sel = new
            elif not self.buf:
                self.scroll_offset = max(0, self.scroll_offset - 3)
            else:
                self._hist_navigate(1)
            return

        if key == "PGUP":
            rows, _ = _term_size()
            self.scroll_offset += max(1, rows - 6)
            return

        if key == "PGDN":
            rows, _ = _term_size()
            self.scroll_offset = max(0, self.scroll_offset - max(1, rows - 6))
            return

        if key == "HIST_UP":
            self._hist_navigate(-1); return
        if key == "HIST_DN":
            self._hist_navigate(1);  return

        # ── tab ───────────────────────────────────────────────────────────────
        if key == "TAB":
            if self.slash_visible and self.slash_hits:
                cmd = self.slash_hits[self.slash_sel][0]
                self.buf = cmd + " "
                self.cur_pos = len(self.buf)
                self.slash_visible = False
            return

        # ── enter ─────────────────────────────────────────────────────────────
        if key == "ENTER":
            if self.picker_visible:
                self._confirm_picker(); return
            if self.slash_visible and self.slash_hits:
                cmd = self.slash_hits[self.slash_sel][0]
                self.slash_visible = False
                self.buf = ""
                self.cur_pos = 0
                self._slash(cmd, "")
                return
            text = self.buf.strip()
            self.buf = ""
            self.cur_pos = 0
            self.slash_visible = False
            self._hist_idx = -1
            if text and not self.busy:
                # save to input history
                if not self._input_history or self._input_history[-1] != text:
                    self._input_history.append(text)
                if text.startswith("/"):
                    parts = text.split(None, 1)
                    self._slash(parts[0].lower(), parts[1] if len(parts) > 1 else "")
                else:
                    self._send(text)
            return

        # ── backspace ─────────────────────────────────────────────────────────
        if key == "BACKSPACE":
            if self.cur_pos > 0:
                self.buf = self.buf[:self.cur_pos-1] + self.buf[self.cur_pos:]
                self.cur_pos -= 1
            self._update_slash()
            return

        # ── delete forward ────────────────────────────────────────────────────
        if key == "DELETE":
            if self.cur_pos < len(self.buf):
                self.buf = self.buf[:self.cur_pos] + self.buf[self.cur_pos+1:]
            return

        # ── delete word (Ctrl+W) ──────────────────────────────────────────────
        if key == "CTRL_W":
            if self.cur_pos > 0:
                t   = self.buf[:self.cur_pos].rstrip()
                idx = t.rfind(" ")
                keep = t[:idx+1] if idx >= 0 else ""
                self.buf = keep + self.buf[self.cur_pos:]
                self.cur_pos = len(keep)
            self._update_slash()
            return

        # ── ctrl+right/left  word jump ────────────────────────────────────────
        if key == "CTRL_RIGHT":
            t = self.buf
            i = self.cur_pos
            while i < len(t) and t[i] == " ": i += 1
            while i < len(t) and t[i] != " ": i += 1
            self.cur_pos = i
            return

        if key == "CTRL_LEFT":
            i = self.cur_pos
            while i > 0 and self.buf[i-1] == " ": i -= 1
            while i > 0 and self.buf[i-1] != " ": i -= 1
            self.cur_pos = i
            return

        if key == "CTRL_BACKSPACE":
            # same as Ctrl+W
            self._handle_key("CTRL_W")
            return

        # ── cursor movement ───────────────────────────────────────────────────
        if key == "LEFT":
            self.cur_pos = max(0, self.cur_pos - 1); return
        if key == "RIGHT":
            self.cur_pos = min(len(self.buf), self.cur_pos + 1); return
        if key == "HOME":
            self.cur_pos = 0; return
        if key == "END":
            self.cur_pos = len(self.buf); return

        # ── printable ─────────────────────────────────────────────────────────
        if len(key) == 1 and (key.isprintable() or ord(key) > 127):
            self.buf = self.buf[:self.cur_pos] + key + self.buf[self.cur_pos:]
            self.cur_pos += 1
            self._update_slash()

    def _update_slash(self) -> None:
        if self.buf.startswith("/"):
            q = self.buf.lower()
            self.slash_hits    = [(c, d) for c, d in SLASH_CMDS if q in c]
            self.slash_sel     = 0
            self.slash_visible = bool(self.slash_hits)
        else:
            self.slash_visible = False

    def _hist_navigate(self, direction: int) -> None:
        """Browse input history with up/down."""
        hist = self._input_history
        if not hist:
            return
        if self._hist_idx == -1:
            self._hist_draft = self.buf  # save current draft
        new_idx = self._hist_idx + direction
        if new_idx < -1:
            return
        if new_idx >= len(hist):
            return
        self._hist_idx = new_idx
        if new_idx == -1:
            self.buf     = self._hist_draft
        else:
            # -1 = latest, so invert
            self.buf = hist[-(new_idx + 1)]
        self.cur_pos = len(self.buf)

    # ── slash ─────────────────────────────────────────────────────────────────

    def _slash(self, cmd: str, arg: str) -> None:
        match cmd:
            case "/council":
                self.prov = self.model = "council"
                self._sys_msg("⚡ Council mode — all agents in parallel")

            case "/model" | "/m":
                self._open_picker()

            case "/clear" | "/c":
                self.store.clear()
                self.history.clear()
                self.agents.clear()
                self.busy         = False
                self.scroll_offset = 0
                self._sys_msg("Chat cleared.")

            case "/retry" | "/r":
                self._do_retry()

            case "/exit" | "/quit" | "/q":
                self._running = False

            case "/web":
                if arg: self._send(f"Search the web for: {arg}")
                else:   self._sys_msg("Usage: /web <query>")

            case "/save":
                self._do_save(arg)

            case "/export":
                self._do_export(arg)

            case "/copy":
                self._do_copy()

            case "/tokens":
                toks  = sum(_tok(m["content"]) for m in self.history)
                turns = sum(1 for m in self.history if m["role"] == "user")
                self._sys_msg(f"Tokens ≈ {toks:,}   ·   Turns: {turns}   ·   Messages: {len(self.history)}")

            case "/sys":
                preview = self.sysprompt[:200] + ("…" if len(self.sysprompt) > 200 else "")
                self._sys_msg(f"System prompt:\n{preview}")

            case "/agent":
                self._sys_msg("Agent mode — prefix next message and Lumi will plan + execute steps.")

            case "/session":
                self._sys_msg("Session management — use main.py /session commands for now.")

            case "/memory":
                self._sys_msg("Memory viewer coming soon.")

            case "/help":
                lines = ["Commands:"] + [f"  {c:<18} {d}" for c, d in SLASH_CMDS]
                lines += [
                    "",
                    "Keybinds:",
                    "  Ctrl+N        model picker",
                    "  Ctrl+L        clear chat",
                    "  Ctrl+R        retry last message",
                    "  Ctrl+W        delete word",
                    "  Ctrl+U        clear input",
                    "  ↑↓            scroll (empty input) or input history",
                    "  PgUp/PgDn     scroll pages",
                    "  Ctrl+←/→      jump words",
                    "  Tab           complete slash command",
                    "  Ctrl+Q        quit",
                ]
                self._sys_msg("\n".join(lines))

            case _:
                self._sys_msg(f"Unknown command: {cmd}  (try /help)")

    def _sys_msg(self, text: str) -> None:
        self.store.add(Msg("system", text))

    def _do_retry(self) -> None:
        if self.busy:
            return
        # Find last user message
        for m in reversed(self.history):
            if m["role"] == "user":
                text = m["content"]
                # Remove last user + assistant pair from history
                self.history = self.history[:-2] if len(self.history) >= 2 else []
                # Remove last two msgs from store (user + assistant)
                snap = self.store.snapshot()
                for i, sm in reversed(list(enumerate(snap))):
                    if sm.role in ("user", "assistant"):
                        with self.store._lock:
                            self.store._data.pop(i)
                        break
                self._send(text)
                return
        self._sys_msg("Nothing to retry.")

    def _do_save(self, filename: str = "") -> None:
        snap = self.store.snapshot()
        if not snap:
            self._sys_msg("Nothing to save."); return
        if not filename:
            filename = f"lumi_chat_{_ts()}.txt"
        path = Path.home() / filename
        with open(path, "w") as f:
            for m in snap:
                if m.role in ("user", "assistant"):
                    f.write(f"[{m.role.upper()}]  {m.ts}\n{m.text}\n\n")
        self._notify(f"Saved → {path}")

    def _do_export(self, filename: str = "") -> None:
        snap = self.store.snapshot()
        if not snap:
            self._sys_msg("Nothing to export."); return
        if not filename:
            filename = f"lumi_chat_{_ts()}.md"
        path = Path.home() / filename
        with open(path, "w") as f:
            f.write(f"# Lumi Chat  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            for m in snap:
                if m.role == "user":
                    f.write(f"**You** · {m.ts}\n\n{m.text}\n\n---\n\n")
                elif m.role == "assistant":
                    label = m.label or "Lumi"
                    f.write(f"**{label}** · {m.ts}\n\n{m.text}\n\n---\n\n")
        self._notify(f"Exported → {path}")

    def _do_copy(self) -> None:
        text = self.store.last_assistant()
        if not text:
            self._sys_msg("No response to copy."); return
        if _clipboard_copy(text):
            self._notify("Copied to clipboard ✓")
        else:
            self._sys_msg("Clipboard tool not found (install xclip or xsel).")

    # ── model picker ──────────────────────────────────────────────────────────

    def _open_picker(self) -> None:
        from src.chat.hf_client import get_available_providers, get_models
        items: list[tuple] = []
        try:
            avail  = get_available_providers()
            models = get_models(self.prov) if self.prov not in ("council", "unknown") else []
            items.append(("header", "", "── Provider ──────────────────"))
            for p in avail:
                items.append(("provider", p, PROV_NAME.get(p, p)))
            if len(avail) >= 2:
                items.append(("provider", "council", "⚡ Council  (all agents in parallel)"))
            if models:
                items.append(("header", "", f"── Models  ({PROV_NAME.get(self.prov, self.prov)}) ──"))
                for m in models[:16]:
                    items.append(("model", m, m.split("/")[-1]))
        except Exception:
            pass
        self.picker_items   = items
        self.picker_sel     = 0
        self.picker_visible = True

    def _confirm_picker(self) -> None:
        from src.chat.hf_client import set_provider, get_models
        if not self.picker_items:
            self.picker_visible = False; return
        kind, value, label = self.picker_items[self.picker_sel]
        if kind == "header":
            return
        if kind == "provider":
            if value == "council":
                self.prov = self.model = "council"
            else:
                try:
                    set_provider(value)
                    self.prov  = value
                    ms = get_models(value)
                    self.model = ms[0] if ms else ""
                    self._open_picker()   # reload with new models
                    return
                except Exception:
                    pass
            self._sys_msg(f"Provider → {PROV_NAME.get(self.prov, self.prov)}")
        elif kind == "model":
            self.model = value
            self._sys_msg(f"Model → {value.split('/')[-1]}")
        self.picker_visible = False

    # ── send ──────────────────────────────────────────────────────────────────

    def _send(self, text: str) -> None:
        self.scroll_offset = 0
        self.store.add(Msg("user", text))
        self.history.append({"role": "user", "content": text})
        self.busy = True
        if self.prov == "council":
            self._thread_council(text)
        else:
            self._thread_normal(text)

    # ── normal stream ─────────────────────────────────────────────────────────

    def _thread_normal(self, text: str) -> None:
        from src.chat.hf_client import get_client
        msgs  = [{"role": "system", "content": self.sysprompt}] + self.history
        model = self.model
        idx   = self.store.add(Msg("streaming", "", "◆ lumi"))

        def _go():
            full = ""
            try:
                client = get_client()
                for chunk in client.chat.completions.create(
                    model=model, messages=msgs,
                    max_tokens=2048, temperature=0.7, stream=True
                ):
                    if not chunk.choices: continue
                    d = chunk.choices[0].delta.content
                    if d:
                        full += d
                        self.store.append(idx, d)
                        self.redraw()
            except Exception as ex:
                self.store.set_text(idx, f"⚠  {ex}")
                self.store.finalize(idx)
                self.history.append({"role": "assistant", "content": f"Error: {ex}"})
                self.busy = False
                self.redraw()
                return

            self.store.finalize(idx)
            self.history.append({"role": "assistant", "content": full})
            self.busy = False
            self.redraw()

        threading.Thread(target=_go, daemon=True).start()

    # ── council stream ────────────────────────────────────────────────────────

    def _thread_council(self, text: str) -> None:
        from src.agents.council import (
            _get_available_agents, LEAD_AGENTS, classify_task, council_ask,
        )
        avail   = _get_available_agents()
        task    = classify_task(text)
        lead_id = LEAD_AGENTS.get(task, "gemini")
        self.agents = [AgentState(a["id"], a["name"], a["id"] == lead_id) for a in avail]

        label = f"◆ council  {len(avail)} agents · {task}"
        msgs  = [{"role": "system", "content": self.sysprompt}] + self.history
        idx   = self.store.add(Msg("streaming", "", label))

        def _cb(aid, ok, conf, t):
            for ag in self.agents:
                if ag.aid == aid:
                    ag.done(ok, conf, t)
            self.redraw()

        def _spin():
            frame = 0
            while self.busy:
                for ag in self.agents:
                    ag.frame = frame
                self.redraw()
                frame = (frame + 1) % len(SPINNER_FRAMES)
                time.sleep(0.08)   # ← fixed: was threading.Event().wait which creates new obj each loop

        threading.Thread(target=_spin, daemon=True).start()

        def _go():
            full = refined = ""
            try:
                gen = council_ask(
                    msgs, text, stream=True, debate=True,
                    refine=True, silent=True, agent_callback=_cb,
                )
                for chunk in gen:
                    if chunk.startswith("\n\n__STATS__\n"):    continue
                    if chunk.startswith("\n\n__REFINED__\n\n"):
                        refined = chunk[len("\n\n__REFINED__\n\n"):]; continue
                    full += chunk
                    self.store.append(idx, chunk)
                    self.redraw()
            except Exception as ex:
                self.store.set_text(idx, f"⚠  {ex}")
                self.store.finalize(idx)
                self.history.append({"role": "assistant", "content": f"Error: {ex}"})
                self.busy = False
                self.redraw()
                return

            final = refined or full
            # BUG FIX: set_text so refined version actually shows
            if refined:
                self.store.set_text(idx, final)
            self.store.finalize(idx)
            self.history.append({"role": "assistant", "content": final})
            self.busy = False
            self.redraw()

        threading.Thread(target=_go, daemon=True).start()


# ── entry ─────────────────────────────────────────────────────────────────────

def launch() -> None:
    LumiTUI().run()

if __name__ == "__main__":
    launch()
