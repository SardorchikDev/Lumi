from __future__ import annotations

from src.utils import repo_profile, runtime_config


def test_runtime_config_adds_and_removes_context_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    extra = tmp_path / "shared"
    extra.mkdir()

    config, added = runtime_config.add_context_directory("shared", base_dir=tmp_path)

    assert added == extra.resolve()
    assert config.extra_dirs == (str(extra.resolve()),)
    assert runtime_config.iter_context_roots(tmp_path) == (tmp_path.resolve(), extra.resolve())

    config, removed = runtime_config.remove_context_directory("shared", base_dir=tmp_path)

    assert removed == extra.resolve()
    assert config.extra_dirs == ()


def test_inspect_workspace_surfaces_extra_context_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    extra = tmp_path / "shared"
    extra.mkdir()
    (extra / "helper.ts").write_text("export const helper = () => 1\n", encoding="utf-8")
    runtime_config.add_context_directory("shared", base_dir=tmp_path)

    profile = repo_profile.inspect_workspace(tmp_path)
    overview = repo_profile.render_workspace_overview(profile)

    assert str(extra.resolve()) in profile.context_directories
    assert "typescript" in profile.languages
    assert "Context:" in overview


def test_render_runtime_config_report_includes_flags_and_context_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    extra = tmp_path / "shared"
    extra.mkdir()
    runtime_config.update_runtime_config(
        tmp_path,
        extra_dirs=(str(extra.resolve()),),
        brief_mode=True,
        fast_mode=True,
        compact_mode=True,
        multiline=True,
        reasoning_effort="high",
    )

    report = runtime_config.render_runtime_config_report(base_dir=tmp_path, provider="gemini", model="gemini-2.5-flash")

    assert "Lumi config" in report
    assert str(extra.resolve()) in report
    assert "Brief:     on" in report
    assert "Fast:      on" in report
    assert "Live:      on" in report


def test_parse_runtime_config_update_accepts_live_lookup_aliases():
    assert runtime_config.parse_runtime_config_update("live_lookup", "off") == {"live_lookup": False}
    assert runtime_config.parse_runtime_config_update("search", "on") == {"live_lookup": True}
