"""
CLI command implementations for Lumi.

All cmd_* functions are moved here from main.py to modularize the codebase.
"""

import os
import sys
import pathlib
import textwrap
import threading
import time
import itertools
import json
import subprocess
from typing import Optional, Any

from src.chat.hf_client import get_client, get_provider, set_provider, get_models
from src.memory.short_term import ShortTermMemory
from src.utils.markdown import render as md_render
from src.utils.intelligence import classify_request, is_complex_coding_task
from src.utils.filesystem import (
    generate_file_plan,
    write_file_plan,
    format_creation_summary,
    is_create_request,
)
from src.utils.tools import (
    analyze_data_file,
    clipboard_get,
    clipboard_set,
    encode_image_base64,
    get_weather,
    load_project,
    read_pdf,
    take_screenshot,
)
from src.utils.voice import record_audio, speak, transcribe_groq
from src.utils.web import fetch_url
from src.utils.autoremember import auto_extract_facts
from src.utils.history import save as history_save
from src.utils.notes import note_add, note_list, note_remove, note_search, notes_to_markdown
from src.utils.todo import todo_add, todo_clear_done, todo_done, todo_list, todo_remove
from src.utils.plugins import dispatch as plugin_dispatch
from src.utils.themes import get_theme
from src.tools.mcp import get_session as mcp_session
from src.tools.mcp import list_servers as mcp_list
from src.tools.mcp import add_server as mcp_add
from src.tools.mcp import remove_server as mcp_remove
from src.tools.search import search, search_display
from src.agents.council import council_ask, _get_available_agents as get_council_agents

from .render import (
    ok,
    fail,
    info,
    warn,
    div,
    print_you,
    print_lumi_label,
    print_welcome,
    draw_header,
    Spinner,
    terminal_width as W,
    current_time as ts,
    word_count as wc,
    provider_color as _pcolor,
    visual_length as _vlen,
    center_visual as _center,
    PROV_COL,
    LOGO,
    LOGO_WIDTH as LOGO_W,
    C1, C2, C3, PU, BL, CY, GR, DG, MU, GN, RE, YE, WH, R, B, D,
)

# Re-export for backward compatibility
_PROVIDER_LABELS = {
    "gemini":      ("Gemini",        "Google Gemini — 2.5 Pro · Flash · 1M context"),
    "groq":        ("Groq",          "Groq — fastest, Llama / Qwen / GPT-OSS"),
    "openrouter":  ("OpenRouter",    "30+ free models — DeepSeek R1, Llama 4, Qwen3"),
    "mistral":     ("Mistral",       "Mistral free tier — great for coding"),
    "huggingface": ("HuggingFace",   "HuggingFace — free tier, rate limited"),
    "github":      ("GitHub Models", "GPT-4o, o1, DeepSeek R1, Phi-4 — free with GitHub"),
    "cohere":      ("Cohere",        "Cohere — free 1,000 req/month"),
    "bytez":       ("Bytez",         "Bytez — 100,000+ open-source models, full HuggingFace catalog"),
    "cloudflare":  ("Cloudflare",    "Cloudflare Workers AI — free 10 k neurons/day"),
    "ollama":      ("Ollama",        "Local Ollama — fully offline, no API limits"),
    "council":     ("⚡ Council",    "All agents in parallel — synthesized best answer"),
}

# Helper functions moved from main.py
def stream_and_render(
    client, messages: list, model: str, name: str = "Lumi"
) -> str:
    """Stream a response from the model and render it with markdown."""

    # ── Council mode ──────────────────────────────────────────────────────────
    if model == "council":
        user_q = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        avail = get_council_agents()
        print(f"\n  {DG}council  {GR}{len(avail)} agents  {DG}→  asking in parallel...{R}\n")

        gen        = council_ask(messages, user_q, show_individual=False,
                                 stream=True, debate=True, refine=True, client=client)
        raw_reply  = ""
        stats_line = ""
        refined    = ""

        print_lumi_label(name + f"  {DG}[council]{R}")
        for chunk in gen:
            if chunk.startswith("\n\n__STATS__\n"):
                stats_line = chunk[len("\n\n__STATS__\n"):]
                continue
            if chunk.startswith("\n\n__REFINED__\n\n"):
                refined = chunk[len("\n\n__REFINED__\n\n"):]
                continue
            print(chunk, end="", flush=True)
            raw_reply += chunk
        print()

        final = refined if refined else raw_reply
        # Re-render with markdown (erase raw stream first)
        for _ in range(final.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name + f"  {DG}[council]{R}")
        from src.utils.markdown import render as _mdr
        print("\n".join("  " + l for l in _mdr(final).split("\n")))
        print(f"\n  {MU}{wc(final)} words  {DG}{len(avail)} agents{R}")
        if stats_line:
            print(f"  {stats_line}")
        return final

    # ── Normal streaming ──────────────────────────────────────────────────────
    spinner   = Spinner("thinking")
    spinner.start()
    raw_reply = ""
    first     = True

    try:
        stream = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=1024, temperature=0.7, stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                if first:
                    spinner.stop()
                    print_lumi_label(name)
                    first = False
                print(delta, end="", flush=True)
                raw_reply += delta
        if first:
            spinner.stop()
        print()
    except Exception as exc:
        spinner.stop()
        raise exc

    if raw_reply:
        for _ in range(raw_reply.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name)
        indented = "\n".join("  " + l for l in md_render(raw_reply).split("\n"))
        print(indented)
        print(f"\n  {MU}{wc(raw_reply)} words{R}")

    return raw_reply