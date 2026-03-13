"""Tests for src.agents.agent — autonomous task execution."""

from src.agents.agent import RISKY_KEYWORDS, is_risky, make_plan


class TestIsRisky:
    def test_explicitly_risky(self):
        step = {"risky": True, "description": "anything"}
        assert is_risky(step) is True

    def test_risky_command_keywords(self):
        assert is_risky({"command": "rm -rf /tmp/test"}) is True
        assert is_risky({"command": "sudo apt install foo"}) is True
        assert is_risky({"command": "git push origin main"}) is True
        assert is_risky({"command": "npm publish"}) is True

    def test_risky_description_keywords(self):
        assert is_risky({"description": "delete the old database"}) is True
        assert is_risky({"description": "overwrite config file"}) is True

    def test_safe_step(self):
        step = {"command": "echo hello", "description": "print greeting"}
        assert is_risky(step) is False

    def test_safe_file_write(self):
        step = {"type": "file_write", "path": "test.txt", "description": "create test file"}
        assert is_risky(step) is False

    def test_risky_keywords_list(self):
        """Verify RISKY_KEYWORDS contains expected dangerous operations."""
        assert "delete" in RISKY_KEYWORDS
        assert "sudo" in RISKY_KEYWORDS
        assert "rm " in RISKY_KEYWORDS
