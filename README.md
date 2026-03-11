# ◆ Lumi AI — Terminal Development Environment

```
██╗      ██╗   ██╗  ███╗   ███╗  ██╗
██║      ██║   ██║  ████╗ ████║  ██║
██║      ██║   ██║  ██╔████╔██║  ██║
██║      ██║   ██║  ██║╚██╔╝██║  ██║
███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║
╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝
```

**Lumi** is a full-featured AI development environment that lives entirely inside your terminal. Pure Python, zero UI library dependencies — no `rich`, no `textual`, no `curses`. Every pixel is hand-drawn with raw ANSI escape codes and a Tokyo Night color palette.

> Built by **Sardor Sodiqov**

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running Lumi](#running-lumi)
6. [Command Reference](#command-reference)
7. [Vessel Mode](#vessel-mode)
8. [Provider System](#provider-system)
9. [Council Mode](#council-mode)
10. [Memory System](#memory-system)
11. [Plugin System](#plugin-system)
12. [Keybindings](#keybindings)
13. [Project Context (LUMI.md)](#project-context-lumimd)
14. [File Structure](#file-structure)

---

## Features

- **Pure Python TUI** — Tokyo Night theme, zero external UI libraries
- **10 AI providers** — Gemini, Groq, OpenRouter, Mistral, HuggingFace, GitHub Models, Cohere, Cloudflare, Ollama, Council
- **8-agent Council mode** — all providers answer in parallel, debate, and produce a refined consensus
- **Vessel Mode** — strip the Lumi persona and channel Gemini, Qwen, or OpenCode directly through your terminal
- **Long-term memory** — facts persist across sessions and are injected into every system prompt
- **Auto web search** — questions about current events trigger a live search before the AI answers
- **File agent** — say "create a FastAPI app" and Lumi plans and writes every file to disk
- **Context compression** — every 10 turns, old history is summarized to preserve quality
- **Auto-remember** — every 8 turns, Lumi silently extracts facts and stores them permanently
- **Plugin system** — drop a `.py` file into `~/Lumi/plugins/` to add new slash commands
- **Session persistence** — auto-saves every 5 turns; full session list and restore
- **Git integration** — status, AI commit messages, PR descriptions, changelogs, daily standups
- **Code tools** — explain, review, fix, debug, refactor, optimize, security audit, type hints, tests
- **Developer tools** — grep, find, tree, lint, format, scaffold any framework
- **Emotion detection** — adjusts tone based on how you write
- **Multiline input** — Enter for newlines, Ctrl+D to submit

---

## Architecture

```
Lumi/
├── main.py                      # CLI entry point
├── lumi_system_instructions.md  # Core system prompt
├── LUMI.md                      # Per-project context (auto-loaded)
├── .env                         # API keys
├── requirements.txt
├── install.sh
│
└── src/
    ├── tui/
    │   └── app.py               # Full TUI — renderer, input, commands, Vessel Mode
    │
    ├── chat/
    │   └── hf_client.py         # Multi-provider OpenAI-compatible client
    │
    ├── agents/
    │   ├── agent.py             # Autonomous multi-step agent
    │   └── council.py           # 8-agent parallel council with debate + refinement
    │
    ├── memory/
    │   ├── short_term.py        # Rolling window (max 20 turns)
    │   ├── longterm.py          # Persistent facts, persona overrides
    │   └── conversation_store.py
    │
    ├── prompts/
    │   └── builder.py           # System prompt builder, task detection
    │
    ├── tools/
    │   ├── search.py            # Web search + top-page fetch
    │   └── mcp.py               # MCP (Model Context Protocol) server manager
    │
    └── utils/
        ├── intelligence.py      # Emotion, topic detection, search triggers
        ├── web.py               # URL fetcher
        ├── filesystem.py        # File plan generator and writer
        ├── autoremember.py      # Silent fact extraction
        ├── export.py            # Markdown export
        ├── plugins.py           # Plugin loader + dispatcher
        ├── tools.py             # Weather, clipboard, PDF, project loader, data
        ├── todo.py              # Persistent todo list
        ├── notes.py             # Persistent notes
        └── voice.py             # Voice input (Groq Whisper) + TTS
```

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/yourusername/Lumi.git ~/Lumi
cd ~/Lumi
python3 -m venv venv
source venv/bin/activate.fish    # fish shell
# or: source venv/bin/activate   # bash/zsh
pip install -r requirements.txt
```

Or use the one-line installer:

```bash
chmod +x install.sh && ./install.sh
```

Add an alias to your shell config:

```bash
# fish (~/.config/fish/config.fish)
alias lumi "source ~/Lumi/venv/bin/activate.fish && python ~/Lumi/main.py"

# bash/zsh (~/.bashrc or ~/.zshrc)
alias lumi="source ~/Lumi/venv/bin/activate && python ~/Lumi/main.py"
```

---

## Configuration

Create `~/Lumi/.env`:

```env
# ── Required (at least one) ───────────────────────────────────────────
GEMINI_API_KEY=AIza...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
MISTRAL_API_KEY=...
HF_TOKEN=hf_...
GITHUB_API_KEY=ghp_...
COHERE_API_KEY=...
CLOUDFLARE_API_KEY=...

# ── Optional ──────────────────────────────────────────────────────────
TAVILY_API_KEY=tvly-...        # Enables real-time web search
GITHUB_TOKEN=ghp_...           # /github issues integration
```

Keys you don't have are skipped. Lumi falls back to the next available provider automatically on quota exhaustion.

---

## Running Lumi

```bash
# Full TUI (recommended)
lumi --tui

# CLI interactive
lumi

# Single prompt
lumi "explain async/await in Python"

# Specific provider
lumi --provider groq

# Council mode
lumi --council "architect a distributed job queue"
```

---

## Command Reference

All commands use the `/` prefix. Tab-completes in the TUI. Press `/` to open the command picker.

### Conversation

| Command | Description |
|---------|-------------|
| `/clear` | Clear conversation and memory |
| `/retry` | Resend the last message |
| `/redo [hint]` | Regenerate with a different approach: `/redo be more concise` |
| `/undo` | Remove the last exchange |
| `/more` | Expand the last response |
| `/rewrite` | Rewrite with different structure |
| `/tl;dr` | One-sentence summary of the last reply |
| `/summarize` | Bullet-point conversation summary |
| `/translate <lang>` | Translate the last reply |
| `/short` | Next reply: concise |
| `/detailed` | Next reply: comprehensive |
| `/bullets` | Next reply: bullet points |
| `/multi` | Toggle multiline input |

### Code & Dev

| Command | Description |
|---------|-------------|
| `/fix <error>` | Root cause, fix, and prevention |
| `/debug [error]` | Deep debug: root cause + fix + regression test |
| `/explain [file]` | Line-by-line explanation |
| `/review [file]` | Full code review |
| `/improve [file]` | Fix bugs, improve style and error handling |
| `/optimize [file]` | Performance optimization with before/after |
| `/security [file]` | Security audit with severity ratings |
| `/refactor [file]` | Refactor with SOLID principles |
| `/test [file]` | Generate pytest unit tests |
| `/docs [file]` | Generate Google-style docstrings |
| `/types [file]` | Add Python 3.10+ type hints |
| `/comment [file]` | Add inline comments |
| `/run` | Execute code block from last reply |
| `/shell <cmd>` | Run any shell command |
| `/edit <file>` | AI-rewrite a file |
| `/file <path>` | Load file into context |
| `/diff` | Diff current reply vs previous |

### Scaffolding & Project

| Command | Description |
|---------|-------------|
| `/scaffold <type>` | Full project: `fastapi`, `react`, `cli`, `flask`, `django`, `nextjs` |
| `/readme [path]` | Generate README.md |
| `/lint [path]` | Run ruff or flake8 |
| `/fmt [path]` | Format with black or prettier |
| `/grep <pattern> [path]` | Search codebase |
| `/find <name>` | Find files by name |
| `/tree [path]` | Directory tree |

### Git

| Command | Description |
|---------|-------------|
| `/git status` | Status + recent log |
| `/git log` | Graph log |
| `/git diff` | Full diff |
| `/git branch` | List branches |
| `/git commit` | AI-generate commit message |
| `/git commit-confirm` | Stage all and commit |
| `/git push` / `/git pull` | Push or pull |
| `/pr` | Write PR description |
| `/changelog` | Generate CHANGELOG |
| `/standup` | Daily standup from commits + todos |

### Web & Data

| Command | Description |
|---------|-------------|
| `/web <url> [q]` | Fetch URL, ask a question |
| `/search <query>` | Web search + AI summary |
| `/image <path> [q]` | Vision: describe or query an image |
| `/data <file>` | Analyze CSV or JSON |
| `/agent <task>` | Autonomous multi-step agent |

### Memory & Persona

| Command | Description |
|---------|-------------|
| `/remember <fact>` | Save to long-term memory |
| `/memory` | Show all stored facts |
| `/forget [n]` | Remove fact by number |
| `/persona [key=val]` | Change persona attribute |
| `/persona reset` | Restore default Lumi persona |
| `/sys` | Show current system prompt |

### Tools

| Command | Description |
|---------|-------------|
| `/todo add <text>` | Add a todo |
| `/todo list` | List todos |
| `/todo done <n>` | Mark done |
| `/todo rm <n>` | Remove |
| `/note add <text>` | Save a note |
| `/note list` | List notes |
| `/note search <q>` | Search notes |
| `/draft <details>` | Draft email, Slack message, or text |
| `/weather [location]` | Current weather |
| `/timer 25m` | Countdown timer with system notification |
| `/copy` | Copy last reply to clipboard |
| `/paste` | Paste clipboard as message |
| `/pdf <path>` | Load PDF into context |
| `/project <path>` | Load project directory into context |

### Session

| Command | Description |
|---------|-------------|
| `/save [name]` | Save session |
| `/load [name]` | Load session |
| `/sessions` | List saved sessions |
| `/export` | Export as Markdown |
| `/tokens` | Token usage estimate |
| `/context` | Context window breakdown |

### Mode & System

| Command | Description |
|---------|-------------|
| `/model` | Open provider/model picker (`Ctrl+N`) |
| `/council` | Switch to Council mode |
| `/mode normal` | Restore Lumi persona |
| `/mode vessel <ai>` | Activate Vessel Mode |
| `/compact` | Toggle compact display |
| `/plugins` | List loaded plugins |
| `/help` | Show all commands |
| `/exit` | Quit (`Ctrl+Q`) |

---

## Vessel Mode

Vessel Mode transforms Lumi into a pure conduit for another AI. Your TUI stays exactly the same — Tokyo Night theme, same layout, same keybindings — but the underlying model, system prompt, and visual indicators all shift to reflect the new identity.

```bash
/mode vessel gemini      # Channel Google Gemini
/mode vessel qwen        # Channel Qwen (via OpenRouter)
/mode vessel opencode    # Channel OpenCode (via OpenRouter)
/mode normal             # Restore Lumi
```

### What changes

| Element | Normal | Vessel |
|---------|--------|--------|
| Input `λ` symbol | Purple | **Red** |
| Status bar | `◆ Gemini · model · ~2,000tk` | `⬡ VESSEL [GEMINI] · ~2,000tk` |
| Message header | `◆ lumi` in purple | `◆ vessel [gemini]` in **red** |
| System prompt | Full Lumi persona | Stripped — target AI identity injected |
| Provider + model | Current | Switched to target model |

### How it works

1. `set_provider()` switches the client to the correct backend
2. The model is selected from available options, preferring one matching the target name
3. `set_persona_override()` injects a vessel system prompt that explicitly strips the Lumi identity
4. The full system prompt is rebuilt with the vessel instruction prepended
5. All visual indicators shift to red

No new imports. All colors use the existing `_fg()`, `_bg()`, `_bold()` helpers.

---

## Provider System

| Provider | Key | Best For |
|----------|-----|----------|
| Gemini | `GEMINI_API_KEY` | Long context, multimodal |
| Groq | `GROQ_API_KEY` | Speed — Llama, Mixtral, Whisper |
| OpenRouter | `OPENROUTER_API_KEY` | Qwen, Claude, many others |
| Mistral | `MISTRAL_API_KEY` | Code (Codestral), multilingual |
| HuggingFace | `HF_TOKEN` | Open source models |
| GitHub Models | `GITHUB_API_KEY` | GPT-4o, o1, Phi |
| Cohere | `COHERE_API_KEY` | Command A, RAG |
| Cloudflare AI | `CLOUDFLARE_API_KEY` | Edge inference |
| Ollama | *(auto-detect)* | Local models |
| Council | *(uses all above)* | Maximum quality |

**Auto-fallback:** On rate limit or quota exhaustion, Lumi automatically switches to the next available provider without interrupting you.

---

## Council Mode

Council sends your message to all 8 available agents simultaneously. They debate, and a lead agent (selected by task type) produces a refined consensus.

```
/council          # switch to Council mode
/model            # switch back to single provider
```

**Council agents:** Gemini · Kimi K2 (Groq) · GPT-OSS (OpenRouter) · Codestral (Mistral) · Llama 3.3 (HuggingFace) · GPT-4o (GitHub) · Command A (Cohere) · Cloudflare AI

While running, the sidebar shows each agent's live spinner, confidence score (out of 10), and response time.

---

## Memory System

### Short-term (in-session)
Rolling window of the last 20 turns. When full, old turns are compressed silently in a background thread.

### Long-term (persistent)
Facts you tell Lumi are stored and injected into every system prompt.

```
/remember I use TypeScript, not JavaScript
/remember My DB is PostgreSQL 16 on port 5433
/memory                    # show all facts
/forget 2                  # remove fact #2
```

### Auto-remember
Every 8 turns, Lumi reads the conversation and extracts facts worth keeping — your name, preferences, tech stack, project details — without interrupting you.

### Sessions
Auto-saves every 5 turns and on exit. Restore with `/load`, browse with `/sessions`.

---

## Plugin System

Drop a `.py` file into `~/Lumi/plugins/`:

```python
# ~/Lumi/plugins/my_tools.py

def register(registry):
    @registry.register("/hello", "Greet someone")
    def cmd_hello(tui, arg):
        tui._sys(f"Hello, {arg or 'world'}!")
```

List loaded plugins: `/plugins`

---

## Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+N` | Model/provider picker |
| `Ctrl+L` | Clear conversation |
| `Ctrl+R` | Retry last message |
| `Ctrl+W` | Delete previous word |
| `Ctrl+U` | Clear input |
| `Ctrl+D` | Submit multiline input |
| `Ctrl+Q` / `Ctrl+C` | Quit |
| `↑ / ↓` | Input history (input not empty) |
| `↑ / ↓` | Scroll chat (input empty) |
| `PgUp / PgDn` | Scroll by page |
| `Ctrl+← / →` | Jump word |
| `Home / End` | Start/end of input |
| `Tab` | Complete slash command |
| `Esc` | Close popup |

---

## Project Context (LUMI.md)

Create `LUMI.md` in your project root. Lumi loads it on startup and injects it into every system prompt.

```markdown
# Project Context

## Stack
Python 3.12, FastAPI, PostgreSQL 16, Redis, Docker

## Conventions
- All endpoints return {"data": ..., "error": null}
- Tests in tests/ using pytest + httpx
- Type hints required everywhere

## Rules
- Never use print() — use logger.info()
- All DB queries go through the repository layer

## Key files
- src/api/routes/   HTTP routes
- src/db/models.py  SQLAlchemy models
- src/core/config.py  settings (pydantic-settings)
```

---

## File Structure

```
~/Lumi/
├── .env
├── LUMI.md               # optional, per-project
├── main.py
├── requirements.txt
├── install.sh
├── README.md
│
├── src/
│   ├── tui/app.py
│   ├── chat/hf_client.py
│   ├── agents/
│   ├── memory/
│   ├── prompts/
│   ├── tools/
│   └── utils/
│
├── data/
│   ├── memory/           # long-term memory + mood log
│   └── sessions/         # saved conversations
│
└── plugins/              # drop .py files here
```

---

## Design Philosophy

Lumi is deliberately built with no external UI libraries. Every border, color, and animation is raw ANSI. This means:

- **No dependencies that can break your terminal** — works anywhere Python 3.10 runs
- **Zero startup overhead** from TUI framework initialization
- **Complete visual control** — Tokyo Night is the rendering logic, not a theme applied to someone else's widgets
- **The TUI and CLI share identical code** — `main.py` and `src/tui/app.py` import the same modules. There is no "TUI mode" with cut-down features

---

*Lumi v3.0 — built for developers who live in the terminal.*
