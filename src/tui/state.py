"""Lightweight shared state objects for the TUI."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


def current_hm() -> str:
    return datetime.now().strftime("%H:%M")


@dataclass(slots=True)
class Msg:
    role: str
    text: str
    label: str = ""
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = current_hm()


@dataclass(slots=True)
class PaneState:
    active: bool = False
    title: str = ""
    subtitle: str = ""
    lines: list[str] | None = None
    footer: str = ""
    close_on_escape: bool = False

    def content(self) -> list[str]:
        return list(self.lines or [])


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: list[Msg] = []

    def add(self, msg: Msg) -> int:
        with self._lock:
            self._data.append(msg)
            return len(self._data) - 1

    def append(self, index: int, chunk: str) -> None:
        with self._lock:
            self._data[index].text += chunk

    def set_text(self, index: int, text: str) -> None:
        with self._lock:
            self._data[index].text = text

    def finalize(self, index: int) -> None:
        with self._lock:
            if self._data[index].role == "streaming":
                self._data[index].role = "assistant"

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def snapshot(self) -> list[Msg]:
        with self._lock:
            return list(self._data)


@dataclass
class AgentState:
    aid: str
    name: str
    lead: bool = False
    st: str = "spin"
    conf: str = ""
    t: str = ""
    frame: int = 0

    def done(self, ok: bool, conf: str, timing: str) -> None:
        self.st = "ok" if ok else "fail"
        self.conf = conf
        self.t = timing
