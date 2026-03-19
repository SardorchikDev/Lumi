"""Composable view helpers for the Lumi TUI."""

from __future__ import annotations

import re
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ViewStyle:
    fg_fn: Callable[[str], str]
    bg_fn: Callable[[str], str]
    bold: Callable[[], str]
    italic: Callable[[], str]
    reset: str
    bg_value: str
    bg_pop_value: str
    bg_hl_value: str
    border: str
    muted: str
    comment: str
    fg_dim: str
    fg: str
    fg_hi: str
    cyan: str
    red: str
    teal: str


@dataclass(frozen=True)
class PromptRender:
    line: str
    prefix: int


@dataclass(frozen=True)
class IntroRender:
    header_lines: list[str]
    prompt: PromptRender
    trailing_lines: list[str]


class StarterView:
    def __init__(
        self,
        tui: Any,
        style: ViewStyle,
        provider_resolver: Callable[[], str],
        provider_label: Callable[[str], str],
        spinner_frames: list[str],
    ) -> None:
        self.tui = tui
        self.style = style
        self.provider_resolver = provider_resolver
        self.provider_label = provider_label
        self.spinner_frames = spinner_frames

    def _build_prompt(self, width: int, prefix: str, placeholder: str) -> PromptRender:
        txt = self.tui.buf
        disp_w = max(10, width - len(prefix) - 4)
        scroll = max(0, self.tui.cur_pos - disp_w + 1)
        shown = txt[scroll : scroll + disp_w]
        pending_label, pending_hint = self.tui.filesystem_prompt_hint()
        if self.tui.busy:
            frame = int(time.time() * 10) % len(self.spinner_frames)
            sym = self.style.fg_fn(self.style.cyan) + self.spinner_frames[frame] + " " + self.style.reset
            tail = self.style.fg_fn(self.style.muted) + self.style.italic() + "thinking softly" + self.style.reset if not shown else ""
        elif pending_label:
            sym = self.style.fg_fn(self.style.cyan) + self.style.bold() + "? " + self.style.reset
            prompt_text = pending_label + (f" · {pending_hint}" if pending_hint else "")
            tail = self.style.fg_fn(self.style.muted) + prompt_text + self.style.reset if not shown else ""
        else:
            sym = self.style.fg_fn(self.style.fg_hi) + self.style.bold() + "> " + self.style.reset
            tail = self.style.fg_fn(self.style.muted) + placeholder + self.style.reset if not shown else ""
        line = prefix + sym + self.style.fg_fn(self.style.fg_hi) + shown + tail + self.style.reset
        return PromptRender(line=line, prefix=len(prefix) + 3)

    def build(self, width: int) -> IntroRender:
        if not getattr(self.tui, "show_starter_panel", True):
            return IntroRender(
                header_lines=["", ""],
                prompt=self._build_prompt(width, " " * 4, "say something nice"),
                trailing_lines=[""],
            )

        provider_key = self.provider_resolver()
        provider = self.provider_label(provider_key)
        model = self.tui.current_model.split("/")[-1][:24]
        cwd = Path.cwd().resolve()
        cwd_text = str(cwd)
        cwd_short = cwd_text if len(cwd_text) <= 28 else "..." + cwd_text[-25:]
        panel_w = min(max(74, width - 10), 108)
        panel_pad = " " * max(2, (width - panel_w - 2) // 2)
        left_w = max(28, panel_w // 2)
        right_w = panel_w - left_w - 1
        border = self.style.fg_fn(self.style.border)

        def pad(text: str, width_: int) -> str:
            return text[:width_].ljust(width_)

        def center(text: str, width_: int) -> str:
            return text[:width_].center(width_)

        def row(left: str = "", right: str = "", left_tone: str | None = None, right_tone: str | None = None) -> str:
            left_tone = left_tone or self.style.fg_hi
            right_tone = right_tone or self.style.fg_hi
            return (
                panel_pad
                + border + "│" + self.style.reset
                + " " + self.style.fg_fn(left_tone) + pad(left, left_w - 2) + self.style.reset + " "
                + border + "│" + self.style.reset
                + " " + self.style.fg_fn(right_tone) + pad(right, right_w - 2) + self.style.reset + " "
                + border + "│" + self.style.reset
            )

        notes_store = getattr(self.tui, "little_notes", None)
        note_lines = notes_store.display_lines(limit=3) if notes_store else [
            cmd for cmd in getattr(self.tui, "recent_commands", []) if cmd
        ][:3]
        action_lines = notes_store.display_action_lines(limit=2) if notes_store else getattr(self.tui, "recent_actions", [])[:2]
        while len(note_lines) < 3:
            note_lines.append("")

        logo = "[˶ᵔ ᵕ ᵔ˶]"
        trailing_lines = [""]
        if action_lines:
            trailing_lines.append("  " + self.style.fg_fn(self.style.muted) + "recent action  " + action_lines[0][: min(width - 20, 72)] + self.style.reset)
        lines = [
            panel_pad + border + "╭" + "─" * panel_w + "╮" + self.style.reset,
            row(center("welcome to lumi", left_w - 2), center("little notes", right_w - 2)),
            row("", note_lines[0], self.style.fg_dim, self.style.fg_dim),
            row(center(logo, left_w - 2), note_lines[1], self.style.fg_hi, self.style.fg_dim),
            row("", note_lines[2], self.style.fg_dim, self.style.fg_dim),
            row("", "", self.style.fg_dim, self.style.fg_dim),
            row(center(f"{provider}  ·  {model}", left_w - 2), "", self.style.muted, self.style.fg_dim),
            row(center(cwd_short, left_w - 2), "", self.style.muted, self.style.fg_dim),
            row("", "", self.style.fg_dim, self.style.fg_dim),
            row("", "", self.style.fg_dim, self.style.fg_dim),
            panel_pad + border + "╰" + "─" * panel_w + "╯" + self.style.reset,
            "",
            "",
        ]
        return IntroRender(
            header_lines=lines,
            prompt=self._build_prompt(width, panel_pad + "  ", "say something nice"),
            trailing_lines=trailing_lines,
        )


class TranscriptView:
    def __init__(
        self,
        tui: Any,
        style: ViewStyle,
        inline_renderer: Callable[[str], str],
        syntax_highlighter: Callable[[str], str],
        strip_ansi: Callable[[str], str],
        visible_len: Callable[[str], int],
    ) -> None:
        self.tui = tui
        self.style = style
        self.inline_renderer = inline_renderer
        self.syntax_highlighter = syntax_highlighter
        self.strip_ansi = strip_ansi
        self.visible_len = visible_len

    def build(self, width: int) -> list[str]:
        msgs = self.tui.store.snapshot()
        lines: list[str] = []
        inner = max(30, width - 8)
        if not msgs:
            return lines

        if getattr(self.tui, "agent_active_objective", None) and getattr(self.tui, "agent_tasks", None):
            lines.append("")
            lines.append("  " + self.style.fg_fn(self.style.muted) + "objective" + self.style.reset + "  " + self.style.fg_fn(self.style.fg_hi) + self.tui.agent_active_objective + self.style.reset)
            for task in self.tui.agent_tasks:
                bullet = "·"
                label = task.get("text", "")
                for ln in textwrap.wrap(label, inner - 6) or [label]:
                    lines.append("    " + self.style.fg_fn(self.style.muted) + bullet + " " + self.style.fg_fn(self.style.fg_dim) + ln + self.style.reset)
                    bullet = " "
            lines.append("")

        for msg in msgs:
            if msg.role == "user":
                rail = self.style.fg_fn(self.style.border) + "|" + self.style.reset
                lines.append("  " + rail + " " + self.style.fg_fn(self.style.muted) + "you" + self.style.reset)
                for ln in textwrap.wrap(msg.text, inner) or [msg.text]:
                    lines.append("  " + rail + " " + self.style.fg_fn(self.style.fg_hi) + ln + self.style.reset)
                lines.append("")
                continue

            if msg.role in ("assistant", "streaming"):
                label = msg.label or "lumi"
                is_stream = msg.role == "streaming"
                if is_stream:
                    blink_on = int(time.time() * 4) % 2 == 0
                    cursor = " " + self.style.fg_fn(self.style.cyan) + ("▋" if blink_on else " ") + self.style.reset
                else:
                    cursor = ""

                if self.tui.vessel_mode and self.tui.active_vessel:
                    hdr = self.style.fg_fn(self.style.red) + self.style.bold()
                    if "vessel" not in label:
                        label = f"vessel [{self.tui.active_vessel}]"
                else:
                    hdr = self.style.fg_fn(self.style.fg_hi) + self.style.bold()

                rail = self.style.fg_fn(self.style.border) + "|" + self.style.reset
                prefix = "  " + rail + " "
                lines.append("  " + rail + " " + hdr + label + self.style.reset)
                raw_lines = msg.text.split("\n") if msg.text else [""]
                in_code = False
                code_w = min(inner - 2, 88)
                code_lineno = 0

                for ln in raw_lines:
                    if ln.startswith("```"):
                        if not in_code:
                            in_code = True
                            code_lang = ln[3:].strip() or "code"
                            bar_fill = "─" * max(0, code_w - len(code_lang) - 3)
                            lines.append(
                                prefix
                                + self.style.fg_fn(self.style.border) + "  " + self.style.reset
                                + self.style.fg_fn(self.style.muted) + code_lang + self.style.reset
                                + self.style.fg_fn(self.style.border) + " " + bar_fill + self.style.reset
                            )
                            code_lineno = 0
                        else:
                            in_code = False
                            lines.append(prefix)
                        continue

                    if in_code:
                        code_lineno += 1
                        lineno = self.style.fg_fn(self.style.border) + f"{code_lineno:>3} " + self.style.reset
                        max_code = code_w - 6
                        segments = textwrap.wrap(ln, max_code) if len(ln) > max_code else [ln]
                        for segment in segments or [""]:
                            hi = self.syntax_highlighter(segment)
                            pad = max(0, max_code - self.visible_len(segment))
                            lines.append(prefix + self.style.bg_fn(self.style.bg_pop_value) + lineno + hi + self.style.bg_fn(self.style.bg_pop_value) + " " * pad + self.style.reset)
                            lineno = self.style.fg_fn(self.style.border) + "    " + self.style.reset
                        continue

                    if re.match(r"^#{1,6} ", ln):
                        lines.append(prefix + self.style.fg_fn(self.style.fg_hi) + self.style.bold() + ln.lstrip("# ").strip() + self.style.reset)
                    elif ln.startswith("> "):
                        body = ln[2:]
                        lines.append(prefix + self.style.fg_fn(self.style.teal) + "│ " + self.style.italic() + self.style.fg_fn(self.style.fg_dim) + body + self.style.reset)
                    elif re.match(r"^[-*•] ", ln):
                        body = ln[2:]
                        lines.append(prefix + self.style.fg_fn(self.style.muted) + "• " + self.style.fg_fn(self.style.fg) + body + self.style.reset)
                    elif re.match(r"^\d+\. ", ln):
                        match = re.match(r"^(\d+)\. (.*)", ln)
                        if match:
                            num, body = match.group(1), match.group(2)
                            lines.append(prefix + self.style.fg_fn(self.style.cyan) + self.style.bold() + f"{num}." + self.style.reset + " " + self.style.fg_fn(self.style.fg) + body + self.style.reset)
                        else:
                            lines.append(prefix + self.style.fg_fn(self.style.fg) + ln + self.style.reset)
                    elif not ln.strip():
                        if not lines or lines[-1] != prefix:
                            lines.append(prefix)
                    else:
                        rendered = self.inline_renderer(ln)
                        if len(self.strip_ansi(ln)) <= inner:
                            lines.append(prefix + rendered + self.style.reset)
                        else:
                            for wrapped in textwrap.wrap(self.strip_ansi(ln), inner) or [ln]:
                                lines.append(prefix + self.style.fg_fn(self.style.fg) + wrapped + self.style.reset)

                if in_code:
                    lines.append(prefix + self.style.bg_fn(self.style.bg_pop_value) + self.style.fg_fn(self.style.red) + "[stream paused]" + " " * (code_w - 15) + self.style.reset)
                if cursor and lines:
                    lines[-1] += cursor
                lines.append("")
                continue

            if msg.role == "system":
                rail = self.style.fg_fn(self.style.border) + "|" + self.style.reset
                for chunk in msg.text.split("\n"):
                    for wrapped in (textwrap.wrap(chunk, inner) if chunk.strip() else [""]):
                        lines.append("  " + rail + " " + self.style.fg_fn(self.style.fg_dim) + wrapped + self.style.reset)
                lines.append("")
                continue

            if msg.role == "error":
                rail = self.style.fg_fn(self.style.red) + "|" + self.style.reset
                lines.append("  " + rail + " " + self.style.fg_fn(self.style.red) + "warning" + self.style.reset + "  " + self.style.fg_fn(self.style.fg_hi) + msg.text + self.style.reset)
                lines.append("")

        return lines


class OverlayView:
    def __init__(
        self,
        tui: Any,
        style: ViewStyle,
        popup_frame: Callable[[int, int, int, str], str],
        popup_line: Callable[[int, int, int, str, str, bool], str],
        move: Callable[[int, int], str],
        strip_ansi: Callable[[str], str],
    ) -> None:
        self.tui = tui
        self.style = style
        self.popup_frame = popup_frame
        self.popup_line = popup_line
        self.move = move
        self.strip_ansi = strip_ansi

    def browser_popup(self, rows: int, cols: int) -> str:
        items = self.tui.browser_items
        sel = self.tui.browser_sel
        pop_w = min(60, cols - 6)
        pop_h = min(20, rows - 6)
        left = max(2, (cols - pop_w) // 2)
        top = max(2, (rows - pop_h) // 2)

        if items:
            total = len(items)
            start = max(0, min(sel - pop_h // 2, total - pop_h + 2))
            disp_items = items[start : start + pop_h - 2]
            local_sel = sel - start
        else:
            disp_items = []
            local_sel = -1

        out = [self.popup_frame(top, left, pop_w, "browser")]
        cwd = self.tui.browser_cwd
        if len(cwd) > pop_w - 6:
            cwd = "..." + cwd[-(pop_w - 9) :]
        out.append(self.popup_line(top + 1, left, pop_w, cwd, self.style.fg_hi, False))
        out.append(self.move(top + 2, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)

        row = top + 3
        for idx, item in enumerate(disp_items):
            itype, iname, _ = item
            is_sel = idx == local_sel
            icon = "󰜄" if iname == ".." else ("󰉋" if itype == "dir" else "󰈔")
            pointer = "› " if is_sel else "  "
            content = f"{icon} {pointer}{iname[: pop_w - 10]}"
            out.append(self.popup_line(row, left, pop_w, self.strip_ansi(content), self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1

        while row < top + pop_h - 1:
            out.append(self.popup_line(row, left, pop_w, "", self.style.fg_dim, False))
            row += 1

        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row += 1
        out.append(self.popup_line(row, left, pop_w, "Esc Close  ·  ↑↓ Move  ·  Enter/→ Open  ·  ← Back", self.style.muted, False))
        row += 1
        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        return "".join(out)

    def slash_popup(self, rows: int, cols: int) -> str:
        hits = self.tui.slash_hits
        sel = self.tui.slash_sel
        pop_w = min(58, cols - 4)
        n = min(len(hits), 10)
        top = rows - 2 - n - 2
        left = max(2, (cols - pop_w) // 2)
        out = [self.popup_frame(top, left, pop_w, "commands")]
        for idx, (cmd, desc) in enumerate(hits[:10]):
            is_sel = idx == sel
            content = f"{'› ' if is_sel else '  '}{cmd[:15]:<16} {desc[:max(0, pop_w - 26)]}"
            out.append(self.popup_line(top + 1 + idx, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
        out.append(self.move(top + 1 + n, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        return "".join(out)

    def picker_popup(self, rows: int, cols: int) -> str:
        items = self.tui.picker_items
        sel = self.tui.picker_sel
        pop_w = min(64, cols - 4)
        left = max(2, (cols - pop_w) // 2)
        top = max(2, (rows - len(items) - 5) // 2)
        out = [self.popup_frame(top, left, pop_w, "picker")]
        out.append(self.popup_line(top + 1, left, pop_w, "model · provider", self.style.muted, False))
        out.append(self.move(top + 2, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row = top + 3
        for idx, (kind, _, label) in enumerate(items):
            if kind == "header":
                out.append(self.popup_line(row, left, pop_w, label[: pop_w - 6], self.style.muted, False))
            else:
                is_sel = idx == sel
                content = f"{'› ' if is_sel else '  '}{'●' if is_sel else '○'} {label[: pop_w - 12]}"
                out.append(self.popup_line(row, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1
        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row += 1
        out.append(self.popup_line(row, left, pop_w, "Esc Close  ·  ↑↓ Navigate  ·  Enter Mount", self.style.muted, False))
        row += 1
        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        return "".join(out)

    def path_popup(self, rows: int, cols: int) -> str:
        hits = self.tui.path_hits
        sel = self.tui.path_sel
        pop_w = min(64, cols - 4)
        n = min(len(hits), 8)
        top = rows - 2 - n - 2
        left = max(2, (cols - pop_w) // 2)
        out = [self.popup_frame(top, left, pop_w, "paths")]
        for idx, path in enumerate(hits[:8]):
            is_sel = idx == sel
            content = f"{'› ' if is_sel else '  '}{path[: pop_w - 8]}"
            out.append(self.popup_line(top + 1 + idx, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
        out.append(self.move(top + 1 + n, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        return "".join(out)

    def notification_bar(self, rows: int, cols: int) -> str:
        msg = self.tui.notification[: max(0, cols - 18)]
        left = max(2, cols - len(msg) - 10)
        return self.move(rows - 3, left) + self.style.fg_fn(self.style.muted) + msg + self.style.reset
