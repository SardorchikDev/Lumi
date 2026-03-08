"""Lumi CLI — smarter chatbot."""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
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
from src.memory.short_term import ShortTermMemory
from src.memory.longterm import (
    get_facts, add_fact, remove_fact, clear_facts, build_memory_block,
    get_persona_override, set_persona_override, clear_persona_override,
)
from src.memory.conversation_store import save, load_latest, list_sessions
from src.prompts.builder import load_persona, build_system_prompt, build_messages
from src.tools.search import search, search_display
from src.utils.markdown import render as md_render
from src.utils.export import export_md
from src.utils.themes import get_theme, list_themes, save_theme_name, load_theme_name
from src.utils.history import setup as history_setup, save as history_save
from src.utils.intelligence import detect_emotion, emotion_hint, detect_topic, should_search
from src.utils.autoremember import auto_extract_facts

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

# ── ASCII logo ─────────────────────────────────────────────────
LOGO_ROWS = [
    " ██╗     ██╗   ██╗███╗   ███╗██╗",
    " ██║     ██║   ██║████╗ ████║██║",
    " ██║     ██║   ██║██╔████╔██║██║",
    " ██║     ██║   ██║██║╚██╔╝██║██║",
    " ███████╗╚██████╔╝██║ ╚═╝ ██║██║",
    " ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝",
]

def draw_header(model: str, turns: int = 0):
    clear()
    pad = " " * max((W() - 34) // 2, 0)
    print()
    for row, color in zip(LOGO_ROWS, [C1, C1, C2, C2, C3, C3]):
        print(f"{pad}{color}{B}{row}{R}")
    print()
    sub = "A R T I F I C I A L   I N T E L L I G E N C E"
    print(f"{' ' * max((W()-len(sub))//2, 0)}{DG}{sub}{R}")
    print()
    m       = model.split("/")[-1]
    count   = f"  {DG}·{R}  {DG}{turns} turns{R}" if turns else ""
    raw_len = len(f"model › {m}") + (len(f"  ·  {turns} turns") if turns else 0)
    print(f"{' ' * max((W()-raw_len)//2, 0)}{DG}model › {GR}{m}{R}{count}")
    print()
    div()
    print()


# ── Spinner ───────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, label="thinking"):
        self._label = label
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self):
        for f in itertools.cycle(self.FRAMES):
            if not self._running: break
            sys.stdout.write(f"\r  {PU}{f}{R}  {DG}{self._label}{R}  ")
            sys.stdout.flush()
            time.sleep(0.08)

    def stop(self):
        self._running = False
        if self._thread: self._thread.join()
        sys.stdout.write(f"\r{' ' * W()}\r")
        sys.stdout.flush()


# ── Print helpers ─────────────────────────────────────────────
def print_you(text: str):
    w       = W() - 12
    wrapped = textwrap.wrap(text, width=w) if len(text) > w else [text]
    print()
    print(f"  {GR}{D}you{R}  {WH}{wrapped[0]}{R}  {MU}{ts()}{R}")
    for line in wrapped[1:]:
        print(f"        {WH}{line}{R}")

def print_lumi_label(name="Lumi"):
    print(f"\n  {PU}{B}✦ {name}{R}  {MU}{ts()}{R}\n")

def print_welcome(name: str):
    print(f"  {PU}✦{R}  {GR}Hi! I'm {name}. Type {WH}/help{GR} for commands.{R}\n")


