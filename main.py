"""Lumi CLI — smarter chatbot."""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import pathlib
import json
import shutil
import textwrap
import threading
import subprocess
import difflib
import shlex
import select
import time
import itertools
import webbrowser
import urllib.parse
from datetime import datetime

from src.chat.hf_client import get_client, get_models, get_provider, set_provider, get_available_providers
from src.utils.todo  import todo_add, todo_list, todo_done, todo_remove, todo_clear_done
from src.utils.notes import note_add, note_list, note_search, note_remove, notes_to_markdown
from src.utils.tools import (get_weather, clipboard_get, clipboard_set, read_pdf,
                              take_screenshot, encode_image_base64, load_project, analyze_data_file)
from src.utils.voice import record_audio, transcribe_groq, speak
from src.utils.filesystem import is_create_request, generate_file_plan, write_file_plan, format_creation_summary

from src.memory.short_term import ShortTermMemory
from src.memory.longterm import (
    get_facts, add_fact, remove_fact, clear_facts, build_memory_block,
    get_persona_override, set_persona_override, clear_persona_override,
)
from src.memory.conversation_store import save, load_latest, load_by_name, list_sessions, delete_session
from src.utils.web import fetch_url
from src.utils.plugins import load_plugins, get_commands, dispatch as plugin_dispatch
from src.tools.mcp import list_servers as mcp_list, add_server as mcp_add, remove_server as mcp_remove, get_session as mcp_session, stop_all as mcp_stop
from src.prompts.builder import load_persona, build_system_prompt, build_messages, is_coding_task, is_file_generation_task
from src.agents.council import council_ask, AGENTS as COUNCIL_AGENTS
from src.tools.search import search, search_display
from src.utils.markdown import render as md_render
from src.utils.export import export_md
from src.utils.themes import get_theme, list_themes, save_theme_name, load_theme_name
from src.utils.history import setup as history_setup, save as history_save
from src.utils.intelligence import detect_emotion, emotion_hint, detect_topic, should_search, is_complex_coding_task, needs_plan_first
from src.utils.autoremember import auto_extract_facts

# ── System prompt builder (unified) ──────────────────────────
def make_system_prompt(persona: dict, override: dict = None,
                       coding_mode: bool = False,
                       file_mode: bool = False) -> str:
    """Build full system prompt with memory, optional coding/file modes."""
    merged = {**persona, **(override or {})}
    mem    = build_memory_block()
    return build_system_prompt(merged, mem, coding_mode, file_mode)


# ── ANSI base ─────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
D  = "\033[2m"

# ── Theme globals ─────────────────────────────────────────────
C1 = C2 = C3 = PU = BL = CY = GR = DG = MU = GN = RE = YE = WH = R

def reload_theme(name: str = None):
    global C1, C2, C3, PU, BL, CY, GR, DG, MU, GN, RE, YE, WH
    t  = get_theme(name)
    C1 = t["C1"]; C2 = t["C2"]; C3 = t["C3"]
    PU = t["PU"]; BL = t["BL"]; CY = t["CY"]
    GR = t["GR"]; DG = t["DG"]; MU = t["MU"]
    GN = t["GN"]; RE = t["RE"]; YE = t["YE"]; WH = t["WH"]

reload_theme()

# ── Helpers ───────────────────────────────────────────────────
def W():     return shutil.get_terminal_size().columns
def clear(): os.system("clear")
def ts():    return datetime.now().strftime("%H:%M")
def div():   print(f"{DG}{'─' * W()}{R}")
def wc(s):   return len(s.split())

def ok(msg, icon="✓", c=None):  print(f"\n  {c or GN}{icon}{R}  {GR}{msg}{R}\n")
def fail(msg):                    print(f"\n  {RE}✗{R}  {GR}{textwrap.fill(str(msg), W()-10)}{R}\n")
def info(msg):                    print(f"\n  {CY}◆{R}  {GR}{msg}{R}\n")
def warn(msg):                    print(f"\n  {YE}!{R}  {GR}{msg}{R}\n")

# ── Visual constants ──────────────────────────────────────────
LOGO = [
    "    ██╗      ██╗   ██╗  ███╗   ███╗  ██╗   ",
    "    ██║      ██║   ██║  ████╗ ████║  ██║   ",
    "    ██║      ██║   ██║  ██╔████╔██║  ██║   ",
    "    ██║      ██║   ██║  ██║╚██╔╝██║  ██║   ",
    "    ███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║   ",
    "    ╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝   ",
]
LOGO_W = 46

PROV_COL = {
    "gemini":      "\033[38;5;75m",
    "groq":        "\033[38;5;215m",
    "openrouter":  "\033[38;5;141m",
    "mistral":     "\033[38;5;210m",
    "huggingface": "\033[38;5;179m",
    "ollama":      "\033[38;5;114m",
}

def _pcolor(p: str) -> str:
    return PROV_COL.get(p.lower(), DG)

