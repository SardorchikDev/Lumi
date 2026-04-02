"""Lumi CLI — smarter chatbot.

Improvements vs original:
  - ShortTermMemory accessed only through public API (thread-safe helpers)
  - No shadowing of the `args` local variable with module-level names
  - Duplicate function definitions removed (ok/fail/info/warn/div defined once)
  - SESSIONS_DIR imported from config so /find works without a local import
  - _parse_args return stored as `cli` not `args` (avoids shadowing builtins)
  - All memory mutations use memory.replace_last / memory.trim_last_n / memory.pop_last
"""

from dotenv import load_dotenv

load_dotenv()

import difflib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime

from src.agents.benchmark import load_benchmark_scenarios, render_benchmark_catalog
from src.agents.council import council_ask
from src.chat.hf_client import (
    chat_stream,
    get_available_providers,
    get_client,
    get_models,
    get_provider,
    pick_startup_model,
    set_provider,
)
from src.chat.model_filters import filter_models_by_allowlist, model_allowlist_env_keys
from src.chat.optimizer import (
    get_global_context_cache,
    get_global_telemetry,
    optimize_messages,
)
from src.chat.runtime import build_runtime_messages
from src.chat.runtime import route_helper_model as _shared_route_helper_model
from src.cli.args import parse_cli_args, print_cli_help
from src.config import PLUGINS_DIR, SESSIONS_DIR, ensure_dirs
from src.memory.conversation_store import list_sessions, load_by_name, load_latest, save
from src.memory.longterm import (
    add_fact,
    auto_summarize_and_save,
    build_memory_block,
    clear_facts,
    clear_persona_override,
    get_facts,
    get_persona_override,
    remove_fact,
    set_persona_override,
)
from src.memory.short_term import ShortTermMemory
from src.prompts.builder import (
    build_system_prompt,
    is_file_generation_task,
    load_persona,
)
from src.tools.mcp import add_server as mcp_add
from src.tools.mcp import get_session as mcp_session
from src.tools.mcp import list_servers as mcp_list
from src.tools.mcp import remove_server as mcp_remove
from src.tools.search import search, search_display
from src.utils.autoremember import auto_extract_facts
from src.utils.export import export_md
from src.utils.filesystem import (
    format_creation_summary,
    generate_file_plan,
    is_create_request,
    write_file_plan,
)
from src.utils.git_tools import GIT_USAGE, run_git_subcommand
from src.utils.history import save as history_save
from src.utils.history import setup as history_setup
from src.utils.intelligence import (
    classify_request,
    emotion_hint,
    is_complex_coding_task,
    needs_plan_first,
    should_search,
)
from src.utils.markdown import render as md_render
from src.utils.notes import note_add, note_list, note_remove, note_search, notes_to_markdown
from src.utils.plugins import (
    describe_plugins,
    get_commands,
    load_plugins,
    render_permission_report,
    render_plugin_audit_report,
)
from src.utils.plugins import dispatch as plugin_dispatch
from src.utils.rebirth import load_rebirth_profile, rebirth_status_summary, render_rebirth_report
from src.utils.system_reports import build_doctor_report, build_onboarding_report, build_status_report
from src.utils.themes import get_theme, list_themes, load_theme_name, save_theme_name
from src.utils.todo import todo_add, todo_clear_done, todo_done, todo_list, todo_remove
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

ensure_dirs()

LUMI_VERSION = "2.1.0"

# ── System prompt builder ─────────────────────────────────────────────────────

def make_system_prompt(
    persona: dict,
    override: dict = None,
    coding_mode: bool = False,
    file_mode: bool = False,
) -> str:
    merged = {**persona, **(override or {})}
    mem    = build_memory_block()
    return build_system_prompt(merged, mem, coding_mode, file_mode)


_context_cache = get_global_context_cache()
_session_telemetry = get_global_telemetry()


def build_messages(system_prompt: str, history: list[dict[str, str]], *, model: str = "") -> list[dict[str, str]]:
    return build_runtime_messages(
        system_prompt,
        history,
        model=model,
        get_provider_fn=get_provider,
        get_models_fn=get_models,
        context_cache=_context_cache,
        telemetry=_session_telemetry,
        search_markers=("page content", "url:"),
        file_markers=("loaded file", "project loaded", "create a folder"),
    )


def _remember_context_text(label: str, content: str, *, kind: str) -> None:
    _context_cache.remember_text(f"{kind}:{label}", label, content, kind=kind)


def _route_helper_model(current_model: str, mode: str) -> str:
    return _shared_route_helper_model(
        current_model,
        mode,
        get_provider_fn=get_provider,
        get_models_fn=get_models,
    )


# ── ANSI reset ────────────────────────────────────────────────────────────────
# ── Theme globals (populated by reload_theme) ─────────────────────────────────
from src.cli.render import (
    BL,
    C2,
    CY,
    DG,
    GN,
    GR,
    MU,
    PU,
    RE,
    WH,
    YE,
    B,
    R,
    Spinner,
    div,
    draw_header,
    fail,
    info,
    ok,
    print_lumi_label,
    print_welcome,
    print_you,
    reload_theme,
    terminal_width,
    warn,
)
from src.cli.render import (
    word_count as wc,
)

reload_theme()






# ── Header ────────────────────────────────────────────────────────────────────



# ── Spinner ───────────────────────────────────────────────────────────────────



# ── Message display ───────────────────────────────────────────────────────────



# ── Help ──────────────────────────────────────────────────────────────────────

def print_help() -> None:
    w    = terminal_width()
    line = f"  {DG}{'─' * (w - 4)}{R}"

    def section(title: str) -> None:
        print(f"\n  {C2}{B}{title}{R}")

    def cmd(name: str, desc: str) -> None:
        print(f"  {CY}  {name:<28}{R}{DG}{desc}{R}")

    print(f"\n{line}")
    print(f"  {PU}{B}  ✦  LUMI - REBIRTH COMMANDS{R}")
    print(line)

    section("CHAT")
    cmd("/council <q>",              "ask all agents — best answer synthesized")
    cmd("/council --show <q>",       "same + show each agent's raw response")
    cmd("/context",                  "show token usage and context window")
    cmd("/status",                   "session + workspace status summary")
    cmd("/doctor",                   "check Lumi setup and workspace health")
    cmd("/onboard",                  "show first-run and workspace guidance")
    cmd("/rebirth [status|on|off]", "Lumi - rebirth capability report and profile toggle")
    cmd("/benchmark [list]",         "show built-in benchmark scenarios")
    cmd("/redo [hint]",              "regenerate last answer, optionally with a hint")
    cmd("/help",                     "show this")
    cmd("/clear",                    "reset conversation")
    cmd("/undo · /retry",            "remove last turn or resend it")
    cmd("/more · /tl;dr",            "expand or summarize last reply")
    cmd("/rewrite · /summarize",     "rewrite reply or summarize chat")
    cmd("/short · /detailed · /bullets", "one-shot reply format")
    cmd("/multi",                    "toggle multi-line input")

    section("CODE")
    cmd("/edit <path>",              "edit a file — AI rewrites, shows diff, confirms")
    cmd("/file <path>",              "load file as context")
    cmd("/project <dir>",            "load entire codebase as context")
    cmd("/fix <error>",              "diagnose and fix an error")
    cmd("/review [file]",            "full code review")
    cmd("/explain [file]",           "explain code or last reply")
    cmd("/comment [file]",           "add docstrings and inline comments")
    cmd("/run",                      "run code block from last reply")
    cmd("/diff",                     "diff previous reply vs latest")
    cmd(f"/git {GIT_USAGE}",         "git helpers")
    cmd("/github issues",            "pull GitHub issues (needs GITHUB_TOKEN)")

    section("FILES & DATA")
    cmd("/pdf <path>",               "read and analyze a PDF")
    cmd("/data <path>",              "analyze CSV or JSON file")
    cmd("/screenshot",               "capture screen → AI vision analysis")
    cmd("/paste · /copy",            "clipboard into chat / copy last reply out")

    section("VOICE")
    cmd("/listen [seconds]",         "record mic → Groq Whisper → send to Lumi")
    cmd("/speak",                    "read last reply aloud")

    section("PRODUCTIVITY")
    cmd("/todo add|list|done|remove", "persistent task tracker")
    cmd("/note [#tag] <text>",       "timestamped notes — list · search · export")
    cmd("/standup",                  "daily standup from git log + todos")
    cmd("/timer <25m|5s|1h>",        "countdown timer with desktop notification")
    cmd("/draft <description>",      "draft an email, Slack message, or text")
    cmd("/weather [city]",           "current weather (wttr.in — no key needed)")

    section("WEB & VISION")
    cmd("/search <query>",           "explicit web search")
    cmd("/web <url> [question]",     "fetch any webpage, ask questions about it")
    cmd("/image <path> [question]",  "send image to AI — vision support")
    cmd("/translate <language>",     "translate last reply")
    cmd("/imagine <prompt>",         "generate image (opens browser)")

    section("AUTONOMOUS")
    cmd("/agent <task>",             "multi-step autonomous agent")
    cmd("/lumi.md show|create",      "view or create project context file")

    section("MCP SERVERS")
    cmd("/mcp list",                 "show configured MCP servers")
    cmd("/mcp add <n> <cmd>",        "add a new MCP server")
    cmd("/mcp remove <n>",           "remove a server")
    cmd("/mcp tools <server>",       "list tools on a server")
    cmd("/mcp call <srv> <tool>",    "call a tool directly")

    section("PLUGINS")
    cmd("/plugins [inspect|audit]",  "list loaded plugins, inspect metadata, or audit permissions")
    cmd("/permissions [all|plugins]", "show plugin permission model")
    cmd("/plugins reload",           f"reload plugins from {PLUGINS_DIR}")

    section("MEMORY & PERSONA")
    cmd("/remember <fact>",          "save fact to long-term memory")
    cmd("/memory",                   "view all saved memories")
    cmd("/forget",                   "delete memories interactively")
    cmd("/persona",                  "edit Lumi's name, tone, and traits")

    section("SESSIONS")
    cmd("/save [name]",              "save conversation with optional name")
    cmd("/load [name]",              "load session by name or latest")
    cmd("/sessions",                 "list all saved sessions")
    cmd("/export",                   "export current session as markdown")
    cmd("/find <keyword>",           "search through past sessions")

    section("SETTINGS")
    cmd("/model",                    "switch provider and model (interactive picker)")
    cmd("/theme",                    "show the fixed ANSI palette")
    cmd("/cost",                     "show token usage this session")
    cmd("/compact",                  "toggle minimal output mode")
    cmd("/quit",                     "save and exit")

    print(f"\n{line}")
    print(f"  {DG}  tip  →  just type naturally. Lumi auto-detects coding tasks and file creation.{R}")
    print(f"{line}\n")


# ── Token / cost tracker ──────────────────────────────────────────────────────

_session_tokens: dict[str, int] = {"input": 0, "output": 0}


