"""Tests for src.utils.export — conversation export to markdown."""

import pathlib
import shutil
from unittest.mock import patch

from src.utils.export import export_md


class TestExportMd:
    def setup_method(self):
        self._tmp_dir = pathlib.Path("/tmp/lumi_test_exports")
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._patcher = patch(
            "src.utils.export.export_md",
            wraps=export_md,
        )
        # We patch the exports_dir inside the function
        self._dir_patcher = patch(
            "src.utils.export.pathlib.Path",
        )

    def teardown_method(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_export_creates_file(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        path = export_md(history)
        assert path.exists()
        assert path.suffix == ".md"

    def test_export_content(self):
        history = [
            {"role": "user", "content": "what is python"},
            {"role": "assistant", "content": "Python is a programming language"},
        ]
        path = export_md(history)
        content = path.read_text()
        assert "what is python" in content
        assert "Python is a programming language" in content
        assert "**You**" in content

    def test_export_custom_name(self):
        history = [{"role": "user", "content": "test"}]
        path = export_md(history, name="CustomBot")
        content = path.read_text()
        assert "CustomBot" in content

    def test_export_empty_history(self):
        path = export_md([])
        assert path.exists()
        content = path.read_text()
        assert "Conversation" in content

    def test_export_default_name_is_lumi(self):
        history = [{"role": "assistant", "content": "hello"}]
        path = export_md(history)
        content = path.read_text()
        assert "Lumi" in content
