"""Lumi CLI — polished."""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import shutil
import textwrap
import threading
import time
import itertools
from datetime import datetime

from src.chat.hf_client import get_client, chat_stream, MODELS
from src.memory.short_term import ShortTermMemory
from src.memory.conversation_store import save, load_latest, list_sessions
from src.prompts.builder import load_persona, build_system_prompt, build_messages
from src.tools.search import search, should_search
from src.utils.markdown import render as md_render
from src.utils.export import export_md

# ── Palette ───────────────────────────────────────────────────
def fg(n): return f"\033[38;5;{n}m"
R  = "\033[0m"
B  = "\033[1m"
D  = "\033[2m"
IT = "\033[3m"

C1 = fg(117)  # bright cyan      — logo row 1-2
C2 = fg(111)  # blue-cyan        — logo row 3-4
C3 = fg(105)  # muted purple     — logo row 5-6
PU = fg(141)  # purple           — lumi label
BL = fg(75)   # blue             — prompt arrow
CY = fg(117)  # cyan             — info/search
GR = fg(245)  # gray             — secondary text
DG = fg(238)  # dark gray        — dividers
MU = fg(60)   # very muted       — timestamps
GN = fg(114)  # green            — success
RE = fg(203)  # red              — errors
YE = fg(179)  # yellow           — warnings
WH = fg(255)  # white            — main text

def W():     return shutil.get_terminal_size().columns
def clear(): os.system("clear")
def ts():    return datetime.now().strftime("%H:%M")
def div(c=DG, ch="─"): print(f"{c}{ch * W()}{R}")


# ── ASCII logo ────────────────────────────────────────────────
LOGO = [
    (" ██╗     ██╗   ██╗███╗   ███╗██╗", C1),
    (" ██║     ██║   ██║████╗ ████║██║", C1),
    (" ██║     ██║   ██║██╔████╔██║██║", C2),
    (" ██║     ██║   ██║██║╚██╔╝██║██║", C2),
    (" ███████╗╚██████╔╝██║ ╚═╝ ██║██║", C3),
    (" ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝", C3),
]


