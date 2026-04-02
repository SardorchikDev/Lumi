"""Single fixed ANSI palette for Lumi."""

from __future__ import annotations

import json

from src.config import MEMORY_DIR

THEME_FILE = MEMORY_DIR / "theme.json"


def fg(n: int) -> str:
    return f"\033[38;5;{n}m"


DEFAULT = "ansi"
THEMES = {
    DEFAULT: {
        "name": "Fixed ANSI",
        "C1": fg(255),
        "C2": fg(252),
        "C3": fg(249),
        "PU": fg(81),
        "BL": fg(117),
        "CY": fg(117),
        "GR": fg(250),
        "DG": fg(241),
        "MU": fg(244),
        "GN": fg(114),
        "RE": fg(203),
        "YE": fg(179),
        "WH": fg(255),
    },
}


def load_theme_name() -> str:
    try:
        if THEME_FILE.exists():
            json.loads(THEME_FILE.read_text())
    except Exception:
        pass
    return DEFAULT


def save_theme_name(name: str) -> None:
    THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
    THEME_FILE.write_text(json.dumps({"theme": DEFAULT}))


def get_theme(name: str | None = None) -> dict:
    return THEMES[DEFAULT]


def list_themes() -> list[str]:
    return [DEFAULT]
