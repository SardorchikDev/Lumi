"""
Terminal syntax highlighter using Pygments.
Maps Pygments tokens to Lumi TUI colors.
"""

from __future__ import annotations

try:
    from pygments import token
    from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from src.tui.colors import BLUE, COMMENT, CYAN, FG_DIM, FG_HI, ORANGE, PURPLE, YELLOW, B, R, _fg, _italic

if HAS_PYGMENTS:
    TOKEN_COLORS = {
        token.Keyword: B(PURPLE),
        token.Keyword.Constant: B(ORANGE),
        token.Keyword.Namespace: B(PURPLE),
        token.Name.Builtin: _fg(CYAN),
        token.Name.Function: _fg(BLUE),
        token.Name.Class: B(BLUE),
        token.Name.Decorator: _fg(YELLOW),
        token.Name.Exception: B(ORANGE),
        token.String: _fg(YELLOW),
        token.String.Doc: _fg(COMMENT) + _italic(),
        token.Number: _fg(ORANGE),
        token.Comment: _fg(COMMENT) + _italic(),
        token.Operator: _fg(CYAN),
        token.Operator.Word: B(PURPLE),
        token.Punctuation: _fg(FG_DIM),
        token.Text: _fg(FG_HI),
        token.Error: _fg(ORANGE),
    }

def _get_color(ttype):
    """Find appropriate color for a token type."""
    # Fast path
    if ttype in TOKEN_COLORS:
        return TOKEN_COLORS[ttype]

    # Walk up the parent chain
    curr = ttype
    while curr is not None:
        if curr in TOKEN_COLORS:
            return TOKEN_COLORS[curr]
        curr = curr.parent

    return _fg(FG_HI)



def highlight_line(code: str, lang: str = "") -> str:
    """
    Highlight a line (or fragment) of code using Pygments.
    Returns ANSI string WITHOUT resets at the end of every token,
    to preserve background color.
    """
    if not code:
        return ""

    if not HAS_PYGMENTS:
        return code

    try:
        if lang:
            try:
                lexer = get_lexer_by_name(lang, stripnl=False)
            except Exception:
                lexer = TextLexer()
        else:
            # Short snippets are hard to guess, default to Text or Python if ambiguous
            if len(code) > 20:
                try:
                    lexer = guess_lexer(code, stripnl=False)
                except Exception:
                    lexer = TextLexer()
            else:
                lexer = TextLexer()
    except Exception:
        lexer = TextLexer()

    tokens = lexer.get_tokens(code)
    out = ""
    for ttype, value in tokens:
        # We wrap each token in its color
        # IMPORTANT: We append R (reset) after each token?
        # The TUI app loop does: `lpre + _bg(BG_DARK) + lineno_str + hi + _bg(BG_DARK) + ... + R`
        # If we return `Color + text + R`, the `_bg(BG_DARK)` after `hi` restores the BG.
        # But `R` kills the BG *inside* the highlighted string if there are multiple tokens.
        # So we should NOT emit R, but rather just emit the next Color.
        # However, if we don't emit R, the foreground color persists.
        # That's what we want!
        # What about `token.Text`? It usually means whitespace or plain text.
        # We need to explicitly color it FG_HI so it doesn't inherit the previous token's color.

        c = _get_color(ttype)
        out += c + value

    # We explicitly return R at the end so the caller knows we are done with colors,
    # although the caller appends `_bg(BG_DARK)` right after, which sets BG but maybe not FG?
    # The caller appends `+ R` at the very end of the line.
    # To be safe and compatible with the old regex behavior (which did append R after every token),
    # let's try appending R.
    # WAIT: Old regex `_syntax_hi` appended R after EVERY token.
    # `elif g == 'str': out += _fg(YELLOW) + t.group() + R`
    # This means the author expected `R` to be safe.
    # If `R` resets BG, then the old code had broken BG too!
    # Let's assume the TUI relies on the caller re-applying BG or `BG_DARK` is simply not visible behind text?
    # Actually, in `app.py`:
    # lines.append(lpre + _bg(BG_DARK) + lineno_str + hi + _bg(BG_DARK) + " " * pad + R)
    # If `hi` has `... + R` in the middle, the text AFTER `R` has default BG.
    # If `hi` ends with `R`, then `_bg(BG_DARK)` is applied immediately after `hi`.
    # So the *padding* has BG_DARK.
    # But the text itself?
    # If `hi` is `YEL + "foo" + R + CYAN + "bar" + R`.
    # "foo" has YEL FG. BG? If `_bg(BG_DARK)` was emitted before `hi`, then "foo" has BG_DARK *until* `R`.
    # `R` resets BG.
    # So "bar" has CYAN FG and DEFAULT BG.
    # So the old regex code produced "striped" backgrounds (Dark, Default, Dark, Default...).
    # If I want to fix this, I should NOT emit R.
    # Instead, I should emit `_fg(FG_HI)` for plain text.

    return out + R


def highlight(code: str, lang: str = "") -> str:
    """Backward-compatible helper used by tests and older callers."""
    if not code:
        return ""

    normalized_lang = (lang or "").lower()
    aliases = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sh": "bash",
        "yml": "yaml",
    }
    normalized_lang = aliases.get(normalized_lang, normalized_lang)

    return "\n".join(highlight_line(line, normalized_lang) for line in code.split("\n"))


def render_code_block(code: str, lang: str = "", indent: str = "  ") -> str:
    """Render a code block with syntax highlighting."""
    normalized_lang = (lang or "").lower()
    aliases = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sh": "bash",
        "yml": "yaml",
    }
    normalized_lang = aliases.get(normalized_lang, normalized_lang)
    label = normalized_lang or "code"

    lines = code.split("\n")
    content_width = max([len(line) for line in lines] + [len(label), 4])
    top = f"{indent}╭─ {label} " + "─" * max(0, content_width - len(label) + 1) + "╮"
    bottom = f"{indent}╰" + "─" * (content_width + 4) + "╯"

    output = [top]
    for line in lines:
        highlighted = highlight_line(line, normalized_lang) if HAS_PYGMENTS else line
        padding = " " * max(0, content_width - len(line))
        output.append(f"{indent}│ {highlighted}{padding} │")
    output.append(bottom)
    return "\n".join(output)
