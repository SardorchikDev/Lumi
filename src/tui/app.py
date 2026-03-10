"""
◆ Lumi TUI — Tokyo Night · Polished terminal interface
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from datetime import datetime

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Markdown, Static, Button

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.chat.hf_client import (
    get_client, get_models, get_provider, set_provider,
    get_available_providers,
)
from src.prompts.builder import build_system_prompt

# ── Tokyo Night palette ───────────────────────────────────────────────────────
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

SPINNER  = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

AGENT_COL = {
    "gemini":     CYAN,
    "groq":       ORANGE,
    "openrouter": PURPLE,
    "mistral":    RED,
    "hf":         YELLOW,
    "github":     FG_HI,
    "cohere":     GREEN,
    "cloudflare": ORANGE,
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
    ("/council",  "switch to council — all agents"),
    ("/model",    "open model picker"),
    ("/clear",    "clear conversation"),
    ("/web",      "/web <query> — search the web"),
    ("/agent",    "autonomous agent mode"),
    ("/memory",   "view saved memory"),
    ("/session",  "list & resume sessions"),
    ("/help",     "show all commands"),
    ("/exit",     "quit lumi"),
]

def _tok(t: str) -> int:
    return max(1, int(len(t.split()) * 1.35))

def _hm() -> str:
    return datetime.now().strftime("%H:%M")

_bid = 0

# ═══════════════════════════════════════════════════════════════════════════════
#   CHAT BUBBLES
# ═══════════════════════════════════════════════════════════════════════════════

class UserBubble(Widget):
    DEFAULT_CSS = f"""
    UserBubble {{
        height: auto;
        padding: 0 2 1 2;
        margin: 1 6 0 0;
        background: {BG_HL};
        border-left: outer {BLUE};
    }}
    UserBubble .hdr {{ height: 1; }}
    UserBubble .who {{ color: {BLUE}; text-style: bold; width: 1fr; }}
    UserBubble .ts  {{ color: {COMMENT}; width: auto; }}
    UserBubble .msg {{ color: {FG_HI}; margin-top: 0; }}
    """
    def __init__(self, text: str, **kw):
        super().__init__(**kw)
        self._text = text

    def compose(self) -> ComposeResult:
        with Horizontal(classes="hdr"):
            yield Label(" you", classes="who")
            yield Label(_hm(), classes="ts")
        yield Static(self._text, classes="msg")


class AssistantBubble(Widget):
    DEFAULT_CSS = f"""
    AssistantBubble {{
        height: auto;
        padding: 0 2 1 2;
        margin: 1 0 0 6;
        background: {BG_POP};
        border-left: outer {PURPLE};
    }}
    AssistantBubble .hdr {{ height: 1; }}
    AssistantBubble .who {{ color: {PURPLE}; text-style: bold; width: 1fr; }}
    AssistantBubble .ts  {{ color: {COMMENT}; width: auto; }}
    AssistantBubble .cur {{ color: {CYAN}; }}
    AssistantBubble Markdown {{
        background: transparent; padding: 0; margin: 0; color: {FG};
    }}
    """
    def __init__(self, label: str = "◆ lumi", **kw):
        global _bid
        _bid += 1
        self._sid   = f"s{_bid}"
        self._label = label
        self._text  = ""
        super().__init__(**kw)

    def compose(self) -> ComposeResult:
        with Horizontal(classes="hdr"):
            yield Label(f" {self._label}", classes="who")
            yield Label(_hm(), classes="ts")
        yield Static("", classes="cur", id=self._sid)

    def append(self, chunk: str) -> None:
        self._text += chunk
        try:
            self.query_one(f"#{self._sid}", Static).update(self._text + f"[{CYAN}]▊[/]")
        except Exception:
            pass
        self._scroll()

    def finalize(self, override: str | None = None) -> None:
        final = override or self._text
        self._text = final
        try:
            self.query_one(f"#{self._sid}").remove()
        except Exception:
            pass
        self.mount(Markdown(final))
        self._scroll()

    def _scroll(self) -> None:
        try:
            self.app.query_one("#chat-scroll").scroll_end(animate=False)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#   SIDEBAR WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class SbHeader(Static):
    DEFAULT_CSS = f"""
    SbHeader {{
        height: 1;
        background: {BG_HL};
        color: {COMMENT};
        text-style: bold;
        padding: 0 2;
        margin-top: 1;
    }}
    """

class CouncilRow(Static):
    DEFAULT_CSS = f"""
    CouncilRow {{ height: 1; padding: 0 2; color: {FG_DIM}; }}
    """
    def __init__(self, agent_id: str, name: str, **kw):
        super().__init__(**kw)
        self.aid  = agent_id
        self.name = name
        self.st   = "wait"
        self.conf = ""
        self.t    = ""
        self.lead = False
        self._fr  = 0
        self._upd()

    def _upd(self) -> None:
        icon = {
            "wait": f"[{MUTED}]·[/]",
            "spin": f"[{YELLOW}]{SPINNER[self._fr]}[/]",
            "ok":   f"[{GREEN}]✓[/]",
            "fail": f"[{RED}]✗[/]",
        }.get(self.st, "·")
        col  = AGENT_COL.get(self.aid, FG)
        nm   = f"[{col}]{self.name}[/]"
        star = f" [{YELLOW}]★[/]" if self.lead else ""
        if self.st == "ok" and self.conf:
            ex = f" [{COMMENT}]{self.conf}/10 · {self.t}s[/]"
        elif self.st == "spin":
            ex = f" [{MUTED}]thinking…[/]"
        else:
            ex = ""
        self.update(f"{icon} {nm}{star}{ex}")

    def tick(self, fr: int) -> None:
        self._fr = fr
        if self.st == "spin":
            self._upd()

    def start(self) -> None:
        self.st = "spin"; self._upd()

    def done(self, ok: bool, conf: str = "", t: str = "") -> None:
        self.st = "ok" if ok else "fail"
        self.conf, self.t = conf, t
        self._upd()


class Sidebar(Vertical):
    DEFAULT_CSS = f"""
    Sidebar {{
        width: 30;
        background: {BG_DARK};
        border-left: solid {BORDER};
        overflow: hidden hidden;
    }}
    Sidebar .sb-top   {{
        height: 1;
        background: {BG_DARK};
        color: {PURPLE};
        text-style: bold;
        padding: 0 2;
        border-bottom: solid {BORDER};
    }}
    Sidebar .sb-val   {{ color: {FG_HI};   padding: 0 2; text-style: bold; }}
    Sidebar .sb-dim   {{ color: {FG_DIM};  padding: 0 2; }}
    Sidebar .sb-stat  {{ color: {FG};      padding: 0 2; height: 2; }}
    Sidebar .sb-keys  {{ color: {FG_DIM};  padding: 0 2; margin-top: 1; }}
    Sidebar #sb-cbox  {{ padding: 0 0; }}
    """

    def compose(self) -> ComposeResult:
        yield Static(" ◆ Lumi", classes="sb-top")
        yield SbHeader(" Model")
        yield Label("—", id="sb-model",    classes="sb-val")
        yield Label("—", id="sb-prov",     classes="sb-dim")
        yield SbHeader(" Session")
        yield Static("", id="sb-stat",     classes="sb-stat")
        yield SbHeader(" Council")
        yield Container(id="sb-cbox")
        yield SbHeader(" Shortcuts")
        yield Static(
            f"[{BLUE}]Ctrl+M[/]  model picker\n"
            f"[{BLUE}]Ctrl+L[/]  clear chat\n"
            f"[{BLUE}]Ctrl+Q[/]  quit\n"
            f"[{BLUE}]/[/]       commands",
            classes="sb-keys",
        )

    def set_model(self, prov: str, model: str) -> None:
        try:
            col = PROV_COL.get(prov, FG_HI)
            self.query_one("#sb-model", Label).update(f"[{col}]{model.split('/')[-1][:24]}[/]")
            self.query_one("#sb-prov",  Label).update(f"[{COMMENT}]{PROV_NAME.get(prov, prov)}[/]")
        except Exception:
            pass

    def set_stats(self, tokens: int, turns: int) -> None:
        try:
            self.query_one("#sb-stat", Static).update(
                f"[{COMMENT}]tokens[/]  [{CYAN}]{tokens:,}[/]\n"
                f"[{COMMENT}]turns [/]  [{CYAN}]{turns}[/]"
            )
        except Exception:
            pass

    def setup_council(self, agents: list, lead_id: str) -> dict:
        box  = self.query_one("#sb-cbox", Container)
        box.remove_children()
        rows = {}
        for a in agents:
            row      = CouncilRow(a["id"], a["name"], id=f"cr-{a['id']}")
            row.lead = a["id"] == lead_id
            box.mount(row)
            rows[a["id"]] = row
        return rows

    def clear_council(self) -> None:
        try:
            self.query_one("#sb-cbox", Container).remove_children()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#   SLASH COMMAND POPUP
# ═══════════════════════════════════════════════════════════════════════════════

class SlashPopup(Widget):
    DEFAULT_CSS = f"""
    SlashPopup {{
        height: auto;
        background: {BG_POP};
        border: round {BLUE};
        margin: 0 2 0 2;
        display: none;
        layer: overlay;
    }}
    SlashPopup.open {{ display: block; }}
    SlashPopup .row {{
        height: 1;
        padding: 0 2;
        color: {FG};
    }}
    SlashPopup .row.sel {{
        background: {BG_HL};
        color: {FG_HI};
    }}
    SlashPopup .row-hdr {{
        height: 1;
        padding: 0 2;
        background: {BG_HL};
        color: {COMMENT};
        text-style: bold;
    }}
    """
    sel: reactive[int] = reactive(0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._hits: list[tuple[str,str]] = []

    def show_for(self, query: str) -> None:
        q = query.lower()
        self._hits = [(c,d) for c,d in SLASH_CMDS if q in c]
        self.sel = 0
        self._rebuild()
        if self._hits:
            self.add_class("open")
        else:
            self.remove_class("open")

    def hide(self) -> None:
        self._hits = []
        self.remove_class("open")
        self.remove_children()

    def _rebuild(self) -> None:
        self.remove_children()
        self.mount(Static(f" Commands  [{COMMENT}]Tab to complete · Enter to run[/]", classes="row-hdr"))
        for i, (cmd, desc) in enumerate(self._hits[:9]):
            cls = "row sel" if i == self.sel else "row"
            self.mount(Static(
                f"[{BLUE}]{cmd:<16}[/][{COMMENT}]{desc}[/]",
                classes=cls,
            ))

    def move(self, d: int) -> None:
        if not self._hits: return
        self.sel = (self.sel + d) % len(self._hits)
        self._rebuild()

    def current(self) -> str | None:
        if self._hits and 0 <= self.sel < len(self._hits):
            return self._hits[self.sel][0]
        return None

    def is_open(self) -> bool:
        return "open" in self.classes


# ═══════════════════════════════════════════════════════════════════════════════
#   MODEL PICKER MODAL
# ═══════════════════════════════════════════════════════════════════════════════

class ModelPicker(ModalScreen):
    CSS = f"""
    ModelPicker {{ align: center middle; background: rgba(0,0,0,0.8); }}
    #mp {{
        width: 64; height: auto; max-height: 88%;
        background: {BG_POP}; border: round {PURPLE}; padding: 1 2;
    }}
    #mp-title {{
        color: {PURPLE}; text-style: bold;
        text-align: center; height: 1; margin-bottom: 1;
    }}
    .mp-sec {{
        height: 1; background: {BG_HL};
        color: {COMMENT}; text-style: bold; padding: 0 1; margin-top: 1;
    }}
    .pb {{
        width: 1fr; height: 1; background: transparent; border: none;
        color: {FG_DIM}; padding: 0 1;
    }}
    .pb:hover  {{ background: {BG_HL}; color: {CYAN}; }}
    .pb.cur    {{ color: {PURPLE}; text-style: bold; }}
    .mb {{
        width: 1fr; height: 1; background: transparent; border: none;
        color: {FG_DIM}; padding: 0 2;
    }}
    .mb:hover {{ background: {BG_HL}; color: {FG_HI}; }}
    .mb.cur   {{ color: {CYAN}; text-style: bold; }}
    #mp-hint  {{ color: {MUTED}; text-align: center; margin-top: 1; height: 1; }}
    """
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, prov: str, model: str, **kw):
        super().__init__(**kw)
        self._prov  = prov
        self._model = model
        self._mm: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        avail  = get_available_providers()
        models = get_models(self._prov) if self._prov not in ("council","unknown") else []
        with Container(id="mp"):
            yield Label("◆  LUMI  —  Model Picker", id="mp-title")
            yield Static(" Providers", classes="mp-sec")
            for p in avail:
                col    = PROV_COL.get(p, FG)
                active = "  cur" if p == self._prov else ""
                dot    = "●" if p == self._prov else "○"
                yield Button(f" {dot}  [{col}]{PROV_NAME.get(p,p)}[/]",
                             classes=f"pb{active}", id=f"p_{p}")
            if len(avail) >= 2:
                active = "  cur" if self._prov == "council" else ""
                dot    = "●" if self._prov == "council" else "○"
                yield Button(f" {dot}  [{PURPLE}]⚡ Council[/]  [{COMMENT}]all agents in parallel[/]",
                             classes=f"pb{active}", id="p_council")
            yield Static(" Models", classes="mp-sec")
            for i, m in enumerate(models[:16]):
                short  = m.split("/")[-1]
                active = "  cur" if m == self._model else ""
                dot    = "●" if m == self._model else "○"
                bid    = f"m_{i}"
                self._mm[bid] = m
                yield Button(f" {dot}  {short}", classes=f"mb{active}", id=bid)
            yield Label(f"[{MUTED}]Esc  close   ·   click to select[/]", id="mp-hint")

    @on(Button.Pressed)
    def _press(self, e: Button.Pressed) -> None:
        bid = e.button.id or ""
        if bid.startswith("p_"):   self.dismiss(("provider", bid[2:]))
        elif bid.startswith("m_"):
            m = self._mm.get(bid)
            if m: self.dismiss(("model", m))


# ═══════════════════════════════════════════════════════════════════════════════
#   INPUT BAR
# ═══════════════════════════════════════════════════════════════════════════════

class InputBar(Widget):
    DEFAULT_CSS = f"""
    InputBar {{
        height: 3;
        background: {BG_DARK};
        border-top: solid {BORDER};
    }}
    InputBar #ib-inner {{
        height: 3;
        align: left middle;
        padding: 0 2;
    }}
    InputBar #ib-icon {{
        width: 3; color: {PURPLE}; text-style: bold;
    }}
    InputBar #chat-input {{
        width: 1fr; background: transparent;
        border: none; color: {FG_HI}; padding: 0;
    }}
    InputBar #chat-input:focus {{ border: none; outline: none; }}
    InputBar #ib-info {{
        width: auto; color: {COMMENT}; padding: 0 1;
    }}
    """
    def compose(self) -> ComposeResult:
        with Horizontal(id="ib-inner"):
            yield Label(" ›", id="ib-icon")
            yield Input(
                placeholder="  ask lumi anything…   ( / for commands )",
                id="chat-input",
            )
            yield Label("", id="ib-info")

    def set_busy(self, busy: bool) -> None:
        try:
            self.query_one("#ib-icon",  Label).update(
                f"[{YELLOW}] ⠿[/]" if busy else f"[{PURPLE}] ›[/]"
            )
            self.query_one("#ib-info",  Label).update(
                f"[{YELLOW}]generating…[/]" if busy else ""
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#   TITLE BAR
# ═══════════════════════════════════════════════════════════════════════════════

class TitleBar(Static):
    DEFAULT_CSS = f"""
    TitleBar {{
        height: 1;
        background: {BG_DARK};
        color: {COMMENT};
        padding: 0 2;
        border-bottom: solid {BORDER};
    }}
    """
    def on_mount(self) -> None:
        self.update(
            f"[{PURPLE}] ◆ [/][{FG_HI}]Lumi AI[/]"
            f"  [{MUTED}]·[/]  [{COMMENT}]terminal assistant[/]"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#   SYSTEM MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════

class SystemMsg(Static):
    DEFAULT_CSS = f"""
    SystemMsg {{
        height: auto;
        padding: 0 2 1 2;
        margin: 1 6 0 6;
        background: {BG_HL};
        border-left: outer {TEAL};
        color: {FG_DIM};
    }}
    """


# ═══════════════════════════════════════════════════════════════════════════════
#   MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════

class LumiApp(App):
    TITLE = "Lumi AI"

    CSS = f"""
    Screen {{
        background: {BG};
        layers: base overlay;
    }}

    #app-grid {{ layout: horizontal; height: 100%; }}

    #chat-col {{
        width: 1fr; height: 100%; layout: vertical;
    }}

    #chat-scroll {{
        height: 1fr;
        padding: 0 1;
        scrollbar-color: {MUTED};
        scrollbar-size: 1 1;
    }}

    #slash-wrap {{
        height: auto;
        layer: overlay;
        dock: bottom;
        margin-bottom: 3;
        margin-right: 30;
        margin-left: 1;
    }}

    #welcome {{
        height: auto;
        padding: 2 4;
        margin: 3 8;
        background: {BG_POP};
        border: round {BORDER};
        color: {FG_DIM};
        text-align: center;
    }}

    Footer {{
        background: {BG_DARK};
        color: {MUTED};
        border-top: solid {BORDER};
        height: 1;
    }}
    Footer .footer--key {{ color: {BLUE}; text-style: bold; }}
    """

    BINDINGS = [
        Binding("ctrl+q", "quit",         "Quit"),
        Binding("ctrl+m", "model_picker", "Model"),
        Binding("ctrl+l", "clear_chat",   "Clear"),
        Binding("escape", "esc",          show=False),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._msgs:      list[dict] = []
        self._sysprompt: str        = ""
        self._prov:      str        = "unknown"
        self._model:     str        = "unknown"
        self._busy:      bool       = False
        self._rows:      dict       = {}
        self._sfr:       int        = 0
        self._stimer                = None

    # ── compose ───────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with Horizontal(id="app-grid"):
            with Vertical(id="chat-col"):
                yield TitleBar()
                yield ScrollableContainer(id="chat-scroll")
                yield Container(SlashPopup(id="slash"), id="slash-wrap")
                yield InputBar(id="input-bar")
            yield Sidebar(id="sidebar")
        yield Footer()

    # ── mount ─────────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        try:
            p = get_provider()
            m = get_models(p)[0] if p != "council" else "council"
        except Exception:
            p, m = "unknown", "unknown"
        self._prov, self._model = p, m
        try:
            self._sysprompt = build_system_prompt()
        except Exception:
            self._sysprompt = "You are Lumi, a helpful AI assistant."
        self._welcome()
        self._sync()
        self.query_one("#chat-input", Input).focus()

    def _welcome(self) -> None:
        col   = PROV_COL.get(self._prov, PURPLE)
        pname = PROV_NAME.get(self._prov, self._prov)
        model = self._model.split("/")[-1]
        self.query_one("#chat-scroll").mount(Static(
            f"[{PURPLE}]◆  Lumi AI[/]\n\n"
            f"[{COMMENT}]model   [/][{col}]{model}[/]  [{MUTED}]via {pname}[/]\n\n"
            f"[{MUTED}]Type anything to start.  Use [/][{BLUE}]/[/][{MUTED}] for commands.[/]",
            id="welcome",
        ))

    # ── input changed → slash menu ────────────────────────────────────────────
    @on(Input.Changed, "#chat-input")
    def _changed(self, e: Input.Changed) -> None:
        v    = e.value
        menu = self.query_one("#slash", SlashPopup)
        if v.startswith("/"):
            menu.show_for(v)
        else:
            menu.hide()

    # ── keys ──────────────────────────────────────────────────────────────────
    def on_key(self, event) -> None:
        menu = self.query_one("#slash", SlashPopup)
        if not menu.is_open():
            return
        if event.key == "up":
            menu.move(-1); event.stop()
        elif event.key == "down":
            menu.move(1);  event.stop()
        elif event.key == "tab":
            cmd = menu.current()
            if cmd:
                inp = self.query_one("#chat-input", Input)
                inp.value = cmd + " "
                inp.cursor_position = len(inp.value)
                menu.hide()
            event.stop()
        elif event.key == "enter" and menu.is_open():
            cmd = menu.current()
            if cmd:
                menu.hide()
                self.query_one("#chat-input", Input).value = ""
                self._slash(cmd, "")
                event.stop()

    def action_esc(self) -> None:
        menu = self.query_one("#slash", SlashPopup)
        if menu.is_open():
            menu.hide()

    # ── submit ────────────────────────────────────────────────────────────────
    @on(Input.Submitted, "#chat-input")
    def _submit(self, e: Input.Submitted) -> None:
        text = e.value.strip()
        if not text or self._busy:
            return
        e.input.value = ""
        self.query_one("#slash", SlashPopup).hide()
        if text.startswith("/"):
            parts = text.split(None, 1)
            self._slash(parts[0].lower(), parts[1] if len(parts) > 1 else "")
        else:
            self._send(text)

    # ── slash commands ────────────────────────────────────────────────────────
    def _slash(self, cmd: str, arg: str) -> None:
        def sys(txt: str) -> None:
            self.query_one("#chat-scroll").mount(SystemMsg(txt))
            self.query_one("#chat-scroll").scroll_end(animate=False)

        match cmd:
            case "/council":
                self._prov = self._model = "council"
                self._sync()
                sys(f"[{PURPLE}]⚡ Council mode[/] [{COMMENT}]— all agents in parallel[/]")
            case "/model" | "/m":
                self.action_model_picker()
            case "/clear" | "/c":
                self.action_clear_chat()
            case "/exit" | "/quit" | "/q":
                self.exit()
            case "/web":
                if arg:   self._send(f"Search the web for: {arg}")
                else:     sys(f"[{RED}]Usage: /web <query>[/]")
            case "/agent":
                sys(f"[{YELLOW}]Agent mode active — Lumi will plan and execute multi-step tasks.[/]")
            case "/memory":
                sys(f"[{COMMENT}]Memory viewer coming soon.[/]")
            case "/session":
                sys(f"[{COMMENT}]Session management coming soon.[/]")
            case "/help":
                lines = [f"[{PURPLE}]◆ Commands[/]"]
                for c, d in SLASH_CMDS:
                    lines.append(f"[{BLUE}]{c:<16}[/][{FG_DIM}]{d}[/]")
                sys("\n".join(lines))
            case _:
                sys(f"[{RED}]Unknown: {cmd}[/]  [{COMMENT}]try /help[/]")

    # ── send ──────────────────────────────────────────────────────────────────
    def _send(self, text: str) -> None:
        scroll = self.query_one("#chat-scroll")
        try:   self.query_one("#welcome").remove()
        except Exception: pass

        scroll.mount(UserBubble(text))
        scroll.scroll_end(animate=False)
        self._msgs.append({"role": "user", "content": text})
        self._busy = True
        self._sync()
        self.query_one("#input-bar", InputBar).set_busy(True)

        if self._prov == "council":
            self._council(text)
        else:
            self._normal(text)

    # ── normal stream ─────────────────────────────────────────────────────────
    def _normal(self, text: str) -> None:
        bubble   = AssistantBubble()
        messages = [{"role": "system", "content": self._sysprompt}] + self._msgs
        model    = self._model
        self.query_one("#chat-scroll").mount(bubble)
        self.query_one("#chat-scroll").scroll_end(animate=False)

        def _go():
            full = ""
            try:
                client = get_client()
                for chunk in client.chat.completions.create(
                    model=model, messages=messages,
                    max_tokens=2048, temperature=0.7, stream=True,
                ):
                    if not chunk.choices: continue
                    d = chunk.choices[0].delta.content
                    if d:
                        full += d
                        self.call_from_thread(bubble.append, d)
            except Exception as ex:
                full = f"⚠  {ex}"
                self.call_from_thread(bubble.append, full)
            self.call_from_thread(self._done_normal, bubble, full)

        threading.Thread(target=_go, daemon=True).start()

    def _done_normal(self, bubble: AssistantBubble, full: str) -> None:
        bubble.finalize()
        self._msgs.append({"role": "assistant", "content": full})
        self._busy = False
        self._sync()
        self.query_one("#input-bar", InputBar).set_busy(False)

    # ── council stream ────────────────────────────────────────────────────────
    def _council(self, text: str) -> None:
        from src.agents.council import (
            _get_available_agents, LEAD_AGENTS, classify_task, council_ask,
        )
        avail     = _get_available_agents()
        task      = classify_task(text)
        lead_id   = LEAD_AGENTS.get(task, "gemini")
        sb        = self.query_one("#sidebar", Sidebar)
        self._rows = sb.setup_council(avail, lead_id)
        for r in self._rows.values(): r.start()
        self._spin_start()

        bubble   = AssistantBubble(label=f"◆ council  [{COMMENT}]{len(avail)} agents · {task}[/]")
        messages = [{"role": "system", "content": self._sysprompt}] + self._msgs
        self.query_one("#chat-scroll").mount(bubble)
        self.query_one("#chat-scroll").scroll_end(animate=False)

        def _cb(aid, ok, conf, t):
            self.call_from_thread(self._agent_done, aid, ok, conf, t)

        def _go():
            try:
                gen  = council_ask(messages, text, stream=True, debate=True,
                                   refine=True, silent=True, agent_callback=_cb)
                full = refined = ""
                for chunk in gen:
                    if chunk.startswith("\n\n__STATS__\n"):    continue
                    if chunk.startswith("\n\n__REFINED__\n\n"):
                        refined = chunk[len("\n\n__REFINED__\n\n"):]; continue
                    full += chunk
                    self.call_from_thread(bubble.append, chunk)
                self.call_from_thread(self._done_council, bubble, refined or full)
            except Exception as ex:
                err = f"⚠  {ex}"
                self.call_from_thread(bubble.append, err)
                self.call_from_thread(self._done_council, bubble, err)

        threading.Thread(target=_go, daemon=True).start()

    def _agent_done(self, aid, ok, conf, t) -> None:
        r = self._rows.get(aid)
        if r: r.done(ok, conf, t)

    def _done_council(self, bubble: AssistantBubble, full: str) -> None:
        self._spin_stop()
        bubble.finalize()
        self._msgs.append({"role": "assistant", "content": full})
        self._busy = False
        self._sync()
        self.query_one("#input-bar", InputBar).set_busy(False)

    # ── spinner ───────────────────────────────────────────────────────────────
    def _spin_start(self) -> None:
        self._sfr    = 0
        self._stimer = self.set_interval(0.08, self._tick)

    def _spin_stop(self) -> None:
        if self._stimer:
            self._stimer.stop()
            self._stimer = None

    def _tick(self) -> None:
        self._sfr = (self._sfr + 1) % len(SPINNER)
        for r in self._rows.values(): r.tick(self._sfr)

    # ── actions ───────────────────────────────────────────────────────────────
    def action_model_picker(self) -> None:
        def _cb(result) -> None:
            if not result: return
            action, value = result
            if action == "provider":
                if value == "council":
                    self._prov = self._model = "council"
                else:
                    try:
                        set_provider(value)
                        self._prov = value
                        ms = get_models(value)
                        self._model = ms[0] if ms else ""
                    except Exception:
                        pass
            elif action == "model":
                self._model = value
            self._sync()
            self.query_one("#chat-input", Input).focus()
        self.push_screen(ModelPicker(self._prov, self._model), _cb)

    def action_clear_chat(self) -> None:
        self._msgs = []
        self._busy = False
        self._spin_stop()
        try:
            self.query_one("#chat-scroll").remove_children()
            self.query_one("#sidebar", Sidebar).clear_council()
        except Exception:
            pass
        self._welcome()
        self._sync()
        self.query_one("#input-bar", InputBar).set_busy(False)
        self.query_one("#chat-input", Input).focus()

    def _sync(self) -> None:
        toks  = sum(_tok(m["content"]) for m in self._msgs)
        turns = sum(1 for m in self._msgs if m["role"] == "user")
        try:
            sb = self.query_one("#sidebar", Sidebar)
            sb.set_model(self._prov, self._model)
            sb.set_stats(toks, turns)
        except Exception:
            pass


# ── entry ─────────────────────────────────────────────────────────────────────
def launch() -> None:
    LumiApp().run()

if __name__ == "__main__":
    launch()
