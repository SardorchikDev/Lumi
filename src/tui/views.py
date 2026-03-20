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
    lines: list[str]
    cursor_row: int
    cursor_col: int


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

    @staticmethod
    def _chunk_plain(text: str, width: int) -> list[str]:
        width = max(1, width)
        logical_lines = text.split("\n") or [""]
        out: list[str] = []
        for logical in logical_lines:
            if logical == "":
                out.append("")
                continue
            start = 0
            while start < len(logical):
                out.append(logical[start : start + width])
                start += width
        return out or [""]

    def _build_prompt(self, width: int, prefix: str, placeholder: str) -> PromptRender:
        txt = self.tui.buf
        prompt_prefix = prefix + "  "
        badge_prefix = prefix + "  "
        plain_prefix = len(prompt_prefix) + 2
        plain_cont_prefix = len(prompt_prefix) + 2
        disp_w = max(10, width - plain_prefix - 3)
        pending_label, pending_hint = self.tui.filesystem_prompt_hint()
        badges = ["compose"]
        if self.tui.multiline:
            badges.append("multiline")
        if pending_label:
            badges.append("approval")
        if self.tui.response_mode:
            badges.append(self.tui.response_mode)
        if getattr(self.tui.history, "index", -1) != -1:
            badges.append("history")
        if getattr(self.tui, "agent_active_objective", None):
            badges.append("agent")
        meta = (
            badge_prefix
            + self.style.fg_fn(self.style.muted)
            + " · ".join(badges)
            + self.style.reset
        )

        if self.tui.busy:
            frame = int(time.time() * 10) % len(self.spinner_frames)
            sym = self.style.fg_fn(self.style.cyan) + self.spinner_frames[frame] + " " + self.style.reset
            tail_text = "thinking softly"
        elif pending_label:
            sym = self.style.fg_fn(self.style.cyan) + self.style.bold() + "? " + self.style.reset
            tail_text = pending_label + (f" · {pending_hint}" if pending_hint else "")
        else:
            sym = self.style.fg_fn(self.style.fg_hi) + self.style.bold() + "> " + self.style.reset
            tail_text = placeholder

        if not txt:
            line = prompt_prefix + sym + self.style.fg_fn(self.style.muted) + tail_text + self.style.reset
            cursor_col = plain_prefix + 1
            return PromptRender(lines=[meta, line], cursor_row=1, cursor_col=cursor_col)

        cursor_before = txt[: self.tui.cur_pos]
        all_lines = self._chunk_plain(txt, disp_w)
        cursor_lines = self._chunk_plain(cursor_before, disp_w)
        cursor_row = max(0, len(cursor_lines) - 1)
        cursor_line_col = len(cursor_lines[-1]) if cursor_lines else 0
        visible_limit = 3 if (self.tui.multiline or "\n" in txt or len(txt) > disp_w) else 1
        start = max(0, cursor_row - visible_limit + 1)
        visible = all_lines[start : start + visible_limit] or [""]
        cursor_row_rel = cursor_row - start

        lines = [meta]
        for index, segment in enumerate(visible):
            prefix_text = prompt_prefix
            tone = self.style.fg_hi
            if index > 0:
                prefix_text = prompt_prefix
                sym = self.style.fg_fn(self.style.border) + "· " + self.style.reset
                tone = self.style.fg
            lines.append(prefix_text + sym + self.style.fg_fn(tone) + segment + self.style.reset)

        cursor_prefix = plain_prefix if cursor_row_rel == 0 else plain_cont_prefix
        return PromptRender(
            lines=lines,
            cursor_row=1 + cursor_row_rel,
            cursor_col=cursor_prefix + cursor_line_col + 1,
        )

    def _build_review_lines(self, width: int) -> list[str]:
        pending = getattr(self.tui, "_pending_file_plan", None)
        if not pending:
            return []
        inspection = pending.get("inspection") if isinstance(pending, dict) else None
        plan = pending.get("plan", {}) if isinstance(pending, dict) else pending[0]
        operation = plan.get("operation", "create")
        title = {
            "delete": "review removal",
            "move": "review move",
            "copy": "review copy",
            "rename": "review rename",
        }.get(operation, "review filesystem plan")
        panel_w = min(max(44, width - 16), 84)
        left = " " * max(2, (width - panel_w) // 2)
        summary = list((inspection or {}).get("summary_lines", []))[:5]
        preview = list((inspection or {}).get("preview_lines", []))[:4]

        def row(text: str = "", tone: str | None = None, *, center: bool = False) -> str:
            tone = tone or self.style.fg_dim
            rendered = text[:panel_w].center(panel_w) if center else text[:panel_w].ljust(panel_w)
            return (
                left
                + self.style.fg_fn(tone)
                + rendered
                + self.style.reset
            )

        lines = [
            "",
            row(title, self.style.muted, center=True),
            left + self.style.fg_fn(self.style.border) + "─" * panel_w + self.style.reset,
        ]
        for line in summary or ["plan ready for review"]:
            lines.append(row(line, self.style.fg_hi))
        if preview:
            lines.append("")
            lines.append(row("preview", self.style.muted))
            for line in preview:
                lines.append(row(line, self.style.fg_dim))
        lines.extend(
            [
                "",
                row("y apply  ·  n cancel  ·  enter cancel", self.style.muted),
                "",
            ]
        )
        return lines

    def _render_box(self, width: int, lines: list[str], *, tone: str | None = None) -> list[str]:
        tone = tone or self.style.fg_hi
        box_w = min(max(44, width - 8), 78)
        left = " " * 2
        border = self.style.fg_fn(self.style.border)
        rendered = [left + border + "╭" + "─" * box_w + "╮" + self.style.reset]
        for line in lines:
            rendered.append(
                left
                + border
                + "│"
                + self.style.reset
                + " "
                + self.style.fg_fn(tone)
                + line[: box_w - 2].ljust(box_w - 2)
                + self.style.reset
                + " "
                + border
                + "│"
                + self.style.reset
            )
        rendered.append(left + border + "╰" + "─" * box_w + "╯" + self.style.reset)
        return rendered

    def _compact_build(self, width: int, provider: str, model: str, cwd_short: str) -> IntroRender:
        lines = [
            "",
        ]
        lines.extend(
            self._render_box(
                width,
                [f"Lumi TUI  ({provider})", f"model: {model}"],
                tone=self.style.fg_hi,
            )
        )
        lines.append("")
        approval = "confirm" if getattr(self.tui, "_pending_file_plan", None) else "suggest"
        lines.extend(
            self._render_box(
                width,
                [
                    "local session",
                    f"workdir: {cwd_short}",
                    f"model: {provider} · {model}",
                    f"approval: {approval}",
                ],
                tone=self.style.fg_dim,
            )
        )
        lines.append("")
        header_lines = lines + self._build_review_lines(width)
        return IntroRender(
            header_lines=header_lines,
            prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
            trailing_lines=[""],
        )

    def build(self, width: int) -> IntroRender:
        provider_key = self.provider_resolver()
        provider = self.provider_label(provider_key)
        model = self.tui.current_model.split("/")[-1][:24]
        cwd = Path.cwd().resolve()
        cwd_text = str(cwd)
        cwd_short = cwd_text if len(cwd_text) <= 52 else "..." + cwd_text[-49:]
        if width < 88 and getattr(self.tui, "show_starter_panel", True):
            return self._compact_build(width, provider, model, cwd_short)

        if not getattr(self.tui, "show_starter_panel", True):
            header_lines = self._build_review_lines(width)
            return IntroRender(
                header_lines=header_lines,
                prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
                trailing_lines=[""],
            )

        approval = "confirm" if getattr(self.tui, "_pending_file_plan", None) else "suggest"
        title_box = self._render_box(
            width,
            ["Lumi TUI  (research preview)", f"{provider} · {model}"],
            tone=self.style.fg_hi,
        )
        session_box = self._render_box(
            width,
            [
                "local session",
                f"workdir: {cwd_short}",
                f"model: {provider} · {model}",
                f"approval: {approval}",
            ],
            tone=self.style.fg_dim,
        )
        lines = [
            *title_box,
            "",
            *session_box,
            "",
        ]
        lines.extend(self._build_review_lines(width))
        return IntroRender(
            header_lines=lines,
            prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
            trailing_lines=[""],
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
                lines.append(
                    "  "
                    + self.style.fg_fn(self.style.muted)
                    + "you"
                    + (f"  {msg.ts}" if msg.ts else "")
                    + self.style.reset
                )
                for ln in textwrap.wrap(msg.text, inner) or [msg.text]:
                    lines.append("    " + self.style.fg_fn(self.style.fg_hi) + ln + self.style.reset)
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

                prefix = "    "
                label_text = label + (f"  {msg.ts}" if msg.ts else "")
                lines.append("  " + hdr + label_text + self.style.reset)
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
                                + self.style.fg_fn(self.style.muted) + code_lang + self.style.reset
                                + self.style.fg_fn(self.style.border) + " " + bar_fill + self.style.reset
                            )
                            code_lineno = 0
                        else:
                            in_code = False
                            lines.append("")
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
                    elif ln.startswith("@@"):
                        lines.append(prefix + self.style.fg_fn(self.style.cyan) + self.style.bold() + ln + self.style.reset)
                    elif ln.startswith("+") and not ln.startswith("+++"):
                        lines.append(prefix + self.style.fg_fn("#9ad27a") + ln + self.style.reset)
                    elif (ln.startswith("-") and not ln.startswith("---")) or re.match(r"^(FAILED|ERROR|E +|AssertionError|Traceback)", ln):
                        lines.append(prefix + self.style.fg_fn(self.style.red) + ln + self.style.reset)
                    elif re.match(r"^(PASSED|OK|SUCCESS|collected \d+ items)", ln):
                        lines.append(prefix + self.style.fg_fn("#9ad27a") + ln + self.style.reset)
                    elif not ln.strip():
                        if not lines or lines[-1] != "":
                            lines.append("")
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
                lines.append("  " + self.style.fg_fn(self.style.muted) + "note" + self.style.reset)
                for chunk in msg.text.split("\n"):
                    for wrapped in (textwrap.wrap(chunk, inner) if chunk.strip() else [""]):
                        lines.append("    " + self.style.fg_fn(self.style.fg_dim) + wrapped + self.style.reset)
                lines.append("")
                continue

            if msg.role == "error":
                lines.append("  " + self.style.fg_fn(self.style.red) + "warning" + self.style.reset)
                lines.append("    " + self.style.fg_fn(self.style.fg_hi) + msg.text + self.style.reset)
                lines.append("")

        return lines


class PaneView:
    def __init__(self, tui: Any, style: ViewStyle, strip_ansi: Callable[[str], str]) -> None:
        self.tui = tui
        self.style = style
        self.strip_ansi = strip_ansi

    def build(self, width: int, height: int) -> list[str]:
        pane = getattr(self.tui, "pane", None)
        active = getattr(self.tui, "pane_active", False) or bool(getattr(pane, "active", False))
        if not active or width < 16:
            return []

        title = getattr(pane, "title", "") or "side pane"
        subtitle = getattr(pane, "subtitle", "")
        footer = getattr(pane, "footer", "") or "/pane close"
        content = pane.content() if pane else list(getattr(self.tui, "pane_lines_output", []))
        inner_w = max(8, width - 1)
        lines: list[str] = []

        def wrap(text: str) -> list[str]:
            if not text:
                return [""]
            return textwrap.wrap(text, inner_w, break_long_words=True, break_on_hyphens=False) or [text]

        def row(text: str = "", tone: str | None = None) -> str:
            tone = tone or self.style.fg_dim
            plain = self.strip_ansi(text)[:inner_w]
            return self.style.fg_fn(tone) + plain.ljust(inner_w) + self.style.reset

        lines.append(row(title, self.style.muted))
        if subtitle:
            for piece in wrap(subtitle)[:2]:
                lines.append(row(piece, self.style.fg_hi))
        lines.append(self.style.fg_fn(self.style.border) + "─" * inner_w + self.style.reset)

        body_room = max(1, height - 4 - len(lines))
        wrapped_content: list[str] = []
        for item in content[-max(1, body_room * 2) :]:
            wrapped_content.extend(wrap(item))
        visible_content = wrapped_content[-body_room:] if wrapped_content else [""]
        for item in visible_content:
            lines.append(row(item, self.style.fg))
        while len(lines) < max(0, height - 2):
            lines.append(row("", self.style.fg_dim))

        lines.append(self.style.fg_fn(self.style.border) + "─" * inner_w + self.style.reset)
        lines.append(row(footer, self.style.muted))
        return lines[:height]


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
        pop_w = min(74, cols - 4)
        n = min(len(hits), 10)
        top = rows - 2 - n - 2
        left = max(2, (cols - pop_w) // 2)
        out = [self.popup_frame(top, left, pop_w, "commands")]
        for idx, (cmd, desc, category, example) in enumerate(hits[:10]):
            is_sel = idx == sel
            cmd_cell = f"{'› ' if is_sel else '  '}{cmd[:15]:<16}"
            category_cell = f"[{category}]"
            hint = example or desc
            content = f"{cmd_cell}{category_cell:<12} {hint[:max(0, pop_w - 33)]}"
            out.append(
                self.popup_line(
                    top + 1 + idx,
                    left,
                    pop_w,
                    content,
                    self.style.fg_hi if is_sel else self.style.fg_dim,
                    is_sel,
                )
            )
        out.append(self.move(top + 1 + n, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        return "".join(out)

    def picker_popup(self, rows: int, cols: int) -> str:
        items = self.tui.picker_items
        sel = self.tui.picker_sel
        pop_w = min(78, cols - 4)
        left = max(2, (cols - pop_w) // 2)
        preview_lines = list(getattr(self.tui, "picker_preview_lines", []))[:5]
        query = getattr(self.tui, "picker_query", "")
        stage = getattr(self.tui, "picker_stage", "providers")
        visible_limit = min(len(items), max(8, rows - 14))
        top = max(2, (rows - visible_limit - len(preview_lines) - 7) // 2)
        title = "providers" if stage == "providers" else f"models · {getattr(self.tui, 'picker_provider_key', '')}"
        out = [self.popup_frame(top, left, pop_w, title)]
        filter_text = query or ("type to filter providers" if stage == "providers" else "type to filter models")
        out.append(self.popup_line(top + 1, left, pop_w, f"filter: {filter_text}", self.style.muted, False))
        out.append(self.move(top + 2, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row = top + 3
        start = 0
        if items:
            start = max(0, min(sel - visible_limit // 2, max(0, len(items) - visible_limit)))
        for idx, item in enumerate(items[start : start + visible_limit], start=start):
            kind = item.get("kind")
            label = item.get("label", "")
            meta = item.get("meta", "")
            if kind == "header":
                out.append(self.popup_line(row, left, pop_w, label[: pop_w - 6], self.style.muted, False))
            elif kind == "hint":
                out.append(self.popup_line(row, left, pop_w, label[: pop_w - 6], self.style.fg_dim, False))
            else:
                is_sel = idx == sel
                marker = "●" if item.get("current") else ("★" if label.startswith("★") else "○")
                state = "× " if item.get("disabled") else f"{marker} "
                label_width = max(12, pop_w - 32)
                content = f"{'› ' if is_sel else '  '}{state}{label[:label_width]:<{label_width}} {meta[:max(0, pop_w - label_width - 10)]}"
                out.append(self.popup_line(row, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1
        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row += 1
        for preview in preview_lines or [getattr(self.tui, "picker_empty_message", "Type to filter")]:
            out.append(self.popup_line(row, left, pop_w, preview[: pop_w - 6], self.style.fg_dim, False))
            row += 1
        out.append(self.move(row, left) + self.style.fg_fn(self.style.border) + "  " + "─" * (pop_w - 4) + "  " + self.style.reset)
        row += 1
        footer = "Esc close · ↑↓ move · Enter select · ← back · type filter · Ctrl+F favorite"
        out.append(self.popup_line(row, left, pop_w, footer[: pop_w - 6], self.style.muted, False))
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
