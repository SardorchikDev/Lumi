"""Composable view helpers for the Lumi TUI."""

from __future__ import annotations

import re
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


def _load_app_version() -> str:
    try:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        if tomllib is not None:
            data = tomllib.loads(content)
            project = data.get("project", {})
            version = str(project.get("version", "")).strip()
            if version:
                return version
        match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"\s*$', content)
        if match:
            return match.group(1).strip() or "dev"
        return "dev"
    except Exception:
        return "dev"


APP_VERSION = _load_app_version()
TUI_LOGO_LINES: tuple[str, ...] = (
    "▐▛███▜▌",
    "▝▜█████▛▘",
    "▘▘ ▝▝",
)
SHORTCUT_ROWS: tuple[tuple[str, str], ...] = (
    ("?", "show or hide shortcuts"),
    ("/", "open the command menu"),
    ("Ctrl+P", "open the command palette"),
    ("Ctrl+N", "open the model picker"),
    ("Ctrl+T", "toggle the TODO pane"),
    ("Tab", "accept a command or path suggestion"),
    ("Esc", "close menus and pending UI"),
    ("Ctrl+L", "clear the current chat"),
    ("Ctrl+R", "retry the last Lumi reply"),
    ("Ctrl+G", "toggle the starter card"),
    ("Shift+↑/↓", "scroll the transcript"),
)


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
    orange: str


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

    @staticmethod
    def _display_path(path: Path, *, max_len: int = 56) -> str:
        text = str(path.resolve())
        home = str(Path.home())
        if text == home:
            text = "~"
        elif text.startswith(home + "/"):
            text = "~/" + text[len(home) + 1 :]
        if len(text) <= max_len:
            return text
        return "..." + text[-(max_len - 3) :]

    @staticmethod
    def _wrap_plain(text: str, width: int) -> list[str]:
        if not text:
            return [""]
        return textwrap.wrap(text, max(1, width), break_long_words=True, break_on_hyphens=False) or [text]

    @staticmethod
    def _fit_plain(text: str, width: int) -> str:
        if width <= 0:
            return ""
        if len(text) <= width:
            return text
        if width <= 1:
            return text[:width]
        return text[: max(1, width - 1)].rstrip() + "…"

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
        review_card = getattr(self.tui, "review_card", None)
        if pending:
            inspection = pending.get("inspection") if isinstance(pending, dict) else None
            plan = pending.get("plan", {}) if isinstance(pending, dict) else pending[0]
            operation = plan.get("operation", "create")
            title = {
                "delete": "review removal",
                "move": "review move",
                "copy": "review copy",
                "rename": "review rename",
            }.get(operation, "review filesystem plan")
            summary = list((inspection or {}).get("summary_lines", []))[:5]
            preview = list((inspection or {}).get("preview_lines", []))[:4]
            footer = "y apply  ·  n cancel  ·  enter cancel"
        elif getattr(review_card, "active", False):
            title = review_card.title or "review"
            summary = review_card.summary()[:5]
            preview = review_card.preview()[:4]
            footer = review_card.footer or "Esc close"
        else:
            return []
        left = "    "
        content_w = max(18, width - len(left) - 2)
        rule_w = min(72, content_w)

        def row(text: str = "", tone: str | None = None) -> str:
            tone = tone or self.style.fg_dim
            return left + self.style.fg_fn(tone) + text[:content_w] + self.style.reset

        lines = [
            row(title, self.style.muted),
            left + self.style.fg_fn(self.style.border) + "─" * rule_w + self.style.reset,
        ]
        for line in summary or ["plan ready for review"]:
            lines.append(row(line, self.style.fg_hi))
        if preview:
            lines.append("")
            lines.append(row("preview", self.style.muted))
            for line in preview:
                lines.append(row(line, self.style.fg_dim))
        lines.extend(["", row(footer, self.style.muted)])
        return lines

    def _build_tip_lines(self, width: int, *, left: str = "  ", max_width: int | None = None) -> list[str]:
        tip = str(getattr(self.tui, "session_tip", "") or "").strip()
        if not tip:
            return []
        label = "tip  "
        left = left + "  "
        available = max_width if max_width is not None else max(32, width - len(left) - 4)
        content_w = max(12, available - len(label))
        if len(tip) > content_w:
            tip = tip[: max(9, content_w - 3)].rstrip() + "..."
        return [
            left
            + self.style.fg_fn(self.style.muted)
            + label
            + self.style.reset
            + self.style.fg_fn(self.style.fg_dim)
            + tip
            + self.style.reset
        ]

    def _recent_activity_lines(self, width: int) -> list[str]:
        content_w = max(12, width)
        actions = list(getattr(self.tui, "recent_actions", []) or [])
        commands = list(getattr(self.tui, "recent_commands", []) or [])
        source = actions[:3] if actions else commands[:3]
        if not source:
            return ["No recent activity"]
        lines: list[str] = []
        for item in source:
            label = str(item).strip()
            icon = "󰄬" if not label.startswith("/") else "󰘳"
            lines.extend(self._wrap_plain(f"{icon} {label}", content_w)[:2])
        return lines[:4]

    def _welcome_card(self, width: int, provider: str, model: str, cwd_short: str) -> list[str]:
        total_w = max(48, width - 2)
        left_col = min(52, max(38, total_w // 3 + 8))
        right_col = max(36, total_w - left_col - 5)
        top_fill = left_col + right_col + 5
        title = f" Lumi v{APP_VERSION}: Operator "
        title = title[: max(0, top_fill - 2)]
        left_rule = max(0, (top_fill - len(title)) // 2)
        right_rule = max(0, top_fill - len(title) - left_rule)

        def row(
            left_text: str = "",
            right_text: str = "",
            *,
            left_tone: str | None = None,
            right_tone: str | None = None,
            left_bold: bool = False,
            right_bold: bool = False,
            left_center: bool = False,
        ) -> str:
            left_fit = self._fit_plain(left_text, left_col)
            right_fit = self._fit_plain(right_text, right_col)
            left_plain = left_fit.center(left_col) if left_center else left_fit.ljust(left_col)
            right_plain = right_fit.ljust(right_col)
            left_prefix = self.style.bold() if left_bold else ""
            right_prefix = self.style.bold() if right_bold else ""
            return (
                self.style.fg_fn(self.style.border)
                + "│ "
                + self.style.reset
                + left_prefix
                + self.style.fg_fn(left_tone or self.style.fg_dim)
                + left_plain
                + self.style.reset
                + self.style.fg_fn(self.style.border)
                + " │ "
                + self.style.reset
                + right_prefix
                + self.style.fg_fn(right_tone or self.style.fg_dim)
                + right_plain
                + self.style.reset
                + self.style.fg_fn(self.style.border)
                + " │"
                + self.style.reset
            )

        tip = str(getattr(self.tui, "session_tip", "") or "").removeprefix("Tip: ").strip()
        tips = [
            "Tips for getting started",
            *self._wrap_plain(tip, right_col)[:2],
            *self._wrap_plain("Use /model to switch providers and models.", right_col)[:2],
            *self._wrap_plain("Launch Lumi in a project directory for repo-aware workflows.", right_col)[:2],
            "__RULE__",
            "Recent activity",
            *self._recent_activity_lines(right_col),
        ]
        identity_line = self._fit_plain(f"{provider} · {model}", left_col)
        cwd_line = self._fit_plain(cwd_short, left_col)
        centered_left = {"Welcome back!", *TUI_LOGO_LINES, identity_line, cwd_line}
        logo = [
            "",
            "Welcome back!",
            "",
            *TUI_LOGO_LINES,
            "",
            identity_line,
            cwd_line,
        ]
        body_rows = max(len(logo), len(tips))
        left_lines = logo + [""] * max(0, body_rows - len(logo))
        right_lines = tips + [""] * max(0, body_rows - len(tips))

        lines = [
            self.style.fg_fn(self.style.border)
            + "╭"
            + "─" * left_rule
            + self.style.reset
            + self.style.fg_fn(self.style.muted)
            + title
            + self.style.reset
            + self.style.fg_fn(self.style.border)
            + "─" * right_rule
            + "╮"
            + self.style.reset,
        ]
        for left_text, right_text in zip(left_lines, right_lines, strict=False):
            if right_text == "__RULE__":
                lines.append(
                    row(
                        left_text,
                        "─" * right_col,
                        left_tone=self.style.fg_hi if left_text == "Welcome back!" else self.style.muted if left_text in {identity_line, cwd_line} else self.style.fg_dim,
                        right_tone=self.style.border,
                        left_bold=left_text == "Welcome back!",
                        left_center=left_text in centered_left,
                    )
                )
                continue
            lines.append(
                row(
                    left_text,
                    right_text,
                    left_tone=self.style.fg_hi if left_text == "Welcome back!" else self.style.muted if left_text in {identity_line, cwd_line} else self.style.fg_dim,
                    right_tone=self.style.fg_hi if right_text in {"Tips for getting started", "Recent activity"} else self.style.fg_dim,
                    left_bold=left_text == "Welcome back!",
                    right_bold=right_text in {"Tips for getting started", "Recent activity"},
                    left_center=left_text in centered_left,
                )
            )
        lines.append(
            self.style.fg_fn(self.style.border)
            + "╰"
            + "─" * top_fill
            + "╯"
            + self.style.reset
        )
        return lines

    def _build_identity_lines(self, width: int, provider: str, model: str, cwd_short: str) -> list[str]:
        left = "    "
        content_w = max(18, width - len(left) - 2)

        def row(text: str, tone: str, *, bold: bool = False) -> str:
            prefix = self.style.bold() if bold else ""
            return left + prefix + self.style.fg_fn(tone) + text[:content_w] + self.style.reset

        return [
            row("Lumi Operator", self.style.fg_hi, bold=True)
            + self.style.fg_fn(self.style.muted)
            + f"  v{APP_VERSION}"
            + self.style.reset,
            row(f"{provider} · {model}", self.style.fg_dim),
            row(cwd_short, self.style.muted),
        ]

    def _compact_build(self, width: int, provider: str, model: str, cwd_short: str) -> IntroRender:
        review_lines = self._build_review_lines(width)
        tip_lines = self._build_tip_lines(width, max_width=width - 8) if not review_lines else []
        lines = self._build_identity_lines(width, provider, model, cwd_short)
        if tip_lines:
            lines.extend(tip_lines)
        header_lines = lines + review_lines
        return IntroRender(
            header_lines=header_lines,
            prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
            trailing_lines=[],
        )

    def _minimal_header(self, width: int, provider: str, model: str, cwd_short: str) -> list[str]:
        logo_width = max(len(line) for line in TUI_LOGO_LINES)
        text_width = max(18, width - logo_width - 6)
        title = self._fit_plain(f"Lumi Operator v{APP_VERSION}", text_width)
        runtime = self._fit_plain(f"{provider} · {model}", text_width)
        cwd = self._fit_plain(cwd_short, text_width)
        logo_offsets = (2, 1, 3)
        logo_cell_width = logo_width + 2

        meta_rows = (
            (title, self.style.fg_hi, True),
            (runtime, self.style.fg_dim, False),
            (cwd, self.style.muted, False),
        )
        lines: list[str] = []
        for icon, offset, (text, tone, bold) in zip(TUI_LOGO_LINES, logo_offsets, meta_rows, strict=False):
            line = " " * offset
            line += self.style.fg_fn(self.style.fg_dim) + icon.ljust(logo_cell_width - offset) + self.style.reset
            line += "  "
            if bold:
                line += self.style.bold()
            line += self.style.fg_fn(tone) + text + self.style.reset
            lines.append(line)
        return lines

    def build(self, width: int) -> IntroRender:
        provider_key = self.provider_resolver()
        provider = self.provider_label(provider_key)
        model = self.tui.current_model.split("/")[-1][:26]
        cwd = Path.cwd().resolve()
        cwd_short = self._display_path(cwd)
        review_lines = self._build_review_lines(width)
        if review_lines:
            return IntroRender(
                header_lines=review_lines,
                prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
                trailing_lines=[],
            )
        if not getattr(self.tui, "show_starter_panel", True):
            return IntroRender(
                header_lines=[],
                prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
                trailing_lines=[],
            )
        return IntroRender(
            header_lines=self._minimal_header(width, provider, model, cwd_short),
            prompt=PromptRender(lines=[], cursor_row=0, cursor_col=0),
            trailing_lines=[],
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
        inner = max(30, width - 4)
        body_prefix = "    "
        if not msgs:
            return lines

        def append_prefixed(marker: str, text: str, *, marker_tone: str, tone: str) -> None:
            raw_lines = text.split("\n") or [""]
            first_prefix = "  " + self.style.fg_fn(marker_tone) + marker + self.style.reset + " "
            first_prefix_plain = self.strip_ansi(first_prefix)
            cont_prefix = "    "
            for index, chunk in enumerate(raw_lines):
                wrap_width = max(12, inner - (len(first_prefix_plain) if index == 0 else len(cont_prefix)))
                wrapped = textwrap.wrap(chunk, wrap_width, break_long_words=True, break_on_hyphens=False) if chunk.strip() else [""]
                for wrap_index, piece in enumerate(wrapped or [""]):
                    prefix = first_prefix if index == 0 and wrap_index == 0 else cont_prefix
                    lines.append(prefix + self.style.fg_fn(tone) + piece + self.style.reset)
            lines.append("")

        if getattr(self.tui, "agent_active_objective", None) and getattr(self.tui, "agent_tasks", None):
            lines.append("  " + self.style.fg_fn(self.style.muted) + "objective" + self.style.reset)
            for task in self.tui.agent_tasks:
                bullet = "·"
                label = task.get("text", "")
                for ln in textwrap.wrap(label, max(12, inner - len(body_prefix) - 2)) or [label]:
                    lines.append(body_prefix + self.style.fg_fn(self.style.muted) + bullet + " " + self.style.fg_fn(self.style.fg_dim) + ln + self.style.reset)
                    bullet = " "
            lines.append("")

        for msg in msgs:
            if msg.role == "user":
                append_prefixed("›", msg.text, marker_tone=self.style.fg_dim, tone=self.style.fg_hi)
                continue

            if msg.role == "tool":
                meta = msg.meta or {}
                status = str(meta.get("status") or "running")
                ok = bool(meta.get("ok", status == "done"))
                duration_ms = int(meta.get("duration_ms") or 0)
                icon = "▶"
                tone = self.style.cyan
                if status == "done":
                    icon = "✓" if ok else "✗"
                    tone = self.style.fg_hi if ok else self.style.red
                elif status == "failed":
                    icon = "✗"
                    tone = self.style.red
                label = (msg.label or "tool").strip()
                suffix = msg.text.strip()
                parts = [f"{icon} {label}"]
                if suffix:
                    parts.append(suffix)
                elif duration_ms:
                    parts.append(f"{duration_ms}ms")
                rendered = "  ".join(part for part in parts if part).strip()
                wrap_width = max(12, inner - 2)
                for chunk in textwrap.wrap(rendered, wrap_width, break_long_words=False) or [rendered]:
                    lines.append("  " + self.style.fg_fn(tone) + chunk + self.style.reset)
                lines.append("")
                continue

            if msg.role in ("assistant", "streaming"):
                is_stream = msg.role == "streaming"
                if is_stream:
                    blink_on = int(time.time() * 4) % 2 == 0
                    cursor = " " + self.style.fg_fn(self.style.cyan) + ("▋" if blink_on else " ") + self.style.reset
                else:
                    cursor = ""

                if self.tui.vessel_mode and self.tui.active_vessel:
                    marker_tone = self.style.red
                else:
                    marker_tone = self.style.fg_dim

                prefix = body_prefix
                inline_prefix = "  " + self.style.fg_fn(marker_tone) + "•" + self.style.reset + " "
                inline_prefix_plain = self.strip_ansi(inline_prefix)
                raw_lines = msg.text.split("\n") if msg.text else [""]
                in_code = False
                code_w = min(max(18, inner - len(body_prefix)), 88)
                code_lineno = 0
                used_inline_prefix = False

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
                        wrap_width = max(12, inner - (len(inline_prefix_plain) if not used_inline_prefix else len(prefix)))
                        if not used_inline_prefix and len(self.strip_ansi(ln)) <= wrap_width:
                            lines.append(inline_prefix + rendered + self.style.reset)
                            used_inline_prefix = True
                        elif not used_inline_prefix:
                            wrapped = textwrap.wrap(self.strip_ansi(ln), wrap_width) or [ln]
                            lines.append(inline_prefix + self.style.fg_fn(self.style.fg) + wrapped[0] + self.style.reset)
                            for extra in wrapped[1:]:
                                lines.append(prefix + self.style.fg_fn(self.style.fg) + extra + self.style.reset)
                            used_inline_prefix = True
                        else:
                            for wrapped in textwrap.wrap(self.strip_ansi(ln), max(12, inner - len(prefix))) or [ln]:
                                lines.append(prefix + self.style.fg_fn(self.style.fg) + wrapped + self.style.reset)

                if in_code:
                    lines.append(prefix + self.style.bg_fn(self.style.bg_pop_value) + self.style.fg_fn(self.style.red) + "[stream paused]" + " " * (code_w - 15) + self.style.reset)
                if cursor and lines:
                    lines[-1] += cursor
                lines.append("")
                continue

            if msg.role == "system":
                append_prefixed("⎿", msg.text, marker_tone=self.style.muted, tone=self.style.fg_dim)
                continue

            if msg.role == "error":
                append_prefixed("!", msg.text, marker_tone=self.style.red, tone=self.style.fg_hi)

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
        lines.append(row("", self.style.fg_dim))

        body_room = max(1, height - 2 - len(lines))
        wrapped_content: list[str] = []
        for item in content[-max(1, body_room * 2) :]:
            wrapped_content.extend(wrap(item))
        visible_content = wrapped_content[-body_room:] if wrapped_content else [""]
        for item in visible_content:
            lines.append(row(item, self.style.fg))
        while len(lines) < max(0, height - 2):
            lines.append(row("", self.style.fg_dim))

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

    @staticmethod
    def _command_icon(cmd: str) -> str:
        return {
            "/add-dir": "󰉓",
            "/agents": "󰚩",
            "/brief": "󰘙",
            "/config": "󰒓",
            "/files": "󰈔",
            "/fast": "󰓅",
            "/model": "󰒓",
            "/mode": "󰆍",
            "/browse": "󰉋",
            "/file": "󰈔",
            "/permissions": "󰌾",
            "/hooks": "󰛢",
            "/review": "󰦨",
            "/image": "󰉏",
            "/voice": "󰍬",
            "/search": "󰍉",
            "/agent": "󰚩",
            "/git": "󰊢",
            "/memory": "󰍛",
            "/skills": "󰠮",
            "/plugins": "󰏖",
            "/plugin": "󰏖",
            "/reload-plugins": "󰑐",
            "/offline": "󰛳",
            "/compact": "󰘕",
            "/tasks": "󰄳",
            "/version": "󰑔",
        }.get(cmd, "󰘳")

    def _popup_anchor(self, rows: int, chat_w: int, total_lines: int) -> tuple[int, int, int]:
        renderer = getattr(self.tui, "renderer", None)
        prompt_top = int(getattr(self.tui, "_last_prompt_top", 0) or 0)
        prompt_height = int(getattr(self.tui, "_last_prompt_height", 0) or 0)
        if renderer is not None and (prompt_top <= 1 or prompt_height <= 1):
            starter_rows = len(renderer._build_starter_lines(chat_w))
            chat_line_count = len(renderer._build_chat_lines(chat_w))
            prompt_lines, _cursor_row, _cursor_col = renderer._prompt_bar(rows, chat_w, chat_w)
            prompt_top = renderer._prompt_top(
                rows,
                renderer._transcript_top(starter_rows, chat_line_count),
                len(prompt_lines),
                chat_line_count,
            )
            prompt_height = len(prompt_lines)
        prompt_top = max(1, prompt_top or 1)
        prompt_height = max(1, prompt_height or 1)
        usable_width = max(24, chat_w - 4)
        below_top = prompt_top + prompt_height
        below_space = max(0, rows - below_top + 1)
        above_top = max(2, prompt_top - total_lines)
        if below_space >= total_lines:
            top = below_top
        else:
            top = min(max(2, above_top), max(1, rows - total_lines + 1))
        return top, 2, usable_width

    @staticmethod
    def _windowed_items(total: int, sel: int, body_rows: int) -> tuple[int, int, bool, bool]:
        if total <= 0:
            return 0, 0, False, False
        count = max(1, min(total, body_rows))
        start = max(0, min(sel - count // 2, total - count))
        has_above = start > 0
        has_below = start + count < total
        return start, count, has_above, has_below

    def browser_popup(self, rows: int, chat_w: int) -> str:
        items = self.tui.browser_items
        sel = self.tui.browser_sel
        prompt_height = max(1, int(getattr(self.tui, "_last_prompt_height", 1) or 1))
        available_rows = max(6, rows - prompt_height - 1)
        pop_w = min(52, max(30, chat_w - 8))
        visible_items = min(len(items), max(6, min(10, available_rows - 3))) if items else 1
        pop_h = min(max(5, visible_items + 3), available_rows)
        top, left, _usable_width = self._popup_anchor(rows, chat_w, pop_h)

        if items:
            total = len(items)
            body_rows = max(1, pop_h - 3)
            start, count, has_above, has_below = self._windowed_items(total, sel, body_rows)
            disp_items = items[start : start + count]
            local_sel = sel - start
        else:
            disp_items = []
            local_sel = -1
            has_above = False
            has_below = False

        title = "browser"
        if has_above or has_below:
            title += (" ↑" if has_above else "") + (" ↓" if has_below else "")
        out = [self.popup_frame(top, left, pop_w, title)]
        cwd = self.tui.browser_cwd
        if len(cwd) > pop_w - 6:
            cwd = "..." + cwd[-(pop_w - 9) :]
        out.append(self.popup_line(top + 1, left, pop_w, cwd, self.style.fg_hi, False))

        row = top + 2
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

        out.append(self.popup_line(row, left, pop_w, "Esc close · Enter open · ← back · PgUp/PgDn", self.style.muted, False))
        return "".join(out)

    def slash_popup(self, rows: int, chat_w: int) -> str:
        hits = self.tui.slash_hits
        sel = self.tui.slash_sel
        prompt_height = max(1, int(getattr(self.tui, "_last_prompt_height", 1) or 1))
        pop_w = min(76, max(38, chat_w - 6))
        visible_limit = min(len(hits), max(4, min(8, rows - prompt_height - 3)))
        visible_count = max(1, min(len(hits), visible_limit))
        total_lines = visible_count + 2
        top, left, _usable_width = self._popup_anchor(rows, chat_w, total_lines)
        start, count, has_above, has_below = self._windowed_items(len(hits), sel, visible_limit)
        title = "commands"
        if has_above or has_below:
            title += (" ↑" if has_above else "") + (" ↓" if has_below else "")
        out: list[str] = [self.popup_frame(top, left, pop_w, title)]
        row = top + 1
        for idx, (cmd, desc, _category, _example) in enumerate(hits[start : start + count], start=start):
            is_sel = idx == sel
            cmd_cell = f"{cmd[:13]:<13}"
            desc_width = max(0, pop_w - 24)
            marker = "›" if is_sel else " "
            icon = self._command_icon(cmd)
            content = f"{marker} {icon} {cmd_cell}  {desc[:desc_width]}"
            out.append(
                self.popup_line(
                    row,
                    left,
                    pop_w,
                    content,
                    self.style.fg_hi if is_sel else self.style.fg_dim,
                    is_sel,
                )
            )
            row += 1
        out.append(self.popup_line(row, left, pop_w, "Esc close · Tab/Enter select · PgUp/PgDn", self.style.muted, False))
        return "".join(out)

    def shortcuts_popup(self, rows: int, chat_w: int) -> str:
        pop_w = min(68, max(42, chat_w - 4))
        total_lines = len(SHORTCUT_ROWS) + 2
        top, left, _usable_width = self._popup_anchor(rows, chat_w, total_lines)
        key_w = max(len(label) for label, _desc in SHORTCUT_ROWS)
        desc_w = max(12, pop_w - key_w - 7)
        out = [self.popup_frame(top, left, pop_w, "shortcuts")]
        row = top + 1
        for label, desc in SHORTCUT_ROWS:
            content = f"  {label:<{key_w}}  {desc[:desc_w]}"
            out.append(self.popup_line(row, left, pop_w, content, self.style.fg_dim, False))
            row += 1
        out.append(self.popup_line(row, left, pop_w, "  Enter or Esc to close", self.style.muted, False))
        return "".join(out)

    def command_palette_popup(self, rows: int, chat_w: int) -> str:
        hits = list(getattr(self.tui, "command_palette_hits", []) or [])
        sel = int(getattr(self.tui, "command_palette_sel", 0) or 0)
        query = str(getattr(self.tui, "command_palette_query", "") or "")
        pop_w = min(78, max(42, chat_w - 6))
        visible_limit = min(len(hits), max(5, min(10, rows - 6)))
        total_lines = visible_limit + 3
        top, left, _usable_width = self._popup_anchor(rows, chat_w, total_lines)
        start, count, has_above, has_below = self._windowed_items(len(hits), sel, visible_limit)
        title = "palette"
        if has_above or has_below:
            title += (" ↑" if has_above else "") + (" ↓" if has_below else "")
        out = [self.popup_frame(top, left, pop_w, title)]
        row = top + 1
        out.append(self.popup_line(row, left, pop_w, f"󰱼 {query}" if query else "󰱼 type to search commands or prompts", self.style.muted, False))
        row += 1
        for idx, item in enumerate(hits[start : start + count], start=start):
            is_sel = idx == sel
            kind = str(item.get("kind") or "command")
            label = str(item.get("label") or "")
            desc = str(item.get("desc") or "")
            icon = "󰘳" if kind == "command" else "󰆍"
            marker = "›" if is_sel else " "
            desc_width = max(8, pop_w - 22)
            content = f"{marker} {icon} {label[:16]:<16}  {desc[:desc_width]}"
            out.append(self.popup_line(row, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1
        while row < top + total_lines - 1:
            out.append(self.popup_line(row, left, pop_w, "", self.style.fg_dim, False))
            row += 1
        out.append(self.popup_line(row, left, pop_w, "Esc close · Enter run/fill · PgUp/PgDn", self.style.muted, False))
        return "".join(out)

    def permission_popup(self, rows: int, cols: int) -> str:
        prompt = getattr(self.tui, "permission_prompt", None)
        if prompt is None or not getattr(prompt, "active", False):
            return ""
        options = ("Allow Once", "Allow Always", "Deny")
        selected = int(getattr(prompt, "selected", 0) or 0)
        body_w = min(max(54, cols - 18), 88)
        left = max(2, (cols - body_w) // 2)
        lines = [
            "┌─ Permission required " + "─" * max(0, body_w - 24) + "┐",
            f"│  {str(getattr(prompt, 'tool_name', '') or '')[: body_w - 4]:<{body_w - 4}}│",
        ]
        detail_lines = textwrap.wrap(str(getattr(prompt, "display", "") or ""), max(16, body_w - 6), break_long_words=False) or [""]
        for detail in detail_lines[:2]:
            lines.append(f"│  {detail[: body_w - 4]:<{body_w - 4}}│")
        rule_hint = str(getattr(prompt, "rule_hint", "") or "")
        if rule_hint and rule_hint != getattr(prompt, "display", ""):
            for detail in textwrap.wrap(rule_hint, max(16, body_w - 6), break_long_words=False)[:1]:
                lines.append(f"│  {detail[: body_w - 4]:<{body_w - 4}}│")
        lines.append(f"│  {'':<{body_w - 4}}│")
        option_cells: list[str] = []
        for idx, label in enumerate(options):
            if idx == selected:
                option_cells.append(f"[{label}]")
            else:
                option_cells.append(label)
        option_line = "  ".join(option_cells)
        lines.append(f"│  {option_line[: body_w - 4]:<{body_w - 4}}│")
        lines.append("└" + "─" * (body_w - 2) + "┘")
        top = max(2, (rows - len(lines)) // 2)
        out: list[str] = []
        for offset, line in enumerate(lines):
            out.append(self.move(top + offset, left) + self.style.fg_fn(self.style.fg_hi if offset in {0, len(lines) - 1} else self.style.fg_dim) + line + self.style.reset)
        return "".join(out)

    def picker_popup(self, rows: int, chat_w: int) -> str:
        items = self.tui.picker_items
        sel = self.tui.picker_sel
        pop_w = min(52, max(30, chat_w - 8))
        query = getattr(self.tui, "picker_query", "")
        stage = getattr(self.tui, "picker_stage", "providers")
        prompt_height = max(1, int(getattr(self.tui, "_last_prompt_height", 1) or 1))
        query_block = 1 if query else 0
        reserved = 1 + query_block
        visible_limit = min(len(items), max(6, min(10, rows - prompt_height - reserved - 1)))
        total_lines = reserved + visible_limit + 1
        top, left, _usable_width = self._popup_anchor(rows, chat_w, total_lines)
        has_above = False
        has_below = False
        title_base = "providers" if stage == "providers" else f"models · {getattr(self.tui, 'picker_provider_key', '')}"
        out = [self.popup_frame(top, left, pop_w, title_base)]
        row = top + 1
        if query:
            out.append(self.popup_line(row, left, pop_w, f"󰱼 {query}", self.style.muted, False))
            row += 1
        start = 0
        if items:
            start = max(0, min(sel - visible_limit // 2, max(0, len(items) - visible_limit)))
            has_above = start > 0
            has_below = start + visible_limit < len(items)
        for idx, item in enumerate(items[start : start + visible_limit], start=start):
            kind = item.get("kind")
            label = item.get("label", "")
            icon = item.get("icon", "󰘳")
            if kind == "header":
                out.append(self.popup_line(row, left, pop_w, f"  {icon} {label}"[: pop_w - 6], self.style.muted, False))
            elif kind == "hint":
                out.append(self.popup_line(row, left, pop_w, f"  󰞋 {label}"[: pop_w - 6], self.style.fg_dim, False))
            else:
                is_sel = idx == sel
                marker = "›" if is_sel else " "
                state_icon = "󰄬" if item.get("current") else "󰓎" if item.get("favorite") else "󰘳"
                if item.get("disabled"):
                    state_icon = "󰜺"
                label_width = max(12, pop_w - 12)
                content = f"{marker} {state_icon} {icon} {label[:label_width]}"
                out.append(self.popup_line(row, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1
        hint = "Esc close · Enter select · PgUp/PgDn page"
        out.append(self.popup_line(row, left, pop_w, hint[: pop_w - 2], self.style.muted, False))
        if has_above or has_below:
            arrows = ("↑" if has_above else " ") + (" ↓" if has_below else "")
            title = f"{title_base} {arrows}"
        else:
            title = title_base
        out[0] = self.popup_frame(top, left, pop_w, title)
        return "".join(out)

    def path_popup(self, rows: int, chat_w: int) -> str:
        hits = self.tui.path_hits
        sel = self.tui.path_sel
        prompt_height = max(1, int(getattr(self.tui, "_last_prompt_height", 1) or 1))
        pop_w = min(52, max(28, chat_w - 8))
        visible_limit = min(len(hits), max(4, min(8, rows - prompt_height - 3)))
        total_lines = visible_limit + 2
        top, left, _usable_width = self._popup_anchor(rows, chat_w, total_lines)
        start, count, has_above, has_below = self._windowed_items(len(hits), sel, visible_limit)
        title = "paths"
        if has_above or has_below:
            title += (" ↑" if has_above else "") + (" ↓" if has_below else "")
        out = [self.popup_frame(top, left, pop_w, title)]
        row = top + 1
        for idx, path in enumerate(hits[start : start + count], start=start):
            is_sel = idx == sel
            content = f"{'› ' if is_sel else '  '}{path[: pop_w - 8]}"
            out.append(self.popup_line(row, left, pop_w, content, self.style.fg_hi if is_sel else self.style.fg_dim, is_sel))
            row += 1
        out.append(self.popup_line(row, left, pop_w, "Esc close · Tab accept · PgUp/PgDn", self.style.muted, False))
        return "".join(out)

    def workspace_trust_popup(self, rows: int, cols: int) -> str:
        cwd = str(Path.cwd().resolve())
        body_w = min(max(72, cols - 14), 132)
        left = max(2, (cols - body_w) // 2)
        question = (
            "Quick safety check: Is this a project you created or one you trust? "
            "(Like your own code, a well-known open source project, or work from your team). "
            "If not, take a moment to review what's in this folder first."
        )
        wrapped_question = textwrap.wrap(question, max(24, body_w - 2), break_long_words=False)
        option_one = "1. Yes, I trust this folder"
        option_two = "2. No, exit"
        selected = int(getattr(self.tui, "workspace_trust_sel", 0) or 0)
        lines = [
            self.style.fg_fn(self.style.border) + "─" * body_w + self.style.reset,
            "",
            self.style.bold() + self.style.fg_fn(self.style.fg_hi) + "Accessing workspace:" + self.style.reset,
            "",
            self.style.fg_fn(self.style.muted) + cwd + self.style.reset,
            "",
            *[
                self.style.fg_fn(self.style.fg_dim) + line + self.style.reset
                for line in wrapped_question
            ],
            "",
            self.style.fg_fn(self.style.fg_dim) + "Lumi will be able to read, edit, and execute files here." + self.style.reset,
            "",
            self.style.fg_fn(self.style.cyan) + "Security guide" + self.style.reset,
            "",
            (self.style.bold() if selected == 0 else "")
            + self.style.fg_fn(self.style.fg_hi if selected == 0 else self.style.fg_dim)
            + ("❯ " if selected == 0 else "  ")
            + option_one
            + self.style.reset,
            (self.style.bold() if selected == 1 else "")
            + self.style.fg_fn(self.style.fg_hi if selected == 1 else self.style.fg_dim)
            + ("❯ " if selected == 1 else "  ")
            + option_two
            + self.style.reset,
            "",
            self.style.fg_fn(self.style.muted) + "Enter to confirm · Esc to cancel" + self.style.reset,
            self.style.fg_fn(self.style.border) + "─" * body_w + self.style.reset,
        ]
        top = max(2, (rows - len(lines)) // 2)
        out: list[str] = []
        for idx, line in enumerate(lines):
            plain = self.strip_ansi(line)
            padded = line + " " * max(0, body_w - len(plain))
            out.append(self.move(top + idx, left) + padded)
        return "".join(out)

    def _notification_meta(self, msg: str) -> tuple[str, str, str]:
        lower = msg.lower()
        if any(token in lower for token in ("warning", "guardian", "failed", "error", "missing", "denied", "cancelled")):
            return "warning", "󰀦", self.style.red
        if any(
            token in lower
            for token in (
                "saved",
                "loaded",
                "trusted",
                "enabled",
                "disabled",
                "added",
                "removed",
                "model",
                "mode",
                "effort",
                "multiline",
                "rebirth",
                "offline",
                "chat cleared",
            )
        ):
            return "status", "󰄬", self.style.cyan
        return "notice", "󰋽", self.style.fg_hi

    def notification_bar(self, rows: int, cols: int) -> str:
        msg = str(getattr(self.tui, "notification", "") or "").strip()
        if not msg:
            return ""

        label, icon, tone = self._notification_meta(msg)
        max_w = min(72, max(30, cols - 4))
        inner_w = max(18, max_w - 2)
        content_w = max(16, inner_w - 4)
        wrapped = textwrap.wrap(msg, content_w, break_long_words=True, break_on_hyphens=False) or [msg]
        body_w = max(
            18,
            min(
                max_w - 2,
                max(len(line) for line in wrapped) + 4,
            ),
        )
        width = min(max_w, max(24, body_w + 2, len(label) + 6))
        inner_w = max(18, width - 2)
        content_w = max(16, inner_w - 4)
        wrapped = textwrap.wrap(msg, content_w, break_long_words=True, break_on_hyphens=False) or [msg]

        title = f" {label} "
        left_rule = max(0, (inner_w - len(title)) // 2)
        right_rule = max(0, inner_w - len(title) - left_rule)
        top_line = (
            self.style.fg_fn(self.style.border)
            + "╭"
            + "─" * left_rule
            + self.style.reset
            + self.style.fg_fn(self.style.muted)
            + title
            + self.style.reset
            + self.style.fg_fn(self.style.border)
            + "─" * right_rule
            + "╮"
            + self.style.reset
        )

        body_lines: list[str] = []
        for idx, line in enumerate(wrapped[:3]):
            prefix = f"{icon} " if idx == 0 else "  "
            padded = f"{prefix}{line}"[: inner_w - 2]
            body_lines.append(
                self.style.fg_fn(self.style.border)
                + "│ "
                + self.style.reset
                + self.style.fg_fn(tone if idx == 0 else self.style.fg_dim)
                + padded.ljust(inner_w - 2)
                + self.style.reset
                + self.style.fg_fn(self.style.border)
                + " │"
                + self.style.reset
            )

        bottom_line = (
            self.style.fg_fn(self.style.border)
            + "╰"
            + "─" * inner_w
            + "╯"
            + self.style.reset
        )

        lines = [top_line, *body_lines, bottom_line]
        top = max(2, rows - len(lines) - 1)
        left = max(2, cols - width - 2)
        out: list[str] = []
        for idx, line in enumerate(lines):
            plain = self.strip_ansi(line)
            out.append(self.move(top + idx, left) + line + " " * max(0, width - len(plain)))
        return "".join(out)
