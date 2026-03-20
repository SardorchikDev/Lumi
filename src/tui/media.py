"""Shared media helpers for Lumi TUI commands."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import shlex
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.chat.optimizer import route_model
from src.chat.providers import (
    pick_provider_for_capability,
    provider_capability_model_hints,
)
from src.config import GENERATED_IMAGES_DIR

VISION_PROVIDER_ORDER = (
    "gemini",
    "vertex",
    "vercel",
    "openrouter",
    "airforce",
    "pollinations",
)
AUDIO_TRANSCRIPTION_PROVIDER_ORDER = (
    "groq",
    "gemini",
    "huggingface",
)
IMAGE_GENERATION_PROVIDER_ORDER = (
    "gemini",
)


def parse_image_request(arg: str) -> tuple[Path, str] | None:
    stripped = arg.strip()
    if not stripped:
        return None
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        tokens = stripped.split()
    if not tokens:
        return None
    for end in range(len(tokens), 0, -1):
        candidate = Path(" ".join(tokens[:end])).expanduser()
        if candidate.exists():
            question = " ".join(tokens[end:]).strip()
            return candidate, question
    candidate = Path(tokens[0]).expanduser()
    question = " ".join(tokens[1:]).strip()
    return candidate, question


def image_mime(path: Path) -> str | None:
    guessed, _encoding = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    fallback = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    return fallback.get(path.suffix.lower())


def resolve_media_target(
    *,
    capability: str,
    current_provider: str,
    current_model: str,
    configured_providers: list[str],
    get_models_fn,
) -> tuple[str, str, bool]:
    preferred_order = {
        "vision": VISION_PROVIDER_ORDER,
        "audio_transcription": AUDIO_TRANSCRIPTION_PROVIDER_ORDER,
        "image_generation": IMAGE_GENERATION_PROVIDER_ORDER,
    }.get(capability, ())
    provider = pick_provider_for_capability(
        configured_providers,
        capability,
        current_provider=current_provider,
        preferred_order=preferred_order,
    )
    if not provider:
        raise RuntimeError(f"No configured provider supports {capability.replace('_', ' ')}.")
    models = list(get_models_fn(provider) or [])
    if not models:
        raise RuntimeError(f"No models available for {provider}.")
    hints = provider_capability_model_hints(provider, capability)
    model = next((candidate for candidate in hints if candidate in models), "")
    if not model:
        model = route_model(current_model, models, "chat", provider=provider)
    return provider, model, provider != current_provider


def build_image_messages(prompt: str, path: Path) -> list[dict[str, object]]:
    from src.utils.tools import encode_image_base64

    mime = image_mime(path)
    if not mime:
        raise RuntimeError(f"Not an image: {path}")
    data_url = f"data:{mime};base64,{encode_image_base64(str(path))}"
    return [
        {
            "role": "system",
            "content": "You are Lumi. Analyze the provided image and answer the user's question clearly and concisely.",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt or "Describe this image clearly and concisely."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]


def parse_voice_duration(arg: str) -> int:
    raw = arg.strip()
    if not raw:
        return 5
    if not raw.isdigit():
        raise ValueError("Usage: /voice [seconds]")
    seconds = int(raw)
    if seconds < 1 or seconds > 30:
        raise ValueError("Voice duration must be between 1 and 30 seconds.")
    return seconds


def parse_imagine_request(arg: str) -> tuple[Path | None, str] | None:
    stripped = arg.strip()
    if not stripped:
        return None
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        tokens = stripped.split()
    if not tokens:
        return None
    for end in range(len(tokens), 0, -1):
        candidate = Path(" ".join(tokens[:end])).expanduser()
        if candidate.exists():
            prompt = " ".join(tokens[end:]).strip()
            return candidate, prompt
    return None, stripped


def record_voice_clip(seconds: int) -> str | None:
    from src.utils.voice import record_audio

    return record_audio(seconds=seconds)


def transcribe_audio_file(audio_path: str) -> tuple[str, str]:
    from src.tools.voice import transcribe_audio_hf
    from src.utils.voice import transcribe_groq

    if os.getenv("GROQ_API_KEY"):
        text = transcribe_groq(audio_path).strip()
        if text:
            return text, "Groq Whisper"

    if os.getenv("HF_TOKEN"):
        text = transcribe_audio_hf(audio_path).strip()
        if text:
            return text, "HuggingFace Whisper"

    if os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN"):
        return "", ""
    raise RuntimeError("Voice transcription needs GROQ_API_KEY or HF_TOKEN in .env.")


def inject_text_at_cursor(buffer: str, cursor: int, text: str) -> tuple[str, int]:
    if not text:
        return buffer, cursor
    left = buffer[:cursor]
    right = buffer[cursor:]
    injected = text
    if left and not left.endswith((" ", "\n")):
        injected = " " + injected
    if right and not right.startswith((" ", "\n")):
        injected = injected + " "
    updated = left + injected + right
    return updated, len(left + injected)


def _mime_extension(mime_type: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    return mapping.get(mime_type.lower(), ".png")


def _friendly_generation_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            payload = exc.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        if payload:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return payload
            error = data.get("error", {})
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return str(message)
        return f"Image generation failed with HTTP {exc.code}"
    return str(exc)


def generate_gemini_images(
    prompt: str,
    *,
    source_image: Path | None = None,
    model: str = "gemini-2.5-flash-image",
    output_dir: Path | None = None,
) -> tuple[list[Path], str]:
    from src.utils.tools import encode_image_base64

    prompt = prompt.strip()
    if not prompt:
        raise RuntimeError("Image generation needs a prompt.")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Image generation needs GEMINI_API_KEY in .env.")

    parts: list[dict[str, object]] = []
    if source_image is not None:
        mime = image_mime(source_image)
        if not mime:
            raise RuntimeError(f"Not an image: {source_image}")
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": encode_image_base64(str(source_image)),
                }
            }
        )
    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(_friendly_generation_error(exc)) from exc

    target_dir = (output_dir or GENERATED_IMAGES_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    saved_paths: list[Path] = []
    text_parts: list[str] = []
    image_index = 0
    for candidate in body.get("candidates", []):
        content = candidate.get("content", {})
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                text_parts.append(str(part["text"]).strip())
                continue
            blob = part.get("inlineData") or part.get("inline_data")
            if not isinstance(blob, dict):
                continue
            data = blob.get("data")
            mime_type = blob.get("mimeType") or blob.get("mime_type") or "image/png"
            if not data:
                continue
            image_index += 1
            filename = f"lumi_image_{timestamp}_{image_index:02d}{_mime_extension(str(mime_type))}"
            output_path = target_dir / filename
            output_path.write_bytes(base64.b64decode(data))
            saved_paths.append(output_path)

    if not saved_paths:
        message = "\n".join(part for part in text_parts if part).strip()
        raise RuntimeError(message or "Gemini did not return an image.")
    return saved_paths, "\n".join(part for part in text_parts if part).strip()
