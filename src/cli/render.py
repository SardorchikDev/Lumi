"""
Terminal rendering utilities for Lumi CLI.

This renderer aims for a calmer, Codex-like terminal layout:
- compact header instead of a giant banner
- subtle separators and metadata
- cleaner user / assistant message labels
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
import threading
import time
from datetime import datetime

from src.utils.themes import get_theme

R = "\033[0m"
B = "\033[1m"
D = "\033[2m"

C1 = C2 = C3 = PU = BL = CY = GR = DG = MU = GN = RE = YE = WH = R


def reload_theme(name: str = None) -> None:
    """Load a color theme and update global color variables."""
    global C1, C2, C3, PU, BL, CY, GR, DG, MU, GN, RE, YE, WH
    theme = get_theme(name)
    C1 = theme["C1"]
    C2 = theme["C2"]
    C3 = theme["C3"]
    PU = theme["PU"]
    BL = theme["BL"]
    CY = theme["CY"]
    GR = theme["GR"]
    DG = theme["DG"]
    MU = theme["MU"]
    GN = theme["GN"]
    RE = theme["RE"]
    YE = theme["YE"]
    WH = theme["WH"]


reload_theme()


def terminal_width() -> int:
    return shutil.get_terminal_size((110, 30)).columns


def clear_screen() -> None:
    os.system("clear")


def current_time() -> str:
    return datetime.now().strftime("%H:%M")


def word_count(s: str) -> int:
    return len(s.split())


def _strip_ansi(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


def visual_length(s: str) -> int:
    return len(_strip_ansi(s))


def center_visual(s: str, width: int, fill: str = " ") -> str:
    vis = visual_length(s)
    pad = max(width - vis, 0)
    return fill * (pad // 2) + s + fill * (pad - pad // 2)


def _truncate_visual(text: str, width: int) -> str:
    plain = _strip_ansi(text)
    if len(plain) <= width:
        return text
    return plain[: max(width - 1, 0)] + "…"


def _rule(char: str = "─") -> str:
    return f"  {DG}{char * max(terminal_width() - 4, 8)}{R}"


def _badge(text: str, tone: str) -> str:
    return f"{tone}{B} {text} {R}"


def ok(msg: str, icon: str = "✓", c=None) -> None:
    print(f"\n  {c or GN}{icon}{R}  {GR}{msg}{R}\n")


def fail(msg: str) -> None:
    wrapped = textwrap.fill(str(msg), max(terminal_width() - 8, 20))
    print(f"\n  {RE}x{R}  {GR}{wrapped}{R}\n")


def info(msg: str) -> None:
    print(f"\n  {CY}i{R}  {GR}{msg}{R}\n")


def warn(msg: str) -> None:
    print(f"\n  {YE}!{R}  {GR}{msg}{R}\n")


def div(label: str = "") -> None:
    if label:
        text = f"{DG}──{R} {WH}{label}{R} {DG}──{R}"
        remaining = max(terminal_width() - visual_length(text) - 2, 0)
        print(f"\n  {text}{DG}{'─' * remaining}{R}\n")
    else:
        print(f"\n{_rule()}\n")


LOGO = [
    "lumi",
    "terminal coding assistant",
]
LOGO_WIDTH = len(LOGO[1])

PROV_COL = {
    "gemini": "\033[38;5;81m",
    "groq": "\033[38;5;215m",
    "openrouter": "\033[38;5;183m",
    "mistral": "\033[38;5;210m",
    "huggingface": "\033[38;5;179m",
    "github": "\033[38;5;252m",
    "cohere": "\033[38;5;86m",
    "bytez": "\033[38;5;51m",
    "cloudflare": "\033[38;5;208m",
    "ollama": "\033[38;5;114m",
    "council": "\033[38;5;141m",
}


def provider_color(p: str) -> str:
    return PROV_COL.get((p or "").lower(), DG)


def draw_header(model: str, turns: int = 0, provider: str = "") -> None:
    clear_screen()
    width = terminal_width()

    model_name = model.split("/")[-1]
    if provider == "council":
        from src.agents.council import _get_available_agents as _get_agents

        provider_name = "council"
        model_name = f"{len(_get_agents())} agents"
        pcol = provider_color("council")
    else:
        provider_name = provider or "provider"
        pcol = provider_color(provider_name)

    left = f"{C1}{B}{LOGO[0]}{R}  {DG}{LOGO[1]}{R}"
    meta = "  ".join(
        part
        for part in (
            _truncate_visual(_badge(provider_name, pcol), 18),
            _truncate_visual(_badge(model_name, BL), 34),
            _badge(f"{turns} turns", MU) if turns else "",
        )
        if part
    )

    print()
    print(_rule("╌"))
    gap = max(width - visual_length(left) - visual_length(meta) - 4, 1)
    print(f"  {left}{' ' * gap}{meta}")
    print(f"  {DG}workspace{R}  {D}{os.getcwd()}{R}")
    print(_rule("╌"))
    print()


def print_you(text: str) -> None:
    time_str = current_time()
    wrap_w = max(terminal_width() - 16, 24)
    wrapped = textwrap.wrap(text, width=wrap_w) or [text]
    print()
    print(f"  {DG}you{R}  {WH}{wrapped[0]}{R}")
    for line in wrapped[1:]:
        print(f"       {WH}{line}{R}")
    print(f"  {D}{time_str}{R}")


def print_lumi_label(name: str = "Lumi") -> None:
    time_str = current_time()
    label = _strip_ansi(name).lower()
    print(f"\n  {C1}{B}{label}{R}  {DG}·{R}  {D}{time_str}{R}\n")


def print_welcome(name: str) -> None:
    print(f"  {DG}ready{R}  {WH}{name}{R}  {DG}/help for commands{R}\n")


class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str = "thinking") -> None:
        self._label = label
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        for frame in self.FRAMES:
            if not self._running:
                break
            sys.stdout.write(f"\r  {PU}{frame}{R}  {DG}{self._label}{R}  ")
            sys.stdout.flush()
            time.sleep(0.08)
        while self._running:
            for frame in self.FRAMES:
                if not self._running:
                    break
                sys.stdout.write(f"\r  {PU}{frame}{R}  {DG}{self._label}{R}  ")
                sys.stdout.flush()
                time.sleep(0.08)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join()
        sys.stdout.write(f"\r{' ' * terminal_width()}\r")
        sys.stdout.flush()