# ── Help ──────────────────────────────────────────────────────
def print_help():
    print(); div()
    print(f"\n  {B}{WH}Commands{R}\n")
    sections = [
        ("Chat", [
            ("/help",             "show this"),
            ("/clear",            "reset conversation memory"),
            ("/undo",             "remove last exchange"),
            ("/retry",            "resend last message"),
            ("/more",             "expand on the last reply"),
            ("/tl;dr",            "one-line summary of last reply"),
            ("/rewrite",          "rewrite last reply differently"),
            ("/summarize",        "summarize the whole chat"),
            ("/save",             "save conversation"),
            ("/load",             "load last saved conversation"),
            ("/sessions",         "list saved sessions"),
            ("/export",           "export chat as .md file"),
            ("/find <keyword>",   "search through saved sessions"),
        ]),
        ("Coding", [
            ("/fix <e>",          "diagnose and fix an error"),
            ("/explain [file]",       "explain last reply or a file"),
            ("/review [file]",        "full code review"),
            ("/file <path>",          "load a file into conversation"),
            ("/edit <path>",          "edit a file — Lumi writes changes back"),
            ("/run",                  "execute code from last reply"),
            ("/diff",                 "diff previous vs latest reply"),
            ("/git [status|commit|log]", "git helper"),
        ]),
        ("Response style (one-shot)", [
            ("/short",            "next reply: concise"),
            ("/detailed",         "next reply: detailed"),
            ("/bullets",          "next reply: bullet points"),
        ]),
        ("Web & tools", [
            ("/search <query>",   "search the web"),
            ("/imagine <prompt>", "generate an image (opens browser)"),
            ("/translate <lang>", "translate last reply"),
        ]),
        ("Memory & persona", [
            ("/remember <fact>",  "save a fact to long-term memory"),
            ("/memory",           "view long-term memory"),
            ("/forget",           "manage long-term memory"),
            ("/persona",          "change Lumi's name/tone/traits"),
        ]),
        ("Settings", [
            ("/theme",            "switch color theme"),
            ("/model",            "switch provider + model"),
            ("/multi",            "toggle multi-line input"),
            ("/cost",             "session token usage"),
            ("/quit",             "save and exit"),
        ]),
    ]
    for section, cmds in sections:
        print(f"  {DG}{section}{R}")
        for cmd, desc in cmds:
            print(f"  {CY}{cmd:<22}{R}  {GR}{desc}{R}")
        print()
    print(f"  {DG}tip{R}  {GR}run with {WH}--debug{GR} for raw API logs{R}")
    print(); div(); print()


# ── System prompt builder ─────────────────────────────────────
def make_system_prompt(persona: dict, override: dict = None) -> str:
    merged = {**persona, **(override or {})}
    base   = build_system_prompt(merged)
    mem    = build_memory_block()
    return f"{base}\n\n{mem}" if mem else base


# ── Model picker ──────────────────────────────────────────────
PROVIDER_LABELS = {
    "gemini":      ("Gemini",      "Google Gemini — smart, 1M context"),
    "groq":        ("Groq",        "Groq — fastest, Llama/Qwen/GPT-OSS"),
    "openrouter":  ("OpenRouter",  "30+ free models — DeepSeek R1, Llama 4, Qwen3"),
    "mistral":     ("Mistral",     "Mistral free tier — great for coding"),
    "huggingface": ("HuggingFace", "HuggingFace — free tier, rate limited"),
}

def pick_model(cur_model: str) -> tuple:
    """Returns (new_model, new_provider). Shows provider picker first, then models."""
    available = get_available_providers()
    if not available:
        warn("No API keys found in .env"); return cur_model, get_provider()

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
        raw = input(f"  {BL}{B}›{R}  ").strip()
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

    # Switch provider
    if chosen_provider != cur_provider:
        set_provider(chosen_provider)

    # ── Step 2: pick model ────────────────────────────────────
    sp = Spinner("loading models"); sp.start()
    models = get_models(chosen_provider)
    sp.stop()

    print(f"\n  {B}{WH}Available models{R}  {DG}({PROVIDER_LABELS[chosen_provider][0]}){R}\n")
    default_model = models[0] if models else cur_model
    for i, m in enumerate(models):
        dot    = f"{GN}●{R}" if m == cur_model and chosen_provider == cur_provider else f"{DG}○{R}"
        active = f"  {MU}active{R}" if m == cur_model and chosen_provider == cur_provider else ""
        print(f"  {dot}  {GR}{i+1}.{R}  {WH}{m.split('/')[-1]}{R}{active}")
    print()

    try:
        raw = input(f"  {BL}{B}›{R}  ").strip()
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
    """Ping each provider silently at startup and warn if any are down."""
    import urllib.request
    checks = {
        "gemini":     ("https://generativelanguage.googleapis.com", os.getenv("GEMINI_API_KEY")),
        "groq":       ("https://api.groq.com",                      os.getenv("GROQ_API_KEY")),
        "openrouter": ("https://openrouter.ai",                     os.getenv("OPENROUTER_API_KEY")),
        "mistral":    ("https://api.mistral.ai",                    os.getenv("MISTRAL_API_KEY")),
        "huggingface":("https://huggingface.co",                    os.getenv("HF_TOKEN")),
    }
    dead = []
    for p in providers:
        url, key = checks.get(p, (None, None))
        if not url or not key: continue
        try:
            urllib.request.urlopen(url, timeout=3)
        except Exception:
            dead.append(p)
    if dead:
        warn(f"Can't reach: {', '.join(dead)} — check your connection or key")


