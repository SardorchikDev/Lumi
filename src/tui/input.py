"""TUI input parsing and prompt history helpers."""

from __future__ import annotations

import os
import select
from pathlib import Path

_PENDING_BYTES = bytearray()
_BRACKETED_PASTE_START = b"\x1b[200~"
_BRACKETED_PASTE_END = b"\x1b[201~"


def _push_pending(data: bytes) -> None:
    if not data:
        return
    _PENDING_BYTES[:0] = data


def _read_chunk(fd: int, size: int) -> bytes:
    if size <= 0:
        return b""
    if _PENDING_BYTES:
        take = min(size, len(_PENDING_BYTES))
        chunk = bytes(_PENDING_BYTES[:take])
        del _PENDING_BYTES[:take]
        if take == size:
            return chunk
        return chunk + os.read(fd, size - take)
    return os.read(fd, size)


def _decode_paste(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_bracketed_paste(fd: int, initial: bytes) -> tuple[str, str] | None:
    if not initial.startswith(_BRACKETED_PASTE_START):
        return None
    payload = initial[len(_BRACKETED_PASTE_START) :]
    while True:
        marker = payload.find(_BRACKETED_PASTE_END)
        if marker != -1:
            remainder = payload[marker + len(_BRACKETED_PASTE_END) :]
            _push_pending(remainder)
            return ("PASTE", _decode_paste(payload[:marker]))
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            return ("PASTE", _decode_paste(payload))
        payload += _read_chunk(fd, 4096)


def _parse_sgr_mouse(full: bytes) -> str:
    """Parse SGR mouse sequences and normalize wheel events."""
    if not (full.startswith(b"\x1b[<") and full[-1:] in {b"M", b"m"}):
        return ""
    try:
        encoded = full[3:-1].decode("ascii")
        button_str, _x, _y = encoded.split(";")
        button = int(button_str)
    except (UnicodeDecodeError, ValueError):
        return ""
    if button & 64:
        wheel = button & 0b11
        if wheel == 0:
            return "WHEEL_UP"
        if wheel == 1:
            return "WHEEL_DOWN"
    return ""


def parse_escape_sequence(full: bytes) -> str:
    """Normalize common terminal escape sequences into logical key names."""
    if not full:
        return ""
    mouse_key = _parse_sgr_mouse(full)
    if mouse_key:
        return mouse_key
    if full.startswith(b"\x1b["):
        if full.endswith(b"A"):
            if b";2" in full or b"[a" in full:
                return "SHIFT_UP"
            if b";5" in full:
                return "CTRL_UP"
            return "UP"
        if full.endswith(b"B"):
            if b";2" in full or b"[b" in full:
                return "SHIFT_DOWN"
            if b";5" in full:
                return "CTRL_DOWN"
            return "DOWN"
        if full.endswith(b"C"):
            if b";5" in full:
                return "CTRL_RIGHT"
            return "RIGHT"
        if full.endswith(b"D"):
            if b";5" in full:
                return "CTRL_LEFT"
            return "LEFT"
        if full.endswith(b"H"):
            return "HOME"
        if full.endswith(b"F"):
            return "END"
        if full.endswith(b"~"):
            if b"[3~" in full:
                return "DELETE"
            if b"[5~" in full:
                return "PGUP"
            if b"[6~" in full:
                return "PGDN"

    fallback = {
        b"\x1b[A": "UP",
        b"\x1b[B": "DOWN",
        b"\x1b[C": "RIGHT",
        b"\x1b[D": "LEFT",
        b"\x1b[1;2A": "SHIFT_UP",
        b"\x1b[1;2B": "SHIFT_DOWN",
        b"\x1b[1;5A": "CTRL_UP",
        b"\x1b[1;5B": "CTRL_DOWN",
        b"\x1b[H": "HOME",
        b"\x1b[F": "END",
        b"\x1b[3~": "DELETE",
        b"\x1b[5~": "PGUP",
        b"\x1b[6~": "PGDN",
        b"\x1b[1;5C": "CTRL_RIGHT",
        b"\x1b[1;5D": "CTRL_LEFT",
    }
    return fallback.get(full, "")


def read_key(fd: int) -> str | tuple[str, str]:
    """Read a key press from a raw terminal file descriptor."""
    while True:
        try:
            ch = _read_chunk(fd, 1)
            if not ch:
                return ""
            if ch == b"\x1b":
                ready, _, _ = select.select([fd], [], [], 0.05)
                if ready:
                    seq = _read_chunk(fd, 32)
                    full = ch + seq
                    paste = _read_bracketed_paste(fd, full)
                    if paste is not None:
                        return paste
                    return parse_escape_sequence(full)
                return "ESC"

            if ch in (b"\r", b"\n"):
                return "ENTER"
            if ch in (b"\x7f", b"\x08"):
                return "BACKSPACE"
            if ch == b"\x09":
                return "TAB"
            if ch == b"\x0c":
                return "CTRL_L"
            if ch == b"\x11":
                return "CTRL_Q"
            if ch == b"\x07":
                return "CTRL_G"
            if ch == b"\x06":
                return "CTRL_F"
            if ch == b"\x03":
                return "CTRL_C"
            if ch == b"\x0e":
                return "CTRL_N"
            if ch == b"\x17":
                return "CTRL_W"
            if ch == b"\x01":
                return "HOME"
            if ch == b"\x05":
                return "END"
            if ch == b"\x15":
                return "CTRL_U"
            if ch == b"\x12":
                return "CTRL_R"
            if ch == b"\x04":
                return "CTRL_D"

            buf = ch
            while True:
                try:
                    return buf.decode("utf-8")
                except UnicodeDecodeError:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if ready:
                        buf += _read_chunk(fd, 1)
                    else:
                        return ""
        except InterruptedError:
            continue


class InputHistory:
    """Prompt history with draft restoration when navigating back to the present."""

    def __init__(self, path: Path, limit: int = 500) -> None:
        self.path = path
        self.limit = limit
        self.entries = self._load()
        self.index = -1
        self.draft = ""

    def _load(self) -> list[str]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.strip()][-self.limit :]

    def append(self, text: str) -> None:
        normalized = text.replace("\n", " ").strip()
        if not normalized:
            return
        if self.entries[-1:] == [normalized]:
            return
        self.entries.append(normalized)
        self.entries = self.entries[-self.limit :]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(normalized + "\n")

    def reset_navigation(self) -> None:
        self.index = -1
        self.draft = ""

    def navigate(self, current_text: str, direction: int) -> str | None:
        if not self.entries:
            return None
        if self.index == -1:
            self.draft = current_text
        if direction < 0:
            new_index = 0 if self.index == -1 else self.index + 1
        else:
            new_index = self.index - 1
        if new_index < -1 or new_index >= len(self.entries):
            return None
        self.index = new_index
        if new_index == -1:
            return self.draft
        return self.entries[-(new_index + 1)]
