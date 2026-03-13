"""Terminal markdown renderer with syntax-highlighted code blocks."""

import re

from src.utils.highlight import render_code_block

R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
UL  = "\033[4m"

C_H1     = "\033[38;5;141m"  # purple
C_H2     = "\033[38;5;75m"   # blue
C_H3     = "\033[38;5;81m"   # cyan
C_BOLD   = "\033[38;5;252m"  # bright white
C_CODE   = "\033[38;5;215m"  # orange
C_BULLET = "\033[38;5;141m"  # purple
C_DIM    = "\033[38;5;59m"   # gray


def render(text: str, indent: str = "  ") -> str:
    """Render markdown to ANSI terminal output."""
    lines   = text.split("\n")
    output  = []
    i       = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code blocks ─────────────────────────────────
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)
            output.append(render_code_block(code, lang, indent=indent))
            i += 1
            continue

        # ── Headings ───────────────────────────────────────────
        if line.startswith("### "):
            output.append(f"{indent}{C_H3}{B}{line[4:]}{R}")
            i += 1; continue
        if line.startswith("## "):
            output.append(f"\n{indent}{C_H2}{B}{line[3:]}{R}")
            i += 1; continue
        if line.startswith("# "):
            output.append(f"\n{indent}{C_H1}{B}{line[2:]}{R}\n")
            i += 1; continue

        # ── Horizontal rule ────────────────────────────────────
        if re.match(r'^[-*_]{3,}$', line.strip()):
            output.append(f"{indent}{C_DIM}{'─' * 50}{R}")
            i += 1; continue

        # ── Bullet lists ───────────────────────────────────────
        m = re.match(r'^(\s*)([-*+])\s+(.*)', line)
        if m:
            pad  = m.group(1)
            rest = _inline(m.group(3))
            output.append(f"{indent}{pad}{C_BULLET}·{R}  {rest}")
            i += 1; continue

        # ── Numbered lists ─────────────────────────────────────
        m = re.match(r'^(\s*)(\d+)[.)]\s+(.*)', line)
        if m:
            pad  = m.group(1)
            num  = m.group(2)
            rest = _inline(m.group(3))
            output.append(f"{indent}{pad}{C_H2}{num}.{R}  {rest}")
            i += 1; continue

        # ── Blank line ─────────────────────────────────────────
        if not line.strip():
            output.append("")
            i += 1; continue

        # ── Normal paragraph ───────────────────────────────────
        output.append(f"{indent}{_inline(line)}")
        i += 1

    return "\n".join(output)


def _inline(text: str) -> str:
    """Render inline markdown: bold, italic, inline code."""
    # Inline code
    text = re.sub(r'`([^`]+)`', lambda m: C_CODE + m.group(1) + R, text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: C_BOLD + B + m.group(1) + R, text)
    text = re.sub(r'__(.+?)__',     lambda m: C_BOLD + B + m.group(1) + R, text)
    # Italic
    text = re.sub(r'\*(.+?)\*',     lambda m: DIM + m.group(1) + R, text)
    text = re.sub(r'_(.+?)_',       lambda m: DIM + m.group(1) + R, text)
    # Strikethrough
    text = re.sub(r'~~(.+?)~~',     lambda m: DIM + UL + m.group(1) + R, text)
    return text
