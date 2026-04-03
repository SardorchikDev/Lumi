"""Tool protocol, registry, and runtime primitives for Lumi."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from src.utils.permissions import PermissionDecision, PermissionRequest

ToolHandler = Callable[[dict[str, Any], "ToolContext"], str | Awaitable[str]]
PermissionResolver = Callable[[PermissionRequest], PermissionDecision | Awaitable[PermissionDecision]]
ToolEventSink = Callable[["ToolEvent"], None | Awaitable[None]]
TodoGetter = Callable[[], list[dict[str, str]]]
TodoSetter = Callable[[list[dict[str, str]]], None]
ShellOutputSink = Callable[[str], None]
StopChecker = Callable[[], bool]


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    async def run(self, input_data: dict[str, Any], context: ToolContext) -> str:
        ...


@dataclass(frozen=True)
class ToolEvent:
    name: str
    status: str
    input_data: dict[str, Any]
    summary: str = ""
    ok: bool = True
    duration_ms: int = 0
    result: str = ""


@dataclass
class ToolContext:
    base_dir: Path
    permission_resolver: PermissionResolver | None = None
    event_sink: ToolEventSink | None = None
    todo_getter: TodoGetter | None = None
    todo_setter: TodoSetter | None = None
    shell_output_sink: ShellOutputSink | None = None
    stop_checker: StopChecker | None = None
    allow_external_paths: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    async def resolve_permission(self, request: PermissionRequest) -> PermissionDecision | None:
        if self.permission_resolver is None:
            return None
        result = self.permission_resolver(request)
        if inspect.isawaitable(result):
            return await result
        return result

    async def emit(self, event: ToolEvent) -> None:
        if self.event_sink is None:
            return
        result = self.event_sink(event)
        if inspect.isawaitable(result):
            await result

    def get_todos(self) -> list[dict[str, str]]:
        if self.todo_getter is None:
            return []
        return list(self.todo_getter())

    def set_todos(self, todos: list[dict[str, str]]) -> None:
        if self.todo_setter is not None:
            self.todo_setter(list(todos))

    def emit_shell_output(self, chunk: str) -> None:
        if self.shell_output_sink is not None:
            self.shell_output_sink(chunk)

    def stop_requested(self) -> bool:
        return bool(self.stop_checker and self.stop_checker())


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    async def run(self, input_data: dict[str, Any], context: ToolContext) -> str:
        result = self.handler(input_data, context)
        if inspect.isawaitable(result):
            return str(await result)
        return str(result)

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> RegisteredTool:
        tool = RegisteredTool(name=name, description=description, input_schema=input_schema, handler=handler)
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> RegisteredTool:
        return self._tools[name]

    def all(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self.all()]

    def render_for_prompt(self) -> str:
        blocks: list[str] = []
        for tool in self.all():
            schema = json.dumps(tool.input_schema, indent=2, ensure_ascii=False)
            blocks.append(f"- {tool.name}: {tool.description}\n  schema: {schema}")
        return "\n".join(blocks)

    async def invoke(self, name: str, input_data: dict[str, Any], context: ToolContext) -> str:
        tool = self.get(name)
        started = time.perf_counter()
        await context.emit(ToolEvent(name=name, status="running", input_data=dict(input_data)))
        try:
            result = await tool.run(input_data, context)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            await context.emit(
                ToolEvent(
                    name=name,
                    status="failed",
                    input_data=dict(input_data),
                    ok=False,
                    duration_ms=duration_ms,
                    result=str(exc),
                )
            )
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        await context.emit(
            ToolEvent(
                name=name,
                status="done",
                input_data=dict(input_data),
                ok=True,
                duration_ms=duration_ms,
                result=result,
            )
        )
        return result


def run_async(coro: Awaitable[Any]) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    return asyncio.run(coro)


__all__ = [
    "PermissionDecision",
    "PermissionRequest",
    "RegisteredTool",
    "Tool",
    "ToolContext",
    "ToolEvent",
    "ToolRegistry",
    "run_async",
]
