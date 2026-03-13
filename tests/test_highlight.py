"""Tests for src.utils.highlight — syntax highlighting."""

from src.utils.highlight import highlight, render_code_block


class TestHighlight:
    def test_python_keywords(self):
        result = highlight("def hello():\n    return True", "python")
        assert "def" in result
        assert "return" in result
        assert "True" in result

    def test_javascript_keywords(self):
        result = highlight("const x = function() { return true; }", "javascript")
        assert "const" in result
        assert "function" in result
        assert "return" in result

    def test_bash_keywords(self):
        result = highlight("if [ -f file ]; then echo ok; fi", "bash")
        assert "if" in result
        assert "then" in result
        assert "echo" in result

    def test_json_highlighting(self):
        result = highlight('{"key": "value", "num": 42}', "json")
        assert "key" in result
        assert "value" in result

    def test_unknown_language_dimmed(self):
        result = highlight("some code here", "unknown")
        # Should still return the code, just dimmed
        assert "some code here" in result

    def test_python_strings(self):
        result = highlight('x = "hello world"', "python")
        assert "hello world" in result

    def test_python_comments(self):
        result = highlight("# this is a comment", "python")
        assert "this is a comment" in result

    def test_empty_code(self):
        result = highlight("", "python")
        assert result == ""

    def test_lang_case_insensitive(self):
        result1 = highlight("def f(): pass", "Python")
        result2 = highlight("def f(): pass", "PYTHON")
        result3 = highlight("def f(): pass", "python")
        # All should produce the same result
        assert result1 == result2 == result3

    def test_py_alias(self):
        result = highlight("import os", "py")
        assert "import" in result


class TestRenderCodeBlock:
    def test_has_border(self):
        result = render_code_block("print('hi')", "python")
        assert "╭" in result
        assert "╰" in result
        assert "│" in result

    def test_includes_lang_label(self):
        result = render_code_block("x = 1", "python")
        assert "python" in result

    def test_default_label(self):
        result = render_code_block("x = 1", "")
        assert "code" in result

    def test_code_content_present(self):
        result = render_code_block("console.log('test')", "js")
        assert "console" in result
        assert "test" in result