def draw_header(model: str, turns: int = 0):
    clear()
    pad = " " * max((W() - 34) // 2, 0)
    print()
    for row, color in LOGO:
        print(f"{pad}{color}{B}{row}{R}")
    print()

    sub = "A R T I F I C I A L   I N T E L L I G E N C E"
    print(f"{' ' * max((W()-len(sub))//2, 0)}{DG}{sub}{R}")
    print()

    m       = model.split("/")[-1]
    count   = f"  {DG}·{R}  {DG}{turns} turns{R}" if turns else ""
    raw_len = len(f"model › {m}") + (len(f"  ·  {turns} turns") if turns else 0)
    line    = f"{DG}model › {GR}{m}{R}{count}"
    print(f"{' ' * max((W()-raw_len)//2, 0)}{line}")
    print()
    div()
    print()


# ── Spinner ───────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, label="thinking"):
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
            time.sleep(0.08)

    def stop(self):
        self._running = False
        if self._thread: self._thread.join()
        sys.stdout.write(f"\r{' ' * W()}\r")
        sys.stdout.flush()


# ── Print helpers ─────────────────────────────────────────────
def print_you(text: str):
    # Wrap long messages
    w        = W() - 12
    wrapped  = textwrap.wrap(text, width=w) if len(text) > w else [text]
    stamp    = f"{MU}{ts()}{R}"
    print()
    print(f"  {GR}{D}you{R}  {WH}{wrapped[0]}{R}  {stamp}")
    for line in wrapped[1:]:
        print(f"        {WH}{line}{R}")


def print_lumi_label():
    print(f"\n  {PU}{B}✦ Lumi{R}  {MU}{ts()}{R}\n")


def ok(msg, icon="✓", c=GN):
    print(f"\n  {c}{icon}{R}  {GR}{msg}{R}\n")

def fail(msg):
    wrapped = textwrap.fill(str(msg), width=W() - 10)
    print(f"\n  {RE}✗{R}  {GR}{wrapped}{R}\n")

def info(msg):
    print(f"\n  {CY}◆{R}  {GR}{msg}{R}\n")

def warn(msg):
    print(f"\n  {YE}!{R}  {GR}{msg}{R}\n")


# ── Welcome ───────────────────────────────────────────────────
def print_welcome(name: str):
    msg = f"Hi! I'm {name}. Type {WH}/help{GR} for commands or just start chatting."
    print(f"  {PU}✦{R}  {GR}{msg}{R}\n")


# ── Help ──────────────────────────────────────────────────────
def print_help():
    print()
    div()
    print(f"\n  {B}{WH}Commands{R}\n")
    cmds = [
        ("/help",        "show this"),
        ("/clear",       "reset conversation"),
        ("/save",        "save conversation to disk"),
        ("/load",        "load last saved conversation"),
        ("/sessions",    "list all saved sessions"),
        ("/export",      "export chat as .md file"),
        ("/retry",       "resend last message"),
        ("/model",       "switch model interactively"),
        ("/model <n>",   "set model by name directly"),
        ("/multi",       "toggle multi-line paste mode"),
        ("/quit",        "save and exit"),
    ]
    for cmd, desc in cmds:
        print(f"  {CY}{cmd:<16}{R}  {GR}{desc}{R}")
    print(f"\n  {DG}tip{R}  {GR}run with {WH}--debug{GR} to see raw API logs{R}")
    print()
    div()
    print()


# ── Model picker ──────────────────────────────────────────────
def pick_model(cur: str) -> str:
    print(f"\n  {B}{WH}Available models{R}\n")
    for i, m in enumerate(MODELS):
        dot    = f"{GN}●{R}" if m == cur else f"{DG}○{R}"
        active = f"  {MU}active{R}" if m == cur else ""
        print(f"  {dot}  {GR}{i+1}.{R}  {WH}{m.split('/')[-1]}{R}{active}")
    print()
    try:
        raw = input(f"  {BL}{B}›{R}  ").strip()
        idx = int(raw) - 1
        if 0 <= idx < len(MODELS): return MODELS[idx]
    except (ValueError, KeyboardInterrupt): pass
    warn("Keeping current model.")
    return cur


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


# ── Stream into buffer, rerender as markdown ──────────────────
def stream_and_render(client, messages: list, model: str) -> str:
    """Stream tokens live, then clear and reprint as styled markdown."""
    spinner    = Spinner("thinking")
    spinner.start()

    raw_reply  = ""
    first      = True

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                if first:
                    spinner.stop()
                    print_lumi_label()
                    first = False
                print(delta, end="", flush=True)
                raw_reply += delta

        if first:
            spinner.stop()

        print()

    except Exception as e:
        spinner.stop()
        raise e

    # Clear what was streamed, reprint as styled markdown
    if raw_reply:
        # Count lines we printed: lumi label (3 lines) + streamed lines
        streamed_lines = raw_reply.count("\n") + 4
        for _ in range(streamed_lines):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()

        print_lumi_label()
        rendered = md_render(raw_reply)
        indented = "\n".join("  " + l for l in rendered.split("\n"))
        print(indented)

    return raw_reply


# ── Main ─────────────────────────────────────────────────────
def main():
    persona       = load_persona()
    system_prompt = build_system_prompt(persona)
    memory        = ShortTermMemory(max_turns=20)
    client        = get_client()
    name          = persona.get("name", "Lumi")
    current_model = MODELS[0]
    multiline     = False
    last_msg      = None
    turns         = 0

    draw_header(current_model)
    print_welcome(name)

    while True:

        # ── Input ─────────────────────────────────────────────
        try:
            div()
            if multiline:
                user_input = read_multiline().strip()
            else:
                user_input = input(f"  {BL}{B}›{R}  ").strip()
        except (KeyboardInterrupt, EOFError):
            ok(f"Saved → {save(memory.get())}")
            ok("Goodbye!", "◆", BL)
            print()
            sys.exit(0)

        if not user_input: continue

        cmd = user_input.split()[0] if user_input.startswith("/") else None

        # ── Commands ──────────────────────────────────────────
        if cmd in ("/quit", "/exit"):
            ok(f"Saved → {save(memory.get())}")
            ok("Goodbye!", "◆", BL)
            break

        if cmd == "/help":    print_help(); continue
        if cmd == "/clear":
            memory.clear(); last_msg = None; turns = 0
            draw_header(current_model)
            print_welcome(name)
            continue

        if cmd == "/save":    ok(f"Saved → {save(memory.get())}"); continue

        if cmd == "/load":
            h = load_latest()
            if h:
                memory._history = h
                turns = len(h) // 2
                draw_header(current_model, turns)
                ok(f"Loaded {len(h)} messages.")
            else:
                warn("No saved conversations found.")
            continue

        if cmd == "/sessions":
            s = list_sessions()
            if s:
                print(f"\n  {B}{WH}Saved sessions{R}\n")
                for x in s: print(f"  {DG}·{R}  {GR}{x}{R}")
                print()
            else:
                warn("No saved sessions.")
            continue

        if cmd == "/export":
            if not memory.get(): warn("Nothing to export yet.")
            else: ok(f"Exported → {export_md(memory.get(), name)}")
            continue

        if cmd == "/retry":
            if last_msg:
                user_input = last_msg
                info(f"Retrying: {user_input}")
                memory._history = memory._history[:-2] if len(memory._history) >= 2 else []
                turns = max(0, turns - 1)
            else:
                warn("Nothing to retry.")
                continue

        if cmd == "/model":
            parts = user_input.split(maxsplit=1)
            current_model = parts[1].strip() if len(parts) > 1 else pick_model(current_model)
            draw_header(current_model, turns)
            ok(f"Model → {current_model.split('/')[-1]}")
            continue

        if cmd == "/multi":
            multiline = not multiline
            info(f"Multi-line input {'on' if multiline else 'off'}")
            continue

        if cmd and cmd.startswith("/"):
            fail(f"Unknown command: {cmd}  —  type /help")
            continue

        # ── Web search ────────────────────────────────────────
        augmented = user_input
        if should_search(user_input):
            print(f"\n  {CY}◆{R}  {DG}Searching the web...{R}", end="", flush=True)
            results = search(user_input)
            if not results.startswith("[No results") and not results.startswith("[Search failed"):
                augmented = (
                    f"{user_input}\n\n[Search results:]\n{results}\n"
                    "[Use the above to inform your answer if relevant.]"
                )
                print(f"  {GN}done{R}")
            else:
                print(f"  {YE}no results{R}")

        # ── Chat ──────────────────────────────────────────────
        last_msg = user_input
        memory.add("user", augmented)
        messages = build_messages(system_prompt, memory.get())

        print_you(user_input)

        try:
            raw_reply = stream_and_render(client, messages, current_model)
        except Exception as e:
            fail(str(e))
            memory._history.pop()
            continue

        memory._history[-1] = {"role": "user", "content": user_input}
        memory.add("assistant", raw_reply)
        turns += 1
        print()


if __name__ == "__main__":
    main()
