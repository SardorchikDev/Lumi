"""
Centralized color definitions for Lumi TUI.
"""

ESC = "\033"
CSI = ESC + "["
R = f"{CSI}0m"

def _fg(h):
    if not h: return ""
    h = h.lstrip("#")
    return f"{CSI}38;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"

def _bg(h):
    if h == "transparent" or not h: return f"{CSI}49m"
    h = h.lstrip("#")
    return f"{CSI}48;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"

def _bold(): return f"{CSI}1m"
def _italic(): return f"{CSI}3m"
def _reset(): return f"{CSI}0m"

# Palette
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
