"""
Session context for CLI commands.

Contains all the mutable state that commands need to access.
"""

from __future__ import annotations

import pathlib

from src.chat.hf_client import get_client, get_models, get_provider, pick_startup_model, set_provider
from src.memory.longterm import get_persona_override
from src.memory.short_term import ShortTermMemory
from src.prompts.builder import load_persona


class SessionContext:
    """Mutable session state shared across CLI commands."""

    def __init__(self) -> None:
        # Core state
        self.memory: ShortTermMemory = ShortTermMemory(max_turns=20)
        self.client = get_client()
        provider = get_provider()
        self.current_model: str = pick_startup_model(provider, get_models(provider))
        self.name: str = "Lumi"
        self.system_prompt: str = ""
        self.turns: int = 0
        self.multiline: bool = False
        self.last_msg: str | None = None
        self.last_reply: str | None = None
        self.prev_reply: str | None = None
        self.response_mode: str | None = None
        self.current_theme: str = "default"
        self.max_turns: int | None = None

        # Derived state
        self.persona = load_persona()
        self.persona_override = get_persona_override()

        # References to functions that need to be injected
        self.draw_header = None  # will be set later
        self.ok = None
        self.fail = None
        self.info = None
        self.warn = None
        self.div = None
        self.print_welcome = None
        self.print_lumi_label = None
        self.print_you = None

    def update_system_prompt(self) -> None:
        """Rebuild system prompt based on current persona and overrides."""
        from src.memory.longterm import build_memory_block
        from src.prompts.builder import build_system_prompt as build_sp
        merged = {**self.persona, **(self.persona_override or {})}
        mem = build_memory_block()
        self.system_prompt = build_sp(merged, mem, False, False)

    def save_session(self, name: str = "") -> pathlib.Path:
        """Save current conversation to disk."""
        from src.memory.conversation_store import save
        return save(self.memory.get(), name)

    def load_session(self, name: str = "") -> bool:
        """Load session by name (empty for latest). Returns success."""
        from src.memory.conversation_store import load_by_name, load_latest
        h = load_by_name(name) if name else load_latest()
        if h:
            self.memory.set_history(h)
            self.turns = len(h) // 2
            return True
        return False

    def get_provider(self) -> str:
        """Current provider name."""
        return get_provider()

    def set_provider(self, provider: str) -> None:
        """Switch provider and reset client."""
        set_provider(provider)
        self.client = get_client()
        self.current_model = pick_startup_model(provider, get_models(provider))

    def get_available_providers(self):
        """Get list of available providers."""
        from src.chat.hf_client import get_available_providers
        self.available_providers = get_available_providers()
