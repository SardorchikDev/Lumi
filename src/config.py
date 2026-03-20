"""Centralized configuration for Lumi install, state, and cache paths."""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


# Install/workspace root. This can still point at a checkout like ~/Lumi.
LUMI_HOME = _resolve_path(os.environ.get("LUMI_HOME", Path.home() / "Lumi"))

# Runtime state and cache should live outside the tracked repo by default.
DEFAULT_RUNTIME_HOME = Path.home() / ".codex" / "memories" / "lumi"
STATE_ROOT = _resolve_path(
    os.environ.get(
        "LUMI_STATE_DIR",
        DEFAULT_RUNTIME_HOME / "state",
    )
)
CACHE_ROOT = _resolve_path(
    os.environ.get(
        "LUMI_CACHE_DIR",
        DEFAULT_RUNTIME_HOME / "cache",
    )
)

# Durable runtime data (sessions, notes, memory).
DATA_DIR = _resolve_path(os.environ.get("LUMI_DATA_DIR", STATE_ROOT / "data"))
CONVERSATIONS_DIR = DATA_DIR / "conversations"
MEMORY_DIR = DATA_DIR / "memory"
SESSIONS_DIR = DATA_DIR / "sessions"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
PERSONAS_DIR = DATA_DIR / "personas"
UI_STATE_DIR = STATE_ROOT / "ui"
GENERATED_IMAGES_DIR = STATE_ROOT / "generated"

# Runtime caches and ephemeral backups.
MODEL_CACHE_DIR = CACHE_ROOT / "model_catalogs"
UNDO_DIR = STATE_ROOT / "undo"

# Model weights directory
MODELS_DIR = LUMI_HOME / "models"
MODELS_WEIGHTS_DIR = MODELS_DIR / "weights"
MODELS_ADAPTERS_DIR = MODELS_DIR / "adapters"

# Plugins directory
PLUGINS_DIR = LUMI_HOME / "plugins"

# Config file
CONFIG_FILE = LUMI_HOME / "configs" / "config.yaml"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    dirs = [
        DATA_DIR,
        CONVERSATIONS_DIR,
        MEMORY_DIR,
        SESSIONS_DIR,
        KNOWLEDGE_DIR,
        PERSONAS_DIR,
        UI_STATE_DIR,
        GENERATED_IMAGES_DIR,
        MODEL_CACHE_DIR,
        UNDO_DIR,
        MODELS_WEIGHTS_DIR,
        MODELS_ADAPTERS_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def get_data_path(subpath: str) -> Path:
    return DATA_DIR / subpath


def get_memory_path(filename: str) -> Path:
    return MEMORY_DIR / filename


def get_session_path(filename: str) -> Path:
    return SESSIONS_DIR / filename


def get_conversation_path(filename: str) -> Path:
    return CONVERSATIONS_DIR / filename
