"""Anthropic Claude adapter with an OpenAI-like chat.completions surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

import requests

ANTHROPIC_VERSION = "2023-06-01"


def _is_data_url(value: str) -> bool:
    return value.startswith("data:")


def _data_url_to_image_source(url: str) -> dict[str, str]:
    header, encoded = url.split(",", 1)
    meta = header[5:]
    media_type = meta.split(";", 1)[0] or "image/png"
    return {
        "type": "base64",
        "media_type": media_type,
        "data": encoded,
    }


def _convert_content(content) -> list[dict[str, object]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]
    blocks: list[dict[str, object]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip().lower()
        if kind == "text":
            text = str(item.get("text") or "")
            if text:
                blocks.append({"type": "text", "text": text})
        elif kind == "image_url":
            raw_url = item.get("image_url")
            if isinstance(raw_url, dict):
                raw_url = raw_url.get("url")
            url = str(raw_url or "")
            if not url:
                continue
            if _is_data_url(url):
                blocks.append({"type": "image", "source": _data_url_to_image_source(url)})
            else:
                blocks.append({"type": "text", "text": f"[Image URL: {url}]"})
    return blocks or [{"type": "text", "text": ""}]


def _convert_tools(tools: list[dict[str, object]] | None) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if item.get("type") == "function" else item
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        converted.append(
            {
                "name": name,
                "description": str(function.get("description") or ""),
                "input_schema": function.get("parameters") if isinstance(function.get("parameters"), dict) else {"type": "object", "properties": {}},
            }
        )
    return converted


def _tool_use_block(call: dict[str, object]) -> dict[str, object] | None:
    function = call.get("function")
    if not isinstance(function, dict):
        return None
    name = str(function.get("name") or "").strip()
    if not name:
        return None
    arguments_text = str(function.get("arguments") or "{}")
    try:
        arguments = json.loads(arguments_text or "{}")
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return {
        "type": "tool_use",
        "id": str(call.get("id") or f"tool_{name}"),
        "name": name,
        "input": arguments,
    }


def convert_messages(messages: list[dict[str, object]]) -> tuple[str, list[dict[str, object]]]:
    system_parts: list[str] = []
    converted: list[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(message.get("tool_call_id") or message.get("name") or "tool"),
                            "content": str(message.get("content") or ""),
                        }
                    ],
                }
            )
            continue
        content = _convert_content(message.get("content", ""))
        if role == "system":
            system_parts.extend(
                block["text"]
                for block in content
                if block.get("type") == "text" and str(block.get("text") or "").strip()
            )
            continue
        anthropic_role = "assistant" if role == "assistant" else "user"
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                tool_blocks = [_tool_use_block(call) for call in tool_calls if isinstance(call, dict)]
                content = [*content, *[block for block in tool_blocks if block is not None]]
        converted.append({"role": anthropic_role, "content": content})
    return "\n\n".join(system_parts).strip(), converted


def _raise_for_response(response: requests.Response) -> None:
    if response.ok:
        return
    message = response.text.strip()
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("type") or message)
        elif payload.get("message"):
            message = str(payload.get("message"))
    raise RuntimeError(f"{response.status_code} {message}".strip())


def _extract_text_blocks(payload: dict[str, object]) -> str:
    blocks = payload.get("content") if isinstance(payload, dict) else []
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts).strip()


def _extract_tool_calls(payload: dict[str, object]) -> list[SimpleNamespace]:
    blocks = payload.get("content") if isinstance(payload, dict) else []
    if not isinstance(blocks, list):
        return []
    tool_calls: list[SimpleNamespace] = []
    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        arguments = json.dumps(block.get("input") or {}, ensure_ascii=False)
        tool_calls.append(
            SimpleNamespace(
                id=str(block.get("id") or f"tool_{index}"),
                function=SimpleNamespace(
                    name=str(block.get("name") or ""),
                    arguments=arguments,
                ),
            )
        )
    return tool_calls


def _build_response(text: str, *, output_tokens: int = 0, tool_calls: list[SimpleNamespace] | None = None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=tool_calls or []))],
        usage=SimpleNamespace(completion_tokens=output_tokens),
    )


def _build_chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
    )


def _iter_sse(response: requests.Response):
    event_name = ""
    data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line or ""
        if not line:
            if event_name or data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = ""
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if event_name or data_lines:
        yield event_name, "\n".join(data_lines)


@dataclass
class AnthropicChatCompletions:
    api_key: str
    base_url: str
    timeout: int = 120

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, object]],
        max_tokens: int,
        temperature: float,
        stream: bool = False,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | None = None,
        thinking: dict[str, object] | None = None,
    ):
        system, anthropic_messages = convert_messages(messages)
        payload: dict[str, object] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        converted_tools = _convert_tools(tools)
        if converted_tools:
            payload["tools"] = converted_tools
        if isinstance(thinking, dict) and thinking:
            payload["thinking"] = thinking
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        response = requests.post(
            f"{self.base_url.rstrip('/')}/messages",
            headers=headers,
            json=payload,
            stream=stream,
            timeout=self.timeout,
        )
        _raise_for_response(response)
        if not stream:
            data = response.json()
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            output_tokens = int(usage.get("output_tokens") or 0)
            return _build_response(
                _extract_text_blocks(data),
                output_tokens=output_tokens,
                tool_calls=_extract_tool_calls(data),
            )
        return self._stream_chunks(response)

    def _stream_chunks(self, response: requests.Response):
        for event_name, raw_data in _iter_sse(response):
            if raw_data == "[DONE]":
                break
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                continue
            if event_name == "error":
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                raise RuntimeError(str(error.get("message") or error.get("type") or "Anthropic stream error"))
            if event_name != "content_block_delta":
                continue
            delta = payload.get("delta", {}) if isinstance(payload, dict) else {}
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = str(delta.get("text") or "")
                if text:
                    yield _build_chunk(text)


class AnthropicChat:
    def __init__(self, api_key: str, base_url: str):
        self.completions = AnthropicChatCompletions(api_key=api_key, base_url=base_url)


class AnthropicCompatClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        parsed = urlparse(base_url)
        if not parsed.scheme:
            raise ValueError("Anthropic base URL must include a scheme")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chat = AnthropicChat(api_key=api_key, base_url=self.base_url)