def stream_and_render(client, messages: list, model: str, name: str = "Lumi") -> str:
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
        val = input(f"  {BL}{B}›{R}  ").strip()
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
    print(f"\n  {B}{WH}Themes{R}\n")
    for i, t in enumerate(themes):
        dot    = f"{GN}●{R}" if t == current else f"{DG}○{R}"
        tname  = get_theme(t)["name"]
        active = f"  {MU}active{R}" if t == current else ""
        print(f"  {dot}  {GR}{i+1}.{R}  {WH}{tname}{R}{active}")
    print()
    try:
        idx = int(input(f"  {BL}{B}›{R}  ").strip()) - 1
        if 0 <= idx < len(themes):
            chosen = themes[idx]
            save_theme_name(chosen)
            reload_theme(chosen)
            return chosen
    except (ValueError, KeyboardInterrupt): pass
    warn("Keeping current theme.")
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
        instruction = input(f"  {BL}{B}›{R}  ").strip()
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


def main():
    # Pipe mode: python main.py < file.txt or echo "msg" | python main.py
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
    client           = get_client()
    name             = persona_override.get("name") or persona.get("name", "Lumi")
    current_model    = get_models(get_provider())[0]
    current_theme    = load_theme_name()
    multiline        = False
    last_msg         = None
    last_reply       = None
    prev_reply       = None
    turns            = 0
    response_mode    = None
    current_topic    = None
    AUTOSAVE_EVERY   = 5
    AUTOREMEMBER_EVERY = 8  # extract facts every N turns

    draw_header(current_model)
    print_welcome(name)
    # Background health check
    threading.Thread(target=health_check, args=(get_available_providers(),), daemon=True).start()

    while True:

        # ── Input ─────────────────────────────────────────────
        try:
            div()
            user_input = read_multiline().strip() if multiline else input(f"  {BL}{B}›{R}  ").strip()
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
            draw_header(current_model); print_welcome(name); continue

        if cmd == "/save":    ok(f"Saved → {save(memory.get())}"); continue

        if cmd == "/load":
            h = load_latest()
            if h:
                memory._history = h; turns = len(h) // 2
                draw_header(current_model, turns); ok(f"Loaded {len(h)} messages.")
            else: warn("No saved conversations found.")
            continue

        if cmd == "/sessions":
            s = list_sessions()
            if s:
                print(f"\n  {B}{WH}Saved sessions{R}\n")
                for x in s: print(f"  {DG}·{R}  {GR}{x}{R}")
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
                    feedback = input(f"  {BL}{B}›{R}  ").strip()
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
            draw_header(current_model, turns); continue

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
            draw_header(current_model, turns); continue

        if cmd == "/model":
            new_model, new_provider = pick_model(current_model)
            current_model = new_model
            client = get_client()   # refresh client for new provider
            draw_header(current_model, turns)
            ok(f"Model → {current_model.split('/')[-1]}  ({PROVIDER_LABELS.get(new_provider, (new_provider,))[0]})"); continue

        if cmd == "/multi":
            multiline = not multiline
            info(f"Multi-line input {'on' if multiline else 'off'}"); continue

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

        if cmd and cmd.startswith("/"):
            fail(f"Unknown command: {cmd}  —  type /help"); continue

        # ── Emotion detection ─────────────────────────────────
        emotion = detect_emotion(user_input)
        hint    = emotion_hint(emotion) if emotion else ""

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
                draw_header(current_model, turns)
        except Exception as e:
            fail(str(e)); memory._history.pop(); continue

        memory._history[-1] = {"role": "user", "content": user_input}
        memory.add("assistant", raw_reply)
        prev_reply = last_reply
        last_reply = raw_reply
        turns += 1
        print()

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
