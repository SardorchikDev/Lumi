from __future__ import annotations

from src.utils import skills


def test_scan_skills_prefers_workspace_over_global(tmp_path, monkeypatch):
    global_home = tmp_path / "lumi-home"
    monkeypatch.setattr(skills, "LUMI_HOME", global_home)

    (global_home / "skills").mkdir(parents=True)
    (global_home / "skills" / "release.md").write_text(
        "---\nname: Global Release\ncommand: /release\ndescription: Global skill\n---\nGlobal body.\n",
        encoding="utf-8",
    )
    (tmp_path / ".lumi" / "skills").mkdir(parents=True)
    (tmp_path / ".lumi" / "skills" / "release.md").write_text(
        "---\nname: Workspace Release\ncommand: /release\ndescription: Workspace skill\n---\nWorkspace body.\n",
        encoding="utf-8",
    )

    found = skills.scan_skills(tmp_path)

    assert len(found) == 1
    assert found[0].command == "/release"
    assert found[0].scope == "workspace"
    assert found[0].description == "Workspace skill"


def test_skill_hits_and_detail_report_include_workspace_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "LUMI_HOME", tmp_path / "global-home")
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "ship.md").write_text(
        "---\nname: Ship Ready\ncommand: /shipready\nmode: coding\n---\nPrepare release notes and changelog.\n",
        encoding="utf-8",
    )

    hits = skills.skill_hits("/ship", base_dir=tmp_path)
    report = skills.render_skill_detail("/shipready", base_dir=tmp_path)

    assert hits == [("/shipready", "Prepare release notes and changelog.", "skills", "/shipready")]
    assert "Skill /shipready" in report
    assert "Mode:        coding" in report
    assert "Prepare release notes and changelog." in report


def test_build_skill_prompt_replaces_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "LUMI_HOME", tmp_path / "global-home")
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    path = skill_dir / "review.md"
    path.write_text(
        "---\nname: Focus Review\ncommand: /focus\n---\nReview {{args}} in {{workspace}} using {{command}}.\n",
        encoding="utf-8",
    )

    spec = skills.find_skill("/focus", base_dir=tmp_path)
    assert spec is not None

    prompt = skills.build_skill_prompt(spec, "src/app.py", workspace=tmp_path)

    assert "src/app.py" in prompt
    assert str(tmp_path) in prompt
    assert "/focus" in prompt
