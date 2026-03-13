"""Tests for src.utils.filesystem — file creation detection and plan execution."""

import os
import shutil
import tempfile

from src.utils.filesystem import (
    format_creation_summary,
    is_create_request,
    write_file_plan,
)


class TestIsCreateRequest:
    def test_create_folder(self):
        assert is_create_request("create a folder called myapp") is True

    def test_make_project(self):
        assert is_create_request("make a new project") is True

    def test_scaffold(self):
        assert is_create_request("scaffold a React app") is True

    def test_create_files(self):
        assert is_create_request("create index.html with some content") is True

    def test_set_up_project(self):
        assert is_create_request("set up a project structure") is True

    def test_not_create_request(self):
        assert is_create_request("explain how files work") is False
        assert is_create_request("what is a directory") is False
        assert is_create_request("hello world") is False


class TestWriteFilePlan:
    def setup_method(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="lumi_test_fs_")

    def teardown_method(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_creates_root_folder(self):
        plan = {
            "root": "myproject",
            "files": [{"path": "README.md", "content": "# Hello"}],
        }
        created = write_file_plan(plan, self._tmp_dir)
        assert any("myproject" in c for c in created)
        assert os.path.isdir(os.path.join(self._tmp_dir, "myproject"))

    def test_creates_files(self):
        plan = {
            "root": "testapp",
            "files": [
                {"path": "index.html", "content": "<html></html>"},
                {"path": "style.css", "content": "body {}"},
            ],
        }
        created = write_file_plan(plan, self._tmp_dir)
        assert len(created) == 3  # root dir + 2 files
        assert os.path.isfile(os.path.join(self._tmp_dir, "testapp", "index.html"))
        assert os.path.isfile(os.path.join(self._tmp_dir, "testapp", "style.css"))

    def test_file_content_written(self):
        plan = {
            "root": ".",
            "files": [{"path": "test.txt", "content": "hello world"}],
        }
        write_file_plan(plan, self._tmp_dir)
        with open(os.path.join(self._tmp_dir, "test.txt")) as f:
            assert f.read() == "hello world"

    def test_creates_nested_directories(self):
        plan = {
            "root": "app",
            "files": [{"path": "src/components/Button.tsx", "content": "export default {}"}],
        }
        write_file_plan(plan, self._tmp_dir)
        assert os.path.isfile(os.path.join(self._tmp_dir, "app", "src", "components", "Button.tsx"))

    def test_dot_root_no_subfolder(self):
        plan = {
            "root": ".",
            "files": [{"path": "main.py", "content": "print('hi')"}],
        }
        created = write_file_plan(plan, self._tmp_dir)
        # Should not create a "." folder entry
        assert not any(c.endswith("./") for c in created)

    def test_empty_files_list(self):
        plan = {"root": "empty", "files": []}
        created = write_file_plan(plan, self._tmp_dir)
        assert len(created) == 1  # just the root dir


class TestFormatCreationSummary:
    def test_basic_summary(self):
        plan = {
            "root": "myapp",
            "files": [
                {"path": "index.html", "content": "<html></html>"},
                {"path": "style.css", "content": "body { margin: 0; }"},
            ],
        }
        summary = format_creation_summary(plan, [])
        assert "myapp" in summary
        assert "index.html" in summary
        assert "style.css" in summary

    def test_dot_root_not_shown(self):
        plan = {"root": ".", "files": [{"path": "main.py", "content": "pass"}]}
        summary = format_creation_summary(plan, [])
        assert summary.count("./") == 0 or "." not in summary.split("\n")[0]

    def test_shows_byte_sizes(self):
        plan = {
            "root": "proj",
            "files": [{"path": "big.txt", "content": "x" * 1000}],
        }
        summary = format_creation_summary(plan, [])
        assert "1,000" in summary or "1000" in summary
