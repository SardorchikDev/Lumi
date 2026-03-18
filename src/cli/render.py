"""
Terminal rendering utilities for Lumi CLI.

Includes ANSI color constants, theme management, and formatted output functions.
"""

import os
import shutil
import sys
import textwrap
from datetime import datetime

from src.utils.themes import get_theme

# ANSI reset
R = "\033[0m"
B = "\033[1m"
D = "\033[2m"

# Theme globals (populated by reload_theme)
C1 = C2 = C3 = PU = BL = CY = GR = DG = MU = GN = RE = YE = WH = R


def reload_theme(name: str = None) -> None:
    """Load a color theme and update global color variables."""
    global C1, C2, C3, PU, BL, CY, GR, DG, MU, GN, RE, YE, WH
    t = get_theme(name)
    C1 = t["C1"]
    C2 = t["C2"]
    C3 = t["C3"]
    PU = t["PU"]
    BL = t["BL"]
    CY = t["CY"]
    GR = t["GR"]
    DG = t["DG"]
    MU = t["MU"]
    GN = t["GN"]
    RE = t["RE"]
    YE = t["YE"]
    WH = t["WH"]


# Initialize theme
reload_theme()


# Terminal helpers
def terminal_width() -> int:
    return shutil.get_terminal_size().columns


def clear_screen() -> None:
    os.system("clear")


def current_time() -> str:
    return datetime.now().strftime("%H:%M")


def word_count(s: str) -> int:
    return len(s.split())


# Formatted output
def ok(msg: str, icon: str = "✓", c=None) -> None:
    print(f"\n  {c or GN}{icon}  {GR}{msg}{R}\n")


def fail(msg: str) -> None:
    wrapped = textwrap.fill(str(msg), terminal_width() - 8)
    print(f"\n  {RE}✗  {GR}{wrapped}{R}\n")


def info(msg: str) -> None:
    print(f"\n  {CY}◆  {GR}{msg}{R}\n")


def warn(msg: str) -> None:
    print(f"\n  {YE}▲  {GR}{msg}{R}\n")


def div(label: str = "") -> None:
    w = terminal_width()
    if label:
        bar = f"  {DG}── {WH}{label}{R}{DG} ──{R}"
        trail = max(w - len(label) - 10, 0)
        print(f"\n{bar}{DG}{'─' * trail}{R}\n")
    else:
        print(f"\n  {DG}{'─' * (w - 4)}{R}\n")


# Visual constants
LOGO = [
    "    ██╗      ██╗   ██╗  ███╗   ███╗  ██╗   ",
    "    ██║      ██║   ██║  ████╗ ████║  ██║   ",
    "    ██║      ██║   ██║  ██╔████╔██║  ██║   ",
    "    ██║      ██║   ██║  ██║╚██╔╝██║  ██║   ",
    "    ███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║   ",
    "    ╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝   ",
]
LOGO_WIDTH = 46

PROV_COL = {
    "gemini": "\033[38;5;75m",
    "groq": "\033[38;5;215m",
    "openrouter": "\033[38;5;141m",
    "mistral": "\033[38;5;210m",
    "huggingface": "\033[38;5;179m",
    "bytez": "\033[38;5;51m",   # bright cyan
    "ollama": "\033[38;5;114m",
}


def provider_color(p: str) -> str:
    return PROV_COL.get(p.lower(), DG)


def visual_length(s: str) -> int:
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def center_visual(s: str, width: int, fill: str = " ") -> str:
    vis = visual_length(s)
    pad = max(width - vis, 0)
    return fill * (pad // 2) + s + fill * (pad - pad // 2)


# Header drawing
def draw_header(model: str, turns: int = 0, provider: str = "") -> None:
    clear_screen()
    w = terminal_width()
    pad = " " * max((w - LOGO_WIDTH) // 2, 2)
    grad = [C1, C1, C2, C2, C3, C3]

    print()
    for row, col in zip(LOGO, grad):
        print(f"{pad}{col}{B}{row}{R}")
    print()

    tag = "A I   A S S I S T A N T"
    print(center_visual(f"{DG}{tag}{R}", w))
    print()

    m = model.split("/")[-1]
    if provider == "council":
        pcol = PU
        pname = "Council"
        from src.agents.council import _get_available_agents as _gav
        m = f"{len(_gav())} agents"
    else:
        pcol = provider_color(provider)
        pname = provider.capitalize() if provider else "—"

    left = f"  {pcol}◆ {pname}{R}  {DG}│{R}  {WH}{m}{R}"
    right = f"{DG}{turns} turns  {R}" if turns else ""
    gap = max(w - visual_length(left) - visual_length(right) - 2, 1)
    print(f"{left}{' ' * gap}{right}")
    print(f"\n  {DG}{'▁' * (w - 4)}{R}\n")


# Message display
def print_you(text: str) -> None:
    time_str = current_time()
    wrap_w = max(terminal_width() - 16, 20)
    wrapped = textwrap.wrap(text, width=wrap_w) or [text]
    print()
    first = wrapped[0]
    gap = max(terminal_width() - 7 - len(first) - len(time_str) - 2, 1)
    print(f"  {DG}you{R}  {WH}{first}{R}{' ' * gap}{DG}{time_str}{R}")
    for line in wrapped[1:]:
        print(f"       {WH}{line}{R}")


def print_lumi_label(name: str = "Lumi") -> None:
    time_str = current_time()
    gap = max(terminal_width() - len(name) - len(time_str) - 7, 1)
    print(f"\n  {PU}{B}✦{R}  {C1}{B}{name}{R}{' ' * gap}{DG}{time_str}{R}\n")


def print_welcome(name: str) -> None:
    print(f"\n  {PU}✦  {WH}{B}{name}{R}  {DG}is online  —  {R}{DG}/help{R}{DG} for commands{R}\n")


# Spinner class
import itertools
import threading
import time


class Spinner:
    FRAMES = ["⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈"]

    def __init__(self, label: str = "thinking") -> None:
        self._label = label
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        for f in itertools.cycle(self.FRAMES):
            if not self._running:
                break
            sys.stdout.write(f"\r  {PU}{f}{R}  {DG}{self._label}{R}  ")
            sys.stdout.flush()
            time.sleep(0.09)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join()
        sys.stdout.write(f"\r{' ' * terminal_width()}\r")
        sys.stdout.flush()