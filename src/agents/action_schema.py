"""Deterministic schemas for Lumi agent planning steps."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

AgentAction = Literal[
    "list_dir",
    "read_file",
    "inspect_repo",
    "run_tests",
    "run_ruff",
    "run_mypy",
    "run_verify",
    "git_status",
    "git_diff",
    "inspect_changed_files",
    "mkdir",
    "rename_path",
    "write_json",
    "write_yaml",
    "search_code",
    "search_symbols",
    "patch_file",
    "patch_lines",
    "patch_context",
    "patch_apply",
]

SAFE_ACTIONS: tuple[str, ...] = (
    "list_dir",
    "read_file",
    "inspect_repo",
    "run_tests",
    "run_ruff",
    "run_mypy",
    "run_verify",
    "git_status",
    "git_diff",
    "inspect_changed_files",
    "mkdir",
    "rename_path",
    "write_json",
    "write_yaml",
    "search_code",
    "search_symbols",
    "patch_file",
    "patch_lines",
    "patch_context",
    "patch_apply",
)

VERIFY_KINDS = {"tests", "lint", "types", "all"}


class StepBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    description: str = ""
    risky: bool | None = None

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> str:
        return str(value or "").strip()


class ActionStep(StepBase):
    type: Literal["action"]
    action: AgentAction

    target: str | None = None
    path: str | None = None
    destination: str | None = None
    content: str | None = None
    prompt: str | None = None
    question: str | None = None

    query: str | None = None
    symbol: str | None = None
    symbol_kind: str | None = None
    verify_kind: str | None = None

    json_content: Any = None
    yaml_content: Any = None

    old_text: str | None = None
    new_text: str | None = None
    replace_all: bool = False

    start_line: int | None = None
    end_line: int | None = None
    old_block: str | None = None
    replacement: str | None = None

    before_context: str | None = None
    after_context: str | None = None
    hunks: list[dict[str, Any]] | None = None

    @field_validator(
        "target",
        "path",
        "destination",
        "prompt",
        "question",
        "query",
        "symbol",
        "symbol_kind",
        "verify_kind",
        mode="before",
    )
    @classmethod
    def _normalize_optional_str(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator(
        "content",
        "old_text",
        "new_text",
        "old_block",
        "replacement",
        "before_context",
        "after_context",
        mode="before",
    )
    @classmethod
    def _normalize_text_payload(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @model_validator(mode="after")
    def _validate_action_requirements(self):
        if self.action == "mkdir":
            self.target = (self.target or self.path or "").strip()
            if not self.target:
                raise ValueError("mkdir is missing a target")

        if self.action == "rename_path":
            self.target = (self.target or self.path or "").strip()
            if not self.target or not (self.destination or "").strip():
                raise ValueError("rename_path requires target and destination")

        if self.action == "write_json":
            if not (self.path or "").strip():
                raise ValueError("write_json is missing a file path")
            if self.json_content is None:
                raise ValueError("write_json is missing json_content")

        if self.action == "write_yaml":
            if not (self.path or "").strip():
                raise ValueError("write_yaml is missing a file path")
            if self.yaml_content is None:
                raise ValueError("write_yaml is missing yaml_content")

        if self.action == "search_code" and not (self.query or "").strip():
            raise ValueError("search_code is missing a query")

        if self.action == "search_symbols" and not (self.symbol or "").strip():
            raise ValueError("search_symbols is missing a symbol")

        if self.action == "run_verify" and (self.verify_kind or "").strip() not in VERIFY_KINDS:
            raise ValueError("run_verify requires verify_kind")

        if self.action == "patch_file":
            if not (self.path or "").strip():
                raise ValueError("patch_file is missing a file path")
            if self.old_text is None:
                raise ValueError("patch_file is missing old_text")
            if self.new_text is None:
                raise ValueError("patch_file is missing new_text")

        if self.action == "patch_lines":
            if not (self.path or "").strip():
                raise ValueError("patch_lines is missing a file path")
            if self.start_line is None or self.end_line is None:
                raise ValueError("patch_lines is missing line bounds")
            if self.replacement is None:
                raise ValueError("patch_lines is missing replacement")

        if self.action == "patch_context":
            if not (self.path or "").strip():
                raise ValueError("patch_context is missing a file path")
            if not (self.before_context or "").strip() and not (self.after_context or "").strip():
                raise ValueError("patch_context needs before_context or after_context")
            if self.replacement is None:
                raise ValueError("patch_context is missing replacement")

        if self.action == "patch_apply":
            if not (self.path or "").strip():
                raise ValueError("patch_apply is missing a file path")
            if not isinstance(self.hunks, list) or not self.hunks:
                raise ValueError("patch_apply requires hunks")

        return self


class FileWriteStep(StepBase):
    type: Literal["file_write"]
    path: str
    content: str = ""

    @field_validator("path", mode="before")
    @classmethod
    def _normalize_path(cls, value: Any) -> str:
        path = str(value or "").strip()
        if not path:
            raise ValueError("is missing a file path")
        return path

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value: Any) -> str:
        return str(value or "")


class AITaskStep(StepBase):
    type: Literal["ai_task"]
    prompt: str

    @field_validator("prompt", mode="before")
    @classmethod
    def _normalize_prompt(cls, value: Any) -> str:
        prompt = str(value or "").strip()
        if not prompt:
            raise ValueError("ai_task is missing a prompt")
        return prompt


class AskUserStep(StepBase):
    type: Literal["ask_user"]
    question: str

    @field_validator("question", mode="before")
    @classmethod
    def _normalize_question(cls, value: Any) -> str:
        question = str(value or "").strip()
        if not question:
            raise ValueError("ask_user is missing a question")
        return question


def validate_step_schema(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    """Validate and normalize a single step into a deterministic dict payload."""
    stype = str(step.get("type", "")).strip()
    if stype == "action":
        model = ActionStep
    elif stype == "file_write":
        model = FileWriteStep
    elif stype == "ai_task":
        model = AITaskStep
    elif stype == "ask_user":
        model = AskUserStep
    else:
        raise ValueError(f"Step {index} has unsupported type '{stype}'")

    try:
        parsed = model.model_validate(step)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {"msg": str(exc)}
        message = str(first_error.get("msg", str(exc)))
        if "Value error," in message:
            message = message.split("Value error,", 1)[1].strip()
        raise ValueError(f"Step {index} {message}") from exc

    normalized = parsed.model_dump(mode="python", exclude_none=True)
    normalized["id"] = index
    normalized["description"] = normalized.get("description") or f"Step {index}"
    return normalized
