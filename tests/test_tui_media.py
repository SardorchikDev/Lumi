"""Tests for shared TUI media helpers."""

from __future__ import annotations

import base64
import json

from src.tui.media import generate_gemini_images


def test_generate_gemini_images_posts_inline_source_and_saves_output(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    source = tmp_path / "seed.png"
    source.write_bytes(b"seed-image")
    captured: dict[str, object] = {}

    response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Rendered successfully."},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(b"generated-image").decode("ascii"),
                            }
                        },
                    ]
                }
            }
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(response_payload).encode("utf-8")

    def fake_urlopen(request, timeout=60):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    saved_paths, message = generate_gemini_images(
        "make this softer",
        source_image=source,
        output_dir=tmp_path / "generated",
    )

    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    assert captured["timeout"] == 60
    payload = captured["payload"]
    assert payload["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
    parts = payload["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "image/png"
    assert parts[0]["inline_data"]["data"] == base64.b64encode(b"seed-image").decode("ascii")
    assert parts[1] == {"text": "make this softer"}
    assert message == "Rendered successfully."
    assert len(saved_paths) == 1
    assert saved_paths[0].exists()
    assert saved_paths[0].read_bytes() == b"generated-image"
