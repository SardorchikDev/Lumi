"""Tests for src.utils.filesystem — file creation detection and plan execution."""

import os
import shutil
import tempfile
from pathlib import Path

from src.utils.filesystem import (
    delete_file_plan,
    execute_operation_plan,
    format_creation_summary,
    format_delete_summary,
    generate_delete_plan,
    generate_transfer_plan,
    inspect_operation_plan,
    is_copy_request,
    is_create_request,
    is_delete_request,
    is_move_request,
    is_rename_request,
    suggest_paths,
    undo_operation,
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


class TestIsDeleteRequest:
    def test_delete_folder(self):
        assert is_delete_request("delete the folder docs") is True

    def test_remove_file(self):
        assert is_delete_request("remove file notes.txt") is True

    def test_not_delete_request(self):
        assert is_delete_request("explain how to remove files in linux") is False


class TestTransferRequestDetection:
    def test_move_request(self):
        assert is_move_request("move file app.py into src") is True

    def test_copy_request(self):
        assert is_copy_request("copy README.md to docs") is True

    def test_rename_request(self):
        assert is_rename_request("rename app.py to main.py") is True


class TestGenerateDeletePlan:
    def test_delete_file_inside_folder(self):
        plan = generate_delete_plan("delete file README.md inside folder docs")
        assert plan == {
            "operation": "delete",
            "targets": [{"path": "docs/README.md", "kind": "file"}],
        }

    def test_delete_nested_folder_chain(self):
        plan = generate_delete_plan("remove folder app delete file Button.tsx inside that folder")
        assert plan == {
            "operation": "delete",
            "targets": [
                {"path": "app", "kind": "dir"},
                {"path": "app/Button.tsx", "kind": "file"},
            ],
        }


class TestGenerateTransferPlan:
    def test_move_into_folder(self):
        plan = generate_transfer_plan("move file app.py into src")
        assert plan == {
            "operation": "move",
            "items": [{"source": "app.py", "destination": "src", "link": "into"}],
        }

    def test_copy_to_path(self):
        plan = generate_transfer_plan("copy README.md to docs/README-copy.md")
        assert plan == {
            "operation": "copy",
            "items": [{"source": "README.md", "destination": "docs/README-copy.md", "link": "to"}],
        }

    def test_rename_file(self):
        plan = generate_transfer_plan("rename app.py to main.py")
        assert plan == {
            "operation": "rename",
            "items": [{"source": "app.py", "destination": "main.py", "link": "to"}],
        }


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


class TestDeleteFilePlan:
    def setup_method(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="lumi_test_fs_delete_")

    def teardown_method(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_deletes_file(self):
        path = os.path.join(self._tmp_dir, "notes.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("hello")
        deleted = delete_file_plan(
            {"operation": "delete", "targets": [{"path": "notes.txt", "kind": "file"}]},
            self._tmp_dir,
        )
        assert deleted == [str(Path(path).resolve())]
        assert not os.path.exists(path)

    def test_deletes_directory_recursively(self):
        os.makedirs(os.path.join(self._tmp_dir, "docs"), exist_ok=True)
        with open(os.path.join(self._tmp_dir, "docs", "README.md"), "w", encoding="utf-8") as handle:
            handle.write("# hello")
        deleted = delete_file_plan(
            {"operation": "delete", "targets": [{"path": "docs", "kind": "dir"}]},
            self._tmp_dir,
        )
        assert deleted == [str((Path(self._tmp_dir) / "docs").resolve()) + "/"]
        assert not os.path.exists(os.path.join(self._tmp_dir, "docs"))


class TestOperationInspectionAndUndo:
    def setup_method(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="lumi_test_fs_ops_")

    def teardown_method(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_create_inspection_detects_overwrite_and_preview(self):
        path = Path(self._tmp_dir) / "docs" / "README.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old line\n", encoding="utf-8")
        inspection = inspect_operation_plan(
            {
                "operation": "create",
                "root": ".",
                "files": [{"path": "docs/README.md", "content": "new line\n"}],
            },
            self._tmp_dir,
        )
        assert inspection["counts"]["overwrites"] == 1
        assert any("overwrite" in line for line in inspection["preview_lines"])

    def test_delete_inspection_counts_nested_content(self):
        docs = Path(self._tmp_dir) / "docs" / "nested"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "README.md").write_text("# hi\n", encoding="utf-8")
        inspection = inspect_operation_plan(
            {"operation": "delete", "targets": [{"path": "docs", "kind": "dir"}]},
            self._tmp_dir,
        )
        assert inspection["counts"]["delete_files"] == 1
        assert inspection["counts"]["delete_dirs"] == 1

    def test_execute_operation_plan_and_undo_create(self):
        result = execute_operation_plan(
            {
                "operation": "create",
                "root": ".",
                "files": [{"path": "notes.txt", "content": "hello\n"}],
            },
            self._tmp_dir,
        )
        assert Path(self._tmp_dir, "notes.txt").exists()
        undo_operation(result["undo"])
        assert not Path(self._tmp_dir, "notes.txt").exists()

    def test_execute_operation_plan_and_undo_delete(self):
        path = Path(self._tmp_dir) / "docs"
        path.mkdir(parents=True, exist_ok=True)
        (path / "README.md").write_text("# hi\n", encoding="utf-8")
        result = execute_operation_plan(
            {"operation": "delete", "targets": [{"path": "docs", "kind": "dir"}]},
            self._tmp_dir,
        )
        assert not path.exists()
        undo_operation(result["undo"])
        assert (path / "README.md").exists()

    def test_execute_operation_plan_rename(self):
        src = Path(self._tmp_dir) / "app.py"
        src.write_text("print('hi')\n", encoding="utf-8")
        result = execute_operation_plan(
            {"operation": "rename", "items": [{"source": "app.py", "destination": "main.py", "link": "to"}]},
            self._tmp_dir,
        )
        assert result["summary"].startswith("Renamed")
        assert not src.exists()
        assert Path(self._tmp_dir, "main.py").exists()


class TestPathSuggestions:
    def setup_method(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="lumi_test_fs_suggest_")

    def teardown_method(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_suggest_paths_for_delete_request(self):
        (Path(self._tmp_dir) / "src").mkdir(parents=True, exist_ok=True)
        (Path(self._tmp_dir) / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        suggestion = suggest_paths("delete src/a", self._tmp_dir)
        assert suggestion is not None
        assert "src/app.py" in suggestion["items"]


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


class TestFormatDeleteSummary:
    def test_basic_summary(self):
        summary = format_delete_summary(
            {
                "operation": "delete",
                "targets": [
                    {"path": "docs", "kind": "dir"},
                    {"path": "docs/README.md", "kind": "file"},
                ],
            }
        )
        assert "docs/" in summary
        assert "docs/README.md" in summary
