"""Builds the message list sent to the model."""

import json
import pathlib

PERSONA_PATH = pathlib.Path("data/personas/default.json")


def load_persona() -> dict:
    if PERSONA_PATH.exists():
        return json.loads(PERSONA_PATH.read_text())
    return {"name": "Lumi", "tone": "warm, curious, and concise"}


def build_system_prompt(persona: dict) -> str:
    name = persona.get("name", "Lumi")
    tone = persona.get("tone", "helpful")
    traits = ", ".join(persona.get("traits", []))
    return (
        f"You are {name}, a conversational AI assistant. "
        f"Your tone is {tone}. "
        f"{'Your traits are: ' + traits + '.' if traits else ''} "
        f"Be concise and natural. Never break character."
    )


def build_messages(system_prompt: str, history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": system_prompt}] + history

