"""Agentic tool loop and built-in Claude-style tools for Lumi."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from difflib import unified_diff
from pathlib import Path
from typing import Any

from src.agents.edit_engine import build_file_write_preview
from src.chat.optimizer import estimate_message_tokens, estimate_tokens
from src.tools.base import ToolContext, ToolRegistry, run_async
from src.tools.search import search as run_web_search
from src.utils.live_lookup import lookup_time, lookup_weather
from src.utils.permissions import PermissionError, PermissionRequest, PermissionRequired

XML_TOOL_CALL_RE = re.compile(r"<tool_call\s+name=\"(?P<name>[a-zA-Z0-9_:-]+)\">\s*(?P<body>.*?)\s*</tool_call>", re.DOTALL)
OUTPUT_CAP_BYTES = 50 * 1024
MAX_TOOL_ROUNDS = 15


@dataclass(frozen=True)
class ToolCallLog:
    name: str
    input_data: dict[str, Any]
    ok: bool
    result: str
    duration_ms: int


@dataclass(frozen=True)
class ToolLoopResult:
    text: str
    rounds: int
    input_tokens: int
    output_tokens: int
    tool_calls: tuple[ToolCallLog, ...] = ()


@dataclass
class AgenticRuntime:
    registry: ToolRegistry
    context: ToolContext
    provider: str
    model: str
    max_rounds: int = MAX_TOOL_ROUNDS
    recent_results: list[str] = field(default_factory=list)

    def _permission_request(self, tool_name: str, input_data: dict[str, Any]) -> PermissionRequest:
        value = _permission_value(tool_name, input_data)
        display = _display_permission_value(tool_name, input_data)
        return PermissionRequest(tool_name=tool_name, value=value, display=display)

    async def _check_permission(self, tool_name: str, input_data: dict[str, Any]) -> None:
        request = self._permission_request(tool_name, input_data)
        decision = await self.context.resolve_permission(request)
        if decision is None:
            return
        if decision.allowed:
            return
        if decision.reason == "requires approval":
            raise PermissionRequired(request, decision.reason)
        raise PermissionError(decision.reason)

    async def _run_tool(self, tool_name: str, input_data: dict[str, Any]) -> tuple[str, int]:
        if self.context.stop_requested():
            raise RuntimeError("Stopped by user.")
        await self._check_permission(tool_name, input_data)
        started = time.perf_counter()
        result = await self.registry.invoke(tool_name, input_data, self.context)
        duration_ms = int((time.perf_counter() - started) * 1000)
        preview = _trim_result(result)
        self.recent_results.append(f"{tool_name}: {preview}")
        self.recent_results = self.recent_results[-5:]
        return result, duration_ms

    async def run(self, client: Any, messages: list[dict[str, Any]], *, effort_options: dict[str, Any] | None = None) -> ToolLoopResult:
        history = [dict(message) for message in messages]
        tool_logs: list[ToolCallLog] = []
        used_native = self.provider in {"claude", "gemini"}
        for round_index in range(1, self.max_rounds + 1):
            if self.context.stop_requested():
                return ToolLoopResult(
                    text="Stopped by user.",
                    rounds=max(1, round_index - 1),
                    input_tokens=estimate_message_tokens(history),
                    output_tokens=estimate_tokens("Stopped by user."),
                    tool_calls=tuple(tool_logs),
                )
            if used_native:
                response = await asyncio.to_thread(
                    _call_model_native,
                    client,
                    self.model,
                    history,
                    self.registry.openai_schemas(),
                    effort_options or {},
                )
                assistant_text, tool_calls, output_tokens = _parse_native_response(response)
            else:
                prompt_messages = _inject_xml_tool_prompt(history, self.registry)
                response = await asyncio.to_thread(
                    _call_model_xml,
                    client,
                    self.model,
                    prompt_messages,
                    effort_options or {},
                )
                assistant_text, tool_calls, output_tokens = _parse_xml_response(response)

            if not tool_calls:
                return ToolLoopResult(
                    text=(assistant_text or "").strip(),
                    rounds=round_index,
                    input_tokens=estimate_message_tokens(history),
                    output_tokens=output_tokens,
                    tool_calls=tuple(tool_logs),
                )

            if used_native:
                history.append(_assistant_tool_message(assistant_text, tool_calls))
            else:
                history.append({"role": "assistant", "content": assistant_text})

            for call in tool_calls:
                try:
                    result, duration_ms = await self._run_tool(call["name"], call["arguments"])
                    tool_logs.append(ToolCallLog(call["name"], call["arguments"], True, result, duration_ms))
                    if used_native:
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "name": call["name"],
                                "content": result,
                            }
                        )
                    else:
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    f"<tool_result name=\"{call['name']}\">\n{result}\n</tool_result>"
                                ),
                            }
                        )
                except PermissionRequired as exc:
                    tool_logs.append(ToolCallLog(call["name"], call["arguments"], False, exc.reason, 0))
                    history.append({"role": "user", "content": f"Tool {call['name']} requires approval: {exc.request.display}"})
                except Exception as exc:
                    tool_logs.append(ToolCallLog(call["name"], call["arguments"], False, str(exc), 0))
                    if used_native:
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "name": call["name"],
                                "content": f"ERROR: {exc}",
                            }
                        )
                    else:
                        history.append({"role": "user", "content": f"<tool_result name=\"{call['name']}\">ERROR: {exc}</tool_result>"})

        return ToolLoopResult(
            text="Tool loop stopped after the maximum number of rounds.",
            rounds=self.max_rounds,
            input_tokens=estimate_message_tokens(history),
            output_tokens=estimate_tokens("Tool loop stopped after the maximum number of rounds."),
            tool_calls=tuple(tool_logs),
        )


def _call_model_native(client: Any, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], options: dict[str, Any]) -> Any:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
    }
    payload.update(options)
    try:
        return client.chat.completions.create(**payload)
    except TypeError:
        payload.pop("tool_choice", None)
        return client.chat.completions.create(**payload)



def _call_model_xml(client: Any, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> Any:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    payload.update(options)
    return client.chat.completions.create(**payload)



def _assistant_tool_message(text: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    serializable_calls = []
    for call in tool_calls:
        serializable_calls.append(
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            }
        )
    return {
        "role": "assistant",
        "content": text or "",
        "tool_calls": serializable_calls,
    }



def _parse_native_response(response: Any) -> tuple[str, list[dict[str, Any]], int]:
    choice = response.choices[0].message
    content = getattr(choice, "content", "") or ""
    tool_calls = getattr(choice, "tool_calls", None) or []
    parsed: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls, start=1):
        function = getattr(call, "function", None)
        name = getattr(function, "name", "") if function is not None else ""
        arguments_text = getattr(function, "arguments", "{}") if function is not None else "{}"
        try:
            arguments = json.loads(arguments_text or "{}")
        except json.JSONDecodeError:
            arguments = {}
        parsed.append({
            "id": getattr(call, "id", f"call_{index}"),
            "name": str(name),
            "arguments": arguments if isinstance(arguments, dict) else {},
        })
    usage = getattr(response, "usage", None)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return str(content), parsed, output_tokens



def _inject_xml_tool_prompt(messages: list[dict[str, Any]], registry: ToolRegistry) -> list[dict[str, Any]]:
    tool_block = (
        "You may call tools by returning XML blocks in this exact format:\n"
        "<tool_call name=\"tool_name\">{\"json\": \"object\"}</tool_call>\n"
        "Return only the tool call block when you want to use a tool.\n"
        "Available tools:\n"
        f"{registry.render_for_prompt()}"
    )
    injected = [dict(message) for message in messages]
    for message in injected:
        if str(message.get("role")) == "system":
            message["content"] = f"{message.get('content', '')}\n\n{tool_block}".strip()
            return injected
    return [{"role": "system", "content": tool_block}, *injected]



def _parse_xml_response(response: Any) -> tuple[str, list[dict[str, Any]], int]:
    content = str(response.choices[0].message.content or "")
    usage = getattr(response, "usage", None)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or estimate_tokens(content))
    tool_calls: list[dict[str, Any]] = []
    for index, match in enumerate(XML_TOOL_CALL_RE.finditer(content), start=1):
        name = match.group("name").strip()
        body = match.group("body").strip()
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError:
            parsed = {}
        tool_calls.append({"id": f"xml_call_{index}", "name": name, "arguments": parsed if isinstance(parsed, dict) else {}})
    cleaned = XML_TOOL_CALL_RE.sub("", content).strip()
    return cleaned, tool_calls, output_tokens



def _permission_value(tool_name: str, input_data: dict[str, Any]) -> str:
    if tool_name in {"read_file", "write_file", "edit_file", "multi_edit", "list_dir", "git_diff"}:
        return str(input_data.get("path") or input_data.get("pattern") or "*")
    if tool_name in {"web_search", "weather_lookup", "time_lookup"}:
        return str(input_data.get("query") or input_data.get("location") or "*")
    if tool_name == "run_shell":
        return str(input_data.get("command") or "")
    if tool_name == "git_commit":
        return str(input_data.get("message") or "*") or "*"
    return "*"



def _display_permission_value(tool_name: str, input_data: dict[str, Any]) -> str:
    if tool_name == "web_search":
        return str(input_data.get("query") or "web search")
    if tool_name in {"weather_lookup", "time_lookup"}:
        return str(input_data.get("location") or tool_name)
    if tool_name == "run_shell":
        return f"$ {str(input_data.get('command') or '')}".strip()
    if tool_name == "git_commit":
        return str(input_data.get("message") or "git commit")
    return str(input_data.get("path") or input_data.get("pattern") or tool_name)



def _ensure_within_workspace(path: Path, base_dir: Path, *, allow_external: bool = False) -> Path:
    resolved = path.expanduser().resolve()
    if allow_external:
        return resolved
    if not resolved.is_relative_to(base_dir):
        raise PermissionError(f"Path escapes workspace: {resolved}")
    return resolved



def _format_line_range(content: str, start_line: int | None = None, end_line: int | None = None) -> str:
    lines = content.splitlines()
    start = max(1, int(start_line or 1))
    end = min(len(lines), int(end_line or len(lines)))
    if end < start:
        raise ValueError("end_line must be greater than or equal to start_line")
    selected = lines[start - 1 : end]
    return "\n".join(f"{index + start:>4} | {line}" for index, line in enumerate(selected))


async def _tool_read_file(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or "").strip()
    if not raw_path:
        raise ValueError("read_file requires path")
    path = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    return _format_line_range(content, input_data.get("start_line"), input_data.get("end_line"))


async def _tool_write_file(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or "").strip()
    if not raw_path:
        raise ValueError("write_file requires path")
    content = str(input_data.get("content") or "")
    path = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    preview = build_file_write_preview(path, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, content, encoding="utf-8")
    return f"Wrote {path.relative_to(context.base_dir)}\n{preview}".strip()


async def _tool_edit_file(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or "").strip()
    old_str = str(input_data.get("old_str") or "")
    new_str = str(input_data.get("new_str") or "")
    if not raw_path or not old_str:
        raise ValueError("edit_file requires path and old_str")
    path = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    current = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    matches = current.count(old_str)
    if matches == 0:
        raise ValueError("old_str not found")
    if matches > 1:
        raise ValueError("old_str matched more than once")
    updated = current.replace(old_str, new_str, 1)
    diff = "\n".join(unified_diff(current.splitlines(), updated.splitlines(), fromfile=str(path), tofile=str(path), lineterm=""))
    await asyncio.to_thread(path.write_text, updated, encoding="utf-8")
    return f"Edited {path.relative_to(context.base_dir)}\n{diff}".strip()


async def _tool_multi_edit(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or "").strip()
    edits = input_data.get("edits")
    if not raw_path or not isinstance(edits, list) or not edits:
        raise ValueError("multi_edit requires path and edits")
    path = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    current = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    updated = current
    for item in edits:
        if not isinstance(item, dict):
            raise ValueError("each edit must be an object")
        old_str = str(item.get("old_str") or "")
        new_str = str(item.get("new_str") or "")
        matches = updated.count(old_str)
        if matches == 0:
            raise ValueError(f"multi_edit failed: old_str not found: {old_str[:48]}")
        if matches > 1:
            raise ValueError(f"multi_edit failed: old_str matched more than once: {old_str[:48]}")
        updated = updated.replace(old_str, new_str, 1)
    diff = "\n".join(unified_diff(current.splitlines(), updated.splitlines(), fromfile=str(path), tofile=str(path), lineterm=""))
    await asyncio.to_thread(path.write_text, updated, encoding="utf-8")
    return f"Edited {path.relative_to(context.base_dir)} atomically\n{diff}".strip()


async def _tool_run_shell(input_data: dict[str, Any], context: ToolContext) -> str:
    command = str(input_data.get("command") or "").strip()
    timeout = int(input_data.get("timeout") or 30)
    if not command:
        raise ValueError("run_shell requires command")
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        command,
        cwd=str(context.base_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output_parts: list[bytes] = []
    total = 0
    deadline = time.monotonic() + max(1, timeout)
    while True:
        if proc.stdout is None:
            break
        if context.stop_requested():
            proc.kill()
            await proc.wait()
            raise RuntimeError("Stopped by user.")
        if time.monotonic() > deadline:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout}s")
        chunk = await proc.stdout.readline()
        if not chunk:
            break
        output_parts.append(chunk)
        total += len(chunk)
        text = chunk.decode("utf-8", errors="replace")
        context.emit_shell_output(text.rstrip("\n"))
        if total >= OUTPUT_CAP_BYTES:
            output_parts.append(b"\n... output truncated ...\n")
            proc.kill()
            break
    await proc.wait()
    output = b"".join(output_parts).decode("utf-8", errors="replace").strip()
    return f"$ {command}\nexit {proc.returncode}\n{output}".strip()


async def _tool_list_dir(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or ".").strip() or "."
    target = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    if not target.exists():
        raise FileNotFoundError(raw_path)
    if target.is_file():
        stat = await asyncio.to_thread(target.stat)
        return f"file {target.name}  {stat.st_size}B  {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}"
    files: list[Path] = []
    git_dir = context.base_dir / ".git"
    if git_dir.exists() and shutil.which("git"):
        rel_target = "." if target == context.base_dir else str(target.relative_to(context.base_dir))
        proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", rel_target],
            capture_output=True,
            text=True,
            cwd=context.base_dir,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                candidate = context.base_dir / line.strip()
                if candidate.exists():
                    files.append(candidate)
    if not files:
        files = [path for path in target.rglob("*") if path.is_file()][:400]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    lines = [f"Listing for {target.relative_to(context.base_dir) if target != context.base_dir else '.'}"]
    for path in files[:200]:
        stat = await asyncio.to_thread(path.stat)
        lines.append(
            f"{path.relative_to(context.base_dir)}\t{stat.st_size}B\t{datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"
        )
    return "\n".join(lines)


async def _tool_glob_search(input_data: dict[str, Any], context: ToolContext) -> str:
    pattern = str(input_data.get("pattern") or "").strip()
    if not pattern:
        raise ValueError("glob_search requires pattern")
    matches = list(context.base_dir.glob(pattern)) if not pattern.startswith("**") else list(context.base_dir.glob(pattern))
    matches = [match for match in matches if match.exists()]
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return "\n".join(str(match.relative_to(context.base_dir)) for match in matches[:200]) or "(no matches)"


async def _tool_grep_search(input_data: dict[str, Any], context: ToolContext) -> str:
    pattern = str(input_data.get("pattern") or "").strip()
    raw_path = str(input_data.get("path") or ".").strip() or "."
    case_sensitive = bool(input_data.get("case_sensitive", False))
    if not pattern:
        raise ValueError("grep_search requires pattern")
    target = _ensure_within_workspace(Path(raw_path) if Path(raw_path).is_absolute() else context.base_dir / raw_path, context.base_dir, allow_external=context.allow_external_paths)
    lines: list[str] = []
    if shutil.which("rg"):
        cmd = ["rg", "-n", "--max-count", "200"]
        if not case_sensitive:
            cmd.append("-i")
        cmd.extend([pattern, str(target)])
        proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, cwd=context.base_dir, check=False)
        output = (proc.stdout or proc.stderr).strip()
        return output or "(no matches)"
    flags = 0 if case_sensitive else re.IGNORECASE
    regex = re.compile(pattern, flags)
    files = [target] if target.is_file() else [path for path in target.rglob("*") if path.is_file()]
    for file_path in files:
        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                lines.append(f"{file_path.relative_to(context.base_dir)}:{lineno}:{line}")
                if len(lines) >= 200:
                    return "\n".join(lines)
    return "\n".join(lines) or "(no matches)"


async def _tool_git_status(input_data: dict[str, Any], context: ToolContext) -> str:
    proc = await asyncio.to_thread(subprocess.run, ["git", "status", "--short", "--branch"], capture_output=True, text=True, cwd=context.base_dir, check=False)
    last = await asyncio.to_thread(subprocess.run, ["git", "log", "-1", "--oneline"], capture_output=True, text=True, cwd=context.base_dir, check=False)
    branch = (proc.stdout or proc.stderr).strip()
    commit = (last.stdout or last.stderr).strip()
    return f"{branch}\n\nlast commit\n{commit}".strip()


async def _tool_git_diff(input_data: dict[str, Any], context: ToolContext) -> str:
    raw_path = str(input_data.get("path") or "").strip()
    cmd = ["git", "diff", "--", raw_path] if raw_path else ["git", "diff"]
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, cwd=context.base_dir, check=False)
    return (proc.stdout or proc.stderr).strip() or "(no diff)"


async def _tool_git_commit(input_data: dict[str, Any], context: ToolContext) -> str:
    message = str(input_data.get("message") or "").strip()
    if not message:
        raise ValueError("git_commit requires message")
    add_proc = await asyncio.to_thread(subprocess.run, ["git", "add", "-A"], capture_output=True, text=True, cwd=context.base_dir, check=False)
    if add_proc.returncode != 0:
        raise RuntimeError((add_proc.stdout or add_proc.stderr).strip() or "git add failed")
    commit_proc = await asyncio.to_thread(subprocess.run, ["git", "commit", "-m", message], capture_output=True, text=True, cwd=context.base_dir, check=False)
    if commit_proc.returncode != 0:
        raise RuntimeError((commit_proc.stdout or commit_proc.stderr).strip() or "git commit failed")
    return (commit_proc.stdout or commit_proc.stderr).strip()


async def _tool_todo_write(input_data: dict[str, Any], context: ToolContext) -> str:
    todos = input_data.get("todos")
    if not isinstance(todos, list):
        raise ValueError("todo_write requires todos")
    normalized: list[dict[str, str]] = []
    for item in todos:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        status = str(item.get("status") or "pending").strip().lower()
        priority = str(item.get("priority") or "medium").strip().lower()
        if not task:
            continue
        normalized.append({"task": task[:180], "status": status, "priority": priority})
    context.set_todos(normalized)
    return "\n".join(f"- [{item['status']}] {item['task']} ({item['priority']})" for item in normalized) or "(no todos)"


async def _tool_todo_read(input_data: dict[str, Any], context: ToolContext) -> str:
    todos = context.get_todos()
    return "\n".join(f"- [{item.get('status', 'pending')}] {item.get('task', '')} ({item.get('priority', 'medium')})" for item in todos) or "(no todos)"


async def _tool_web_search(input_data: dict[str, Any], context: ToolContext) -> str:
    _ = context
    query = str(input_data.get("query") or "").strip()
    if not query:
        raise ValueError("web_search requires query")
    fetch_top = bool(input_data.get("fetch_top", True))
    return await asyncio.to_thread(run_web_search, query, fetch_top)


async def _tool_weather_lookup(input_data: dict[str, Any], context: ToolContext) -> str:
    _ = context
    location = str(input_data.get("location") or "").strip()
    detailed = bool(input_data.get("detailed", True))
    return await asyncio.to_thread(lookup_weather, location, detailed=detailed)


async def _tool_time_lookup(input_data: dict[str, Any], context: ToolContext) -> str:
    _ = context
    location = str(input_data.get("location") or "").strip()
    return await asyncio.to_thread(lookup_time, location)



def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "web_search",
        "Search the web for current information and fetch the top result.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "fetch_top": {"type": "boolean"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        _tool_web_search,
    )
    registry.register(
        "weather_lookup",
        "Get current weather for a location.",
        {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "detailed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        _tool_weather_lookup,
    )
    registry.register(
        "time_lookup",
        "Get the current local time for a city, country, or timezone.",
        {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
            },
            "additionalProperties": False,
        },
        _tool_time_lookup,
    )
    registry.register(
        "read_file",
        "Read a file with optional line range.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        _tool_read_file,
    )
    registry.register(
        "write_file",
        "Write or overwrite a file.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        _tool_write_file,
    )
    registry.register(
        "edit_file",
        "Replace one exact string in a file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
            "additionalProperties": False,
        },
        _tool_edit_file,
    )
    registry.register(
        "multi_edit",
        "Apply multiple exact string replacements to one file atomically.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_str": {"type": "string"},
                            "new_str": {"type": "string"},
                        },
                        "required": ["old_str", "new_str"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["path", "edits"],
            "additionalProperties": False,
        },
        _tool_multi_edit,
    )
    registry.register(
        "run_shell",
        "Run a shell command in the workspace.",
        {
            "type": "object",
            "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        _tool_run_shell,
    )
    registry.register(
        "list_dir",
        "List files recursively with size and mtime.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        _tool_list_dir,
    )
    registry.register(
        "glob_search",
        "Search for paths matching a glob pattern.",
        {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
            "additionalProperties": False,
        },
        _tool_glob_search,
    )
    registry.register(
        "grep_search",
        "Search file contents for a regex or literal pattern.",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        _tool_grep_search,
    )
    registry.register(
        "git_status",
        "Show git branch, changed files, and last commit.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        _tool_git_status,
    )
    registry.register(
        "git_diff",
        "Show git diff, optionally for a single path.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
        _tool_git_diff,
    )
    registry.register(
        "git_commit",
        "Stage all changes and create a git commit.",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        _tool_git_commit,
    )
    registry.register(
        "todo_write",
        "Write the current agent task list.",
        {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "status": {"type": "string"},
                            "priority": {"type": "string"},
                        },
                        "required": ["task", "status", "priority"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["todos"],
            "additionalProperties": False,
        },
        _tool_todo_write,
    )
    registry.register(
        "todo_read",
        "Read the current agent task list.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        _tool_todo_read,
    )
    return registry



def build_agentic_system_hint(*, live_lookup: bool = True) -> str:
    lines = [
        "Behavior rules:",
        "- Prefer edit_file over write_file for existing files.",
        "- Always read a file before editing it.",
        "- Run tests after making code changes if a test runner is detected.",
        "- Ask for clarification if a task is ambiguous rather than guessing.",
        "- Keep responses concise and action-oriented.",
    ]
    if live_lookup:
        lines.insert(
            4,
            "- For current events, latest facts, time, timezone, date, or weather, use live lookup tools before answering.",
        )
    return "\n".join(lines)



def run_tool_loop_sync(
    client: Any,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    context: ToolContext,
    *,
    effort_options: dict[str, Any] | None = None,
    registry: ToolRegistry | None = None,
) -> ToolLoopResult:
    runtime = AgenticRuntime(registry=registry or build_default_tool_registry(), context=context, provider=provider, model=model)
    return run_async(runtime.run(client, messages, effort_options=effort_options))



def _trim_result(text: str, *, limit: int = 320) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3].rstrip() + "..."


__all__ = [
    "AgenticRuntime",
    "MAX_TOOL_ROUNDS",
    "ToolCallLog",
    "ToolLoopResult",
    "build_agentic_system_hint",
    "build_default_tool_registry",
    "run_tool_loop_sync",
]