def _vlen(s: str) -> int:
    """Visible length — strips ANSI escape codes."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))

def _center(s: str, width: int, fill: str = " ") -> str:
    """Center string accounting for invisible ANSI codes."""
    vis = _vlen(s)
    pad = max(width - vis, 0)
    return fill * (pad // 2) + s + fill * (pad - pad // 2)

def _rpad(s: str, width: int) -> str:
    """Right-pad accounting for ANSI codes."""
    return s + " " * max(width - _vlen(s), 0)


# ── Header ─────────────────────────────────────────────────────
def draw_header(model: str, turns: int = 0, provider: str = ""):
    clear()
    w    = W()
    pad  = " " * max((w - LOGO_W) // 2, 2)
    grad = [C1, C1, C2, C2, C3, C3]

    print()
    for row, col in zip(LOGO, grad):
        print(f"{pad}{col}{B}{row}{R}")
    print()

    # Subtle tagline — spaced letters, centered
    tag = "A I   A S S I S T A N T"
    print(_center(f"{DG}{tag}{R}", w))
    print()

    # Status line — clean, no boxes, just text
    m     = model.split("/")[-1]
    if provider == "council":
        pcol  = PU
        pname = "Council"
        m     = "5 agents"
    else:
        pcol  = _pcolor(provider)
        pname = provider.capitalize() if provider else "—"

    left  = f"  {pcol}◆ {pname}{R}  {DG}│{R}  {WH}{m}{R}"
    right = f"{DG}{turns} turns  {R}" if turns else ""
    gap   = max(w - _vlen(left) - _vlen(right) - 2, 1)
    print(f"{left}{' ' * gap}{right}")

    # Single clean separator
    print(f"\n  {DG}{'▁' * (w - 4)}{R}\n")


# ── Spinner ─────────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"]

    def __init__(self, label: str = "thinking"):
        self._label   = label
        self._running = False
        self._thread  = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self):
        for f in itertools.cycle(self.FRAMES):
            if not self._running: break
            sys.stdout.write(f"\r  {PU}{f}{R}  {DG}{self._label}{R}  ")
            sys.stdout.flush()
            time.sleep(0.09)

    def stop(self):
        self._running = False
        if self._thread: self._thread.join()
        sys.stdout.write(f"\r{' ' * W()}\r")
        sys.stdout.flush()


# ── Message display ─────────────────────────────────────────────
def print_you(text: str):
    time_str = ts()
    # Reserve space for "  you  " prefix (7) and "  HH:MM" suffix (7)
    wrap_w  = max(W() - 16, 20)
    wrapped = textwrap.wrap(text, width=wrap_w) or [text]
    print()
    first = wrapped[0]
    gap   = max(W() - 7 - len(first) - len(time_str) - 2, 1)
    print(f"  {DG}you{R}  {WH}{first}{R}{' ' * gap}{DG}{time_str}{R}")
    for line in wrapped[1:]:
        print(f"       {WH}{line}{R}")

def print_lumi_label(name: str = "Lumi"):
    time_str = ts()
    gap      = max(W() - len(name) - len(time_str) - 7, 1)
    print(f"\n  {PU}{B}✦{R}  {C1}{B}{name}{R}{' ' * gap}{DG}{time_str}{R}\n")

def print_welcome(name: str):
    print(f"\n  {PU}✦  {WH}{B}{name}{R}  {DG}is online  —  {R}{DG}/help{R}{DG} for commands{R}\n")

def div(label: str = ""):
    w = W()
    if label:
        bar   = f"  {DG}── {WH}{label}{R}{DG} ──{R}"
        trail = max(w - _vlen(bar) - 2, 0)
        print(f"\n{bar}{DG}{'─' * trail}{R}\n")
    else:
        print(f"\n  {DG}{'─' * (w - 4)}{R}\n")

def ok(msg: str, icon: str = "✓", c=None):
    print(f"\n  {c or GN}{icon}  {GR}{msg}{R}\n")

def fail(msg: str):
    wrapped = textwrap.fill(str(msg), W() - 8)
    print(f"\n  {RE}✗  {GR}{wrapped}{R}\n")

def info(msg: str):
    print(f"\n  {CY}◆  {GR}{msg}{R}\n")

def warn(msg: str):
    print(f"\n  {YE}▲  {GR}{msg}{R}\n")


def print_help():
    w    = W()
    line = f"  {DG}{'─' * (w - 4)}{R}"

    def section(title):
        print(f"\n  {C2}{B}{title}{R}")

    def cmd(name, desc):
        print(f"  {CY}  {name:<28}{R}{DG}{desc}{R}")

    print(f"\n{line}")
    print(f"  {PU}{B}  ✦  LUMI COMMANDS{R}")
    print(line)

    section("CHAT")
    cmd("/council <q>",             "ask all 5 agents — best answer synthesized")
    cmd("/council --show <q>",      "same + show each agent's raw response")
    cmd("/context",                 "show token usage and context window")
    cmd("/redo [model]",            "regenerate last answer, optionally with different model")
    cmd("/help",                    "show this")
    cmd("/clear",                   "reset conversation")
    cmd("/undo · /retry",           "remove last turn or resend it")
    cmd("/more · /tl;dr",          "expand or summarize last reply")
    cmd("/rewrite · /summarize",    "rewrite reply or summarize chat")
    cmd("/short · /detailed · /bullets", "one-shot reply format")
    cmd("/multi",                   "toggle multi-line input")

    section("CODE")
    cmd("/edit <path>",             "edit a file — AI writes, shows diff, confirms")
    cmd("/file <path>",             "load file as context")
    cmd("/project <dir>",           "load entire codebase as context")
    cmd("/fix <error>",             "diagnose and fix an error")
    cmd("/review [file]",           "full code review")
    cmd("/explain [file]",          "explain code or last reply")
    cmd("/comment [file]",          "add docstrings and inline comments")
    cmd("/run",                     "run code block from last reply")
    cmd("/diff",                    "diff previous reply vs latest")
    cmd("/git status|commit|log",   "git helpers")
    cmd("/github issues",           "pull GitHub issues (needs GITHUB_TOKEN)")

    section("FILES & DATA")
    cmd("/pdf <path>",              "read and analyze a PDF")
    cmd("/data <path>",             "analyze CSV or JSON file")
    cmd("/screenshot",              "capture screen → AI vision analysis")
    cmd("/paste · /copy",           "clipboard into chat / copy last reply out")

    section("VOICE")
    cmd("/listen [seconds]",        "record mic → Groq Whisper → send to Lumi")
    cmd("/speak",                   "read last reply aloud (espeak / say)")

    section("PRODUCTIVITY")
    cmd("/todo add|list|done|remove","persistent task tracker")
    cmd("/note [#tag] <text>",      "timestamped notes — list · search · export")
    cmd("/standup",                 "daily standup from git log + todos")
    cmd("/timer <25m|5s|1h>",       "countdown timer with desktop notification")
    cmd("/draft <description>",     "draft an email, Slack message, or text")
    cmd("/weather [city]",          "current weather (wttr.in — no key needed)")

    section("WEB & TOOLS")
    cmd("/search <query>",          "explicit web search")
    cmd("/translate <language>",    "translate last reply")
    cmd("/imagine <prompt>",        "generate image (opens browser)")
    cmd("/lang <language>",         "language learning mode — /lang off to stop")
    cmd("/compact",                 "toggle minimal output")

    section("MEMORY & PERSONA")
    cmd("/remember <fact>",         "save fact to long-term memory")
    cmd("/memory",                  "view all saved memories")
    cmd("/forget",                  "delete memories interactively")
    cmd("/persona",                 "edit Lumi's name, tone, and traits")

    section("SESSIONS")
    cmd("/save · /load",            "save or load a conversation")
    cmd("/sessions",                "list all saved sessions")
    cmd("/export",                  "export current session as markdown")
    cmd("/find <keyword>",          "search through past sessions")

    section("WEB & VISION")
    cmd("/web <url> [question]",    "fetch any webpage, ask questions about it")
    cmd("/image <path> [question]", "send image to AI — vision support")

    section("AUTONOMOUS")
    cmd("/agent <task>",            "multi-step autonomous agent — plans and executes")
    cmd("/lumi.md show|create",     "view or create project context file")

    section("MCP SERVERS")
    cmd("/mcp list",                "show configured MCP servers")
    cmd("/mcp add <n> <cmd>",       "add a new MCP server")
    cmd("/mcp remove <n>",          "remove a server")
    cmd("/mcp tools <server>",      "list tools on a server")
    cmd("/mcp call <srv> <tool>",   "call a tool directly")

    section("PLUGINS")
    cmd("/plugins",                 "list loaded plugins")
    cmd("/plugins reload",          "reload plugins from ~/Lumi/plugins/")

    section("SESSIONS")
    cmd("/save [name]",             "save conversation with optional name")
    cmd("/load [name]",             "load session by name or latest")
    cmd("/sessions",                "list all saved sessions")

    section("SETTINGS")
    cmd("/model",                   "switch provider and model (2-step picker)")
    cmd("/theme",                   "switch color theme (5 themes)")
    cmd("/cost",                    "show token usage this session")
    cmd("/quit",                    "save and exit")

    print(f"\n{line}")
    print(f"  {DG}  tip  →  just type naturally. Lumi auto-detects coding tasks and file creation.{R}")
    print(f"{line}\n")





# ── Model picker ──────────────────────────────────────────────
PROVIDER_LABELS = {
    "gemini":      ("Gemini",       "Google Gemini — smart, 1M context"),
    "groq":        ("Groq",         "Groq — fastest, Llama/Qwen/GPT-OSS"),
    "openrouter":  ("OpenRouter",   "30+ free models — DeepSeek R1, Llama 4, Qwen3"),
    "mistral":     ("Mistral",      "Mistral free tier — great for coding"),
    "huggingface": ("HuggingFace",  "HuggingFace — free tier, rate limited"),
    "github":      ("GitHub Models","GPT-4o, o1, DeepSeek R1, Phi-4 — free with GitHub account"),
    "ollama":      ("Ollama",       "Local Ollama — fully offline, no API limits"),
    "council":     ("⚡ Council",   "6 agents in parallel — Gemini · Kimi · GPT-OSS · Codestral · Llama · GitHub"),
}

def pick_model(cur_model: str) -> tuple:
    """Returns (new_model, new_provider). Shows provider picker first, then models."""
    available = get_available_providers()
    if not available:
        warn("No API keys found in .env"); return cur_model, get_provider()

    # Always add council if at least 2 providers are available
    from src.agents.council import _get_available_agents as _cagents
    if len(_cagents()) >= 2 and "council" not in available:
        available = available + ["council"]

    cur_provider = get_provider()

    # ── Step 1: pick provider ─────────────────────────────────
    print(f"\n  {B}{WH}Choose provider{R}\n")
    for i, p in enumerate(available):
        label, desc = PROVIDER_LABELS.get(p, (p, ""))
        dot    = f"{GN}●{R}" if p == cur_provider else f"{DG}○{R}"
        active = f"  {MU}active{R}" if p == cur_provider else ""
        print(f"  {dot}  {GR}{i+1}.{R}  {WH}{label}{R}  {DG}{desc}{R}{active}")
    print()

    try:
        raw = input(f"  {PU}›{R}  ").strip()
        if not raw: raise ValueError
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(available):
                chosen_provider = available[idx]
            else:
                warn("Invalid choice."); return cur_model, cur_provider
        except ValueError:
            frag = raw.lower()
            matches = [p for p in available if frag in p.lower()]
            if len(matches) == 1: chosen_provider = matches[0]
            else: warn("No match."); return cur_model, cur_provider
    except (KeyboardInterrupt, EOFError):
        warn("Keeping current provider."); return cur_model, cur_provider

    # Council mode — no model to pick, just confirm
    if chosen_provider == "council":
        from src.agents.council import _get_available_agents as _cag, AGENTS as _CA
        active_agents = _cag()
        names = "  ·  ".join(a["name"] for a in active_agents)
        print(f"\n  {PU}⚡ Council mode{R}  {DG}{names}{R}\n")
        return "council", "council"

    # Switch provider
    if chosen_provider != cur_provider:
        set_provider(chosen_provider)

    # ── Step 2: pick model ────────────────────────────────────
    sp = Spinner("loading models"); sp.start()
    models = get_models(chosen_provider)
    sp.stop()

    # Speed/quality ratings
    MODEL_TAGS = {
        "gemini-flash-latest":          "⚡ fast   🧠 smart",
        "gemini-2.5-flash":             "⚡ fast   🧠 smart",
        "gemini-2.0-flash":             "⚡ fast",
        "gemini-2.0-flash-lite":        "🚀 fastest",
        "kimi-k2":                      "🧠 smart  📊 analysis",
        "llama-3.3-70b-versatile":      "⚡ fast   💬 general",
        "llama-4-maverick":             "🧠 smart",
        "gpt-oss-120b":                 "🧠 smart",
        "gpt-oss-20b":                  "⚡ fast",
        "qwen-3-32b":                   "💻 code",
        "hermes-3-llama-3.1-405b":      "🧠 smart  💬 general",
        "qwen3-coder":                  "💻 code   🧠 smart",
        "codestral-latest":             "💻 code   ⚡ fast",
        "mistral-large-latest":         "🧠 smart",
        "mistral-small-latest":         "⚡ fast",
        "Llama-3.3-70B-Instruct":       "🧠 smart",
        "Qwen2.5-72B-Instruct":         "🧠 smart  💻 code",
        # GitHub Models
        "gpt-4o":                       "🧠 smart  💬 general",
        "gpt-4o-mini":                  "⚡ fast   💬 general",
        "o1-mini":                      "🧠 smart  🔍 reasoning",
        "DeepSeek-R1":                  "🧠 smart  🔍 reasoning",
        "DeepSeek-V3-0324":             "🧠 smart  💻 code",
        "Phi-4":                        "⚡ fast   💻 code",
        "Phi-3.5-MoE":                  "⚡ fast",
        "Mistral-large":                "🧠 smart",
        "grok-3-mini":                  "⚡ fast   🔍 reasoning",
    }
    def _tags(m):
        short = m.split("/")[-1]
        for k, v in MODEL_TAGS.items():
            if k.lower() in short.lower():
                return f"  {DG}{v}{R}"
        return ""

    print(f"\n  {B}{WH}Available models{R}  {DG}({PROVIDER_LABELS[chosen_provider][0]}){R}\n")
    default_model = models[0] if models else cur_model
    for i, m in enumerate(models):
        is_active = m == cur_model and chosen_provider == cur_provider
        is_council = m in [a["models"][0] for a in __import__("src.agents.council", fromlist=["AGENTS"]).AGENTS] if chosen_provider != "council" else False
        dot    = f"{GN}●{R}" if is_active else f"{DG}○{R}"
        active = f"  {MU}active{R}" if is_active else ""
        tags   = _tags(m)
        print(f"  {dot}  {GR}{i+1}.{R}  {WH}{m.split('/')[-1]}{R}{tags}{active}")
    print()

    try:
        raw = input(f"  {PU}›{R}  ").strip()
        if not raw: return default_model, chosen_provider
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(models): return models[idx], chosen_provider
        except ValueError:
            pass
        frag    = raw.lower()
        matches = [m for m in models if frag in m.lower()]
        if len(matches) == 1:   return matches[0], chosen_provider
        elif len(matches) > 1:  warn(f"Ambiguous."); return default_model, chosen_provider
        else:                   warn(f"No model matching '{raw}'."); return default_model, chosen_provider
    except (KeyboardInterrupt, EOFError):
        pass
    return default_model, chosen_provider


# ── Multi-line input ──────────────────────────────────────────
def read_multiline() -> str:
    print(f"  {DG}multi-line — type {GR}END{DG} on its own line to send{R}\n")
    lines = []
    while True:
        try:
            line = input(f"  {DG}│{R}  ")
        except (KeyboardInterrupt, EOFError):
            raise
        if line.strip() == "END": break
        lines.append(line)
    return "\n".join(lines)


# ── Stream + render ───────────────────────────────────────────
# ── Token / cost tracker ─────────────────────────────────────
_session_tokens = {"input": 0, "output": 0}

def _track(prompt_tokens: int = 0, completion_tokens: int = 0):
    _session_tokens["input"]  += prompt_tokens
    _session_tokens["output"] += completion_tokens

def cmd_cost():
    i, o = _session_tokens["input"], _session_tokens["output"]
    total = i + o
    print(f"\n  {B}{WH}Session token usage{R}\n")
    print(f"  {CY}Input tokens {R}  {GR}{i:,}{R}")
    print(f"  {CY}Output tokens{R}  {GR}{o:,}{R}")
    print(f"  {CY}Total        {R}  {WH}{total:,}{R}")
    print(f"\n  {DG}(approx — not all providers report token counts){R}\n")


# ── Provider health check ─────────────────────────────────────
def health_check(providers: list):
    pass  # removed — was causing false positives on startup


# ── /council ─────────────────────────────────────────────────
def cmd_council(user_input: str, messages: list, name: str,
                show_individual: bool = False) -> str:
    """Ask all 5 agents simultaneously, synthesize best answer."""
    from src.utils.markdown import render as _md_render
    try:
        gen = council_ask(messages, user_input,
                          show_individual=show_individual,
                          stream=True, debate=True, refine=True)
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
        final_reply = refined if refined else raw_reply
        # Re-render with markdown
        for _ in range(final_reply.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name + "  " + f"{DG}[council]{R}")
        indented = "\n".join("  " + l for l in _md_render(final_reply).split("\n"))
        print(indented)
        print(f"\n  {MU}{wc(final_reply)} words{R}")
        if stats_line:
            print(f"  {stats_line}")
        return final_reply
    except RuntimeError as e:
        fail(str(e))
        return ""



# ── /web ─────────────────────────────────────────────────────
def cmd_web(url: str, client, model: str, memory, system_prompt: str, name: str):
    """Fetch a webpage and answer questions about it."""
    if not url:
        warn("Usage: /web <url> [question]"); return
    parts    = url.split(None, 1)
    target   = parts[0]
    question = parts[1] if len(parts) > 1 else "Summarize this page."
    sp = Spinner("fetching"); sp.start()
    content  = fetch_url(target)
    sp.stop()
    if content.startswith(("HTTP error", "Could not reach", "Fetch failed")):
        fail(content); return
    ctx = f"URL: {target}\n\nPage content:\n{content}"
    memory.add("user", f"{ctx}\n\n{question}")
    messages = build_messages(system_prompt, memory.get())
    print_you(f"/web {target}")
    try:
        raw = stream_and_render(client, messages, model, name)
        memory._history[-1] = {"role": "user", "content": f"[web: {target}] {question}"}
        memory.add("assistant", raw)
    except Exception as e:
        fail(str(e)); memory._history.pop()


# ── /image ────────────────────────────────────────────────────
def cmd_image(args: str, client, model: str, memory, system_prompt: str, name: str):
    """Send an image to a vision-capable model."""
    parts    = args.split(None, 1)
    path     = parts[0] if parts else ""
    question = parts[1] if len(parts) > 1 else "Describe this image in detail."
    if not path:
        warn("Usage: /image <path> [question]"); return
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        fail(f"File not found: {path}"); return
    try:
        import base64, mimetypes
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        fail(f"Could not read image: {e}"); return

    # Vision message format
    vision_message = {
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": question},
        ]
    }
    messages = build_messages(system_prompt, memory.get()) + [vision_message]
    print_you(f"/image {os.path.basename(path)}")
    sp = Spinner("analyzing image"); sp.start()
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=1024, temperature=0.7, stream=False,
        )
        sp.stop()
        raw = resp.choices[0].message.content.strip() if resp.choices else ""
        if raw:
            print_lumi_label(name)
            from src.utils.markdown import render as _md_render
            print("\n".join("  " + l for l in _md_render(raw).split("\n")))
            print(f"\n  {MU}{wc(raw)} words{R}")
            memory.add("user", f"[image: {os.path.basename(path)}] {question}")
            memory.add("assistant", raw)
        else:
            fail("No response from model")
    except Exception as e:
        sp.stop(); fail(str(e))


# ── /context ─────────────────────────────────────────────────
def cmd_context(memory, system_prompt: str, model: str):
    """Show token estimate for current conversation window."""
    import math
    all_text  = system_prompt + " ".join(
        m["content"] for m in memory.get()
        if isinstance(m.get("content"), str)
    )
    # Rough estimate: 1 token ≈ 4 chars
    est_tokens = math.ceil(len(all_text) / 4)
    turns      = len([m for m in memory.get() if m["role"] == "user"])
    # Context limits by provider/model
    limits = {
        "gemini": 1_000_000, "gpt": 128_000, "llama": 128_000,
        "mistral": 32_000,   "codestral": 200_000, "kimi": 131_072,
        "qwen": 32_768,      "default": 8_192,
    }
    limit = next((v for k, v in limits.items() if k in model.lower()), limits["default"])
    pct   = min(100, round(est_tokens / limit * 100))
    bar_w = 30
    filled = round(bar_w * pct / 100)
    color  = GN if pct < 60 else (YE if pct < 85 else RE)
    bar    = f"{color}{'█' * filled}{DG}{'░' * (bar_w - filled)}{R}"

    print(f"\n  {B}{WH}Context window{R}\n")
    print(f"  {bar}  {color}{pct}%{R}")
    print(f"  {CY}~{est_tokens:,} tokens{R}  {DG}of ~{limit:,} limit{R}")
    print(f"  {GR}{turns} turns  ·  {len(memory.get())} messages{R}\n")


# ── /redo ─────────────────────────────────────────────────────
def cmd_redo(client, model: str, memory, system_prompt: str, name: str,
             last_msg: str, alt_model: str = "") -> str:
    """Regenerate last answer, optionally with a different model."""
    if not last_msg:
        warn("Nothing to redo."); return ""
    use_model = alt_model or model
    # Remove last assistant message from memory
    if memory.get() and memory.get()[-1]["role"] == "assistant":
        memory._history.pop()
    memory.add("user", last_msg)
    messages = build_messages(system_prompt, memory.get())
    if alt_model:
        info(f"Redoing with {alt_model.split('/')[-1]}")
    try:
        raw = stream_and_render(client, messages, use_model, name)
        memory._history[-1] = {"role": "user", "content": last_msg}
        memory.add("assistant", raw)
        return raw
    except Exception as e:
        fail(str(e)); memory._history.pop()
        return ""


# ── /agent ────────────────────────────────────────────────────
def cmd_agent(task: str, client, model: str, memory,
              system_prompt: str, name: str) -> str:
    """Autonomous multi-step agent mode."""
    from src.agents.agent import run_agent
    if not task:
        warn("Usage: /agent <task description>"); return ""
    real_model = get_models(get_provider())[0] if model == "council" else model
    yolo       = bool(os.environ.get("LUMI_YOLO"))
    return run_agent(task, client, real_model, memory, system_prompt, yolo)


# ── /mcp ─────────────────────────────────────────────────────
def cmd_mcp(args: str, client, model: str, memory, system_prompt: str, name: str):
    """MCP server management and tool calls."""
    parts = args.split(None, 2)
    sub   = parts[0] if parts else ""

    if sub == "list" or not sub:
        servers = mcp_list()
        if not servers:
            info("No MCP servers configured.  Use: /mcp add <name> <command>")
            info("Example: /mcp add github npx -y @modelcontextprotocol/server-github")
        else:
            print(f"\n  {B}{WH}MCP servers{R}\n")
            for name_, cfg in servers.items():
                cmd_str = cfg.get("command", "") + " " + " ".join(cfg.get("args", []))
                print(f"  {GN}●{R}  {WH}{name_}{R}  {DG}{cmd_str[:60]}{R}")
            print()

    elif sub == "add":
        if len(parts) < 3:
            warn("Usage: /mcp add <name> <command> [args...]"); return
        mcp_name = parts[1]
        rest     = parts[2].split()
        command  = rest[0]
        mcp_args = rest[1:]
        mcp_add(mcp_name, command, mcp_args)
        ok(f"Added MCP server: {mcp_name}")

    elif sub == "remove":
        if len(parts) < 2:
            warn("Usage: /mcp remove <name>"); return
        if mcp_remove(parts[1]):
            ok(f"Removed: {parts[1]}")
        else:
            fail(f"Server not found: {parts[1]}")

    elif sub == "call":
        # /mcp call <server> <tool> [json_args]
        if len(parts) < 3:
            warn("Usage: /mcp call <server> <tool> [json_args]"); return
        srv, tool = parts[1], parts[2] if len(parts) > 2 else ""
        json_args = parts[3] if len(parts) > 3 else "{}"
        try:
            sess   = mcp_session(srv)
            result = sess.call_tool(tool, __import__("json").loads(json_args or "{}"))
            print(f"\n  {GN}MCP result:{R}\n  {result}\n")
        except Exception as e:
            fail(str(e))

    elif sub == "tools":
        if len(parts) < 2:
            warn("Usage: /mcp tools <server>"); return
        try:
            sess  = mcp_session(parts[1])
            tools = sess.list_tools()
            print(f"\n  {B}{WH}Tools — {parts[1]}{R}\n")
            for t in tools:
                print(f"  {CY}{t['name']}{R}  {DG}{t.get('description','')}{R}")
            print()
        except Exception as e:
            fail(str(e))
    else:
        warn(f"Unknown subcommand: {sub}  (list|add|remove|call|tools)")



def stream_and_render(client, messages: list, model: str, name: str = "Lumi") -> str:
    # ── Council mode — stream synthesized answer ─────────────
    if model == "council":
        user_q = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        from src.agents.council import (
            council_ask as _ca,
            _get_available_agents as _gav,
            format_council_stats as _fcs,
        )
        avail = _gav()
        print(f"\n  {DG}council  {GR}{len(avail)} agents  {DG}→  asking in parallel...{R}\n")

        # council_ask handles agents, spinner, debate, refinement — just stream it
        gen = _ca(messages, user_q, show_individual=False, stream=True,
                  debate=True, refine=True)

        print_lumi_label(name + f"  {DG}[council]{R}")
        raw_reply = ""
        stats_line = ""
        refined    = ""
        for _chunk in gen:
            if _chunk.startswith("\n\n__STATS__\n"):
                stats_line = _chunk[len("\n\n__STATS__\n"):]
                continue
            if _chunk.startswith("\n\n__REFINED__\n\n"):
                refined = _chunk[len("\n\n__REFINED__\n\n"):]
                continue
            print(_chunk, end="", flush=True)
            raw_reply += _chunk
        print()

        # Use refined answer if judge improved it
        final_reply = refined if refined else raw_reply

        # Re-render with markdown
        for _ in range(final_reply.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name + f"  {DG}[council]{R}")
        from src.utils.markdown import render as _mdr
        print("\n".join("  " + l for l in _mdr(final_reply).split("\n")))
        # Stats line: word count + agent breakdown
        n_agents = len([c for c in stats_line.split("  ") if c.strip()])
        print(f"\n  {MU}{wc(final_reply)} words  {DG}{len(avail)} agents{R}")
        if stats_line:
            print(f"  {stats_line}")
        return final_reply

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
        if first: spinner.stop()
        print()
    except Exception as e:
        spinner.stop(); raise e

    if raw_reply:
        for _ in range(raw_reply.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name)
        indented = "\n".join("  " + l for l in md_render(raw_reply).split("\n"))
        print(indented)
        print(f"\n  {MU}{wc(raw_reply)} words{R}")

    return raw_reply


# ── Single-turn AI call (no stream, no display) ──────────────
def silent_call(client, prompt: str, model: str, max_tokens: int = 300) -> str:
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
            stream=False,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return ""


# ── Coding commands ───────────────────────────────────────────

def _read_file(path: str) -> str:
    """Read a file and return its contents, with size guard."""
    import pathlib
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    size = p.stat().st_size
    if size > 200_000:
        raise ValueError(f"File too large ({size//1024}KB). Paste a smaller excerpt.")
    return p.read_text(encoding="utf-8", errors="replace")


def cmd_file(path: str, client, model: str, memory, system_prompt: str, name: str):
    """Load a file into the conversation."""
    try:
        code = _read_file(path)
    except Exception as e:
        fail(str(e)); return None

    import pathlib
    fname = pathlib.Path(path).name
    lines = code.count("\n") + 1
    size  = len(code)

    info(f"Loaded {fname}  {DG}({lines} lines, {size} chars){R}")
    msg = (
        f"I've loaded the file `{fname}` for you to look at:\n\n"
        f"```\n{code}\n```\n\n"
        f"Let me know what you'd like to do with it — review it, explain it, fix something, etc."
    )
    memory.add("user", msg)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"[loaded file: {fname}]")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as e:
        fail(str(e)); memory._history.pop(); return None
    memory._history[-1] = {"role": "user", "content": f"[loaded file: {fname}]"}
    memory.add("assistant", raw)
    return raw


def cmd_fix(error: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str):
    """Diagnose and fix an error."""
    # Inject elite coding prompt for this command
    context = f"\n\nContext from our last exchange:\n{last_reply}" if last_reply else ""
    msg = (
        f"I'm getting this error:\n\n```\n{error}\n```"
        f"{context}\n\n"
        f"Please:\n"
        f"1. Explain what's causing it in plain English\n"
        f"2. Show me the fix with corrected code\n"
        f"3. If relevant, explain how to avoid it next time"
    )
    memory.add("user", msg)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"fix: {error[:80]}{'...' if len(error)>80 else ''}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as e:
        fail(str(e)); memory._history.pop(); return None
    memory._history[-1] = {"role": "user", "content": f"/fix: {error[:200]}"}
    memory.add("assistant", raw)
    return raw


def cmd_explain(target: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str):
    """Explain code — either a file or the last reply."""
    if target:
        try:
            code = _read_file(target)
            import pathlib
            fname = pathlib.Path(target).name
            subject = f"the file `{fname}`"
            content = f"```\n{code}\n```"
        except Exception as e:
            fail(str(e)); return None
    elif last_reply:
        subject = "your last response"
        content = last_reply
    else:
        warn("Nothing to explain yet. Either pass a file path or ask something first."); return None

    msg = (
        f"Please explain {subject} in detail:\n\n{content}\n\n"
        f"Walk through it step by step. Explain what each part does, "
        f"why it's written that way, and anything a developer should know."
    )
    memory.add("user", msg)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"explain: {target or 'last reply'}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as e:
        fail(str(e)); memory._history.pop(); return None
    memory._history[-1] = {"role": "user", "content": f"/explain: {target or 'last reply'}"}
    memory.add("assistant", raw)
    return raw


def cmd_review(target: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str):
    """Code review — either a file or the last reply."""
    # Inject elite coding prompt for this command
    if target:
        try:
            code = _read_file(target)
            import pathlib
            fname = pathlib.Path(target).name
            subject = f"the file `{fname}`"
            content = f"```\n{code}\n```"
        except Exception as e:
            fail(str(e)); return None
    elif last_reply:
        subject = "your last code response"
        content = last_reply
    else:
        warn("Nothing to review. Either pass a file path or ask for code first."); return None

    msg = (
        f"Please do a thorough code review of {subject}:\n\n{content}\n\n"
        f"Cover:\n"
        f"- Bugs or potential bugs\n"
        f"- Performance issues\n"
        f"- Security concerns\n"
        f"- Code style and readability\n"
        f"- What's done well\n"
        f"- Concrete suggestions for improvement with code examples"
    )
    memory.add("user", msg)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"review: {target or 'last reply'}")
    try:
        raw = stream_and_render(client, messages, model, name)
    except Exception as e:
        fail(str(e)); memory._history.pop(); return None
    memory._history[-1] = {"role": "user", "content": f"/review: {target or 'last reply'}"}
    memory.add("assistant", raw)
    return raw


# ── /find ─────────────────────────────────────────────────────
def cmd_find(keyword: str):
    import json, pathlib
    d = pathlib.Path("data/conversations")
    if not d.exists(): warn("No saved sessions."); return
    hits = []
    for f in sorted(d.glob("*.json")):
        try:
            for m in json.loads(f.read_text(encoding="utf-8")):
                if keyword.lower() in m.get("content", "").lower():
                    hits.append((f.name, m["role"], m["content"][:200]))
        except Exception: continue
    if not hits: warn(f"No matches for: {keyword}"); return
    print(f"\n  {B}{WH}Results for:{R}  {GR}{keyword}{R}  {MU}({len(hits)} found){R}\n")
    for fname, role, snippet in hits[:20]:
        label = f"{PU}Lumi{R}" if role == "assistant" else f"{BL}you{R}"
        print(f"  {DG}{fname}{R}  {label}")
        print(f"{GR}{textwrap.fill(snippet, W()-6, initial_indent='    ', subsequent_indent='    ')}{R}\n")


# ── /persona ──────────────────────────────────────────────────
def cmd_persona():
    override = get_persona_override()
    print(f"\n  {B}{WH}Persona editor{R}  {DG}(leave blank to keep){R}\n")
    new = {}
    for key, label in [("name","Name"),("creator","Creator"),("tone","Tone"),("traits","Traits")]:
        cur = override.get(key, "")
        cur_display = f"  {MU}[{cur}]{R}" if cur else ""
        try:
            val = input(f"  {GR}{label}:{cur_display}  {BL}›{R}  ").strip()
        except (KeyboardInterrupt, EOFError):
            warn("Cancelled."); return
        if val: new[key] = val
        elif cur: new[key] = cur
    if new: set_persona_override(new); ok("Persona updated.")
    else:   clear_persona_override();  ok("Persona reset to default.")


# ── /memory ───────────────────────────────────────────────────
def cmd_memory():
    facts = get_facts()
    if not facts: warn("No facts in long-term memory."); return
    print(f"\n  {B}{WH}Long-term memory{R}  {MU}({len(facts)} facts){R}\n")
    for i, f in enumerate(facts):
        print(f"  {CY}{i+1}.{R}  {GR}{f}{R}")
    print()


# ── /forget ───────────────────────────────────────────────────
def cmd_forget():
    facts = get_facts()
    if not facts: warn("No facts in long-term memory."); return
    cmd_memory()
    print(f"  {DG}Enter a number to delete, {GR}all{DG} to clear, or Enter to cancel.{R}\n")
    try:
        val = input(f"  {PU}›{R}  ").strip()
    except (KeyboardInterrupt, EOFError): return
    if val.lower() == "all":
        clear_facts(); ok("All long-term memory cleared.")
    else:
        try:
            idx = int(val) - 1
            if remove_fact(idx): ok(f"Removed fact #{idx+1}.")
            else: warn("Invalid number.")
        except ValueError: info("Cancelled.")


# ── /theme ────────────────────────────────────────────────────
def cmd_theme(current: str) -> str:
    themes = list_themes()
    SW = {
        "tokyo":      ("\033[38;5;141m","\033[38;5;75m", "\033[38;5;117m","\033[38;5;114m"),
        "dracula":    ("\033[38;5;141m","\033[38;5;212m","\033[38;5;84m", "\033[38;5;228m"),
        "nord":       ("\033[38;5;153m","\033[38;5;110m","\033[38;5;108m","\033[38;5;159m"),
        "gruvbox":    ("\033[38;5;214m","\033[38;5;175m","\033[38;5;142m","\033[38;5;108m"),
        "catppuccin": ("\033[38;5;189m","\033[38;5;183m","\033[38;5;149m","\033[38;5;152m"),
    }
    div("THEME")
    for i, t in enumerate(themes):
        tname  = get_theme(t)["name"]
        cols   = SW.get(t, (WH, CY, GN, BL))
        bar    = "".join(f"{c}▐▌{R}" for c in cols)
        marker = f"{GN}●{R}" if t == current else f"{DG}○{R}"
        tag    = f"  {GN}← current{R}" if t == current else ""
        print(f"  {marker}  {WH}{i+1}{R}  {DG}│{R}  {WH}{tname:<18}{R}  {bar}{tag}")
    print()
    sys.stdout.write(f"  {PU}›{R}  ")
    sys.stdout.flush()
    try:
        idx = int(input().strip()) - 1
        if 0 <= idx < len(themes):
            chosen = themes[idx]
            save_theme_name(chosen)
            reload_theme(chosen)
            ok(f"Theme — {get_theme(chosen)['name']}")
            return chosen
    except (ValueError, KeyboardInterrupt): pass
    return current


# ── /imagine ──────────────────────────────────────────────────
def cmd_imagine(prompt: str):
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true"
    info("Generating image — opening in browser...")
    webbrowser.open(url)
    ok(f"Opened: {url}")


# ── Main ──────────────────────────────────────────────────────
# ── /run — execute code from last reply ──────────────────────
def cmd_run(last_reply: str):
    """Extract code block from last reply and run it."""
    import re
    # Find first fenced code block
    m = re.search(r"```(?:python|bash|sh|javascript|js|node)?\n(.*?)```", last_reply, re.DOTALL)
    if not m:
        warn("No code block found in last reply."); return
    code = m.group(1).strip()
    lang = re.search(r"```(\w+)", last_reply)
    lang = lang.group(1).lower() if lang else "python"

    print(f"\n{B}{WH}Running code{R}  {DG}({lang}){R}\n")
    print(f"  {DG}{'─'*40}{R}")

    try:
        if lang in ("python", "py"):
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=15
            )
        elif lang in ("bash", "sh"):
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True, text=True, timeout=15
            )
        elif lang in ("javascript", "js", "node"):
            result = subprocess.run(
                ["node", "-e", code],
                capture_output=True, text=True, timeout=15
            )
        else:
            warn(f"Can't run {lang} yet. Supported: python, bash, javascript"); return

        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"  {GR}{line}{R}")
        if result.stderr:
            print(f"\n{YE}stderr:{R}")
            for line in result.stderr.splitlines():
                print(f"  {RE}{line}{R}")
        if result.returncode == 0:
            print(f"\n{GN}✓{R}  {GR}Exit 0{R}\n")
        else:
            print(f"\n{RE}✗{R}  {GR}Exit {result.returncode}{R}\n")

        return result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        fail("Timed out after 15s")
    except FileNotFoundError as e:
        fail(f"Runtime not found: {e}")


# ── /edit — edit a file using Lumi's last reply ───────────────
def cmd_edit(path: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str = ""):
    """Load a file, send it to Lumi for editing, write result back."""
    # Inject elite coding prompt for this command
    path = path.strip().strip("'\"")
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        fail(f"File not found: {path}"); return last_reply
    ext  = os.path.splitext(path)[1].lstrip(".")
    size = os.path.getsize(path)
    if size > 300_000:
        fail(f"File too large ({size//1024}KB). Max 300KB."); return last_reply
    original = open(path, encoding="utf-8", errors="replace").read()
    fname    = os.path.basename(path)
    print(f"\n  {B}{WH}File loaded:{R}  {GR}{path}{R}  {DG}({len(original.splitlines())} lines){R}")
    print(f"\n  {DG}What should Lumi do to this file?{R}")
    try:
        instruction = input(f"  {PU}›{R}  ").strip()
        if not instruction: warn("No instruction given."); return last_reply
    except (KeyboardInterrupt, EOFError):
        warn("Cancelled."); return last_reply
    prompt = (
        f"You are editing the file `{fname}`.\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"FILE CONTENT:\n```{ext}\n{original}\n```\n\n"
        f"Return ONLY the complete updated file content. No explanation, no markdown fences, no preamble. Just raw file content."
    )
    memory.add("user", prompt)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Edit {fname}: {instruction}")
    try:
        reply = stream_and_render(client, messages, model, name)
    except Exception as e:
        fail(str(e)); memory._history.pop(); return last_reply
    # Strip accidental markdown fences
    import re as _re
    clean = _re.sub(r"^```[^\n]*\n", "", reply.strip())
    clean = _re.sub(r"\n```$", "", clean).strip()
    # Show diff
    diff = list(difflib.unified_diff(
        original.splitlines(), clean.splitlines(),
        fromfile=f"{fname} (before)", tofile=f"{fname} (after)", lineterm=""
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
            print(f"  {DG}... {len(diff)-60} more lines{R}")
    else:
        info("No changes made."); return reply
    # Confirm write
    if os.environ.get("LUMI_YOLO"):
        ok(f"Auto-writing {path}  (--yolo)")
    else:
        print(f"\n  {YE}!{R}  {GR}Write changes to {WH}{path}{GR}? {DG}[y/N]{R}  ", end="")
    try:
        confirm = input().strip().lower()
    except (KeyboardInterrupt, EOFError):
        confirm = "n"
    if confirm == "y":
        backup = path + ".lumi.bak"
        open(backup, "w", encoding="utf-8").write(original)
        open(path, "w", encoding="utf-8").write(clean)
        ok(f"Written → {path}  {DG}(backup: {os.path.basename(backup)})")
    else:
        info("Changes discarded.")
    memory._history[-1] = {"role": "user", "content": f"[Edited file: {fname}]"}
    memory.add("assistant", reply)
    return reply


# ── /diff — show diff of last two replies ────────────────────
def cmd_diff(last_reply: str, prev_reply: str):
    if not prev_reply:
        warn("No previous reply to diff against."); return
    diff = list(difflib.unified_diff(
        prev_reply.splitlines(), last_reply.splitlines(),
        fromfile="previous", tofile="latest", lineterm=""
    ))
    if not diff:
        info("Replies are identical."); return
    print(f"\n{B}{WH}Diff — previous vs latest{R}\n")
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            print(f"  {GN}{line}{R}")
        elif line.startswith("-") and not line.startswith("---"):
            print(f"  {RE}{line}{R}")
        else:
            print(f"  {DG}{line}{R}")
    print()


# ── /git — git helper ─────────────────────────────────────────
def cmd_git(subcmd: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str):
    sub = subcmd.strip().lower() if subcmd else "status"
    if sub == "status":
        r1 = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
        r2 = subprocess.run(["git", "log", "--oneline", "-5"], capture_output=True, text=True)
        out = (r1.stdout + "\n" + r2.stdout).strip()
        if not out: info("Nothing to show (not a git repo or no changes)"); return
        print(f"\n  {B}{WH}Git status{R}\n")
        for line in out.splitlines():
            print(f"  {GR}{line}{R}")
        print()
    elif sub == "commit":
        r1 = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
        if not r1.stdout.strip():
            r1 = subprocess.run(["git", "diff"], capture_output=True, text=True)
        if not r1.stdout.strip():
            warn("No changes to commit."); return
        diff_text = r1.stdout[:3000]
        prompt = (
            "Write a concise git commit message for these changes.\n"
            "Format: short subject line (50 chars max), then optionally a blank line and body.\n"
            "Just return the commit message, nothing else.\n\n"
            f"Diff:\n{diff_text}"
        )
        memory.add("user", prompt)
        messages = build_messages(system_prompt, memory.get())
        print(f"\n  {B}{WH}Generating commit message...{R}\n")
        try:
            reply = stream_and_render(client, messages, model, name)
        except Exception as e:
            fail(str(e)); memory._history.pop(); return
        memory._history[-1] = {"role": "user", "content": "[git commit message]"}
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
        warn(f"Unknown git subcommand: {sub}  —  try: /git status | /git commit | /git log")


# ── Auto-fallback across providers ───────────────────────────
def stream_with_fallback(client, messages: list, model: str, name: str,
                          providers: list, current_provider: str) -> tuple:
    """Try current provider, if quota/rate fails try next provider automatically."""
    try:
        reply = stream_and_render(client, messages, model, name)
        return reply, client, model, current_provider
    except Exception as e:
        msg = str(e)
        # Only auto-fallback on quota/rate errors
        if not any(x in msg for x in ("429", "limit: 0", "RESOURCE_EXHAUSTED", "quota")):
            raise

        # Find next available provider
        remaining = [p for p in providers if p != current_provider]
        if not remaining:
            raise

        next_p = remaining[0]
        info(f"Quota hit on {current_provider} — switching to {next_p} automatically")
        set_provider(next_p)
        new_client = get_client()
        new_model  = get_models(next_p)[0]
        reply = stream_and_render(new_client, messages, new_model, name)
        return reply, new_client, new_model, next_p



# ── /todo ─────────────────────────────────────────────────────
def cmd_todo(args: str):
    parts = args.strip().split(maxsplit=1) if args.strip() else []
    sub   = parts[0].lower() if parts else "list"
    rest  = parts[1] if len(parts) > 1 else ""
    if sub == "list":
        todos = todo_list()
        if not todos: info("No todos yet. Use /todo add <task>"); return
        print(f"\n  {B}{WH}Todos{R}\n")
        for t in todos:
            check = f"{GN}✓{R}" if t["done"] else f"{DG}○{R}"
            style = DG if t["done"] else WH
            print(f"  {check}  {GR}#{t['id']}{R}  {style}{t['text']}{R}  {DG}{t['created']}{R}")
        print()
    elif sub == "done":
        try:
            idx = int(rest)
            if todo_done(idx): ok(f"Marked #{idx} as done")
            else: warn(f"No todo #{idx}")
        except ValueError:
            warn("Usage: /todo done <id>")
    elif sub == "remove":
        try:
            idx = int(rest)
            if todo_remove(idx): ok(f"Removed #{idx}")
            else: warn(f"No todo #{idx}")
        except ValueError:
            warn("Usage: /todo remove <id>")
    elif sub == "clear":
        todo_clear_done(); ok("Cleared all completed todos")
    else:
        text = rest or args.strip()
        if text:
            item = todo_add(text); ok(f"#{item['id']}  {item['text']}")
        else:
            warn("Usage: /todo [add <task>|list|done <id>|remove <id>|clear]")


# ── /note ─────────────────────────────────────────────────────
def cmd_note(args: str):
    parts = args.strip().split(maxsplit=1) if args.strip() else []
    sub   = parts[0].lower() if parts else "list"
    rest  = parts[1] if len(parts) > 1 else ""
    if sub == "list":
        notes = note_list()
        if not notes: info("No notes yet. Use /note <text>"); return
        print(f"\n  {B}{WH}Notes{R}  {DG}({len(notes)}){R}\n")
        for n in notes[-20:]:
            tag = f"  {CY}#{n['tag']}{R}" if n.get("tag") else ""
            print(f"  {GR}#{n['id']}{R}  {DG}{n['created']}{R}{tag}")
            print(f"     {WH}{n['text'][:120]}{R}\n")
    elif sub == "search":
        if not rest: warn("Usage: /note search <query>"); return
        results = note_search(rest)
        if not results: info(f"No notes matching '{rest}'"); return
        print(f"\n  {B}{WH}Search results{R}  {DG}({len(results)}){R}\n")
        for n in results:
            print(f"  {GR}#{n['id']}{R}  {DG}{n['created']}{R}  {WH}{n['text'][:100]}{R}\n")
    elif sub == "remove":
        try:
            idx = int(rest)
            if note_remove(idx): ok(f"Removed note #{idx}")
            else: warn(f"No note #{idx}")
        except ValueError:
            warn("Usage: /note remove <id>")
    elif sub == "export":
        md   = notes_to_markdown()
        path = os.path.expanduser("~/lumi_notes.md")
        open(path, "w").write(md)
        ok(f"Exported to {path}")
    else:
        import re as _re
        text = args.strip()
        tag  = ""
        m = _re.match(r"#(\w+)\s+(.*)", text)
        if m: tag, text = m.group(1), m.group(2)
        if text:
            item = note_add(text, tag)
            ok(f"Note #{item['id']} saved{f'  #{tag}' if tag else ''}")
        else:
            warn("Usage: /note <text>  or  /note #tag <text>  or  /note list|search|remove|export")


# ── /weather ──────────────────────────────────────────────────
def cmd_weather(location: str = ""):
    sp = Spinner("fetching weather"); sp.start()
    try:
        result = get_weather(location or "Tashkent")
    finally:
        sp.stop()
    print(f"\n  {CY}◆{R}  {WH}{result}{R}\n")


# ── /listen — voice input via Groq Whisper ───────────────────
def cmd_listen(seconds: int = 5) -> str:
    if not os.getenv("GROQ_API_KEY"):
        warn("Voice input needs GROQ_API_KEY in .env"); return ""
    info(f"Recording for {seconds}s... speak now")
    path = record_audio(seconds)
    if not path:
        fail("No recording tool found. Install: arecord (Linux) or sox"); return ""
    sp = Spinner("transcribing"); sp.start()
    text = transcribe_groq(path)
    sp.stop()
    try: os.unlink(path)
    except Exception: pass
    if text: ok(f"Heard: {text}")
    else:    warn("Could not transcribe audio")
    return text


# ── /speak — voice output ─────────────────────────────────────
def cmd_speak(text: str):
    if not text: warn("Nothing to speak."); return
    if not speak(text):
        warn("No TTS found. Install: espeak-ng (Linux) or pyttsx3 (pip install pyttsx3)")


# ── /paste — clipboard input ──────────────────────────────────
def cmd_paste() -> str:
    text = clipboard_get()
    if not text: warn("Clipboard is empty or not accessible"); return ""
    ok(f"Pasted {len(text)} chars from clipboard")
    return text


# ── /copy — copy last reply to clipboard ─────────────────────
def cmd_copy(text: str):
    if not text: warn("Nothing to copy."); return
    if clipboard_set(text): ok("Copied to clipboard")
    else: warn("Clipboard not accessible. Install: xclip (Linux) or wl-clipboard (Wayland)")


# ── /screenshot — capture screen + analyze ───────────────────
def cmd_screenshot(client, model: str, memory, system_prompt: str, name: str):
    info("Taking screenshot...")
    path = take_screenshot()
    if not path:
        fail("No screenshot tool found. Install: scrot or ImageMagick (import)"); return
    ok(f"Screenshot saved: {path}")
    print(f"\n  {DG}What should Lumi analyze?{R}  ", end="")
    try:
        question = input().strip() or "Describe what you see in this screenshot."
    except (KeyboardInterrupt, EOFError):
        return
    try:
        import base64 as _b64
        from openai import OpenAI as _OAI
        img_b64 = encode_image_base64(path)
        vision_client = _OAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY", "")
        )
        resp = vision_client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}],
            max_tokens=1024
        )
        reply = resp.choices[0].message.content.strip()
        print_lumi_label(name)
        from src.utils.markdown import render as md_render
        indented = "\n".join("  " + l for l in md_render(reply).split("\n"))
        print(indented)
        memory.add("user", f"[Screenshot]: {question}")
        memory.add("assistant", reply)
    except Exception as e:
        fail(f"Vision analysis failed: {e}")
    finally:
        try: os.unlink(path)
        except Exception: pass


# ── /project — load directory as context ─────────────────────
def cmd_project(path: str, memory):
    if not path: warn("Usage: /project <directory>"); return
    sp = Spinner("loading project"); sp.start()
    context = load_project(path)
    sp.stop()
    if context.startswith("Not a directory"):
        fail(context); return
    memory.add("user", f"[Project loaded: {path}]\n\n{context}")
    memory.add("assistant", "Got it. I have your project context. Ask me anything about the codebase.")
    ok(f"Project loaded: {path}")
    info("Ask me anything about your codebase")


# ── /pdf — read PDF file ──────────────────────────────────────
def cmd_pdf(path: str, memory):
    path = path.strip().strip("'\"")
    if not path: warn("Usage: /pdf <path>"); return
    sp = Spinner("reading PDF"); sp.start()
    text = read_pdf(path)
    sp.stop()
    if text.startswith("File not found") or text.startswith("Could not"):
        fail(text); return
    fname = os.path.basename(path)
    memory.add("user", f"[PDF: {fname}]\n\n{text}")
    memory.add("assistant", f"I've read {fname}. Ask me anything about it.")
    ok(f"PDF loaded: {fname}  ({len(text.split())} words)")
    info("Ask me anything about the document")


# ── /standup ─────────────────────────────────────────────────
def cmd_standup(client, model: str, memory, system_prompt: str, name: str):
    import subprocess as _sp
    r = _sp.run(["git", "log", "--oneline", "--since=24 hours ago"],
                capture_output=True, text=True)
    git_log  = r.stdout.strip() or "No commits in the last 24 hours"
    todos    = [t for t in todo_list() if not t["done"]]
    todo_txt = "\n".join(f"- {t['text']}" for t in todos[:10]) or "No pending todos"
    prompt = (
        "Generate a short daily standup. Format: Yesterday / Today / Blockers. "
        "Keep it concise and realistic.\n\n"
        f"Recent commits:\n{git_log}\n\nPending todos:\n{todo_txt}"
    )
    memory.add("user", prompt)
    messages = build_messages(system_prompt, memory.get())
    print(f"\n  {B}{WH}Daily Standup{R}\n")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory._history[-1] = {"role": "user", "content": "[standup]"}
        memory.add("assistant", reply)
    except Exception as e:
        fail(str(e)); memory._history.pop()


# ── /timer ────────────────────────────────────────────────────
def cmd_timer(args: str):
    import re as _re
    m = _re.match(r"(\d+)\s*(m|min|s|sec|h|hr)?", args.strip().lower())
    if not m: warn("Usage: /timer 25m  or  /timer 5s  or  /timer 1h"); return
    val  = int(m.group(1))
    unit = m.group(2) or "m"
    if unit.startswith("s"):   secs = val
    elif unit.startswith("h"): secs = val * 3600
    else:                      secs = val * 60
    label = args.strip()
    ok(f"Timer set: {label}")
    def _tick():
        import time as _t
        _t.sleep(secs)
        print(f"\n\a  {GN}⏰{R}  {WH}Timer done: {label}{R}\n  ", end="", flush=True)
        try:
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", "Lumi Timer", f"{label} is up!"], capture_output=True)
            elif shutil.which("osascript"):
                subprocess.run(["osascript", "-e",
                    f'display notification "{label} is up!" with title "Lumi"'], capture_output=True)
        except Exception: pass
    threading.Thread(target=_tick, daemon=True).start()


# ── /draft ────────────────────────────────────────────────────
def cmd_draft(args: str, client, model: str, memory, system_prompt: str, name: str):
    if not args.strip(): warn("Usage: /draft email to boss about deadline"); return
    prompt = (
        "Draft the following message. Match tone to medium (email=formal, slack=casual, text=brief). "
        "Return just the message, no meta-commentary.\n\n"
        f"Request: {args}"
    )
    memory.add("user", prompt)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Draft: {args}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory._history[-1] = {"role": "user", "content": f"[draft: {args}]"}
        memory.add("assistant", reply)
    except Exception as e:
        fail(str(e)); memory._history.pop()


# ── /comment — add code comments ─────────────────────────────
def cmd_comment(target: str, client, model: str, memory, system_prompt: str, name: str, last_reply: str):
    # Inject elite coding prompt for this command
    import re as _re
    if target and os.path.exists(os.path.expanduser(target.strip())):
        code  = open(os.path.expanduser(target.strip()), encoding="utf-8", errors="replace").read()
        label = os.path.basename(target.strip())
    elif last_reply:
        m     = _re.search(r"```[^\n]*\n(.*?)```", last_reply, _re.DOTALL)
        code  = m.group(1) if m else last_reply
        label = "last reply"
    else:
        warn("No code to comment. Use /comment <file> or after a code reply."); return
    prompt = (
        "Add clear helpful comments and docstrings to this code. "
        "Explain the 'why', not just the 'what'. Keep existing code unchanged.\n\n"
        f"```\n{code[:5000]}\n```\n\nReturn only the commented code."
    )
    memory.add("user", prompt)
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Add comments to {label}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory._history[-1] = {"role": "user", "content": f"[comment: {label}]"}
        memory.add("assistant", reply)
    except Exception as e:
        fail(str(e)); memory._history.pop()


# ── /lang — language learning mode ───────────────────────────
def cmd_lang(language: str, current_prompt: str) -> str:
    if not language or language.lower() == "off":
        if "[LANGUAGE LEARNING" in current_prompt:
            new = current_prompt.split("[LANGUAGE LEARNING")[0].strip()
            ok("Language learning mode off"); return new
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


# ── /compact — toggle minimal output ─────────────────────────
_compact_mode = [False]
def toggle_compact() -> bool:
    _compact_mode[0] = not _compact_mode[0]
    return _compact_mode[0]
def is_compact() -> bool:
    return _compact_mode[0]


# ── Mood tracking ─────────────────────────────────────────────
MOOD_PATH = "data/memory/mood_log.json"

def log_mood(emotion: str, turn: int):
    if not emotion: return
    try:
        os.makedirs("data/memory", exist_ok=True)
        try:   log = json.loads(open(MOOD_PATH).read())
        except: log = []
        from datetime import datetime as _dt
        log.append({"ts": _dt.now().isoformat(), "emotion": emotion, "turn": turn})
        open(MOOD_PATH, "w").write(json.dumps(log[-100:], indent=2))
    except Exception: pass

def check_mood_pattern() -> str | None:
    try:
        log    = json.loads(open(MOOD_PATH).read())
        recent = log[-10:]
        neg    = sum(1 for e in recent if e.get("emotion") in ("frustrated", "sad", "confused"))
        if neg >= 6:
            return "hey, you've seemed pretty stressed lately — everything good?"
    except Exception: pass
    return None


# ── /github — issues ─────────────────────────────────────────
def cmd_github(subcmd: str, client, model: str, memory, system_prompt: str, name: str):
    import urllib.request as _ur
    token = os.getenv("GITHUB_TOKEN", "")
    sub   = subcmd.strip().lower() if subcmd else "issues"
    if sub == "issues":
        if not token:
            warn("Add GITHUB_TOKEN=ghp_... to .env for GitHub integration"); return
        try:
            req = _ur.Request(
                "https://api.github.com/issues?filter=assigned&state=open&per_page=20",
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github.v3+json"}
            )
            with _ur.urlopen(req, timeout=8) as r:
                issues = json.loads(r.read())
            if not issues: info("No open issues assigned to you"); return
            print(f"\n  {B}{WH}Open Issues{R}\n")
            for iss in issues[:15]:
                repo  = iss.get("repository", {}).get("full_name", "")
                print(f"  {CY}#{iss['number']}{R}  {WH}{iss['title']}{R}  {DG}{repo}{R}")
            print()
            issues_text = "\n".join(f"#{i['number']}: {i['title']}" for i in issues[:15])
            prompt = f"Which of these GitHub issues should I work on first and why?\n\n{issues_text}"
            memory.add("user", prompt)
            messages = build_messages(system_prompt, memory.get())
            try:
                reply = stream_and_render(client, messages, model, name)
                memory._history[-1] = {"role": "user", "content": "[github issues]"}
                memory.add("assistant", reply)
            except Exception as e:
                fail(str(e)); memory._history.pop()
        except Exception as e:
            fail(f"GitHub API error: {e}")
    else:
        warn(f"Unknown: {sub}  —  try /github issues")


# ── /data — CSV/JSON analysis ─────────────────────────────────
def cmd_data(path: str, client, model: str, memory, system_prompt: str, name: str):
    path = path.strip().strip("'\"")
    if not path: warn("Usage: /data <file.csv|file.json>"); return
    sp = Spinner("loading data"); sp.start()
    context = analyze_data_file(path)
    sp.stop()
    if context.startswith("File not found") or context.startswith("Could not"):
        fail(context); return
    fname = os.path.basename(path)
    memory.add("user", f"[Data: {fname}]\n\n{context}\n\nAnalyze this. What are the key insights?")
    messages = build_messages(system_prompt, memory.get())
    print_you(f"Analyze {fname}")
    try:
        reply = stream_and_render(client, messages, model, name)
        memory._history[-1] = {"role": "user", "content": f"[data: {fname}]"}
        memory.add("assistant", reply)
    except Exception as e:
        fail(str(e)); memory._history.pop()


def _parse_args():
    """Parse CLI arguments — inspired by Claude Code and Gemini CLI."""
    import argparse
    ap = argparse.ArgumentParser(
        prog="lumi",
        description="Lumi AI — terminal assistant with 5 providers and council mode",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
    )
    # Core
    ap.add_argument("query",            nargs="?",       default=None,
                    help="Send a message and start interactive session")
    ap.add_argument("-p", "--print",    dest="print_mode", action="store_true",
                    help="Non-interactive: send query, print response, exit")
    ap.add_argument("-c", "--continue", dest="resume_latest", action="store_true",
                    help="Continue most recent conversation")
    ap.add_argument("-r", "--resume",   metavar="SESSION",
                    help="Resume session by name or ID  (use 'latest' for most recent)")
    ap.add_argument("-v", "--version",  action="store_true",
                    help="Show version and exit")
    ap.add_argument("-h", "--help",     action="store_true",
                    help="Show this help and exit")

    # Model / provider
    ap.add_argument("--model", "-m",    metavar="MODEL",
                    help="Set model for this session  (e.g. gemini-2.5-flash, council)")
    ap.add_argument("--provider",       metavar="PROVIDER",
                    help="Set provider  (gemini|groq|openrouter|mistral|huggingface|ollama)")

    # System prompt
    ap.add_argument("--system-prompt",  metavar="TEXT",
                    help="Replace system prompt with custom text")
    ap.add_argument("--append-system-prompt", metavar="TEXT",
                    help="Append text to the default system prompt")
    ap.add_argument("--system-prompt-file",   metavar="FILE",
                    help="Replace system prompt with contents of a file")
    ap.add_argument("--append-system-prompt-file", metavar="FILE",
                    help="Append file contents to default system prompt")

    # Behaviour
    ap.add_argument("--yolo",           action="store_true",
                    help="Auto-approve all file writes — no confirmation prompts")
    ap.add_argument("--max-turns",      metavar="N",     type=int, default=None,
                    help="Exit after N conversation turns  (non-interactive use)")
    ap.add_argument("--output-format",  metavar="FMT",   choices=["text","json"],
                    default="text",
                    help="Output format for --print mode: text (default) or json")
    ap.add_argument("--verbose",        action="store_true",
                    help="Show verbose output (full API errors, token counts, etc)")
    ap.add_argument("--no-color",       action="store_true",
                    help="Disable ANSI colors")

    # Session utils
    ap.add_argument("--list-sessions",  action="store_true",
                    help="List saved sessions and exit")
    ap.add_argument("--delete-session", metavar="ID",
                    help="Delete a session by ID and exit")

    return ap.parse_known_args()[0]


LUMI_VERSION = "2.0.0"


def main():
    args = _parse_args()

    # ── --version ─────────────────────────────────────────────
    if args.version:
        print(f"Lumi {LUMI_VERSION}")
        sys.exit(0)

    # ── --help ────────────────────────────────────────────────
    if args.help:
        print(f"  Lumi AI {LUMI_VERSION}")
        print("  Usage: lumi [query] [flags]")
        print("")
        print(f"  {B}Flags:{R}")
        print("   -p  --print               non-interactive mode")
        print("   -c  --continue            resume last conversation")
        print("   -r  --resume SESSION      resume by name/id")
        print("   -m  --model MODEL         set model")
        print("       --provider PROVIDER   set provider")
        print("       --system-prompt TEXT  replace system prompt")
        print("       --append-system-prompt TEXT  append to prompt")
        print("       --yolo                auto-approve file writes")
        print("       --max-turns N         exit after N turns")
        print("       --output-format FMT   text or json")
        print("       --verbose             full error output")
        print("       --list-sessions       list sessions and exit")
        print("   -v  --version             show version")
        print("")
        print(f"  {B}Examples:{R}")
        print("   lumi -p \"explain this\" < file.py")
        print("   lumi -c --model council")
        print("   lumi --yolo --append-system-prompt \"always use TypeScript\"")
        print("")
        sys.exit(0)

    # ── --no-color ────────────────────────────────────────────
    if args.no_color:
        # Monkey-patch all color vars to empty string
        import src.utils.themes as _themes
        _themes._NO_COLOR = True

    # ── --list-sessions ───────────────────────────────────────
    if args.list_sessions:
        sessions = list_sessions()
        if not sessions:
            print("  No saved sessions found.")
        else:
            header = f"  {'#':<4}  {'ID':<36}  Date"
            sep    = f"  {'─'*4}  {'─'*36}  {'─'*20}"
            print(header)
            print(sep)
            for i, s in enumerate(sessions, 1):
                print(f"  {i:<4}  {s.get('id','?'):<36}  {s.get('date','?')}")
            print()
        sys.exit(0)

    # ── --delete-session ──────────────────────────────────────
    if args.delete_session:
        from src.memory.conversation_store import delete_session
        try:
            delete_session(args.delete_session)
            print(f"  Deleted session: {args.delete_session}")
        except Exception as e:
            print(f"  Error: {e}")
        sys.exit(0)

    # ── Pipe mode ─────────────────────────────────────────────
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            import os as _os
            _os.environ.setdefault("LUMI_PIPE_INPUT", piped)

    history_setup()

    persona          = load_persona()
    persona_override = get_persona_override()
    system_prompt    = make_system_prompt(persona, persona_override)
    memory           = ShortTermMemory(max_turns=20)

    # ── --provider ────────────────────────────────────────────
    if args.provider:
        prov = args.provider.lower()
        if prov in get_available_providers():
            set_provider(prov)
        else:
            print(f"  Unknown provider: {prov}  (available: {', '.join(get_available_providers())})")
            sys.exit(1)

    client           = get_client()
    name             = persona_override.get("name") or persona.get("name", "Lumi")

    # ── --model ───────────────────────────────────────────────
    if args.model:
        current_model = args.model
        if args.model == "council":
            pass  # council handled in stream_and_render
        else:
            # Verify model exists for current provider
            available_models = get_models(get_provider())
            if args.model not in available_models:
                # Try as partial match
                matches = [m for m in available_models if args.model.lower() in m.lower()]
                if matches:
                    current_model = matches[0]
                else:
                    current_model = args.model  # trust the user
    else:
        current_model = get_models(get_provider())[0]

    # ── --system-prompt / --append-system-prompt ──────────────
    if args.system_prompt:
        system_prompt = args.system_prompt
    elif args.system_prompt_file:
        try:
            system_prompt = open(os.path.expanduser(args.system_prompt_file)).read()
        except Exception as e:
            print(f"  Error reading system prompt file: {e}"); sys.exit(1)

    if args.append_system_prompt:
        system_prompt = system_prompt + "\n\n" + args.append_system_prompt
    elif args.append_system_prompt_file:
        try:
            extra = open(os.path.expanduser(args.append_system_prompt_file)).read()
            system_prompt = system_prompt + "\n\n" + extra
        except Exception as e:
            print(f"  Error reading append file: {e}"); sys.exit(1)

    # ── --yolo ────────────────────────────────────────────────
    if args.yolo:
        os.environ["LUMI_YOLO"] = "1"

    # ── --verbose ─────────────────────────────────────────────
    if args.verbose:
        os.environ["LUMI_VERBOSE"] = "1"

    current_theme    = load_theme_name()
    multiline        = False
    last_msg         = None
    last_reply       = None
    prev_reply       = None
    lang_mode        = False
    system_prompt_ref = [system_prompt]

    turns            = 0
    response_mode    = None
    current_topic    = None
    AUTOSAVE_EVERY   = 5
    AUTOREMEMBER_EVERY = 8
    max_turns        = args.max_turns  # None = unlimited

    # ── --continue / --resume ─────────────────────────────────
    _load_session = None
    if args.resume_latest or (args.resume and args.resume.lower() == "latest"):
        _load_session = "latest"
    elif args.resume:
        _load_session = args.resume

    if _load_session:
        try:
            h = load_latest() if _load_session == "latest" else load_by_name(_load_session)
            if h:
                for m in h:
                    if isinstance(m.get("content"), str):
                        memory.add(m["role"], m["content"])
                info(f"Resumed session: {_load_session}  ({len(h)} messages)")
        except Exception:
            pass

    # ── --print mode ──────────────────────────────────────────
    if args.print_mode and args.query:
        piped_ctx = os.environ.get("LUMI_PIPE_INPUT", "")
        q = (piped_ctx + "\n\n" + args.query).strip() if piped_ctx else args.query
        memory.add("user", q)
        messages = build_messages(system_prompt, memory.get())
        try:
            if current_model == "council":
                from src.agents.council import council_ask
                reply, _ = council_ask(messages, q, stream=False, debate=True, refine=True)
            else:
                resp = client.chat.completions.create(
                    model=current_model, messages=messages,
                    max_tokens=1024, temperature=0.7, stream=False,
                )
                reply = resp.choices[0].message.content.strip()
            if args.output_format == "json":
                import json as _json
                print(_json.dumps({"query": q, "response": reply, "model": current_model}))
            else:
                print(reply)
        except Exception as e:
            if os.environ.get("LUMI_VERBOSE"):
                print(f"Error: {e}", file=sys.stderr)
            else:
                print(f"Error: {str(e)[:120]}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # ── LUMI.md project context ──────────────────────────────
    _lumi_md = None
    for _md_path in [pathlib.Path("LUMI.md"), pathlib.Path("lumi.md")]:
        if _md_path.exists():
            _lumi_md = _md_path.read_text().strip()
            break
    if _lumi_md:
        system_prompt += f"\n\n--- Project context (LUMI.md) ---\n{_lumi_md}"
        info(f"Loaded LUMI.md project context ({len(_lumi_md)} chars)")

    # ── Load plugins ──────────────────────────────────────────
    _loaded_plugins = load_plugins()
    if _loaded_plugins:
        info(f"Plugins: {', '.join(_loaded_plugins)}")

    draw_header(current_model, 0, "council" if current_model == "council" else get_provider())
    print_welcome(name)

    # ── Start with a query (interactive) ─────────────────────
    _startup_query = args.query or os.environ.get("LUMI_PIPE_INPUT", "")

    threading.Thread(target=health_check, args=(get_available_providers(),), daemon=True).start()

    # Inject startup query if provided via CLI arg or pipe
    _pending_input = _startup_query if _startup_query else ""

    while True:

        # ── Input ─────────────────────────────────────────────
        try:
            div()
            if _pending_input:
                user_input = _pending_input
                _pending_input = ""
                print(f"  {PU}›{R}  {user_input}")
            else:
                user_input = read_multiline().strip() if multiline else input(f"  {PU}›{R}  ").strip()
        except (KeyboardInterrupt, EOFError):
            history_save()
            ok(f"Saved → {save(memory.get())}")
            ok("Goodbye!", "◆", BL)
            sys.exit(0)

        if not user_input: continue

        cmd = user_input.split()[0] if user_input.startswith("/") else None

        # ── Commands ──────────────────────────────────────────
        if cmd in ("/quit", "/exit"):
            history_save()
            ok(f"Saved → {save(memory.get())}")
            ok("Goodbye!", "◆", BL)
            break

        if cmd == "/help":    print_help(); continue

        if cmd == "/clear":
            memory.clear(); last_msg = None; last_reply = None; turns = 0; current_topic = None
            draw_header(current_model, 0, "council" if current_model == "council" else get_provider()); print_welcome(name); continue

        if cmd == "/save":
            parts = user_input.split(maxsplit=1)
            sname = parts[1].strip() if len(parts) > 1 else ""
            p = save(memory.get(), sname)
            ok(f"Saved → {p.name}"); continue

        if cmd == "/load":
            parts = user_input.split(maxsplit=1)
            sname = parts[1].strip() if len(parts) > 1 else ""
            h = load_by_name(sname) if sname else load_latest()
            if h:
                memory._history = h; turns = len(h) // 2
                draw_header(current_model, turns, "council" if current_model == "council" else get_provider())
                ok(f"Loaded {len(h)} messages" + (f" — {sname}" if sname else ""))
            else: warn("No saved conversations found.")
            continue

        if cmd == "/sessions":
            s = list_sessions()
            if s:
                print(f"\n  {B}{WH}Saved sessions{R}  {DG}({len(s)} total){R}\n")
                for x in s:
                    print(f"  {DG}·{R}  {WH}{x['name']:<28}{R}  {GR}{x['date']}{R}  {DG}{x['msgs']} msgs{R}")
                print()
            else: warn("No saved sessions.")
            continue

        if cmd == "/export":
            if not memory.get(): warn("Nothing to export yet.")
            else: ok(f"Exported → {export_md(memory.get(), name)}")
            continue

        if cmd == "/undo":
            if len(memory._history) >= 2:
                memory._history = memory._history[:-2]
                turns = max(0, turns - 1)
                ok("Last exchange removed from memory.")
            else: warn("Nothing to undo.")
            continue

        if cmd == "/retry":
            if last_msg:
                # Ask what was wrong
                try:
                    print(f"\n  {GR}What was wrong with the last reply? (Enter to just resend){R}")
                    feedback = input(f"  {PU}›{R}  ").strip()
                except (KeyboardInterrupt, EOFError):
                    feedback = ""
                user_input = last_msg
                if feedback:
                    user_input = f"{last_msg}\n\n[My previous response wasn't quite right because: {feedback}. Please try again with that in mind.]"
                info(f"Retrying...")
                memory._history = memory._history[:-2] if len(memory._history) >= 2 else []
                turns = max(0, turns - 1)
            else: warn("Nothing to retry."); continue

        if cmd == "/summarize":
            if not memory.get(): warn("Nothing to summarize yet."); continue
            q = "Summarize our conversation so far in a few bullet points."
            memory.add("user", q)
            messages = build_messages(system_prompt, memory.get())
            print_you(q)
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as e:
                fail(str(e)); memory._history.pop(); continue
            memory._history[-1] = {"role": "user", "content": q}
            memory.add("assistant", raw_reply)
            last_reply = raw_reply; turns += 1; print(); continue

        if cmd == "/tl;dr":
            if not last_reply: warn("No reply to summarize yet."); continue
            sp = Spinner("summarizing"); sp.start()
            summary = silent_call(client,
                f"Summarize this in ONE sentence (max 20 words):\n\n{last_reply}",
                current_model, max_tokens=60)
            sp.stop()
            if summary:
                print(f"\n  {PU}✦{R}  {WH}{summary}{R}\n")
            else:
                warn("Couldn't summarize.")
            continue

        if cmd == "/more":
            if not last_reply: warn("Nothing to expand on yet."); continue
            q = f"Expand on your last response with more detail and examples. Last response was:\n\n{last_reply}"
            memory.add("user", "[User wants more detail on the last response.]")
            messages = build_messages(system_prompt, memory.get())
            print_you("Tell me more...")
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as e:
                fail(str(e)); memory._history.pop(); continue
            memory._history[-1] = {"role": "user", "content": "Tell me more."}
            memory.add("assistant", raw_reply)
            last_reply = raw_reply; turns += 1; print(); continue

        if cmd == "/rewrite":
            if not last_reply: warn("Nothing to rewrite yet."); continue
            q = f"Rewrite your last response in a completely different way — different structure, different wording, same meaning. Last response:\n\n{last_reply}"
            memory.add("user", "[User wants the last response rewritten differently.]")
            messages = build_messages(system_prompt, memory.get())
            print_you("Rewrite that differently...")
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as e:
                fail(str(e)); memory._history.pop(); continue
            memory._history[-1] = {"role": "user", "content": "Rewrite that differently."}
            memory.add("assistant", raw_reply)
            last_reply = raw_reply; turns += 1; print(); continue

        if cmd == "/fix":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /fix <error message>")
            else:
                r = cmd_fix(parts[1].strip(), client, current_model, memory, system_prompt, name, last_reply)
                if r: last_reply = r; turns += 1; print()
            continue

        if cmd == "/explain":
            parts = user_input.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            r = cmd_explain(target, client, current_model, memory, system_prompt, name, last_reply)
            if r: last_reply = r; turns += 1; print()
            continue

        if cmd == "/review":
            parts = user_input.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            r = cmd_review(target, client, current_model, memory, system_prompt, name, last_reply)
            if r: last_reply = r; turns += 1; print()
            continue

        if cmd == "/file":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /file <path>")
            else:
                r = cmd_file(parts[1].strip(), client, current_model, memory, system_prompt, name)
                if r: last_reply = r; turns += 1; print()
            continue

        if cmd == "/find":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /find <keyword>")
            else: cmd_find(parts[1].strip())
            continue

        if cmd == "/remember":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /remember <fact>")
            else:
                n = add_fact(parts[1].strip())
                system_prompt = make_system_prompt(persona, get_persona_override())
                ok(f"Remembered — {n} fact{'s' if n != 1 else ''} stored.")
            continue

        if cmd == "/memory":   cmd_memory(); continue
        if cmd == "/forget":
            cmd_forget()
            system_prompt = make_system_prompt(persona, get_persona_override())
            continue

        if cmd == "/persona":
            cmd_persona()
            persona_override = get_persona_override()
            name             = persona_override.get("name") or persona.get("name", "Lumi")
            system_prompt    = make_system_prompt(persona, persona_override)
            draw_header(current_model, turns, "council" if current_model == "council" else get_provider()); continue

        if cmd in ("/short", "/detailed", "/bullets"):
            response_mode = cmd[1:]
            labels = {"short":"concise","detailed":"in-depth","bullets":"as bullet points"}
            info(f"Next reply will be {labels[response_mode]}."); continue

        if cmd == "/translate":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /translate <language>")
            elif not last_reply: warn("No reply to translate yet.")
            else:
                lang = parts[1].strip()
                q = f"Translate your last response into {lang}. Output only the translation."
                memory.add("user", q)
                messages = build_messages(system_prompt, memory.get())
                print_you(f"Translate to {lang}")
                try:
                    raw_reply = stream_and_render(client, messages, current_model, name)
                except Exception as e:
                    fail(str(e)); memory._history.pop(); continue
                memory._history[-1] = {"role": "user", "content": f"Translate to {lang}"}
                memory.add("assistant", raw_reply)
                last_reply = raw_reply; turns += 1; print()
            continue

        if cmd == "/imagine":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /imagine <prompt>")
            else: cmd_imagine(parts[1].strip())
            continue

        if cmd == "/theme":
            current_theme = cmd_theme(current_theme)
            draw_header(current_model, turns, "council" if current_model == "council" else get_provider()); continue

        if cmd == "/model":
            new_model, new_provider = pick_model(current_model)
            current_model = new_model
            if new_provider != "council":
                client = get_client()   # refresh client for new provider
            draw_header(current_model, turns, get_provider() if new_provider != "council" else "council")
            label = PROVIDER_LABELS.get(new_provider, (new_provider,))[0]
            ok(f"Model → {current_model.split('/')[-1]}  ({label})"); continue

        if cmd == "/multi":
            multiline = not multiline
            info(f"Multi-line input {'on' if multiline else 'off'}"); continue

        if cmd == "/council":
            # Show agent roster
            from src.agents.council import _get_available_agents
            active = _get_available_agents()
            if not active:
                fail("No council agents available — add API keys to .env"); continue
            parts = user_input.split(maxsplit=1)
            # /council <question> or /council --show <question>
            show_ind = False
            if len(parts) > 1 and parts[1].startswith("--show"):
                show_ind = True
                q = parts[1][6:].strip() if len(parts[1]) > 6 else last_msg or ""
            elif len(parts) > 1:
                q = parts[1].strip()
            else:
                q = last_msg or ""
            if not q:
                warn("Usage: /council <question>  or just ask and Lumi picks council mode"); continue
            _coding = is_complex_coding_task(q)
            _sys_prompt = make_system_prompt(persona, override=get_persona_override(), coding_mode=_coding)
            _msgs = build_messages(_sys_prompt, memory.get()) + [{"role": "user", "content": q}]
            last_reply = cmd_council(q, _msgs, name, show_ind)
            if last_reply:
                memory.add("user", q)
                memory.add("assistant", last_reply)
                turns += 1
            continue

        # ── New commands ──────────────────────────────────────

        if cmd == "/web":
            args = user_input.split(maxsplit=1)[1] if len(user_input.split(maxsplit=1)) > 1 else ""
            cmd_web(args, client, current_model, memory, system_prompt, name)
            turns += 1; print(); continue

        if cmd == "/image":
            args = user_input.split(maxsplit=1)[1] if len(user_input.split(maxsplit=1)) > 1 else ""
            cmd_image(args, client, current_model, memory, system_prompt, name)
            turns += 1; print(); continue

        if cmd == "/context":
            cmd_context(memory, system_prompt, current_model); continue

        if cmd == "/redo":
            parts = user_input.split(maxsplit=2)
            alt   = parts[1] if len(parts) > 1 else ""
            raw   = cmd_redo(client, current_model, memory, system_prompt, name, last_msg or "", alt)
            if raw: last_reply = raw; turns += 1
            print(); continue

        if cmd == "/agent":
            args = user_input.split(maxsplit=1)[1] if len(user_input.split(maxsplit=1)) > 1 else ""
            reply = cmd_agent(args, client, current_model, memory, system_prompt, name)
            if reply: last_reply = reply; turns += 1
            print(); continue

        if cmd == "/mcp":
            args = user_input.split(maxsplit=1)[1] if len(user_input.split(maxsplit=1)) > 1 else ""
            cmd_mcp(args, client, current_model, memory, system_prompt, name); continue

        if cmd == "/plugins":
            sub = (user_input.split(maxsplit=1)[1:] or [""])[0].strip()
            if sub == "reload":
                loaded = load_plugins()
                ok(f"Reloaded: {', '.join(loaded) or 'none'}")
            else:
                cmds = get_commands()
                if cmds:
                    print(f"\n  {B}{WH}Loaded plugins{R}\n")
                    for c, d in cmds.items():
                        print(f"  {PU}{c:<20}{R}  {GR}{d}{R}")
                    print()
                else:
                    info(f"No plugins loaded.  Drop .py files in ~/Lumi/plugins/")
            continue

        if cmd == "/lumi.md":
            sub = (user_input.split(maxsplit=1)[1:] or [""])[0].strip()
            if sub == "show":
                md = pathlib.Path("LUMI.md")
                if md.exists():
                    print(f"\n  {GR}{md.read_text()}{R}\n")
                else:
                    warn("No LUMI.md in current directory")
            elif sub == "create":
                if pathlib.Path("LUMI.md").exists():
                    warn("LUMI.md already exists"); 
                else:
                    template = f"""# Project Context

