"""Tests for src.utils.markdown — terminal markdown rendering."""

from src.utils.markdown import _inline, render


class TestInlineMarkdown:
    def test_inline_code(self):
        result = _inline("Use `print()` to debug")
        assert "print()" in result
        assert "`" not in result  # backticks should be consumed

    def test_bold(self):
        result = _inline("This is **bold** text")
        assert "bold" in result
        assert "**" not in result

    def test_bold_underscores(self):
        result = _inline("This is __bold__ text")
        assert "bold" in result
        assert "__" not in result

    def test_italic(self):
        result = _inline("This is *italic* text")
        assert "italic" in result

    def test_strikethrough(self):
        result = _inline("This is ~~deleted~~ text")
        assert "deleted" in result
        assert "~~" not in result

    def test_plain_text_unchanged(self):
        result = _inline("just plain text")
        assert "just plain text" in result


class TestRender:
    def test_heading_h1(self):
        result = render("# Title")
        assert "Title" in result

    def test_heading_h2(self):
        result = render("## Subtitle")
        assert "Subtitle" in result

    def test_heading_h3(self):
        result = render("### Section")
        assert "Section" in result

    def test_bullet_list(self):
        result = render("- item one\n- item two")
        assert "item one" in result
        assert "item two" in result

    def test_numbered_list(self):
        result = render("1. first\n2. second")
        assert "first" in result
        assert "second" in result

    def test_horizontal_rule(self):
        result = render("---")
        assert "─" in result

    def test_code_block(self):
        result = render("```python\nprint('hello')\n```")
        assert "print" in result
        assert "hello" in result

    def test_blank_lines_preserved(self):
        result = render("line one\n\nline two")
        lines = result.split("\n")
        assert len(lines) >= 3  # At least: line, blank, line

    def test_normal_paragraph(self):
        result = render("Just a normal paragraph of text.")
        assert "normal paragraph" in result

    def test_mixed_content(self):
        md = "# Title\n\nSome text with **bold**.\n\n- bullet\n\n```\ncode\n```"
        result = render(md)
        assert "Title" in result
        assert "bold" in result
        assert "bullet" in result
        assert "code" in result