def _track(prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    _session_tokens["input"]  += prompt_tokens
    _session_tokens["output"] += completion_tokens


def cmd_cost() -> None:
    report = _session_telemetry.render_usage_report()
    print(f"\n  {B}{WH}Session token usage{R}\n")
    for line in report.splitlines()[1:]:
        key, value = line.split(":", 1)
        print(f"  {CY}{key:<12}{R}{GR}{value}{R}")
    print(f"\n  {DG}(estimated from packed prompt + reply telemetry){R}\n")


def health_check(_providers: list) -> None:
    pass  # removed — was producing false positives on startup


# ── Provider label table ──────────────────────────────────────────────────────

PROVIDER_LABELS: dict[str, tuple[str, str]] = {
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


# ── Model picker ──────────────────────────────────────────────────────────────

def pick_model(cur_model: str) -> tuple[str, str]:
    available = get_available_providers()
    if not available:
        warn("No API keys found in .env")
        return cur_model, get_provider()

    cur_provider = get_provider()

    print(f"\n  {B}{WH}Choose provider{R}\n")
    for i, p in enumerate(available):
        label, desc = PROVIDER_LABELS.get(p, (p, ""))
        dot    = f"{GN}●{R}" if p == cur_provider else f"{DG}○{R}"
        active = f"  {MU}active{R}" if p == cur_provider else ""
        print(f"  {dot}  {GR}{i + 1}.{R}  {WH}{label}{R}  {DG}{desc}{R}{active}")
    print()

    try:
        raw = input(f"  {PU}›{R}  ").strip()
        if not raw:
            raise ValueError
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(available):
                chosen_provider = available[idx]
            else:
                warn("Invalid choice.")
                return cur_model, cur_provider
        except ValueError:
            frag    = raw.lower()
            matches = [p for p in available if frag in p.lower()]
            if len(matches) == 1:
                chosen_provider = matches[0]
            else:
                warn("No match.")
                return cur_model, cur_provider
    except (KeyboardInterrupt, EOFError):
        warn("Keeping current provider.")
        return cur_model, cur_provider

    if chosen_provider != cur_provider:
        set_provider(chosen_provider)

    sp     = Spinner("loading models")
    sp.start()
    all_models = get_models(chosen_provider)
    models, allowlist = filter_models_by_allowlist(chosen_provider, all_models)
    sp.stop()
    if allowlist:
        info(f".env model allowlist active: showing {len(models)} of {len(all_models)} models.")
    if not models:
        key = model_allowlist_env_keys(chosen_provider)[0]
        warn(f"No models matched {key} in .env")
        return cur_model, cur_provider

    print(f"\n  {B}{WH}Available models{R}  {DG}({PROVIDER_LABELS[chosen_provider][0]}){R}\n")
    default_model = models[0] if models else cur_model
    for i, m in enumerate(models):
        is_active = m == cur_model and chosen_provider == cur_provider
        dot    = f"{GN}●{R}" if is_active else f"{DG}○{R}"
        active = f"  {MU}active{R}" if is_active else ""
        print(f"  {dot}  {GR}{i + 1}.{R}  {WH}{m.split('/')[-1]}{R}{active}")
    print()

    try:
        raw = input(f"  {PU}›{R}  ").strip()
        if not raw:
            return default_model, chosen_provider
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(models):
                return models[idx], chosen_provider
        except ValueError:
            pass
        frag    = raw.lower()
        matches = [m for m in models if frag in m.lower()]
        if len(matches) == 1:
            return matches[0], chosen_provider
        elif len(matches) > 1:
            warn("Ambiguous.")
            return default_model, chosen_provider
        else:
            warn(f"No model matching '{raw}'.")
            return default_model, chosen_provider
    except (KeyboardInterrupt, EOFError):
        pass
    return default_model, chosen_provider


# ── Multi-line input ──────────────────────────────────────────────────────────

def read_multiline() -> str:
    print(f"  {DG}multi-line — type {GR}END{DG} on its own line to send{R}\n")
    lines: list[str] = []
    while True:
        try:
            line = input(f"  {DG}│{R}  ")
        except (KeyboardInterrupt, EOFError):
            raise
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


# ── Stream + render ───────────────────────────────────────────────────────────

def stream_and_render(
    client, messages: list, model: str, name: str = "Lumi"
) -> str:
    """Stream a response from the model and render it with markdown."""

    # ── Council mode ──────────────────────────────────────────────────────────
    if model == "council":
        from src.agents.council import (
            _get_available_agents as _gav,
        )
        from src.agents.council import (
            council_ask as _ca,
        )
        user_q = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        avail = _gav()
        print(f"\n  {DG}council  {GR}{len(avail)} agents  {DG}→  asking in parallel...{R}\n")

        gen        = _ca(messages, user_q, show_individual=False,
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
        _session_telemetry.record_response(final)
        return final

    # ── Normal streaming ──────────────────────────────────────────────────────
    spinner   = Spinner("thinking")
    spinner.start()
    raw_reply = ""
    first     = True

    try:
        def _on_delta(delta: str) -> None:
            nonlocal first, raw_reply
            if first:
                spinner.stop()
                print_lumi_label(name)
                first = False
            print(delta, end="", flush=True)
            raw_reply += delta

        chat_stream(
            client,
            messages,
            model=model,
            max_tokens=896,
            temperature=0.45,
            on_delta=_on_delta,
        )
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
        _session_telemetry.record_response(raw_reply)

    return raw_reply


def stream_with_fallback(
    client,
    messages: list,
    model: str,
    name: str,
    providers: list,
    current_provider: str,
) -> tuple:
    """Try current provider; on quota/rate error auto-switch to the next one."""
    try:
        reply = stream_and_render(client, messages, model, name)
        return reply, client, model, current_provider
    except Exception as exc:
        msg = str(exc)
        if not any(x in msg for x in ("429", "limit: 0", "RESOURCE_EXHAUSTED", "quota")):
            raise
        remaining = [p for p in providers if p != current_provider]
        if not remaining:
            raise
        next_p = remaining[0]
        info(f"Quota hit on {current_provider} — switching to {next_p} automatically")
        set_provider(next_p)
        new_client = get_client()
        new_model  = pick_startup_model(next_p, get_models(next_p))
        reply = stream_and_render(new_client, messages, new_model, name)
        return reply, new_client, new_model, next_p


def silent_call(client, prompt: str, model: str, max_tokens: int = 300) -> str:
    """Single non-streaming call with no display output."""
    routed_model = _route_helper_model(model, "summary")
    provider = get_provider()
    messages = optimize_messages(
        [{"role": "system", "content": "You are Lumi. Return only the requested result."}, {"role": "user", "content": prompt}],
        routed_model,
        mode="summary",
        provider=provider,
        context_cache=_context_cache,
        telemetry=_session_telemetry,
    )
    try:
        r = client.chat.completions.create(
            model=routed_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
            stream=False,
        )
        reply = r.choices[0].message.content.strip()
        usage = getattr(r, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
        _session_telemetry.record_response(reply, actual_tokens=completion_tokens)
        return reply
    except Exception:
        return ""


# ── File helpers ──────────────────────────────────────────────────────────────

def _read_file(path: str) -> str:
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if p.stat().st_size > 200_000:
        raise ValueError(
            f"File too large ({p.stat().st_size // 1024} KB). Paste a smaller excerpt."
        )
    return p.read_text(encoding="utf-8", errors="replace")


# ── /council command ──────────────────────────────────────────────────────────

def cmd_council(
    user_input: str,
    messages: list,
    name: str,
    show_individual: bool = False,
) -> str:
    from src.utils.markdown import render as _md_render
    try:
        gen = council_ask(
            messages, user_input,
            show_individual=show_individual,
            stream=True, debate=True, refine=True,
        )
        print_lumi_label(name + "  " + f"{DG}[council]{R}")
        raw_reply  = ""
        stats_line = ""
        refined    = ""
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
        for _ in range(final.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name + "  " + f"{DG}[council]{R}")
        print("\n".join("  " + l for l in _md_render(final).split("\n")))
        print(f"\n  {MU}{wc(final)} words{R}")
        if stats_line:
            print(f"  {stats_line}")
        return final
    except RuntimeError as exc:
        fail(str(exc))
        return ""


# ── Code / file commands ──────────────────────────────────────────────────────

def cmd_file(
    path: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> str | None:
    try:
        code = _read_file(path)
    except Exception as exc:
        fail(str(exc))
        return None

    fname = pathlib.Path(path).name
    _context_cache.remember_file(path, code)
    info(f"Loaded {fname}  {DG}({code.count(chr(10)) + 1} lines, {len(code)} chars){R}")
    memory.add("user", f"[loaded file: {path}] Relevant file cached for retrieval.")
    messages = build_messages(system_prompt, memory.get(), model=model)
    print_you(f"[loaded file: {fname}]")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return None
    memory.replace_last("user", f"[loaded file: {fname}]")
    memory.add("assistant", raw)
    return raw


def cmd_fix(
    error: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str,
) -> str | None:
    context = f"\n\nContext from our last exchange:\n{last_reply}" if last_reply else ""
    memory.add("user", (
        f"I'm getting this error:\n\n```\n{error}\n```{context}\n\n"
        "Please:\n"
        "1. Explain what's causing it in plain English\n"
        "2. Show me the fix with corrected code\n"
        "3. If relevant, explain how to avoid it next time"
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"fix: {error[:80]}{'...' if len(error) > 80 else ''}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return None
    memory.replace_last("user", f"/fix: {error[:200]}")
    memory.add("assistant", raw)
    return raw


def cmd_explain(
    target: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str,
) -> str | None:
    if target:
        try:
            code    = _read_file(target)
            fname   = pathlib.Path(target).name
            subject = f"the file `{fname}`"
            content = f"```\n{code}\n```"
        except Exception as exc:
            fail(str(exc))
            return None
    elif last_reply:
        subject = "your last response"
        content = last_reply
    else:
        warn("Nothing to explain. Pass a file path or ask something first.")
        return None

    memory.add("user", (
        f"Please explain {subject} in detail:\n\n{content}\n\n"
        "Walk through it step by step. Explain what each part does, "
        "why it's written that way, and anything a developer should know."
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"explain: {target or 'last reply'}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return None
    memory.replace_last("user", f"/explain: {target or 'last reply'}")
    memory.add("assistant", raw)
    return raw


def cmd_review(
    target: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str,
) -> str | None:
    if target:
        try:
            code    = _read_file(target)
            fname   = pathlib.Path(target).name
            subject = f"the file `{fname}`"
            content = f"```\n{code}\n```"
        except Exception as exc:
            fail(str(exc))
            return None
    elif last_reply:
        subject = "your last code response"
        content = last_reply
    else:
        warn("Nothing to review. Pass a file path or ask for code first.")
        return None

    memory.add("user", (
        f"Please do a thorough code review of {subject}:\n\n{content}\n\n"
        "Cover:\n"
        "- Bugs or potential bugs\n"
        "- Performance issues\n"
        "- Security concerns\n"
        "- Code style and readability\n"
        "- What's done well\n"
        "- Concrete suggestions for improvement with code examples"
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"review: {target or 'last reply'}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return None
    memory.replace_last("user", f"/review: {target or 'last reply'}")
    memory.add("assistant", raw)
    return raw


def cmd_edit(
    path: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str = "",
) -> str:
    path = path.strip().strip("'\"")
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        fail(f"File not found: {path}")
        return last_reply
    size = os.path.getsize(path)
    if size > 300_000:
        fail(f"File too large ({size // 1024} KB). Max 300 KB.")
        return last_reply

    ext      = os.path.splitext(path)[1].lstrip(".")
    original = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    fname    = os.path.basename(path)

    print(f"\n  {B}{WH}File loaded:{R}  {GR}{path}{R}  {DG}({len(original.splitlines())} lines){R}")
    print(f"\n  {DG}What should Lumi do to this file?{R}")
    try:
        instruction = input(f"  {PU}›{R}  ").strip()
        if not instruction:
            warn("No instruction given.")
            return last_reply
    except (KeyboardInterrupt, EOFError):
        warn("Cancelled.")
        return last_reply

    memory.add("user", (
        f"You are editing the file `{fname}`.\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"FILE CONTENT:\n```{ext}\n{original}\n```\n\n"
        "Return ONLY the complete updated file content. "
        "No explanation, no markdown fences, no preamble. Just raw file content."
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Edit {fname}: {instruction}")
    try:
        reply = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return last_reply

    import re as _re
    clean = _re.sub(r"^```[^\n]*\n", "", reply.strip())
    clean = _re.sub(r"\n```$", "", clean).strip()

    diff = list(difflib.unified_diff(
        original.splitlines(), clean.splitlines(),
        fromfile=f"{fname} (before)", tofile=f"{fname} (after)", lineterm="",
    ))
    if diff:
        print(f"\n  {B}{WH}Diff{R}\n")
        for line in diff[:60]:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"  {GN}{line}{R}")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"  {RE}{line}{R}")
            else:
                print(f"  {DG}{line}{R}")
        if len(diff) > 60:
            print(f"  {DG}... {len(diff) - 60} more lines{R}")
    else:
        info("No changes made.")
        return reply

    if os.environ.get("LUMI_YOLO"):
        ok(f"Auto-writing {path}  (--yolo)")
        confirm = "y"
    else:
        print(f"\n  {YE}!{R}  {GR}Write changes to {WH}{path}{GR}? {DG}[y/N]{R}  ", end="")
        try:
            confirm = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            confirm = "n"

    if confirm == "y":
        backup = path + ".lumi.bak"
        pathlib.Path(backup).write_text(original, encoding="utf-8")
        pathlib.Path(path).write_text(clean, encoding="utf-8")
        ok(f"Written → {path}  {DG}(backup: {os.path.basename(backup)})")
    else:
        info("Changes discarded.")

    memory.replace_last("user", f"[Edited file: {fname}]")
    memory.add("assistant", reply)
    return reply


def cmd_run(last_reply: str) -> str | None:
    import re
    m = re.search(
        r"```(?:python|bash|sh|javascript|js|node)?\n(.*?)```",
        last_reply, re.DOTALL,
    )
    if not m:
        warn("No code block found in last reply.")
        return None
    code = m.group(1).strip()
    lang_m = re.search(r"```(\w+)", last_reply)
    lang   = lang_m.group(1).lower() if lang_m else "python"

    print(f"\n{B}{WH}Running code{R}  {DG}({lang}){R}\n")
    print(f"  {DG}{'─' * 40}{R}")

    try:
        if lang in ("python", "py"):
            result = subprocess.run(["python3", "-c", code], capture_output=True, text=True, timeout=15)
        elif lang in ("bash", "sh"):
            result = subprocess.run(["bash", "-c", code], capture_output=True, text=True, timeout=15)
        elif lang in ("javascript", "js", "node"):
            result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=15)
        else:
            warn(f"Can't run {lang} yet. Supported: python, bash, javascript")
            return None

        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"  {GR}{line}{R}")
        if result.stderr:
            print(f"\n{YE}stderr:{R}")
            for line in result.stderr.splitlines():
                print(f"  {RE}{line}{R}")
        col = GN if result.returncode == 0 else RE
        sym = "✓" if result.returncode == 0 else "✗"
        print(f"\n{col}{sym}{R}  {GR}Exit {result.returncode}{R}\n")
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        fail("Timed out after 15 s")
    except FileNotFoundError as exc:
        fail(f"Runtime not found: {exc}")
    return None


def cmd_diff(last_reply: str, prev_reply: str) -> None:
    if not prev_reply:
        warn("No previous reply to diff against.")
        return
    diff = list(difflib.unified_diff(
        prev_reply.splitlines(), last_reply.splitlines(),
        fromfile="previous", tofile="latest", lineterm="",
    ))
    if not diff:
        info("Replies are identical.")
        return
    print(f"\n{B}{WH}Diff — previous vs latest{R}\n")
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            print(f"  {GN}{line}{R}")
        elif line.startswith("-") and not line.startswith("---"):
            print(f"  {RE}{line}{R}")
        else:
            print(f"  {DG}{line}{R}")
    print()


def cmd_git(
    subcmd: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str,
) -> None:
    sub = subcmd.strip().lower() if subcmd else "status"
    if sub == "status":
        r1  = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
        r2  = subprocess.run(["git", "log", "--oneline", "-5"], capture_output=True, text=True)
        out = (r1.stdout + "\n" + r2.stdout).strip()
        if not out:
            info("Nothing to show (not a git repo or no changes)")
            return
        print(f"\n  {B}{WH}Git status{R}\n")
        for line in out.splitlines():
            print(f"  {GR}{line}{R}")
        print()
    elif sub == "commit":
        r1 = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
        if not r1.stdout.strip():
            r1 = subprocess.run(["git", "diff"], capture_output=True, text=True)
        if not r1.stdout.strip():
            warn("No changes to commit.")
            return
        memory.add("user", (
            "Write a concise git commit message for these changes.\n"
            "Format: short subject line (50 chars max), then optionally a blank line and body.\n"
            "Just return the commit message, nothing else.\n\n"
            f"Diff:\n{r1.stdout[:3000]}"
        ))
        messages = build_messages(system_prompt, memory.get())
        print(f"\n  {B}{WH}Generating commit message...{R}\n")
        try:
            reply = stream_and_render(client, messages, model, name)
        except Exception as exc:
            fail(str(exc))
            memory.pop_last()
            return
        memory.replace_last("user", "[git commit message]")
        memory.add("assistant", reply)
        print(f"\n  {YE}!{R}  {GR}Stage all and commit?  {DG}[y/N]{R}  ", end="")
        try:
            confirm = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            confirm = "n"
        if confirm == "y":
            msg = reply.strip().splitlines()[0][:72]
            subprocess.run(["git", "add", "-A"])
            subprocess.run(["git", "commit", "-m", msg])
    elif sub == "log":
        r1 = subprocess.run(["git", "log", "--oneline", "-15"], capture_output=True, text=True)
        print(f"\n  {B}{WH}Recent commits{R}\n")
        for line in r1.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                print(f"  {CY}{parts[0]}{R}  {GR}{parts[1]}{R}")
        print()
    else:
        ok_git, output = run_git_subcommand(sub)
        if not ok_git:
            warn(output)
            return
        title = f"Git {sub}"
        print(f"\n  {B}{WH}{title}{R}\n")
        for line in output.splitlines():
            print(f"  {GR}{line}{R}")
        print()


# ── /find ─────────────────────────────────────────────────────────────────────

def cmd_find(keyword: str) -> None:
    if not SESSIONS_DIR.exists():
        warn("No saved sessions.")
        return
    hits: list[tuple[str, str, str]] = []
    for f in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            data  = json.loads(f.read_text(encoding="utf-8"))
            msgs  = data.get("messages", data) if isinstance(data, dict) else data
            for m in msgs:
                if keyword.lower() in m.get("content", "").lower():
                    hits.append((f.name, m["role"], m["content"][:200]))
        except Exception:
            continue
    if not hits:
        warn(f"No matches for: {keyword}")
        return
    print(f"\n  {B}{WH}Results for:{R}  {GR}{keyword}{R}  {MU}({len(hits)} found){R}\n")
    for fname, role, snippet in hits[:20]:
        label = f"{PU}Lumi{R}" if role == "assistant" else f"{BL}you{R}"
        print(f"  {DG}{fname}{R}  {label}")
        print(f"{GR}{textwrap.fill(snippet, terminal_width()-6, initial_indent='    ', subsequent_indent='    ')}{R}\n")


# ── /persona ──────────────────────────────────────────────────────────────────

def cmd_persona() -> None:
    override = get_persona_override()
    print(f"\n  {B}{WH}Persona editor{R}  {DG}(leave blank to keep){R}\n")
    new: dict[str, str] = {}
    for key, label in [("name", "Name"), ("creator", "Creator"),
                       ("tone", "Tone"), ("traits", "Traits")]:
        cur         = override.get(key, "")
        cur_display = f"  {MU}[{cur}]{R}" if cur else ""
        try:
            val = input(f"  {GR}{label}:{cur_display}  {BL}›{R}  ").strip()
        except (KeyboardInterrupt, EOFError):
            warn("Cancelled.")
            return
        if val:
            new[key] = val
        elif cur:
            new[key] = cur
    if new:
        set_persona_override(new)
        ok("Persona updated.")
    else:
        clear_persona_override()
        ok("Persona reset to default.")


def cmd_memory_show() -> None:
    facts = get_facts()
    if not facts:
        warn("No facts in long-term memory.")
        return
    print(f"\n  {B}{WH}Long-term memory{R}  {MU}({len(facts)} facts){R}\n")
    for i, f in enumerate(facts):
        print(f"  {CY}{i + 1}.{R}  {GR}{f}{R}")
    print()


def cmd_forget() -> None:
    facts = get_facts()
    if not facts:
        warn("No facts in long-term memory.")
        return
    cmd_memory_show()
    print(f"  {DG}Enter a number to delete, {GR}all{DG} to clear, or Enter to cancel.{R}\n")
    try:
        val = input(f"  {PU}›{R}  ").strip()
    except (KeyboardInterrupt, EOFError):
        return
    if val.lower() == "all":
        clear_facts()
        ok("All long-term memory cleared.")
    else:
        try:
            idx = int(val) - 1
            if remove_fact(idx):
                ok(f"Removed fact #{idx + 1}.")
            else:
                warn("Invalid number.")
        except ValueError:
            info("Cancelled.")


# ── /theme ────────────────────────────────────────────────────────────────────

def cmd_theme(current: str) -> str:
    chosen = list_themes()[0]
    save_theme_name(chosen)
    reload_theme(chosen)
    info(f"ANSI palette is fixed: {get_theme(chosen)['name']}")
    return chosen


# ── Productivity commands ─────────────────────────────────────────────────────

def cmd_todo(arg_str: str) -> None:
    parts = arg_str.strip().split(maxsplit=1) if arg_str.strip() else []
    sub   = parts[0].lower() if parts else "list"
    rest  = parts[1] if len(parts) > 1 else ""

    if sub == "list":
        todos = todo_list()
        if not todos:
            info("No todos yet. Use /todo add <task>")
            return
        print(f"\n  {B}{WH}Todos{R}\n")
        for t in todos:
            check = f"{GN}✓{R}" if t["done"] else f"{DG}○{R}"
            style = DG if t["done"] else WH
            print(f"  {check}  {GR}#{t['id']}{R}  {style}{t['text']}{R}  {DG}{t['created']}{R}")
        print()
    elif sub == "done":
        try:
            idx = int(rest)
            ok(f"Marked #{idx} as done") if todo_done(idx) else warn(f"No todo #{idx}")
        except ValueError:
            warn("Usage: /todo done <id>")
    elif sub == "remove":
        try:
            idx = int(rest)
            ok(f"Removed #{idx}") if todo_remove(idx) else warn(f"No todo #{idx}")
        except ValueError:
            warn("Usage: /todo remove <id>")
    elif sub == "clear":
        todo_clear_done()
        ok("Cleared all completed todos")
    else:
        text = rest or arg_str.strip()
        if text:
            item = todo_add(text)
            ok(f"#{item['id']}  {item['text']}")
        else:
            warn("Usage: /todo [add <task>|list|done <id>|remove <id>|clear]")


def cmd_note(arg_str: str) -> None:
    import re as _re
    parts = arg_str.strip().split(maxsplit=1) if arg_str.strip() else []
    sub   = parts[0].lower() if parts else "list"
    rest  = parts[1] if len(parts) > 1 else ""

    if sub == "list":
        notes = note_list()
        if not notes:
            info("No notes yet. Use /note <text>")
            return
        print(f"\n  {B}{WH}Notes{R}  {DG}({len(notes)}){R}\n")
        for n in notes[-20:]:
            tag = f"  {CY}#{n['tag']}{R}" if n.get("tag") else ""
            print(f"  {GR}#{n['id']}{R}  {DG}{n['created']}{R}{tag}")
            print(f"     {WH}{n['text'][:120]}{R}\n")
    elif sub == "search":
        if not rest:
            warn("Usage: /note search <query>")
            return
        results = note_search(rest)
        if not results:
            info(f"No notes matching '{rest}'")
            return
        print(f"\n  {B}{WH}Search results{R}  {DG}({len(results)}){R}\n")
        for n in results:
            print(f"  {GR}#{n['id']}{R}  {DG}{n['created']}{R}  {WH}{n['text'][:100]}{R}\n")
    elif sub == "remove":
        try:
            idx = int(rest)
            ok(f"Removed note #{idx}") if note_remove(idx) else warn(f"No note #{idx}")
        except ValueError:
            warn("Usage: /note remove <id>")
    elif sub == "export":
        out_path = os.path.expanduser("~/lumi_notes.md")
        pathlib.Path(out_path).write_text(notes_to_markdown(), encoding="utf-8")
        ok(f"Exported to {out_path}")
    else:
        text = arg_str.strip()
        tag  = ""
        m    = _re.match(r"#(\w+)\s+(.*)", text)
        if m:
            tag, text = m.group(1), m.group(2)
        if text:
            item = note_add(text, tag)
            ok(f"Note #{item['id']} saved{f'  #{tag}' if tag else ''}")
        else:
            warn("Usage: /note <text>  or  /note #tag <text>  or  /note list|search|remove|export")


def cmd_weather(location: str = "") -> None:
    sp = Spinner("fetching weather")
    sp.start()
    try:
        result = get_weather(location or "Tashkent")
    finally:
        sp.stop()
    print(f"\n  {CY}◆{R}  {WH}{result}{R}\n")


def cmd_imagine(prompt: str) -> None:
    url = (
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
        "?width=1024&height=1024&nologo=true"
    )
    info("Generating image — opening in browser...")
    webbrowser.open(url)
    ok(f"Opened: {url}")


def cmd_web(
    arg_str: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    if not arg_str:
        warn("Usage: /web <url> [question]")
        return
    parts    = arg_str.split(None, 1)
    target   = parts[0]
    question = parts[1] if len(parts) > 1 else "Summarize this page."
    sp       = Spinner("fetching")
    sp.start()
    content = fetch_url(target)
    sp.stop()
    if content.startswith(("HTTP error", "Could not reach", "Fetch failed")):
        fail(content)
        return
    _remember_context_text(target, content, kind="web")
    memory.add("user", f"[web: {target}] Cached fetched page. Task: {question}")
    messages = build_messages(system_prompt, memory.get(), model=model)
    print_you(f"/web {target}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return
    memory.replace_last("user", f"[web: {target}] {question}")
    memory.add("assistant", raw)


def cmd_image(
    arg_str: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    import base64
    import mimetypes
    parts    = arg_str.split(None, 1)
    path     = parts[0] if parts else ""
    question = parts[1] if len(parts) > 1 else "Describe this image in detail."
    if not path:
        warn("Usage: /image <path> [question]")
        return
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        fail(f"File not found: {path}")
        return
    try:
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
    except Exception as exc:
        fail(f"Could not read image: {exc}")
        return

    vision_msg = {
        "role":    "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text",      "text": question},
        ],
    }
    messages = build_messages(system_prompt, memory.get()) + [vision_msg]
    print_you(f"/image {os.path.basename(path)}")
    sp = Spinner("analyzing image")
    sp.start()
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, max_tokens=1024, temperature=0.7, stream=False,
        )
        sp.stop()
        raw = resp.choices[0].message.content.strip() if resp.choices else ""
        if raw:
            print_lumi_label(name)
            from src.utils.markdown import render as _mdr
            print("\n".join("  " + l for l in _mdr(raw).split("\n")))
            print(f"\n  {MU}{wc(raw)} words{R}")
            memory.add("user", f"[image: {os.path.basename(path)}] {question}")
            memory.add("assistant", raw)
        else:
            fail("No response from model")
    except Exception as exc:
        sp.stop()
        fail(str(exc))


def cmd_context(memory: ShortTermMemory, system_prompt: str, model: str) -> None:
    print(f"\n  {B}{WH}Context window{R}\n")
    report = _session_telemetry.render_context_report()
    lines = report.splitlines()
    for line in lines[1:]:
        key, value = line.split(":", 1)
        print(f"  {CY}{key:<12}{R}{GR}{value}{R}")
    turns = len([m for m in memory.get() if m["role"] == "user"])
    print(f"\n  {DG}{turns} turns  ·  {len(memory.get())} messages in rolling memory{R}\n")


def cmd_redo(
    client, model: str, memory: ShortTermMemory, system_prompt: str,
    name: str, last_msg: str, alt_model: str = "",
) -> str:
    if not last_msg:
        warn("Nothing to redo.")
        return ""
    use_model = alt_model or model
    memory.trim_last_n(2)
    memory.add("user", last_msg)
    messages = build_messages(system_prompt, memory.get())
    if alt_model:
        info(f"Redoing with {alt_model.split('/')[-1]}")
    try:
        raw = stream_and_render(client, messages, use_model, name)
        memory.replace_last("user", last_msg)
        memory.add("assistant", raw)
        return raw
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()
        return ""


def cmd_agent(
    task: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> str:
    from src.agents.agent import run_agent
    if not task:
        warn("Usage: /agent <task description>")
        return ""
    real_model = get_models(get_provider())[0] if model == "council" else model
    yolo       = bool(os.environ.get("LUMI_YOLO"))
    return run_agent(task, client, real_model, memory, system_prompt, yolo)


def cmd_mcp(
    arg_str: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    parts = arg_str.split(None, 2)
    sub   = parts[0] if parts else ""

    if sub in ("list", ""):
        servers = mcp_list()
        if not servers:
            info("No MCP servers configured.  Use: /mcp add <name> <command>")
        else:
            print(f"\n  {B}{WH}MCP servers{R}\n")
            for sname, cfg in servers.items():
                cmd_str = cfg.get("command", "") + " " + " ".join(cfg.get("args", []))
                print(f"  {GN}●{R}  {WH}{sname}{R}  {DG}{cmd_str[:60]}{R}")
            print()
    elif sub == "add":
        if len(parts) < 3:
            warn("Usage: /mcp add <name> <command> [args...]")
            return
        rest     = parts[2].split()
        command  = rest[0]
        mcp_args = rest[1:]
        mcp_add(parts[1], command, mcp_args)
        ok(f"Added MCP server: {parts[1]}")
    elif sub == "remove":
        if len(parts) < 2:
            warn("Usage: /mcp remove <name>")
            return
        ok(f"Removed: {parts[1]}") if mcp_remove(parts[1]) else fail(f"Server not found: {parts[1]}")
    elif sub == "call":
        if len(parts) < 3:
            warn("Usage: /mcp call <server> <tool> [json_args]")
            return
        srv, tool = parts[1], parts[2]
        json_args = parts[3] if len(parts) > 3 else "{}"
        try:
            sess   = mcp_session(srv)
            result = sess.call_tool(tool, json.loads(json_args or "{}"))
            print(f"\n  {GN}MCP result:{R}\n  {result}\n")
        except Exception as exc:
            fail(str(exc))
    elif sub == "tools":
        if len(parts) < 2:
            warn("Usage: /mcp tools <server>")
            return
        try:
            sess  = mcp_session(parts[1])
            tools = sess.list_tools()
            print(f"\n  {B}{WH}Tools — {parts[1]}{R}\n")
            for t in tools:
                print(f"  {CY}{t['name']}{R}  {DG}{t.get('description', '')}{R}")
            print()
        except Exception as exc:
            fail(str(exc))
    else:
        warn(f"Unknown subcommand: {sub}  (list|add|remove|call|tools)")


# ── Voice / clipboard / misc ──────────────────────────────────────────────────

def cmd_listen(seconds: int = 5) -> str:
    if not os.getenv("GROQ_API_KEY"):
        warn("Voice input needs GROQ_API_KEY in .env")
        return ""
    info(f"Recording for {seconds}s… speak now")
    path = record_audio(seconds)
    if not path:
        fail("No recording tool found. Install: arecord (Linux) or sox")
        return ""
    sp   = Spinner("transcribing")
    sp.start()
    text = transcribe_groq(path)
    sp.stop()
    try:
        os.unlink(path)
    except Exception:
        pass
    if text:
        ok(f"Heard: {text}")
    else:
        warn("Could not transcribe audio")
    return text


def cmd_speak(text: str) -> None:
    if not text:
        warn("Nothing to speak.")
        return
    if not speak(text):
        warn("No TTS found. Install: espeak-ng (Linux) or pyttsx3 (pip)")


def cmd_paste() -> str:
    text = clipboard_get()
    if not text:
        warn("Clipboard is empty or not accessible")
        return ""
    ok(f"Pasted {len(text)} chars from clipboard")
    return text


def cmd_copy(text: str) -> None:
    if not text:
        warn("Nothing to copy.")
        return
    if clipboard_set(text):
        ok("Copied to clipboard")
    else:
        warn("Clipboard not accessible. Install: xclip (Linux) or wl-clipboard (Wayland)")


def cmd_screenshot(
    client, model: str, memory: ShortTermMemory, system_prompt: str, name: str,
) -> None:
    info("Taking screenshot…")
    path = take_screenshot()
    if not path:
        fail("No screenshot tool found. Install: scrot or ImageMagick")
        return
    ok(f"Screenshot saved: {path}")
    print(f"\n  {DG}What should Lumi analyze?{R}  ", end="")
    try:
        question = input().strip() or "Describe what you see in this screenshot."
    except (KeyboardInterrupt, EOFError):
        return
    try:
        from openai import OpenAI as _OAI
        img_b64 = encode_image_base64(path)
        vision_client = _OAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY", ""),
        )
        resp  = vision_client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": [
                {"type": "text",      "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}],
            max_tokens=1024,
        )
        reply = resp.choices[0].message.content.strip()
        print_lumi_label(name)
        from src.utils.markdown import render as _mdr
        print("\n".join("  " + l for l in _mdr(reply).split("\n")))
        memory.add("user",      f"[Screenshot]: {question}")
        memory.add("assistant", reply)
    except Exception as exc:
        fail(f"Vision analysis failed: {exc}")
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def cmd_project(path: str, memory: ShortTermMemory) -> None:
    if not path:
        warn("Usage: /project <directory>")
        return
    sp = Spinner("loading project")
    sp.start()
    context = load_project(path)
    sp.stop()
    if context.startswith("Not a directory"):
        fail(context)
        return
    file_blocks = re.findall(r"###\s+([^\n]+)\n```[^\n]*\n(.*?)\n```", context, re.DOTALL)
    if file_blocks:
        _context_cache.remember_project(path, [(rel, body) for rel, body in file_blocks])
    else:
        _remember_context_text(path, context, kind="project")
    memory.add("user", f"[Project loaded: {path}] Cached for retrieval.")
    memory.add("assistant", "Got it. I cached the project context. Ask me anything about the codebase.")
    ok(f"Project loaded: {path}")
    info("Ask me anything about your codebase")


def cmd_pdf(path: str, memory: ShortTermMemory) -> None:
    path = path.strip().strip("'\"")
    if not path:
        warn("Usage: /pdf <path>")
        return
    sp = Spinner("reading PDF")
    sp.start()
    text = read_pdf(path)
    sp.stop()
    if text.startswith("File not found") or text.startswith("Could not"):
        fail(text)
        return
    fname = os.path.basename(path)
    _remember_context_text(fname, text, kind="pdf")
    memory.add("user", f"[PDF: {fname}] Cached for retrieval.")
    memory.add("assistant", f"I've read {fname}. Ask me anything about it.")
    ok(f"PDF loaded: {fname}  ({len(text.split())} words)")


def cmd_standup(
    client, model: str, memory: ShortTermMemory, system_prompt: str, name: str,
) -> None:
    r        = subprocess.run(["git", "log", "--oneline", "--since=24 hours ago"],
                              capture_output=True, text=True)
    git_log  = r.stdout.strip() or "No commits in the last 24 hours"
    todos    = [t for t in todo_list() if not t["done"]]
    todo_txt = "\n".join(f"- {t['text']}" for t in todos[:10]) or "No pending todos"
    memory.add("user", (
        "Generate a short daily standup. Format: Yesterday / Today / Blockers. "
        "Keep it concise and realistic.\n\n"
        f"Recent commits:\n{git_log}\n\nPending todos:\n{todo_txt}"
    ))
    messages = build_messages(system_prompt, memory.get())
    print(f"\n  {B}{WH}Daily Standup{R}\n")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory.replace_last("user", "[standup]")
        memory.add("assistant", reply)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()


def cmd_timer(arg_str: str) -> None:
    import re as _re
    m = _re.match(r"(\d+)\s*(m|min|s|sec|h|hr)?", arg_str.strip().lower())
    if not m:
        warn("Usage: /timer 25m  or  /timer 5s  or  /timer 1h")
        return
    val  = int(m.group(1))
    unit = m.group(2) or "m"
    if unit.startswith("s"):
        secs = val
    elif unit.startswith("h"):
        secs = val * 3600
    else:
        secs = val * 60
    ok(f"Timer set: {arg_str.strip()}")

    def _tick() -> None:
        time.sleep(secs)
        print(f"\n\a  {GN}⏰{R}  {WH}Timer done: {arg_str.strip()}{R}\n  ", end="", flush=True)
        try:
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", "Lumi Timer", f"{arg_str.strip()} is up!"],
                               capture_output=True)
            elif shutil.which("osascript"):
                subprocess.run(["osascript", "-e",
                    f'display notification "{arg_str.strip()} is up!" with title "Lumi"'],
                    capture_output=True)
        except Exception:
            pass

    threading.Thread(target=_tick, daemon=True).start()


def cmd_draft(
    arg_str: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    if not arg_str.strip():
        warn("Usage: /draft email to boss about deadline")
        return
    memory.add("user", (
        "Draft the following message. Match tone to medium "
        "(email=formal, slack=casual, text=brief). "
        "Return just the message, no meta-commentary.\n\n"
        f"Request: {arg_str}"
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Draft: {arg_str}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory.replace_last("user", f"[draft: {arg_str}]")
        memory.add("assistant", reply)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()


def cmd_comment(
    target: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str, last_reply: str,
) -> None:
    import re as _re
    if target and os.path.exists(os.path.expanduser(target.strip())):
        code  = pathlib.Path(target.strip()).expanduser().read_text(encoding="utf-8", errors="replace")
        label = os.path.basename(target.strip())
    elif last_reply:
        m     = _re.search(r"```[^\n]*\n(.*?)```", last_reply, _re.DOTALL)
        code  = m.group(1) if m else last_reply
        label = "last reply"
    else:
        warn("No code to comment. Use /comment <file> or after a code reply.")
        return

    memory.add("user", (
        "Add clear helpful comments and docstrings to this code. "
        "Explain the 'why', not just the 'what'. Keep existing code unchanged.\n\n"
        f"```\n{code[:5000]}\n```\n\nReturn only the commented code."
    ))
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Add comments to {label}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory.replace_last("user", f"[comment: {label}]")
        memory.add("assistant", reply)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()


def cmd_lang(language: str, current_prompt: str) -> str:
    if not language or language.lower() == "off":
        if "[LANGUAGE LEARNING" in current_prompt:
            new = current_prompt.split("[LANGUAGE LEARNING")[0].strip()
            ok("Language learning mode off")
            return new
        info("Usage: /lang <language>  (e.g. /lang spanish)  |  /lang off to disable")
        return current_prompt
    suffix = (
        f"\n\n[LANGUAGE LEARNING MODE: {language.upper()}]\n"
        f"Naturally mix in {language} words and phrases. "
        f"Add translation in parentheses first time. "
        f"Occasionally invite the user to respond in {language}."
    )
    ok(f"Language learning mode: {language.title()}")
    return current_prompt.split("[LANGUAGE LEARNING")[0].strip() + suffix


def cmd_github(
    subcmd: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    import urllib.request as _ur
    token = os.getenv("GITHUB_TOKEN", "")
    sub   = subcmd.strip().lower() if subcmd else "issues"
    if sub != "issues":
        warn(f"Unknown: {sub}  —  try /github issues")
        return
    if not token:
        warn("Add GITHUB_TOKEN=ghp_... to .env for GitHub integration")
        return
    try:
        req = _ur.Request(
            "https://api.github.com/issues?filter=assigned&state=open&per_page=20",
            headers={"Authorization": f"token {token}",
                     "Accept": "application/vnd.github.v3+json"},
        )
        with _ur.urlopen(req, timeout=8) as r:
            issues = json.loads(r.read())
        if not issues:
            info("No open issues assigned to you")
            return
        print(f"\n  {B}{WH}Open Issues{R}\n")
        for iss in issues[:15]:
            repo = iss.get("repository", {}).get("full_name", "")
            print(f"  {CY}#{iss['number']}{R}  {WH}{iss['title']}{R}  {DG}{repo}{R}")
        print()
        issues_text = "\n".join(f"#{i['number']}: {i['title']}" for i in issues[:15])
        memory.add("user", f"Which of these GitHub issues should I work on first and why?\n\n{issues_text}")
        messages = build_messages(system_prompt, memory.get())
        try:
            reply = stream_and_render(client, messages, model, name)
            memory.replace_last("user", "[github issues]")
            memory.add("assistant", reply)
        except Exception as exc:
            fail(str(exc))
            memory.pop_last()
    except Exception as exc:
        fail(f"GitHub API error: {exc}")


def cmd_data(
    path: str, client, model: str, memory: ShortTermMemory,
    system_prompt: str, name: str,
) -> None:
    path = path.strip().strip("'\"")
    if not path:
        warn("Usage: /data <file.csv|file.json>")
        return
    sp = Spinner("loading data")
    sp.start()
    context = analyze_data_file(path)
    sp.stop()
    if context.startswith("File not found") or context.startswith("Could not"):
        fail(context)
        return
    fname = os.path.basename(path)
    _remember_context_text(fname, context, kind="data")
    memory.add("user", f"[Data: {fname}] Cached data summary. Analyze the key insights.")
    messages = build_messages(system_prompt, memory.get(), model=model)
    print_you(f"Analyze {fname}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory.replace_last("user", f"[data: {fname}]")
        memory.add("assistant", reply)
    except Exception as exc:
        fail(str(exc))
        memory.pop_last()


# ── Mood tracker ──────────────────────────────────────────────────────────────

_MOOD_PATH = pathlib.Path("data/memory/mood_log.json")

_compact_mode: bool = False


def toggle_compact() -> bool:
    global _compact_mode
    _compact_mode = not _compact_mode
    return _compact_mode


def log_mood(emotion: str, turn: int) -> None:
    if not emotion:
        return
    try:
        _MOOD_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            log = json.loads(_MOOD_PATH.read_text(encoding="utf-8"))
        except Exception:
            log = []
        log.append({"ts": datetime.now().isoformat(), "emotion": emotion, "turn": turn})
        _MOOD_PATH.write_text(json.dumps(log[-100:], indent=2), encoding="utf-8")
    except Exception:
        pass


def check_mood_pattern() -> str | None:
    try:
        log    = json.loads(_MOOD_PATH.read_text(encoding="utf-8"))
        recent = log[-10:]
        neg    = sum(1 for e in recent if e.get("emotion") in ("frustrated", "sad", "confused"))
        if neg >= 6:
            return "hey, you've seemed pretty stressed lately — everything good?"
    except Exception:
        pass
    return None


# ── CLI argument parser ───────────────────────────────────────────────────────

def _parse_args():
    return parse_cli_args(LUMI_VERSION)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:  # noqa: C901
    cli = _parse_args()

    if cli.version:
        print(f"Lumi {LUMI_VERSION}")
        sys.exit(0)

    # ── TUI mode (default unless bypassed) ────────────────────────────────────
    _tui_bypass = (
        cli.print_mode or cli.query or cli.no_tui
        or cli.list_sessions or cli.delete_session or cli.help
    )
    if not _tui_bypass:
        try:
            from src.tui.app import launch as _tui_launch
            _tui_launch()
            return
        except ImportError:
            print(f"  {YE}▲  textual not installed — falling back to CLI mode...{R}\n")
        except Exception as _te:
            print(f"  {RE}✗  TUI error: {_te}{R}\n  {DG}falling back to CLI mode...{R}\n")

    if cli.help:
        print_cli_help(LUMI_VERSION, bold=B, reset=R)
        sys.exit(0)

    if cli.list_sessions:
        sessions = list_sessions()
        if not sessions:
            print("  No saved sessions found.")
        else:
            for i, s in enumerate(sessions, 1):
                print(f"  {i:<4}  {s.get('id','?'):<36}  {s.get('date','?')}")
            print()
        sys.exit(0)

    if cli.delete_session:
        from src.memory.conversation_store import delete_session
        try:
            delete_session(cli.delete_session)
            print(f"  Deleted session: {cli.delete_session}")
        except Exception as exc:
            print(f"  Error: {exc}")
        sys.exit(0)

    # ── Pipe input ─────────────────────────────────────────────────────────────
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            os.environ.setdefault("LUMI_PIPE_INPUT", piped)

    history_setup()

    persona          = load_persona()
    persona_override = get_persona_override()
    system_prompt    = make_system_prompt(persona, persona_override)
    memory           = ShortTermMemory(max_turns=20)

    if cli.provider:
        prov = cli.provider.lower()
        if prov in get_available_providers():
            set_provider(prov)
        else:
            print(f"  Unknown provider: {prov}  (available: {', '.join(get_available_providers())})")
            sys.exit(1)

    client = get_client()
    name   = persona_override.get("name") or persona.get("name", "Lumi")

    if cli.model:
        if cli.model == "council":
            current_model = "council"
        else:
            available_models = get_models(get_provider())
            if cli.model in available_models:
                current_model = cli.model
            else:
                matches = [m for m in available_models if cli.model.lower() in m.lower()]
                current_model = matches[0] if matches else cli.model
    else:
        provider = get_provider()
        current_model = pick_startup_model(provider, get_models(provider))

    # ── System prompt customisation ───────────────────────────────────────────
    if cli.system_prompt:
        system_prompt = cli.system_prompt
    elif cli.system_prompt_file:
        try:
            system_prompt = pathlib.Path(cli.system_prompt_file).expanduser().read_text()
        except Exception as exc:
            print(f"  Error reading system prompt file: {exc}")
            sys.exit(1)

    if cli.append_system_prompt:
        system_prompt = system_prompt + "\n\n" + cli.append_system_prompt
    elif cli.append_system_prompt_file:
        try:
            extra         = pathlib.Path(cli.append_system_prompt_file).expanduser().read_text()
            system_prompt = system_prompt + "\n\n" + extra
        except Exception as exc:
            print(f"  Error reading append file: {exc}")
            sys.exit(1)

    if cli.yolo:
        os.environ["LUMI_YOLO"] = "1"
    if cli.verbose:
        os.environ["LUMI_VERBOSE"] = "1"

    # ── Session state ─────────────────────────────────────────────────────────
    current_theme      = load_theme_name()
    multiline          = False
    last_msg: str | None     = None
    last_reply: str | None   = None
    prev_reply: str | None   = None
    # Single-element list so cmd_lang can mutate it from a nested scope
    system_prompt_ref  = [system_prompt]
    turns              = 0
    response_mode: str | None = None
    AUTOSAVE_EVERY     = 5
    AUTOREMEMBER_EVERY = 8
    max_turns          = cli.max_turns

    if cli.rebirth:
        profile = load_rebirth_profile()
        defaults = profile.get("defaults", {}) if isinstance(profile.get("defaults"), dict) else {}
        desired_mode = str(defaults.get("response_mode", "detailed")).strip().lower()
        if desired_mode in {"short", "detailed", "bullets"}:
            response_mode = desired_mode
        desired_compact = bool(defaults.get("compact", False))
        if desired_compact != _compact_mode:
            toggle_compact()
        info(f"Rebirth defaults enabled ({rebirth_status_summary()})")

    # ── Resume ────────────────────────────────────────────────────────────────
    _load_session = None
    if cli.resume_latest or (cli.resume and cli.resume.lower() == "latest"):
        _load_session = "latest"
    elif cli.resume:
        _load_session = cli.resume

    if _load_session:
        try:
            h = load_latest() if _load_session == "latest" else load_by_name(_load_session)
            if h:
                memory.set_history(h)
                info(f"Resumed session: {_load_session}  ({len(h)} messages)")
        except Exception:
            pass

    # ── Non-interactive (--print) mode ────────────────────────────────────────
    if cli.print_mode and cli.query:
        piped_ctx = os.environ.get("LUMI_PIPE_INPUT", "")
        q         = (piped_ctx + "\n\n" + cli.query).strip() if piped_ctx else cli.query
        memory.add("user", q)
        messages = build_messages(system_prompt, memory.get())
        try:
            if current_model == "council":
                reply, _ = council_ask(messages, q, stream=False, debate=True, refine=True)
            else:
                resp  = client.chat.completions.create(
                    model=current_model, messages=messages,
                    max_tokens=1024, temperature=0.7, stream=False,
                )
                reply = resp.choices[0].message.content.strip()
            if cli.output_format == "json":
                print(json.dumps({"query": q, "response": reply, "model": current_model}))
            else:
                print(reply)
        except Exception as exc:
            if os.environ.get("LUMI_VERBOSE"):
                print(f"Error: {exc}", file=sys.stderr)
            else:
                print(f"Error: {str(exc)[:120]}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # ── LUMI.md project context ───────────────────────────────────────────────
    for _md_path in [pathlib.Path("LUMI.md"), pathlib.Path("lumi.md")]:
        if _md_path.exists():
            _lumi_md = _md_path.read_text(encoding="utf-8").strip()
            system_prompt += f"\n\n--- Project context (LUMI.md) ---\n{_lumi_md}"
            info(f"Loaded LUMI.md project context ({len(_lumi_md)} chars)")
            break

    _loaded_plugins = load_plugins()
    if _loaded_plugins:
        info(f"Plugins: {', '.join(_loaded_plugins)}")

    draw_header(
        current_model, 0,
        "council" if current_model == "council" else get_provider(),
    )
    print_welcome(name)

    _pending_input = cli.query or os.environ.get("LUMI_PIPE_INPUT", "")

    threading.Thread(
        target=health_check, args=(get_available_providers(),), daemon=True
    ).start()

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:

        # ── Read input ────────────────────────────────────────────────────────
        try:
            div()
            if _pending_input:
                user_input     = _pending_input
                _pending_input = ""
                print(f"  {PU}›{R}  {user_input}")
            else:
                user_input = (
                    read_multiline().strip()
                    if multiline
                    else input(f"  {PU}›{R}  ").strip()
                )
        except (KeyboardInterrupt, EOFError):
            history_save()
            ok(f"Saved → {save(memory.get())}")
            if client and memory.get():
                auto_summarize_and_save(memory.get(), client, current_model)
            ok("Goodbye!", "◆", BL)
            sys.exit(0)

        if not user_input:
            continue

        cmd = user_input.split()[0] if user_input.startswith("/") else None

        # ── Slash command dispatch ────────────────────────────────────────────

        if cmd in ("/quit", "/exit"):
            history_save()
            ok(f"Saved → {save(memory.get())}")
            if client and memory.get():
                auto_summarize_and_save(memory.get(), client, current_model)
            ok("Goodbye!", "◆", BL)
            break

        if cmd == "/help":
            print_help()
            continue

        if cmd == "/clear":
            memory.clear()
            last_msg = last_reply = prev_reply = None
            turns    = 0
            draw_header(
                current_model, 0,
                "council" if current_model == "council" else get_provider(),
            )
            print_welcome(name)
            continue

        if cmd == "/save":
            parts = user_input.split(maxsplit=1)
            sname = parts[1].strip() if len(parts) > 1 else ""
            p = save(memory.get(), sname)
            ok(f"Saved → {p.name}")
            continue

        if cmd == "/load":
            parts = user_input.split(maxsplit=1)
            sname = parts[1].strip() if len(parts) > 1 else ""
            h     = load_by_name(sname) if sname else load_latest()
            if h:
                memory.set_history(h)
                turns = len(h) // 2
                draw_header(
                    current_model, turns,
                    "council" if current_model == "council" else get_provider(),
                )
                ok(f"Loaded {len(h)} messages" + (f" — {sname}" if sname else ""))
            else:
                warn("No saved conversations found.")
            continue

        if cmd == "/sessions":
            s = list_sessions()
            if s:
                print(f"\n  {B}{WH}Saved sessions{R}  {DG}({len(s)} total){R}\n")
                for x in s:
                    print(f"  {DG}·{R}  {WH}{x['name']:<28}{R}  {GR}{x['date']}{R}  {DG}{x['msgs']} msgs{R}")
                print()
            else:
                warn("No saved sessions.")
            continue

        if cmd == "/export":
            if not memory.get():
                warn("Nothing to export yet.")
            else:
                ok(f"Exported → {export_md(memory.get(), name)}")
            continue

        if cmd == "/undo":
            if len(memory.get()) >= 2:
                memory.trim_last_n(2)
                turns = max(0, turns - 1)
                ok("Last exchange removed from memory.")
            else:
                warn("Nothing to undo.")
            continue

        if cmd == "/retry":
            if last_msg:
                try:
                    print(f"\n  {GR}What was wrong? (Enter to just resend){R}")
                    feedback = input(f"  {PU}›{R}  ").strip()
                except (KeyboardInterrupt, EOFError):
                    feedback = ""
                user_input = last_msg
                if feedback:
                    user_input = (
                        f"{last_msg}\n\n[My previous response wasn't right because: "
                        f"{feedback}. Please try again with that in mind.]"
                    )
                info("Retrying…")
                if len(memory.get()) >= 2:
                    memory.trim_last_n(2)
                    turns = max(0, turns - 1)
            else:
                warn("Nothing to retry.")
                continue

        if cmd == "/summarize":
            if not memory.get():
                warn("Nothing to summarize yet.")
                continue
            q = "Summarize our conversation so far in a few bullet points."
            memory.add("user", q)
            messages = build_messages(system_prompt, memory.get())
            print_you(q)
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as exc:
                fail(str(exc))
                memory.pop_last()
                continue
            memory.replace_last("user", q)
            memory.add("assistant", raw_reply)
            last_reply = raw_reply
            turns     += 1
            print()
            continue

        if cmd == "/tl;dr":
            if not last_reply:
                warn("No reply to summarize yet.")
                continue
            sp = Spinner("summarizing")
            sp.start()
            summary = silent_call(
                client,
                f"Summarize this in ONE sentence (max 20 words):\n\n{last_reply}",
                current_model, max_tokens=60,
            )
            sp.stop()
            if summary:
                print(f"\n  {PU}✦{R}  {WH}{summary}{R}\n")
            else:
                warn("Couldn't summarize.")
            continue

        if cmd == "/more":
            if not last_reply:
                warn("Nothing to expand on yet.")
                continue
            memory.add("user", "[User wants more detail on the last response.]")
            messages = build_messages(system_prompt, memory.get())
            print_you("Tell me more...")
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as exc:
                fail(str(exc))
                memory.pop_last()
                continue
            memory.replace_last("user", "Tell me more.")
            memory.add("assistant", raw_reply)
            last_reply = raw_reply
            turns     += 1
            print()
            continue

        if cmd == "/rewrite":
            if not last_reply:
                warn("Nothing to rewrite yet.")
                continue
            memory.add("user", "[Rewrite the last response completely differently.]")
            messages = build_messages(system_prompt, memory.get())
            print_you("Rewrite that differently...")
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as exc:
                fail(str(exc))
                memory.pop_last()
                continue
            memory.replace_last("user", "Rewrite that differently.")
            memory.add("assistant", raw_reply)
            last_reply = raw_reply
            turns     += 1
            print()
            continue

        if cmd == "/fix":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /fix <error message>")
            else:
                r = cmd_fix(parts[1].strip(), client, current_model,
                            memory, system_prompt, name, last_reply or "")
                if r:
                    last_reply = r
                    turns     += 1
                    print()
            continue

        if cmd == "/explain":
            parts  = user_input.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            r = cmd_explain(target, client, current_model,
                            memory, system_prompt, name, last_reply or "")
            if r:
                last_reply = r
                turns     += 1
                print()
            continue

        if cmd == "/review":
            parts  = user_input.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            r = cmd_review(target, client, current_model,
                           memory, system_prompt, name, last_reply or "")
            if r:
                last_reply = r
                turns     += 1
                print()
            continue

        if cmd == "/file":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /file <path>")
            else:
                r = cmd_file(parts[1].strip(), client, current_model,
                             memory, system_prompt, name)
                if r:
                    last_reply = r
                    turns     += 1
                    print()
            continue

        if cmd == "/find":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /find <keyword>")
            else:
                cmd_find(parts[1].strip())
            continue

        if cmd == "/remember":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /remember <fact>")
            else:
                n = add_fact(parts[1].strip())
                system_prompt = make_system_prompt(persona, get_persona_override())
                ok(f"Remembered — {n} fact{'s' if n != 1 else ''} stored.")
            continue

        if cmd == "/memory":
            cmd_memory_show()
            continue

        if cmd == "/forget":
            cmd_forget()
            system_prompt = make_system_prompt(persona, get_persona_override())
            continue

        if cmd == "/persona":
            cmd_persona()
            persona_override = get_persona_override()
            name             = persona_override.get("name") or persona.get("name", "Lumi")
            system_prompt    = make_system_prompt(persona, persona_override)
            draw_header(
                current_model, turns,
                "council" if current_model == "council" else get_provider(),
            )
            continue

        if cmd in ("/short", "/detailed", "/bullets"):
            response_mode = cmd[1:]
            labels = {"short": "concise", "detailed": "in-depth", "bullets": "as bullet points"}
            info(f"Next reply will be {labels[response_mode]}.")
            continue

        if cmd == "/translate":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /translate <language>")
            elif not last_reply:
                warn("No reply to translate yet.")
            else:
                lang = parts[1].strip()
                memory.add("user", f"Translate your last response into {lang}. Output only the translation.")
                messages = build_messages(system_prompt, memory.get())
                print_you(f"Translate to {lang}")
                try:
                    raw_reply = stream_and_render(client, messages, current_model, name)
                except Exception as exc:
                    fail(str(exc))
                    memory.pop_last()
                    continue
                memory.replace_last("user", f"Translate to {lang}")
                memory.add("assistant", raw_reply)
                last_reply = raw_reply
                turns     += 1
                print()
            continue

        if cmd == "/imagine":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /imagine <prompt>")
            else:
                cmd_imagine(parts[1].strip())
            continue

        if cmd == "/theme":
            current_theme = cmd_theme(current_theme)
            draw_header(
                current_model, turns,
                "council" if current_model == "council" else get_provider(),
            )
            continue

        if cmd == "/model":
            new_model, new_provider = pick_model(current_model)
            current_model = new_model
            if new_provider != "council":
                client = get_client()
            draw_header(
                current_model, turns,
                "council" if new_provider == "council" else get_provider(),
            )
            label = PROVIDER_LABELS.get(new_provider, (new_provider,))[0]
            ok(f"Model → {current_model.split('/')[-1]}  ({label})")
            continue

        if cmd == "/multi":
            multiline = not multiline
            info(f"Multi-line input {'on' if multiline else 'off'}")
            continue

        if cmd == "/council":
            from src.agents.council import _get_available_agents
            if not _get_available_agents():
                fail("No council agents available — add API keys to .env")
                continue
            parts    = user_input.split(maxsplit=1)
            show_ind = False
            if len(parts) > 1 and parts[1].startswith("--show"):
                show_ind = True
                q        = parts[1][6:].strip() if len(parts[1]) > 6 else last_msg or ""
            elif len(parts) > 1:
                q = parts[1].strip()
            else:
                q = last_msg or ""
            if not q:
                warn("Usage: /council <question>")
                continue
            _coding   = is_complex_coding_task(q)
            _sys_p    = make_system_prompt(persona, override=get_persona_override(), coding_mode=_coding)
            _msgs     = build_messages(_sys_p, memory.get()) + [{"role": "user", "content": q}]
            last_reply = cmd_council(q, _msgs, name, show_ind)
            if last_reply:
                memory.add("user", q)
                memory.add("assistant", last_reply)
                turns += 1
            continue

        if cmd == "/web":
            cmd_arg = user_input.split(maxsplit=1)[1] if " " in user_input else ""
            cmd_web(cmd_arg, client, current_model, memory, system_prompt, name)
            turns += 1
            print()
            continue

        if cmd == "/image":
            cmd_arg = user_input.split(maxsplit=1)[1] if " " in user_input else ""
            cmd_image(cmd_arg, client, current_model, memory, system_prompt, name)
            turns += 1
            print()
            continue

        if cmd == "/context":
            cmd_context(memory, system_prompt, current_model)
            continue

        if cmd == "/redo":
            parts = user_input.split(maxsplit=2)
            alt   = parts[1] if len(parts) > 1 else ""
            raw   = cmd_redo(client, current_model, memory, system_prompt,
                             name, last_msg or "", alt)
            if raw:
                last_reply = raw
                turns     += 1
            print()
            continue

        if cmd == "/agent":
            cmd_arg = user_input.split(maxsplit=1)[1] if " " in user_input else ""
            reply = cmd_agent(cmd_arg, client, current_model, memory, system_prompt, name)
            if reply:
                last_reply = reply
                turns     += 1
            print()
            continue

        if cmd == "/mcp":
            cmd_arg = user_input.split(maxsplit=1)[1] if " " in user_input else ""
            cmd_mcp(cmd_arg, client, current_model, memory, system_prompt, name)
            continue

        if cmd == "/plugins":
            sub = (user_input.split(maxsplit=1)[1:] or [""])[0].strip()
            if sub == "reload":
                loaded = load_plugins()
                ok(f"Reloaded: {', '.join(loaded) or 'none'}")
            elif sub == "audit":
                print("\n  " + render_plugin_audit_report().replace("\n", "\n  ") + "\n")
            elif sub in {"inspect", "details", "verbose"}:
                details = describe_plugins()
                if not details:
                    info(f"No plugins loaded.  Drop .py files in {PLUGINS_DIR}")
                else:
                    print(f"\n  {B}{WH}Loaded plugins{R}\n")
                    for item in details:
                        perms = ", ".join(item["permissions"]) if item["permissions"] else "none declared"
                        print(f"  {PU}{item['name']}  v{item['version']}{R}")
                        print(f"  {GR}{item['description']}{R}")
                        print(f"  {DG}commands:{R} {', '.join(item['commands'])}")
                        print(f"  {DG}permissions:{R} {perms}\n")
            else:
                cmds = get_commands()
                if cmds:
                    print(f"\n  {B}{WH}Loaded plugins{R}\n")
                    for c, d in cmds.items():
                        print(f"  {PU}{c:<20}{R}  {GR}{d}{R}")
                    print()
                else:
                    info(f"No plugins loaded.  Drop .py files in {PLUGINS_DIR}")
            continue

        if cmd == "/permissions":
            sub = (user_input.split(maxsplit=1)[1:] or ["summary"])[0].strip().lower() or "summary"
            if sub not in {"summary", "all", "plugins"}:
                warn("Usage: /permissions [all|plugins]")
                continue
            print("\n  " + render_permission_report(sub).replace("\n", "\n  ") + "\n")
            continue

        if cmd == "/status":
            try:
                provider_name = get_provider()
            except Exception:
                provider_name = ""
            print(
                "\n  "
                + build_status_report(
                    base_dir=pathlib.Path.cwd(),
                    provider=provider_name,
                    model=current_model,
                    session_turns=turns,
                    short_term_stats=memory.stats(),
                    recent_commands=[],
                ).replace("\n", "\n  ")
                + "\n"
            )
            continue

        if cmd == "/doctor":
            try:
                provider_name = get_provider()
            except Exception:
                provider_name = ""
            print(
                "\n  "
                + build_doctor_report(
                    base_dir=pathlib.Path.cwd(),
                    provider=provider_name,
                    model=current_model,
                    configured_providers=get_available_providers(),
                ).replace("\n", "\n  ")
                + "\n"
            )
            continue

        if cmd == "/onboard":
            print(
                "\n  "
                + build_onboarding_report(
                    base_dir=pathlib.Path.cwd(),
                    configured_providers=get_available_providers(),
                ).replace("\n", "\n  ")
                + "\n"
            )
            continue

        if cmd == "/rebirth":
            sub = (user_input.split(maxsplit=1)[1:] or ["status"])[0].strip().lower() or "status"
            if sub in {"status", "report"}:
                print("\n  " + render_rebirth_report().replace("\n", "\n  ") + "\n")
                continue
            if sub in {"on", "enable", "apply"}:
                profile = load_rebirth_profile()
                defaults = profile.get("defaults", {}) if isinstance(profile.get("defaults"), dict) else {}
                desired_mode = str(defaults.get("response_mode", "detailed")).strip().lower()
                if desired_mode in {"short", "detailed", "bullets"}:
                    response_mode = desired_mode
                compact = bool(defaults.get("compact", False))
                if compact != _compact_mode:
                    toggle_compact()
                print(
                    "\n  "
                    + f"Rebirth profile enabled ({rebirth_status_summary()})\n"
                    + f"  response mode: {response_mode or 'default'}\n"
                    + f"  compact mode:  {'on' if _compact_mode else 'off'}\n"
                )
                continue
            if sub in {"off", "disable"}:
                response_mode = None
                if _compact_mode:
                    toggle_compact()
                print("\n  Rebirth profile disabled (response mode reset, compact off).\n")
                continue
            warn("Usage: /rebirth [status|on|off]")
            continue

        if cmd == "/benchmark":
            sub = (user_input.split(maxsplit=1)[1:] or ["list"])[0].strip().lower() or "list"
            if sub != "list":
                warn("Usage: /benchmark [list]")
                continue
            print("\n  " + render_benchmark_catalog(load_benchmark_scenarios()).replace("\n", "\n  ") + "\n")
            continue

        if cmd == "/lumi.md":
            sub = (user_input.split(maxsplit=1)[1:] or [""])[0].strip()
            if sub == "show":
                md_f = pathlib.Path("LUMI.md")
                if md_f.exists():
                    print(f"\n  {GR}{md_f.read_text()}{R}\n")
                else:
                    warn("No LUMI.md in current directory")
            elif sub == "create":
                if pathlib.Path("LUMI.md").exists():
                    warn("LUMI.md already exists")
                else:
                    pathlib.Path("LUMI.md").write_text(
                        "# Project Context\n\n## Stack\n\n## Conventions\n\n## Rules\n",
                        encoding="utf-8",
                    )
                    ok("Created LUMI.md — edit it, then restart Lumi to load it")
            else:
                info("Usage: /lumi.md show | /lumi.md create")
            continue

        if cmd == "/search":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                warn("Usage: /search <query>")
                continue
            query = parts[1].strip()
            sp = Spinner("searching")
            sp.start()
            try:
                results, _ = search_display(query)
            except Exception as exc:
                sp.stop()
                fail(str(exc))
                continue
            sp.stop()
            if not results:
                warn("No results found.")
                continue
            print(f"\n  {B}{WH}Results for:{R}  {GR}{query}{R}\n")
            for i, r in enumerate(results, 1):
                print(f"  {CY}{i}.{R}  {WH}{r['title']}{R}")
                print(f"      {MU}{r['url']}{R}")
                if r.get("snippet"):
                    print(f"{GR}{textwrap.fill(r['snippet'], terminal_width()-8, initial_indent='      ', subsequent_indent='      ')}{R}")
                print()
            ctx = search(query, fetch_top=True)
            _remember_context_text(query, ctx, kind="search")
            memory.add("user", f"[search: {query}] Cached search results. Summarize the key findings briefly.")
            messages = build_messages(system_prompt, memory.get(), model=current_model)
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as exc:
                fail(str(exc))
                memory.pop_last()
                continue
            memory.replace_last("user", f"Search: {query}")
            memory.add("assistant", raw_reply)
            last_reply = raw_reply
            turns     += 1
            print()
            continue

        if cmd == "/run":
            if not last_reply:
                warn("No reply yet to run code from.")
                continue
            output = cmd_run(last_reply)
            if output:
                memory.add("user",      f"[Code output]: {output[:500]}")
                memory.add("assistant", "[Output received]")
            continue

        if cmd == "/edit":
            parts = user_input.split(maxsplit=1)
            path  = parts[1].strip() if len(parts) > 1 else ""
            if not path:
                print(f"\n  {DG}Path to file:{R}  ", end="")
                try:
                    path = input().strip()
                except (KeyboardInterrupt, EOFError):
                    continue
            last_reply = cmd_edit(path, client, current_model, memory,
                                  system_prompt, name, last_reply or "")
            turns += 1
            continue

        if cmd == "/diff":
            cmd_diff(last_reply or "", prev_reply or "")
            continue

        if cmd == "/git":
            parts  = user_input.split(maxsplit=1)
            subcmd = parts[1].strip() if len(parts) > 1 else "status"
            cmd_git(subcmd, client, current_model, memory,
                    system_prompt, name, last_reply or "")
            continue

        if cmd == "/cost":
            cmd_cost()
            continue

        if cmd == "/todo":
            parts = user_input.split(maxsplit=1)
            cmd_todo(parts[1] if len(parts) > 1 else "list")
            continue

        if cmd == "/note":
            parts = user_input.split(maxsplit=1)
            cmd_note(parts[1] if len(parts) > 1 else "list")
            continue

        if cmd == "/weather":
            parts = user_input.split(maxsplit=1)
            cmd_weather(parts[1].strip() if len(parts) > 1 else "")
            continue

        if cmd == "/listen":
            parts = user_input.split(maxsplit=1)
            try:
                secs = int(parts[1]) if len(parts) > 1 else 5
            except ValueError:
                secs = 5
            heard = cmd_listen(secs)
            if heard:
                last_msg = heard
                memory.add("user", heard)
                messages = build_messages(system_prompt, memory.get())
                print_you(heard)
                try:
                    raw_reply, client, current_model, _ = stream_with_fallback(
                        client, messages, current_model, name,
                        get_available_providers(), get_provider(),
                    )
                    memory.replace_last("user", heard)
                    memory.add("assistant", raw_reply)
                    prev_reply = last_reply
                    last_reply = raw_reply
                    turns     += 1
                except Exception as exc:
                    fail(str(exc))
                    memory.pop_last()
            continue

        if cmd == "/speak":
            cmd_speak(last_reply or "")
            continue

        if cmd == "/paste":
            pasted = cmd_paste()
            if pasted:
                last_msg = pasted
                memory.add("user", pasted)
                messages = build_messages(system_prompt, memory.get())
                print_you(f"[Clipboard: {pasted[:60]}...]")
                try:
                    raw_reply, client, current_model, _ = stream_with_fallback(
                        client, messages, current_model, name,
                        get_available_providers(), get_provider(),
                    )
                    memory.replace_last("user", pasted)
                    memory.add("assistant", raw_reply)
                    prev_reply = last_reply
                    last_reply = raw_reply
                    turns     += 1
                except Exception as exc:
                    fail(str(exc))
                    memory.pop_last()
            continue

        if cmd == "/copy":
            cmd_copy(last_reply or "")
            continue

        if cmd == "/screenshot":
            cmd_screenshot(client, current_model, memory, system_prompt, name)
            turns += 1
            continue

        if cmd == "/project":
            parts = user_input.split(maxsplit=1)
            path  = parts[1].strip() if len(parts) > 1 else ""
            if not path:
                print(f"\n  {DG}Project path:{R}  ", end="")
                try:
                    path = input().strip()
                except (KeyboardInterrupt, EOFError):
                    continue
            cmd_project(path, memory)
            continue

        if cmd == "/pdf":
            parts = user_input.split(maxsplit=1)
            cmd_pdf(parts[1].strip() if len(parts) > 1 else "", memory)
            continue

        if cmd == "/standup":
            cmd_standup(client, current_model, memory, system_prompt, name)
            turns += 1
            continue

        if cmd == "/timer":
            parts = user_input.split(maxsplit=1)
            cmd_timer(parts[1].strip() if len(parts) > 1 else "25m")
            continue

        if cmd == "/draft":
            parts = user_input.split(maxsplit=1)
            cmd_draft(parts[1].strip() if len(parts) > 1 else "",
                      client, current_model, memory, system_prompt, name)
            turns += 1
            continue

        if cmd == "/comment":
            parts = user_input.split(maxsplit=1)
            cmd_comment(parts[1].strip() if len(parts) > 1 else "",
                        client, current_model, memory, system_prompt, name, last_reply or "")
            turns += 1
            continue

        if cmd == "/lang":
            parts = user_input.split(maxsplit=1)
            lang  = parts[1].strip() if len(parts) > 1 else ""
            system_prompt_ref[0] = cmd_lang(lang, system_prompt_ref[0])
            system_prompt = system_prompt_ref[0]
            continue

        if cmd == "/compact":
            on = toggle_compact()
            info(f"Compact mode {'on' if on else 'off'}")
            continue

        if cmd == "/github":
            parts = user_input.split(maxsplit=1)
            cmd_github(
                parts[1].strip() if len(parts) > 1 else "issues",
                client, current_model, memory, system_prompt, name,
            )
            turns += 1
            continue

        if cmd == "/data":
            parts = user_input.split(maxsplit=1)
            cmd_data(
                parts[1].strip() if len(parts) > 1 else "",
                client, current_model, memory, system_prompt, name,
            )
            turns += 1
            continue

        if cmd and cmd.startswith("/"):
            # Check plugins before declaring unknown
            handled, plug_result = plugin_dispatch(
                cmd,
                user_input.split(maxsplit=1)[1] if " " in user_input else "",
                client=client, model=current_model,
                memory=memory, system_prompt=system_prompt, name=name,
            )
            if handled:
                if plug_result:
                    print(f"  {GR}{plug_result}{R}")
            else:
                fail(f"Unknown command: {cmd}  —  type /help")
            continue

        # ── Intelligence layer ────────────────────────────────────────────────
        _cls_model     = current_model if current_model != "council" else "gemini-2.0-flash-lite"
        classification = classify_request(user_input, client, _cls_model)

        if classification.get("needs_clarification"):
            clarify_q = silent_call(
                client,
                f"The user said: '{user_input}'. Ask one short clarifying question.",
                _cls_model, max_tokens=50,
            )
            if clarify_q:
                info(clarify_q)
                continue

        _is_code  = (
            classification.get("intent") in ("coding", "debug")
            or is_complex_coding_task(user_input)
        )
        _is_files = (
            "fs" in classification.get("tools", [])
            or is_file_generation_task(user_input)
        )

        system_prompt = make_system_prompt(
            persona, override=get_persona_override(),
            coding_mode=_is_code, file_mode=_is_files,
        )

        if "mcp" in classification.get("tools", []):
            from src.tools.mcp import get_tool_context
            mcp_ctx = get_tool_context()
            if mcp_ctx:
                system_prompt += "\n\n" + mcp_ctx

        augmented = user_input
        if "search" in classification.get("tools", []) and should_search(user_input):
            sp = Spinner("searching")
            sp.start()
            try:
                results_text = search(user_input, fetch_top=True)
                if results_text and not results_text.startswith("[No"):
                    augmented = (
                        f"{user_input}\n\n[Web search results]:\n{results_text}\n"
                        "[Use these results to inform your answer.]"
                    )
                    print(f"\n  {CY}◆{R}  {GR}Found web results{R}")
            except Exception:
                pass
            finally:
                sp.stop()

        hint = emotion_hint(classification.get("emotion", "neutral"))
        if hint:
            augmented = hint + augmented

        log_mood(classification.get("emotion"), turns)
        if turns > 0 and turns % 20 == 0:
            mood_msg = check_mood_pattern()
            if mood_msg:
                info(mood_msg)

        # Sync system_prompt from /lang ref
        system_prompt = system_prompt_ref[0]

        if needs_plan_first(user_input) and _is_files:
            system_prompt += (
                "\n\n[INSTRUCTION: Before writing any code, output a brief one-paragraph plan. "
                "Then write each file completely with no placeholders.]"
            )

        # ── File-creation agent ───────────────────────────────────────────────
        if is_create_request(user_input):
            sp = Spinner("generating file plan")
            sp.start()
            _fs_model = current_model
            if current_model == "council":
                _fs_model = get_models(get_provider())[0]
            plan = generate_file_plan(user_input, client, _fs_model)
            sp.stop()
            if plan:
                root     = plan.get("root", ".")
                files    = plan.get("files", [])
                home     = os.path.expanduser("~")
                print(f"\n  {DG}Where should I create this?{R}  {WH}[{home}]{R}  ", end="", flush=True)
                try:
                    dest_input = input().strip()
                except (KeyboardInterrupt, EOFError):
                    dest_input = ""
                base_dir  = os.path.expanduser(dest_input) if dest_input else home
                full_root = os.path.join(base_dir, root) if root and root != "." else base_dir
                print(f"\n  {B}{WH}File plan{R}  {DG}→ {full_root}{R}\n")
                if root and root != ".":
                    print(f"  {CY}📁 {root}/{R}")
                for f in files:
                    print(f"  {GR}   📄 {f.get('path', '')}{R}")
                print()
                print(f"  {DG}Create these files? [Y/n]{R}  ", end="", flush=True)
                try:
                    confirm = input().strip().lower()
                except (KeyboardInterrupt, EOFError):
                    confirm = "n"
                if confirm in ("", "y", "yes"):
                    created = write_file_plan(plan, base_dir=base_dir)
                    summary = format_creation_summary(plan, created)
                    ok(f"Created {len(created)} items in {base_dir}")
                    has_html = any(f.get("path", "").endswith(".html") for f in files)
                    opener   = (
                        f"Open `{full_root}/index.html` in your browser to see it live."
                        if has_html
                        else "Let me know if you want to edit anything."
                    )
                    reply = (
                        f"Done! Created in `{full_root}`:\n\n"
                        f"```\n{summary}\n```\n\n{opener}"
                    )
                    print_lumi_label(name)
                    from src.utils.markdown import render as _md
                    print("\n".join("  " + l for l in _md(reply).split("\n")))
                    memory.add("user",      user_input)
                    memory.add("assistant", reply)
                    prev_reply = last_reply
                    last_reply = reply
                    turns     += 1
                else:
                    info("Cancelled.")
            else:
                fail(
                    "Couldn't generate a file plan. Try being more specific, "
                    "e.g: 'create a folder called myapp with index.html and style.css'"
                )
            continue

        # ── Context compression (background, every 10 turns) ──────────────────
        if len(memory.get()) > 15 and turns % 10 == 0 and turns > 0:
            def _compress() -> None:
                try:
                    snapshot = memory.get()[:-4]
                    if not snapshot:
                        return
                    _m = current_model if current_model != "council" else get_models(get_provider())[0]
                    summ = silent_call(
                        client,
                        "Summarize this conversation briefly (3-5 sentences, keep all key technical details):\n\n"
                        + "\n".join(f"{x['role']}: {x['content'][:200]}" for x in snapshot),
                        _m, 200,
                    )
                    if summ:
                        memory.set_history(
                            [{"role": "system", "content": f"[Conversation summary]: {summ}"}]
                            + memory.get()[-4:]
                        )
                except Exception:
                    pass
            threading.Thread(target=_compress, daemon=True).start()

        # ── Plugin dispatch ───────────────────────────────────────────────────
        if cmd:
            handled, plug_result = plugin_dispatch(
                cmd,
                user_input.split(maxsplit=1)[1] if " " in user_input else "",
                client=client, model=current_model,
                memory=memory, system_prompt=system_prompt, name=name,
            )
            if handled:
                if plug_result:
                    print(f"  {GR}{plug_result}{R}")
                continue

        # ── Chat ──────────────────────────────────────────────────────────────
        last_msg = user_input
        memory.add("user", augmented)
        messages = build_messages(system_prompt, memory.get())

        if response_mode == "short":
            messages[-1]["content"] += "\n\n[Reply concisely — 2-3 sentences max.]"
        elif response_mode == "detailed":
            messages[-1]["content"] += "\n\n[Reply in detail — be thorough and comprehensive.]"
        elif response_mode == "bullets":
            messages[-1]["content"] += "\n\n[Reply using bullet points only.]"
        response_mode = None

        print_you(user_input)

        try:
            raw_reply, client, current_model, new_prov = stream_with_fallback(
                client, messages, current_model, name,
                get_available_providers(), get_provider(),
            )
            if new_prov != get_provider():
                draw_header(
                    current_model, turns,
                    "council" if current_model == "council" else get_provider(),
                )
        except Exception as exc:
            fail(str(exc))
            memory.pop_last()
            continue

        memory.replace_last("user", user_input)
        memory.add("assistant", raw_reply)
        prev_reply = last_reply
        last_reply = raw_reply
        turns     += 1
        print()

        # --max-turns exit
        if max_turns and turns >= max_turns:
            ok(f"Reached --max-turns {max_turns} — exiting")
            history_save()
            save(memory.get())
            sys.exit(0)

        # Auto-save
        if turns % AUTOSAVE_EVERY == 0:
            try:
                save(memory.get())
            except Exception:
                pass

        # Auto-remember (background)
        if turns % AUTOREMEMBER_EVERY == 0:
            def _bg_remember() -> None:
                try:
                    if auto_extract_facts(client, current_model, memory.get()):
                        # Rebuild system prompt now that memory has grown
                        nonlocal system_prompt
                        system_prompt = make_system_prompt(persona, get_persona_override())
                except Exception:
                    pass
            threading.Thread(target=_bg_remember, daemon=True).start()


if __name__ == "__main__":
    main()