## Stack
<!-- e.g. Python 3.11, FastAPI, PostgreSQL -->

## Conventions
<!-- coding style, naming, patterns to follow -->

## Rules
<!-- things Lumi should always / never do in this project -->

## Key files
<!-- important files and what they do -->
"""
                    pathlib.Path("LUMI.md").write_text(template)
                    ok("Created LUMI.md — edit it, then restart Lumi to load it")
            else:
                info("Usage: /lumi.md show | /lumi.md create")
            continue

        if cmd == "/search":
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2: warn("Usage: /search <query>"); continue
            query = parts[1].strip()
            sp = Spinner("searching"); sp.start()
            try:
                results, _ = search_display(query)
            except Exception as e:
                sp.stop(); fail(str(e)); continue
            sp.stop()
            if not results: warn("No results found."); continue
            print(f"\n  {B}{WH}Results for:{R}  {GR}{query}{R}\n")
            for i, r in enumerate(results, 1):
                print(f"  {CY}{i}.{R}  {WH}{r['title']}{R}")
                print(f"      {MU}{r['url']}{R}")
                if r.get("snippet"):
                    print(f"{GR}{textwrap.fill(r['snippet'], W()-8, initial_indent='      ', subsequent_indent='      ')}{R}")
                print()
            ctx = search(query, fetch_top=True)
            memory.add("user", f"I searched for: {query}\n\n{ctx}\n\nSummarize the key findings briefly.")
            messages = build_messages(system_prompt, memory.get())
            try:
                raw_reply = stream_and_render(client, messages, current_model, name)
            except Exception as e:
                fail(str(e)); memory._history.pop(); continue
            memory._history[-1] = {"role": "user", "content": f"Search: {query}"}
            memory.add("assistant", raw_reply)
            last_reply = raw_reply; turns += 1; print(); continue

        if cmd == "/run":
            if not last_reply: warn("No reply yet to run code from."); continue
            output = cmd_run(last_reply)
            if output:
                # Feed output back so Lumi can explain errors
                memory.add("user", f"[Code output]: {output[:500]}")
                memory.add("assistant", "[Output received]")
            continue

        if cmd == "/edit":
            parts = user_input.split(maxsplit=1)
            path  = parts[1].strip() if len(parts) > 1 else ""
            if not path:
                print(f"\n  {DG}Path to file:{R}  ", end="")
                try: path = input().strip()
                except (KeyboardInterrupt, EOFError): continue
            last_reply = cmd_edit(path, client, current_model, memory, system_prompt, name, last_reply or "")
            turns += 1; continue

        if cmd == "/diff":
            cmd_diff(last_reply or "", prev_reply or ""); continue

        if cmd == "/git":
            parts  = user_input.split(maxsplit=1)
            subcmd = parts[1].strip() if len(parts) > 1 else "status"
            cmd_git(subcmd, client, current_model, memory, system_prompt, name, last_reply or ""); continue

        if cmd == "/cost":
            cmd_cost(); continue

        if cmd == "/todo":
            parts = user_input.split(maxsplit=1)
            cmd_todo(parts[1] if len(parts) > 1 else "list"); continue

        if cmd == "/note":
            parts = user_input.split(maxsplit=1)
            cmd_note(parts[1] if len(parts) > 1 else "list"); continue

        if cmd == "/weather":
            parts = user_input.split(maxsplit=1)
            cmd_weather(parts[1].strip() if len(parts) > 1 else ""); continue

        if cmd == "/listen":
            parts = user_input.split(maxsplit=1)
            try: secs = int(parts[1]) if len(parts) > 1 else 5
            except: secs = 5
            heard = cmd_listen(secs)
            if heard:
                last_msg = heard
                memory.add("user", heard)
                messages = build_messages(system_prompt, memory.get())
                print_you(heard)
                try:
                    raw_reply, client, current_model, new_prov = stream_with_fallback(
                        client, messages, current_model, name, get_available_providers(), get_provider()
                    )
                    memory._history[-1] = {"role": "user", "content": heard}
                    memory.add("assistant", raw_reply)
                    prev_reply = last_reply; last_reply = raw_reply; turns += 1
                except Exception as e:
                    fail(str(e)); memory._history.pop()
            continue

        if cmd == "/speak":
            cmd_speak(last_reply or ""); continue

        if cmd == "/paste":
            pasted = cmd_paste()
            if pasted:
                last_msg = pasted
                memory.add("user", pasted)
                messages = build_messages(system_prompt, memory.get())
                print_you(f"[Clipboard: {pasted[:60]}...]")
                try:
                    raw_reply, client, current_model, new_prov = stream_with_fallback(
                        client, messages, current_model, name, get_available_providers(), get_provider()
                    )
                    memory._history[-1] = {"role": "user", "content": pasted}
                    memory.add("assistant", raw_reply)
                    prev_reply = last_reply; last_reply = raw_reply; turns += 1
                except Exception as e:
                    fail(str(e)); memory._history.pop()
            continue

        if cmd == "/copy":
            cmd_copy(last_reply or ""); continue

        if cmd == "/screenshot":
            cmd_screenshot(client, current_model, memory, system_prompt, name)
            turns += 1; continue

        if cmd == "/project":
            parts = user_input.split(maxsplit=1)
            path  = parts[1].strip() if len(parts) > 1 else ""
            if not path:
                print(f"\n  {DG}Project path:{R}  ", end="")
                try: path = input().strip()
                except (KeyboardInterrupt, EOFError): continue
            cmd_project(path, memory); continue

        if cmd == "/pdf":
            parts = user_input.split(maxsplit=1)
            cmd_pdf(parts[1].strip() if len(parts) > 1 else "", memory); continue

        if cmd == "/standup":
            cmd_standup(client, current_model, memory, system_prompt, name)
            turns += 1; continue

        if cmd == "/timer":
            parts = user_input.split(maxsplit=1)
            cmd_timer(parts[1].strip() if len(parts) > 1 else "25m"); continue

        if cmd == "/draft":
            parts = user_input.split(maxsplit=1)
            cmd_draft(parts[1].strip() if len(parts) > 1 else "", client, current_model, memory, system_prompt, name)
            turns += 1; continue

        if cmd == "/comment":
            parts = user_input.split(maxsplit=1)
            cmd_comment(parts[1].strip() if len(parts) > 1 else "", client, current_model, memory, system_prompt, name, last_reply or "")
            turns += 1; continue

        if cmd == "/lang":
            parts = user_input.split(maxsplit=1)
            lang  = parts[1].strip() if len(parts) > 1 else ""
            system_prompt_ref[0] = cmd_lang(lang, system_prompt_ref[0])
            system_prompt = system_prompt_ref[0]; continue

        if cmd == "/compact":
            on = toggle_compact()
            info(f"Compact mode {'on — raw text only' if on else 'off — full formatting'}"); continue

        if cmd == "/github":
            parts = user_input.split(maxsplit=1)
            cmd_github(parts[1].strip() if len(parts) > 1 else "issues",
                       client, current_model, memory, system_prompt, name)
            turns += 1; continue

        if cmd == "/data":
            parts = user_input.split(maxsplit=1)
            cmd_data(parts[1].strip() if len(parts) > 1 else "", client, current_model, memory, system_prompt, name)
            turns += 1; continue

        if cmd and cmd.startswith("/"):
            fail(f"Unknown command: {cmd}  —  type /help"); continue

        # Sync system_prompt from ref (for /lang updates)
        system_prompt = system_prompt_ref[0]

        # ── Dynamic coding mode injection ────────────────────
        # Detect if this is a coding or file-generation task and
        # inject the full elite coding system prompt automatically.
        _is_code  = is_complex_coding_task(user_input) or is_coding_task(user_input)
        _is_files = is_file_generation_task(user_input)
        if _is_code or _is_files:
            # Rebuild system prompt with coding/file modes on
            _enhanced = make_system_prompt(persona,
                                           override=get_persona_override(),
                                           coding_mode=_is_code,
                                           file_mode=_is_files)
            # Preserve any /lang suffix
            if "[LANGUAGE LEARNING" in system_prompt:
                _lang_suffix = "[LANGUAGE LEARNING" + system_prompt.split("[LANGUAGE LEARNING")[1]
                _enhanced += "\n\n" + _lang_suffix
            system_prompt = _enhanced

        # ── Plan-first for complex multi-file tasks ───────────
        if needs_plan_first(user_input) and _is_files:
            _plan_hint = (
                "\n\n[INSTRUCTION: Before writing any code, output a brief one-paragraph plan: "
                "what files you will create, what each does, and how they connect. "
                "Then write each file completely with no placeholders.]"
            )
            system_prompt += _plan_hint

        # ── File system agent (intercept before anything else) ──
        if is_create_request(user_input):
            sp = Spinner("generating file plan"); sp.start()
            # In council mode, client is valid but model is "council" — use a real model
            _fs_client = client
            _fs_model  = current_model
            if current_model == "council":
                from src.chat.hf_client import get_models as _gm
                _real_prov = get_provider()
                _fs_model  = _gm(_real_prov)[0]
            plan = generate_file_plan(user_input, _fs_client, _fs_model)
            sp.stop()
            if plan:
                root  = plan.get("root", ".")
                files = plan.get("files", [])
                # Ask where to create — default home dir
                home = os.path.expanduser("~")
                print(f"\n  {DG}Where should I create this?{R}  {WH}[{home}]{R}  ", end="", flush=True)
                try:
                    dest_input = input().strip()
                except (KeyboardInterrupt, EOFError):
                    dest_input = ""
                base_dir = os.path.expanduser(dest_input) if dest_input else home
                # Show preview with full path
                full_root = os.path.join(base_dir, root) if root and root != "." else base_dir
                print(f"\n  {B}{WH}File plan{R}  {DG}→ {full_root}{R}\n")
                if root and root != ".":
                    print(f"  {CY}📁 {root}/{R}")
                for f in files:
                    print(f"  {GR}   📄 {f.get('path','')}{R}")
                print()
                print(f"  {DG}Create these files? [Y/n]{R}  ", end="", flush=True)
                try:
                    confirm = input().strip().lower()
                except (KeyboardInterrupt, EOFError):
                    confirm = "n"
                if confirm in ("", "y", "yes"):
                    created  = write_file_plan(plan, base_dir=base_dir)
                    summary  = format_creation_summary(plan, created)
                    ok(f"Created {len(created)} items in {base_dir}")
                    has_html = any(f.get("path","").endswith(".html") for f in files)
                    opener   = f"Open `{full_root}/index.html` in your browser to see it live." if has_html else "Let me know if you want to edit anything."
                    reply    = f"Done! Created in `{full_root}`:\n\n```\n{summary}\n```\n\n{opener}"
                    print_lumi_label(name)
                    from src.utils.markdown import render as _md
                    print("\n".join("  " + l for l in _md(reply).split("\n")))
                    memory.add("user", user_input)
                    memory.add("assistant", reply)
                    prev_reply = last_reply; last_reply = reply; turns += 1
                else:
                    info("Cancelled.")
            else:
                fail("Couldn\'t generate a file plan. Try being more specific, e.g: \'create a folder called myapp with index.html and style.css\'")
            continue

        # ── Emotion detection ─────────────────────────────────
        emotion = detect_emotion(user_input)
        hint    = emotion_hint(emotion) if emotion else ""
        log_mood(emotion, turns)
        # Periodic mood check-in
        if turns > 0 and turns % 20 == 0:
            mood_msg = check_mood_pattern()
            if mood_msg: info(mood_msg)

        # ── Topic tracking ────────────────────────────────────
        topic = detect_topic(user_input)
        if topic and topic != current_topic:
            current_topic = topic

        # ── Auto web search ───────────────────────────────────
        augmented = user_input
        if should_search(user_input):
            sp = Spinner("searching"); sp.start()
            try:
                results_text = search(user_input, fetch_top=True)
            except Exception:
                results_text = ""
            sp.stop()
            if results_text and not results_text.startswith("[No"):
                augmented = (
                    f"{user_input}\n\n[Web search results:]\n{results_text}\n"
                    "[Use the above to inform your answer. Cite sources where relevant.]"
                )
                print(f"\n  {CY}◆{R}  {GR}Found web results{R}")

        # ── Response mode prefix ──────────────────────────────
        if response_mode == "short":
            augmented += "\n\n[Reply concisely — 2-3 sentences max.]"
        elif response_mode == "detailed":
            augmented += "\n\n[Reply in detail — be thorough and comprehensive.]"
        elif response_mode == "bullets":
            augmented += "\n\n[Reply using bullet points only.]"
        response_mode = None

        # ── Inject emotion hint ───────────────────────────────
        if hint:
            augmented = hint + augmented

        # ── Context compression (when > 15 turns) ──────────
        if len(memory.get()) > 15 and turns % 10 == 0 and turns > 0:
            def _compress():
                try:
                    old_turns = memory.get()[:-4]  # keep last 4
                    if not old_turns: return
                    _sc_model = get_models(get_provider())[0] if current_model == "council" else current_model
                    summary = silent_call(client,
                        'Summarize this conversation in 3-5 sentences, keeping all key technical details:\n\n' +
                        '\n'.join(f"{m['role']}: {m['content'][:200]}" for m in old_turns),
                        _sc_model, 200
                    )
                    if summary:
                        memory._history = ([{'role':'system','content':f'[Conversation summary]: {summary}'}]
                                          + memory._history[-4:])
                except Exception: pass
            threading.Thread(target=_compress, daemon=True).start()

        # ── Plugin dispatch ───────────────────────────────────
        if cmd:
            handled, plug_result = plugin_dispatch(
                cmd,
                user_input.split(maxsplit=1)[1] if len(user_input.split(maxsplit=1)) > 1 else "",
                client=client, model=current_model,
                memory=memory, system_prompt=system_prompt, name=name,
            )
            if handled:
                if plug_result:
                    print(f"  {GR}{plug_result}{R}")
                continue

        # ── Chat ──────────────────────────────────────────────
        last_msg = user_input
        memory.add("user", augmented)
        messages = build_messages(system_prompt, memory.get())
        print_you(user_input)

        try:
            raw_reply, client, current_model, new_prov = stream_with_fallback(
                client, messages, current_model, name, get_available_providers(), get_provider()
            )
            if new_prov != get_provider():
                draw_header(current_model, turns, "council" if current_model == "council" else get_provider())
        except Exception as e:
            fail(str(e)); memory._history.pop(); continue

        memory._history[-1] = {"role": "user", "content": user_input}
        memory.add("assistant", raw_reply)
        prev_reply = last_reply
        last_reply = raw_reply
        turns += 1
        print()
        # --max-turns exit
        if max_turns and turns >= max_turns:
            ok(f"Reached --max-turns {max_turns} — exiting")
            history_save()
            save(memory.get())
            sys.exit(0)

        # ── Auto-save ─────────────────────────────────────────
        if turns % AUTOSAVE_EVERY == 0:
            try: save(memory.get())
            except Exception: pass

        # ── Auto-remember (background) ────────────────────────
        if turns % AUTOREMEMBER_EVERY == 0:
            def _bg_remember():
                try:
                    new_facts = auto_extract_facts(client, current_model, memory.get())
                    if new_facts:
                        # Rebuild system prompt with new facts
                        nonlocal system_prompt
                        system_prompt = make_system_prompt(persona, get_persona_override())
                except Exception:
                    pass
            threading.Thread(target=_bg_remember, daemon=True).start()


if __name__ == "__main__":
    main()
