"""
Centralized configuration for Lumi paths and settings.
All paths use pathlib.Path for consistency and cross-platform compatibility.
"""
from __future__ import annotations

import os
from pathlib import Path

# Base directory - use LUMI_HOME env var or default to ~/Lumi
LUMI_HOME = Path(os.environ.get("LUMI_HOME", Path.home() / "Lumi")).expanduser().resolve()

# Data directories (gitignored)
DATA_DIR = LUMI_HOME / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
MEMORY_DIR = DATA_DIR / "memory"
SESSIONS_DIR = DATA_DIR / "sessions"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
PERSONAS_DIR = DATA_DIR / "personas"

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
        MODELS_WEIGHTS_DIR,
        MODELS_ADAPTERS_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def get_data_path(subpath: str) -> Path:
    """Get a path within the data directory."""
    return DATA_DIR / subpath


def get_memory_path(filename: str) -> Path:
    """Get a path within the memory directory."""
    return MEMORY_DIR / filename


def get_session_path(filename: str) -> Path:
    """Get a path within the sessions directory."""
    return SESSIONS_DIR / filename


def get_conversation_path(filename: str) -> Path:
    """Get a path within the conversations directory."""
    return CONVERSATIONS_DIR / filename
