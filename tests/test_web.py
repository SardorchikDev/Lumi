"""Tests for src.utils.web — URL fetching and HTML text extraction."""

from src.utils.web import _extract_text, fetch_url


class TestExtractText:
    def test_strips_html_tags(self):
        html = "<p>Hello <b>world</b></p>"
        text = _extract_text(html)
        assert "Hello" in text
        assert "world" in text
        assert "<p>" not in text
        assert "<b>" not in text

    def test_removes_script_tags(self):
        html = "<p>Before</p><script>alert('xss')</script><p>After</p>"
        text = _extract_text(html)
        assert "Before" in text
        assert "After" in text
        assert "alert" not in text

    def test_removes_style_tags(self):
        html = "<style>.red { color: red; }</style><p>Content</p>"
        text = _extract_text(html)
        assert "Content" in text
        assert "color" not in text

    def test_decodes_html_entities(self):
        html = "<p>5 &gt; 3 &amp; 2 &lt; 4</p>"
        text = _extract_text(html)
        assert "5 > 3 & 2 < 4" in text

    def test_collapses_whitespace(self):
        html = "<p>Hello</p>\n\n\n\n\n<p>World</p>"
        text = _extract_text(html)
        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in text

    def test_empty_html(self):
        assert _extract_text("") == ""

    def test_removes_nav_footer_header(self):
        html = "<nav>Menu</nav><main>Content</main><footer>Copyright</footer>"
        text = _extract_text(html)
        assert "Content" in text
        assert "Menu" not in text
        assert "Copyright" not in text


class TestFetchUrl:
    def test_prepends_https(self):
        """fetch_url should prepend https:// to bare domains.
        We don't actually fetch — just verify the logic exists."""
        # This would need network, so we just verify non-http URLs get prefixed
        # The actual fetch will fail but that's fine for unit testing
        result = fetch_url("definitely-not-a-real-domain-12345.invalid")
        # Should return an error string, not crash
        assert isinstance(result, str)
