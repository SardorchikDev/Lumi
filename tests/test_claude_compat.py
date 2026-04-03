from __future__ import annotations

from src.chat.claude_compat import _data_url_to_image_source, convert_messages


def test_convert_messages_separates_system_and_preserves_roles():
    system, messages = convert_messages(
        [
            {"role": "system", "content": "You are Lumi."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )

    assert system == "You are Lumi."
    assert messages == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
    ]


def test_convert_messages_translates_data_url_images():
    system, messages = convert_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmFrZQ=="}},
                ],
            }
        ]
    )

    assert system == ""
    blocks = messages[0]["content"]
    assert blocks[0] == {"type": "text", "text": "describe"}
    assert blocks[1] == {
        "type": "image",
        "source": _data_url_to_image_source("data:image/png;base64,ZmFrZQ=="),
    }
