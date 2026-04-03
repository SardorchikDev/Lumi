from __future__ import annotations

import json

from src.utils import hooks


def test_run_hooks_uses_workspace_and_event_env(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "LUMI_HOME", tmp_path / "global-home")
    hook_file = tmp_path / ".lumi" / "hooks.json"
    hook_file.parent.mkdir(parents=True)
    hook_file.write_text(
        json.dumps(
            {
                "before_message": [
                    {"name": "echo-input", "command": "printf '%s|%s' \"$LUMI_HOOK_EVENT\" \"$LUMI_HOOK_INPUT\""}
                ]
            }
        ),
        encoding="utf-8",
    )

    results = hooks.run_hooks("before_message", base_dir=tmp_path, user_input="hello lumi")

    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].stdout == "before_message|hello lumi"


def test_required_hook_failure_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "LUMI_HOME", tmp_path / "global-home")
    (tmp_path / "hooks.json").write_text(
        json.dumps(
            {
                "before_command": [
                    {"name": "guard", "command": "exit 3", "required": True}
                ]
            }
        ),
        encoding="utf-8",
    )

    results = hooks.run_hooks("before_command", base_dir=tmp_path, command="/build")

    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].blocked is True
    assert results[0].returncode == 3


def test_render_hook_report_lists_events(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "LUMI_HOME", tmp_path / "global-home")
    (tmp_path / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "before_message": ["printf ready"],
                    "after_response": [{"name": "audit", "command": "printf done", "timeout": 5}],
                }
            }
        ),
        encoding="utf-8",
    )

    report = hooks.render_hook_report(base_dir=tmp_path, detail=True)

    assert "Hooks" in report
    assert "before_message: 1" in report
    assert "after_response: 1" in report
    assert "audit" in report
