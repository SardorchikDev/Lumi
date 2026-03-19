"""Input history — up/down arrow key cycling via readline."""


from src.config import MEMORY_DIR

HIST_FILE = MEMORY_DIR / ".input_history"


def setup():
    """Enable readline with persistent history."""
    try:
        import readline
        readline.set_history_length(500)
        HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        if HIST_FILE.exists():
            readline.read_history_file(str(HIST_FILE))
    except Exception:
        pass


def save():
    """Write readline history to disk."""
    try:
        import readline
        HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(str(HIST_FILE))
    except Exception:
        pass
