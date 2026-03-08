"""
Terminal syntax highlighter — pure ANSI, zero dependencies.
Handles Python, JavaScript/TypeScript, Bash, JSON, and generic fallback.
"""

import re

# ── ANSI codes ────────────────────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"

# Colors
KEYWORD  = "\033[38;5;141m"   # purple   — keywords
STRING   = "\033[38;5;114m"   # green    — strings
NUMBER   = "\033[38;5;215m"   # orange   — numbers
COMMENT  = "\033[38;5;59m"    # gray     — comments
FUNC     = "\033[38;5;75m"    # blue     — function names
BUILTIN  = "\033[38;5;81m"    # cyan     — builtins / types
OPERATOR = "\033[38;5;203m"   # red      — operators
PUNCT    = "\033[38;5;246m"   # mid-gray — punctuation
PLAIN    = "\033[38;5;252m"   # off-white — normal text

# ── Language patterns ─────────────────────────────────────────────────────────

PY_KEYWORDS = {
    "False","None","True","and","as","assert","async","await","break",
    "class","continue","def","del","elif","else","except","finally",
    "for","from","global","if","import","in","is","lambda","nonlocal",
    "not","or","pass","raise","return","try","while","with","yield",
}

PY_BUILTINS = {
    "print","len","range","type","str","int","float","bool","list",
    "dict","set","tuple","super","self","cls","open","input","enumerate",
    "zip","map","filter","sorted","reversed","any","all","hasattr",
    "getattr","setattr","isinstance","issubclass","staticmethod","property",
    "classmethod","abs","max","min","sum","round","repr","vars","dir",
}

JS_KEYWORDS = {
    "var","let","const","function","return","if","else","for","while",
    "do","break","continue","switch","case","default","new","delete",
    "typeof","instanceof","in","of","class","extends","super","import",
    "export","from","async","await","try","catch","finally","throw",
    "true","false","null","undefined","this","yield","void","static",
    "get","set","=>",
}

JS_BUILTINS = {
    "console","Math","JSON","Array","Object","String","Number","Boolean",
    "Promise","Map","Set","Date","Error","parseInt","parseFloat",
    "setTimeout","setInterval","fetch","require","module","exports",
}

BASH_KEYWORDS = {
    "if","then","else","elif","fi","for","in","do","done","while",
    "until","case","esac","function","return","exit","echo","export",
    "source","cd","ls","mkdir","rm","cp","mv","cat","grep","sed","awk",
    "local","readonly","declare","unset","shift","set","true","false",
}


def _tokenize(line: str, keywords: set, builtins: set, lang: str) -> str:
    """Colorize a single line of code."""
    result = ""
    i = 0
    n = len(line)

    while i < n:
        # Comments
        if lang in ("python",) and line[i] == "#":
            result += COMMENT + line[i:] + R
            break
        if lang in ("js", "ts") and line[i:i+2] == "//":
            result += COMMENT + line[i:] + R
            break
        if lang == "bash" and line[i] == "#":
            result += COMMENT + line[i:] + R
            break

        # Strings — single, double, backtick, triple
        if line[i:i+3] in ('"""', "'''"):
            q = line[i:i+3]
            end = line.find(q, i+3)
            end = end + 3 if end != -1 else n
            result += STRING + line[i:end] + R
            i = end
            continue
        if line[i] in ('"', "'", "`"):
            q = line[i]
            j = i + 1
            while j < n and line[j] != q:
                if line[j] == "\\" : j += 1
                j += 1
            result += STRING + line[i:j+1] + R
            i = j + 1
            continue

        # Numbers
        if line[i].isdigit() or (line[i] == "." and i+1 < n and line[i+1].isdigit()):
            j = i
            while j < n and (line[j].isalnum() or line[j] in ".xXbBoO_"):
                j += 1
            result += NUMBER + line[i:j] + R
            i = j
            continue

        # Words — keywords / builtins / identifiers
        if line[i].isalpha() or line[i] == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            if word in keywords:
                result += KEYWORD + B + word + R
            elif word in builtins:
                result += BUILTIN + word + R
            elif j < n and line[j] == "(":
                result += FUNC + word + R
            else:
                result += PLAIN + word + R
            i = j
            continue

        # Operators
        if line[i] in "=+-*/%<>!&|^~":
            result += OPERATOR + line[i] + R
            i += 1
            continue

        # Punctuation
        if line[i] in "()[]{}.,;:@":
            result += PUNCT + line[i] + R
            i += 1
            continue

        result += PLAIN + line[i] + R
        i += 1

    return result


def _highlight_json(code: str) -> str:
    lines = []
    for line in code.split("\n"):
        line = re.sub(r'("(?:[^"\\]|\\.)*")\s*:', lambda m: FUNC + m.group(1) + R + PUNCT + ":" + R, line)
        line = re.sub(r':\s*("(?:[^"\\]|\\.)*")', lambda m: ": " + STRING + m.group(1) + R, line)
        line = re.sub(r'\b(true|false|null)\b', KEYWORD + B + r'\1' + R, line)
        line = re.sub(r'\b(\d+\.?\d*)\b', NUMBER + r'\1' + R, line)
        lines.append(line)
    return "\n".join(lines)


def highlight(code: str, lang: str = "") -> str:
    """Highlight code block. lang is the fence language tag."""
    lang = lang.lower().strip()

    if lang == "json":
        return _highlight_json(code)

    if lang in ("python", "py"):
        kw, bi = PY_KEYWORDS, PY_BUILTINS
    elif lang in ("javascript", "js", "typescript", "ts", "jsx", "tsx"):
        kw, bi = JS_KEYWORDS, JS_BUILTINS
    elif lang in ("bash", "sh", "shell", "zsh", "fish"):
        kw, bi = BASH_KEYWORDS, set()
    else:
        # Generic: just dim it slightly, no full tokenization
        return DIM + code + R

    return "\n".join(_tokenize(line, kw, bi, lang or "generic") for line in code.split("\n"))


def render_code_block(code: str, lang: str = "", indent: str = "  ") -> str:
    """Render a full code block with border, language label, and syntax highlighting."""
    lang_label = f" {lang} " if lang else " code "
    border_color = "\033[38;5;238m"  # dark gray border
    label_color  = "\033[38;5;244m"  # medium gray label

    highlighted = highlight(code, lang)
    lines = highlighted.split("\n")

    out = []
    out.append(f"{indent}{border_color}╭─{label_color}{lang_label}{border_color}{'─' * max(0, 40 - len(lang_label))}╮{R}")
    for line in lines:
        out.append(f"{indent}{border_color}│{R}  {line}")
    out.append(f"{indent}{border_color}╰{'─' * 42}╯{R}")
    return "\n".join(out)
