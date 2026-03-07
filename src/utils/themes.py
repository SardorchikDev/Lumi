"""Terminal color themes for Lumi."""

import json
import pathlib

THEME_FILE = pathlib.Path("data/memory/theme.json")


def fg(n): return f"\033[38;5;{n}m"


THEMES = {
    "tokyo": {
        "name": "Tokyo Night Storm",
        "C1": fg(117), "C2": fg(111), "C3": fg(105),
        "PU": fg(141), "BL": fg(75),  "CY": fg(117),
        "GR": fg(245), "DG": fg(238), "MU": fg(60),
        "GN": fg(114), "RE": fg(203), "YE": fg(179), "WH": fg(255),
    },
    "dracula": {
        "name": "Dracula",
        "C1": fg(141), "C2": fg(135), "C3": fg(98),
        "PU": fg(141), "BL": fg(117), "CY": fg(117),
        "GR": fg(250), "DG": fg(240), "MU": fg(60),
        "GN": fg(84),  "RE": fg(203), "YE": fg(228), "WH": fg(255),
    },
    "nord": {
        "name": "Nord",
        "C1": fg(153), "C2": fg(110), "C3": fg(67),
        "PU": fg(110), "BL": fg(153), "CY": fg(159),
        "GR": fg(247), "DG": fg(240), "MU": fg(59),
        "GN": fg(108), "RE": fg(167), "YE": fg(222), "WH": fg(255),
    },
    "gruvbox": {
        "name": "Gruvbox",
        "C1": fg(214), "C2": fg(208), "C3": fg(172),
        "PU": fg(175), "BL": fg(109), "CY": fg(108),
        "GR": fg(246), "DG": fg(239), "MU": fg(59),
        "GN": fg(142), "RE": fg(167), "YE": fg(214), "WH": fg(229),
    },
    "catppuccin": {
        "name": "Catppuccin Mocha",
        "C1": fg(189), "C2": fg(183), "C3": fg(147),
        "PU": fg(183), "BL": fg(111), "CY": fg(152),
        "GR": fg(251), "DG": fg(240), "MU": fg(60),
        "GN": fg(149), "RE": fg(210), "YE": fg(223), "WH": fg(255),
    },
}

DEFAULT = "tokyo"


def load_theme_name() -> str:
    try:
        if THEME_FILE.exists():
            return json.loads(THEME_FILE.read_text()).get("theme", DEFAULT)
    except Exception:
        pass
    return DEFAULT


def save_theme_name(name: str):
    THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
    THEME_FILE.write_text(json.dumps({"theme": name}))


def get_theme(name: str = None) -> dict:
    return THEMES.get(name or load_theme_name(), THEMES[DEFAULT])


def list_themes() -> list:
    return list(THEMES.keys())
