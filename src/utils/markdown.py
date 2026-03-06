"""Render markdown as styled terminal text."""

import re

R       = "\033[0m"
B       = "\033[1m"
D       = "\033[2m"
CY      = "\033[38;5;117m"
GR      = "\033[38;5;245m"
WH      = "\033[97m"
BG_CODE = "\033[48;5;235m"


def render(text: str) -> str:
    lines = text.split("\n")
    out = []
    in_code = False
    code_buf = []
    code_lang = ""

    for line in lines:
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                code_buf = []
            else:
                in_code = False
                lang_label = f" {CY}{code_lang}{R}{GR}" if code_lang else ""
                out.append(f"  {GR}┌─{lang_label}{'─'*(40-len(code_lang))}{R}")
                for cl in code_buf:
                    out.append(f"  {GR}│{R}  {WH}{cl}{R}")
                out.append(f"  {GR}└{'─'*42}{R}")
            continue

        if in_code:
            code_buf.append(line)
            continue

        if line.startswith("# "):
            out.append(f"\n  {B}{WH}{line[2:]}{R}")
            continue
        if line.startswith("## "):
            out.append(f"\n  {B}{CY}{line[3:]}{R}")
            continue
        if line.startswith("### "):
            out.append(f"\n  {B}{line[4:]}{R}")
            continue
        if re.match(r"^[-*] ", line):
            out.append(f"  {GR}•{R} {_inline(line[2:])}")
            continue
        m = re.match(r"^(\d+)\. (.+)", line)
        if m:
            out.append(f"  {GR}{m.group(1)}.{R} {_inline(m.group(2))}")
            continue
        if line.startswith("> "):
            out.append(f"  {GR}│{R} {D}{line[2:]}{R}")
            continue
        if re.match(r"^[-*_]{3,}$", line.strip()):
            out.append(f"  {GR}{'─'*44}{R}")
            continue

        out.append("  " + _inline(line) if line.strip() else "")

    return "\n".join(out)


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", lambda m: f"{BG_CODE}{CY} {m.group(1)} {R}", text)
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"{B}{WH}{m.group(1)}{R}", text)
    text = re.sub(r"__(.+?)__",     lambda m: f"{B}{WH}{m.group(1)}{R}", text)
    text = re.sub(r"\*(.+?)\*",     lambda m: f"{D}{m.group(1)}{R}", text)
    text = re.sub(r"_(.+?)_",       lambda m: f"{D}{m.group(1)}{R}", text)
    return text
