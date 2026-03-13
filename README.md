<div align="center">

```
██╗      ██╗   ██╗  ███╗   ███╗  ██╗
██║      ██║   ██║  ████╗ ████║  ██║
██║      ██║   ██║  ██╔████╔██║  ██║
██║      ██║   ██║  ██║╚██╔╝██║  ██║
███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║
╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝
```

# ◆ Lumi AI
### The Ultimate Terminal Development Environment

*An unapologetically native, high-performance AI agent built exclusively for the CLI.*  
*No Electron. No GUI wrappers. No telemetry. Just raw ANSI, extreme speed, and unprecedented agentic autonomy.*

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![CI](https://img.shields.io/github/actions/workflow/status/SardorchikDev/Lumi/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/SardorchikDev/Lumi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-bb9af7?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/Version-0.3.3-7aa2f7?style=for-the-badge)](https://github.com/SardorchikDev/Lumi)
[![Tests](https://img.shields.io/badge/Tests-182_passing-success?style=for-the-badge)](https://github.com/SardorchikDev/Lumi/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/badge/Linted_with-Ruff-30173d?style=for-the-badge&logo=ruff)](https://docs.astral.sh/ruff/)

</div>

---

## Table of Contents

1. [Why Lumi?](#-why-lumi)
2. [What's New in v0.3.3](#-whats-new-in-v033)
3. [Architecture](#-architecture)
4. [Installation](#-installation)
5. [Configuration](#-configuration)
6. [Running Lumi](#-running-lumi)
7. [Premium Features](#-premium-features)
   - [Subprocess Terminal Handoff](#1-subprocess-terminal-handoff-mode-cli)
   - [Live Split-Screen Multiplexing](#2-live-split-screen-multiplexing-pane)
   - [Local FTS5 Codebase RAG](#3-local-fts5-codebase-rag-index--rag)
   - [Interactive Live Diff Application](#4-interactive-live-diff-application-apply)
   - [Native Voice Commands](#5-native-voice-commands-voice)
   - [Background Guardian Agent](#6-background-guardian-agent)
   - [Autonomous God Mode](#7-autonomous-god-mode-godmode)
   - [Air-gapped Offline Privacy](#8-air-gapped-offline-privacy-offline)
8. [Provider System](#-provider-system)
9. [Council Mode](#-council-mode)
10. [Memory System](#-memory-system)
11. [Full Command Reference](#-full-command-reference)
12. [Keybindings](#-keybindings)
13. [Project Context (LUMI.md)](#-project-context-lumimd)
14. [Plugin System](#-plugin-system)
15. [File Structure](#-file-structure)
16. [Development](#-development)
17. [Contributing](#-contributing)

---

## ⚡ Why Lumi?

Most AI coding tools try to pull you out of the terminal. Lumi pulls the AI *into* it.

### Comparison Table

| Feature | **Lumi AI** | **Aider** | **Cursor** | **GitHub Copilot** | **Gemini Code** | **Claude CLI** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Native TUI** | ✅ Tokyo Night | ✅ Basic | ❌ GUI | ❌ IDE Only | ❌ Cloud | ✅ Terminal |
| **Zero Core Deps** | ✅ Pure Python | ❌ Heavy | ❌ Electron | ❌ IDE Plugin | ❌ | ❌ Node/NPM |
| **Multi-Provider** | ✅ 10 providers | ⚠️ Limited | ❌ Proprietary | ❌ Proprietary | ❌ Google Only | ❌ Anthropic Only |
| **Local RAG** | ✅ SQLite FTS5 | ❌ | ✅ | ❌ | ❌ | ✅ |
| **CLI Handoff** | ✅ `/mode` | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Voice Input** | ✅ `/voice` | ❌ | ❌ | ❌ | ❌ | ❌ |
| **God Mode** | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| **8-Agent Council** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Split Panes** | ✅ Built-in | ❌ | ✅ GUI | ❌ | ❌ | ❌ |
| **Offline Mode** | ✅ Ollama | ⚠️ | ❌ | ❌ | ❌ | ❌ |
| **Performance** | 🚀 Extreme | ⚖️ Moderate | 🐢 Heavy | ⚖️ Moderate | ⚖️ Enterprise | ⚖️ Moderate |

### Lumi vs The Rest

**vs Cursor / Copilot** — Lumi doesn't lock you into a proprietary editor. It runs inside your existing `tmux`/`ssh`/`vim` workflow. No 300MB Electron process consuming 2GB of RAM.

**vs Aider / Claude CLI** — Lumi is a full rich TUI, not a scrolling chat log. You get side-panes, visual file trees, interactive diff patching, a 8-agent debate council, and a background guardian — all in a zero-dependency Python runtime. No Node.js required.

**vs Gemini Code Assist** — Lumi gives you raw local control and 8,192 output tokens without enterprise latency or Cloud Shell lock-in. And if you want Gemini's reasoning specifically, `/mode gemini` hands the TTY directly to the `gemini` CLI binary.

---

## 🆕 What's New in v0.3.3

| Feature | Details |
|---------|---------|
| **Visual File Tree** (`/browse`) | Navigate directories and inject files into context with a Nerd Font-styled explorer |
| **Tokyo Night Overhaul** | Full 24-bit color fidelity — every border, glyph, and gradient is hand-tuned |
| **50+ New Dev Commands** | `/git`, `/todo`, `/note`, `/copy`, `/diff`, `/export`, `/scaffold`, `/pr`, `/changelog`, `/standup`, and more |
| **Expanded Context** | Output limits raised to 8,192 tokens for uninterrupted large file generation |
| **Native `/file`** | Instant file ingestion into AI context with automatic memory mapping |
| **Vessel Mode Visuals** | Red `λ`, red `⬡ VESSEL` badge, and red message headers when in CLI handoff mode |
| **Batch Code Commands** | `/improve`, `/optimize`, `/security`, `/refactor`, `/test`, `/docs`, `/types` all work on files or last reply |

---

## 🏗️ Architecture

```
~/Lumi/
├── main.py                       ← CLI entry point + interactive loop
├── pyproject.toml                ← Project metadata, dependencies, ruff & pytest config
├── lumi_system_instructions.md   ← Core system prompt
├── LUMI.md                       ← Per-project context (auto-loaded)
├── .env                          ← API keys
├── requirements.txt              ← Legacy dependency list
├── install.sh
├── .pre-commit-config.yaml       ← Ruff + standard pre-commit hooks
├── CONTRIBUTING.md               ← Developer guide
│
├── .github/workflows/
│   └── ci.yml                    ← Lint (ruff) + Test (pytest, Python 3.10 & 3.12)
│
├── tests/                        ← 182 unit tests (pytest)
│   ├── test_short_term_memory.py
│   ├── test_longterm_memory.py
│   ├── test_conversation_store.py
│   ├── test_prompts_builder.py
│   ├── test_intelligence.py
│   ├── test_agent.py
│   ├── test_council.py
│   ├── test_themes.py
│   ├── test_web.py
│   ├── test_markdown.py
│   ├── test_highlight.py
│   ├── test_filesystem.py
│   ├── test_export.py
│   └── test_log.py
│
└── src/
    ├── tui/
    │   └── app.py                ← Entire TUI: renderer, input engine,
    │                               Vessel Mode, all 50+ slash commands,
    │                               CommandRegistry, Council sidebar
    │
    ├── chat/
    │   └── hf_client.py          ← Unified OpenAI-compatible client
    │                               for all 10 providers
    │
    ├── agents/
    │   ├── agent.py              ← Autonomous multi-step agent (God Mode)
    │   └── council.py            ← 8-agent parallel council with debate
    │                               + refinement loop
    │
    ├── memory/
    │   ├── short_term.py         ← Rolling window, max 20 turns (typed)
    │   ├── longterm.py           ← Persistent facts + persona overrides (typed)
    │   └── conversation_store.py ← Named session save/load (typed)
    │
    ├── prompts/
    │   └── builder.py            ← System prompt builder, task classifier (typed)
    │
    ├── tools/
    │   ├── search.py             ← Web search + top-page fetch
    │   └── mcp.py                ← MCP server manager
    │
    └── utils/
        ├── intelligence.py       ← Emotion detection, topic detection,
        │                           auto-search trigger logic
        ├── log.py                ← Centralized logging (opt-in)
        ├── web.py                ← URL fetcher
        ├── filesystem.py         ← File plan generator + writer
        ├── autoremember.py       ← Silent background fact extraction
        ├── export.py             ← Markdown session export
        ├── plugins.py            ← Plugin loader + dispatcher
        ├── tools.py              ← Weather, clipboard, PDF, data analysis,
        │                           project loader
        ├── todo.py               ← Persistent SQLite todo list
        ├── notes.py              ← Persistent notes with search
        └── voice.py              ← arecord capture + Whisper API
```

**The TUI and CLI share 100% identical module imports.** `main.py` and `src/tui/app.py` call the same functions from the same files. There is no "TUI mode" with cut-down features — everything available in the CLI is available in the TUI.

---

## 📥 Installation

**Requirements:** Python 3.10+, Unix or macOS (Linux strongly recommended for full feature parity including voice and pane support)

```bash
# Clone
git clone https://github.com/SardorchikDev/Lumi.git ~/Lumi
cd ~/Lumi

# Virtual environment
python3 -m venv venv
source venv/bin/activate        # bash/zsh
source venv/bin/activate.fish   # fish shell

# Install dependencies
pip install -r requirements.txt

# Or install with pyproject.toml (recommended)
pip install -e .

# With dev tools (ruff, pytest, pre-commit)
pip install -e ".[dev]"

# Set up pre-commit hooks (recommended for contributors)
pre-commit install
```

**One-liner:**

```bash
chmod +x install.sh && ./install.sh
```

**Shell alias** (add to `~/.bashrc`, `~/.zshrc`, or `~/.config/fish/config.fish`):

```bash
# bash / zsh
alias lumi="source ~/Lumi/venv/bin/activate && python ~/Lumi/main.py"

# fish
alias lumi "source ~/Lumi/venv/bin/activate.fish && python ~/Lumi/main.py"
```

---

## ⚙️ Configuration

Create `~/Lumi/.env`:

```env
# ── Providers (use as many or as few as you have) ──────────────────────────
GEMINI_API_KEY=AIzaSy...          # gemini-2.5-pro, gemini-2.5-flash
GROQ_API_KEY=gsk_...              # llama-3.3, mixtral — fastest inference
OPENROUTER_API_KEY=sk-or-...      # Qwen 72B, Claude 3.5, hundreds more
MISTRAL_API_KEY=...               # Codestral, Mistral Large
HF_TOKEN=hf_...                   # HuggingFace inference
GITHUB_API_KEY=ghp_...            # GPT-4o, o1, Phi via GitHub Models
COHERE_API_KEY=...                # Command A, RAG-optimized
CLOUDFLARE_API_KEY=...            # Edge inference

# ── Optional integrations ──────────────────────────────────────────────────
TAVILY_API_KEY=tvly-...           # Real-time web search (highly recommended)
CLOUDFLARE_ACCOUNT_ID=...         # Required for Cloudflare AI
```

**You only need one key to start.** Missing providers are skipped. If any provider hits a rate limit or quota, Lumi automatically switches to the next available one mid-conversation without interrupting you.

---

## 🚀 Running Lumi

```bash
# Full TUI — recommended
lumi --tui

# CLI interactive mode
lumi

# Single-shot prompt
lumi "explain the difference between async generators and async iterators in Python"

# Force a specific provider
lumi --provider groq

# Start directly in Council mode
lumi --council "design a distributed rate limiter for a multi-region API"
```

---

## 🔥 Premium Features

### 1. Subprocess Terminal Handoff (`/mode <cli>`)

This is Lumi's most unique capability. `/mode` doesn't just switch API providers — it **physically suspends Lumi's event loop** and hands full, raw control of the terminal TTY to an external AI CLI tool. When you exit that tool, the entire session transcript is injected back into Lumi's memory.

**How it works internally:**
1. Lumi calls `termios.tcsetattr` to restore the terminal to cooked mode
2. It writes the alternate screen buffer exit sequence (`\033[?1049l`) to clear the TUI
3. It spawns the target CLI via `script -q -c "<cli_command>" /tmp/lumi_pty_XXXX.cast` — this records the full PTY session including all keystrokes and responses
4. `os.waitpid()` blocks until the subprocess exits
5. Lumi reads the cast file, strips ANSI tracking sequences, and injects the clean transcript as a system message into `ShortTermMemory`
6. It re-enters raw mode, redraws the TUI, and you're back — now with the full context of what you did in the other tool

```bash
/mode gemini      # hands TTY to the `gemini` CLI binary
/mode opencode    # hands TTY to the `opencode` agent
/mode qwen        # hands TTY to a local qwen CLI wrapper
```

**Visual changes while in API-vessel (no external binary):**

When the target CLI isn't installed or `/mode vessel <name>` is used without a local binary, Lumi falls back to API-level vessel mode. The UI signals this clearly:

| Element | Normal | Vessel |
|---------|--------|--------|
| Input `λ` symbol | Purple | **Red** |
| Status bar | `◆ Gemini · model · ~2,000tk` | `⬡ VESSEL [GEMINI] · ~2,000tk` in red |
| Message header | `◆ lumi` in purple | `◆ vessel [gemini]` in **red** |
| System prompt | Full Lumi persona | Stripped — raw model identity injected |

---

### 2. Live Split-Screen Multiplexing (`/pane`)

Run any long-running command in a built-in terminal pane. The command output streams live in real-time on the right side of the UI, while you continue chatting on the left.

```bash
/pane npm run dev          # watch your dev server output while asking Lumi about errors
/pane pytest --watch       # see test results update live as you write fixes
/pane tail -f app.log      # monitor logs while debugging with the AI
/pane cargo watch -x test  # Rust test watcher in the pane
```

**Implementation:** Lumi spawns a pseudo-terminal (PTY) for the subprocess using `pty.openpty()`. A dedicated reader thread pipes `os.read()` chunks from the PTY master fd into the TUI's right-pane store. The renderer draws the pane at `cols - pane_w` with its own independent scroll offset, fully isolated from the chat area.

The pane persists until you close it with `/pane close` or `Ctrl+K`. You can swap what's running in it at any time.

---

### 3. Local FTS5 Codebase RAG (`/index`, `/rag`)

Lumi builds a local SQLite database with an FTS5 (Full-Text Search) virtual table indexing your entire codebase. No embeddings API. No vector database. No network calls.

```bash
/index              # index the current working directory
/index ~/myproject  # index a specific project
/index --watch      # auto-reindex on file changes (inotify/kqueue)

/rag "database connection pooling"   # semantic keyword search
/rag "authentication middleware"     # finds relevant files + injects context
/rag "how does the job scheduler work"
```

**How it works:**
1. `/index` walks the directory tree, reads all code files (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.md`, `.toml`, etc.), and inserts them into an FTS5 table with columns for `path`, `content`, `lang`, and `mtime`
2. `/rag <query>` runs `SELECT path, snippet(...) FROM code_fts WHERE code_fts MATCH ?` using SQLite's native BM25 ranking
3. The top-ranked snippets are formatted and injected directly into the next LLM prompt as `[Codebase context: ...]`
4. The index is stored at `~/.local/share/lumi/index/<project_hash>.db` — fast to rebuild, never sent anywhere

Indexing a 50,000-line Python project takes under 2 seconds. Queries return in under 50ms.

---

### 4. Interactive Live Diff Application (`/apply`)

When the AI generates a code block, `/apply` lets you review and surgically merge it into an existing file without ever leaving the TUI.

```bash
/apply src/api/routes.py
/apply ~/.config/nvim/init.lua
```

**What happens:**
1. Lumi extracts the code block from the last assistant reply
2. It suspends the TUI, restores the terminal to cooked mode, and runs a side-by-side diff using Python's `difflib.unified_diff`
3. You see a colored unified diff (`+` lines in green, `-` lines in red) rendered directly in the terminal
4. A `[y]es / [n]o / [e]dit` prompt appears at the bottom
5. If you choose `y`: the patch is applied with `patch -p0` or a pure-Python fallback for simple cases
6. If you choose `e`: your `$EDITOR` opens with the proposed content pre-loaded
7. The TUI redraws immediately after, and Lumi stores `"Applied to <file>"` as a system message

No external diff tools required. The pure-Python path handles 90% of typical code generation outputs.

---

### 5. Native Voice Commands (`/voice`)

Speak your prompt. Lumi captures audio from your microphone, transcribes it via Whisper, and drops the text directly onto your input cursor.

```bash
/voice         # start recording, press Enter to stop and transcribe
/voice 10      # record for exactly 10 seconds, then auto-transcribe
/listen        # alias
```

**Pipeline:**
1. Lumi calls `arecord -f cd -t wav /tmp/lumi_voice_XXXX.wav` (Linux) or `rec` (macOS via SoX) with `subprocess.Popen`
2. A spinner appears in the TUI border while recording
3. On stop, the WAV file is base64-encoded and sent to the Groq Whisper API (`whisper-large-v3`)
4. The transcript replaces the current input buffer — your cursor is positioned at the end, ready to edit or submit
5. The temp file is deleted immediately after transcription

**Requirements:** `arecord` (Linux, from `alsa-utils`) or `rec` (macOS, from `sox`). A `GROQ_API_KEY` for the Whisper API (fastest and free tier is generous).

---

### 6. Background Guardian Agent

Guardian runs silently on a dedicated daemon thread from the moment Lumi starts. It watches your working directory for code quality issues and broken tests, surfacing them as non-intrusive TUI notifications.

**What it monitors:**
- **Lint status:** Runs `ruff check .` every 30 seconds. If new errors appear since the last check, a yellow warning notification slides into the TUI border: `⚠ 3 new lint errors — /lint to see`
- **Test status:** Watches for `pytest` result files (`.pytest_cache/v/cache/lastfailed`). If a previously-passing test fails, it notifies: `✗ 2 tests broken — /test to generate fixes`
- **File saves:** If you've used `/apply` to write a file, Guardian automatically re-lints it within 5 seconds and reports

Notifications are non-blocking — they appear in the top-right corner of the TUI for 4 seconds and fade. They never interrupt a streaming response.

**Disable:** `/guardian off` — restarts clean on next Lumi launch unless you add `GUARDIAN=false` to `.env`.

---

### 7. Autonomous God Mode (`/godmode`)

Give Lumi an objective. It plans, executes, checks results, and loops — autonomously — until the goal is complete or it decides it's stuck.

```bash
/godmode build a FastAPI REST API for a todo app with JWT auth, SQLAlchemy, and full pytest coverage
/godmode refactor all files in src/ to use Python 3.12 type hints
/godmode find and fix all failing tests in the test suite
```

**Execution loop:**
1. **Plan:** The LLM generates a step-by-step plan as JSON (`[{"step": 1, "action": "create_file", "path": "...", "reason": "..."}]`)
2. **Execute:** Each step is carried out — `write_file`, `run_shell`, `patch_file`, `search_web`, or `ask_llm`
3. **Observe:** stdout, stderr, and exit codes are captured and fed back to the LLM as `[Step N result]: ...`
4. **Iterate:** The LLM decides whether to continue, backtrack, or declare completion
5. **Report:** A summary of every action taken and every file written is shown in the chat

All shell commands are shown to you in real-time in a God Mode sidebar. You can press `Ctrl+C` at any time to pause and decide whether to continue.

**Safety:** `/godmode` will ask for confirmation before any destructive operation (deleting files, running database migrations, modifying system files outside the project directory).

---

### 8. Air-gapped Offline Privacy (`/offline`)

For sensitive codebases, proprietary work, or air-gapped environments. One command severs all cloud connections.

```bash
/offline              # switch to Ollama with auto-detected best local model
/offline llama3.2     # specify a model
/offline codellama    # use CodeLlama for code-heavy sessions
/offline off          # restore cloud providers
```

**What happens:**
1. All configured cloud API keys are temporarily masked in memory (not deleted from `.env`)
2. `set_provider("ollama")` is called, pointing the client at `http://localhost:11434`
3. Lumi auto-detects available Ollama models with `ollama list` and picks the largest one, or uses the model you specified
4. A persistent red `⊘ OFFLINE` badge appears in the status bar for the entire session
5. Auto web search is disabled
6. `/online` or `/offline off` restores everything

**Requirements:** [Ollama](https://ollama.ai) installed and running locally. Pull a model first: `ollama pull llama3.2`.

---

## 🏗️ Provider System

Lumi uses a unified OpenAI-compatible client interface. Switching providers is instant — no restart required.

| Provider | Default Models | Strengths | Free Tier |
|----------|---------------|-----------|-----------|
| **Gemini** | `gemini-2.5-pro`, `gemini-2.5-flash` | Best context window, multimodal, 8,192 output tokens | ✅ Generous |
| **Groq** | `llama-3.3-70b`, `mixtral-8x7b` | Fastest inference by far (~500 tok/s) | ✅ Yes |
| **OpenRouter** | `qwen/qwen-72b-coder`, `anthropic/claude-3.5-sonnet` | Widest model selection, 200+ models | ✅ Credits |
| **Mistral** | `codestral-latest`, `mistral-large` | Best for pure code generation (Codestral) | ✅ Limited |
| **HuggingFace** | `meta-llama/Llama-3.3-70B` | Open source, research models | ✅ Yes |
| **GitHub Models** | `gpt-4o`, `o1-preview`, `Phi-4` | Free GPT-4o for GitHub accounts | ✅ Yes |
| **Cohere** | `command-a-03-2025` | Best for RAG, long document Q&A | ✅ Trial |
| **Cloudflare AI** | `@cf/meta/llama-3.3-70b` | Edge inference, low latency | ✅ Workers |
| **Ollama** | Any local model | Full privacy, no API key | ✅ Free |
| **Council** | All of the above | Maximum quality via debate | — |

**Auto-fallback:** On any `429`, `RESOURCE_EXHAUSTED`, or quota error, Lumi silently switches to the next available provider and notifies you with: `Quota hit — switching to groq`. The conversation continues without interruption.

**Switch providers:** `Ctrl+N` or `/model` opens the picker popup. Arrow keys to navigate, Enter to select.

---

## ⚡ Council Mode

Council mode routes your message to all 8 available agents simultaneously. They each answer independently, then a debate/refinement cycle produces a single consensus response.

```bash
/council           # switch to Council mode
/model             # switch back to a single provider
```

**How the debate works:**
1. All available agents receive the same message in parallel threads
2. Each agent returns its answer + a confidence score (1–10)
3. The lead agent (selected by task type: coding → Codestral, analysis → GPT-4o, etc.) reads all responses
4. The lead generates a refined synthesis incorporating the strongest points from each
5. The final response is the synthesis, not any single agent's answer

**Council sidebar** (visible when terminal width ≥ 100 columns):

```
◆ Council
  ⠋ Gemini          …
  ✓ Groq          9/10 · 1.2s
  ✓ OpenRouter    8/10 · 1.8s
  ⠹ Codestral     ★  …
  ✓ Llama 3.3     7/10 · 0.9s
```

★ marks the lead agent. Spinners update at 80ms intervals. Response times and confidence scores appear on completion.

---

## 🧠 Memory System

### Short-term Memory
A rolling window of the last 20 conversation turns (`ShortTermMemory(max_turns=20)`). When full, the oldest turns are compressed into a summary by a background thread so the AI always has coherent context without burning your token budget.

**Compression:** Every 10 turns, Lumi silently summarizes the oldest 60% of history into 3–5 sentences and replaces those entries with a single `[Conversation summary]` system message.

### Long-term Memory
Facts persist across sessions in a JSON store and are injected into every system prompt.

```bash
/remember I prefer TypeScript over JavaScript
/remember My API uses PostgreSQL 16 on port 5433 with a connection pool of 20
/remember I'm building a SaaS B2B product — keep answers business-appropriate
/remember My name is Sardor

/memory              # show all stored facts (numbered list)
/forget 2            # remove fact #2
```

### Auto-Remember
Every 8 turns, a background thread reads the conversation and runs a silent extraction call: *"What facts, preferences, or technical details from this conversation are worth remembering long-term?"* Any new facts are added to long-term memory automatically. You'll see them appear in `/memory` without having done anything.

### Session Persistence
Sessions auto-save every 5 turns and on exit. Each save is a timestamped JSON file in `data/sessions/`.

```bash
/save                    # save with auto-generated timestamp name
/save my-feature-branch  # save with a custom name
/load                    # load the most recent session
/load my-feature-branch  # load by name
/sessions                # list all saved sessions with dates and turn counts
/export                  # export current conversation to Markdown
```

---

## 📖 Full Command Reference

### Conversation Control

| Command | Description |
|---------|-------------|
| `/clear` | Clear conversation, memory, and all state |
| `/retry` | Resend the last message to get a fresh response |
| `/redo [hint]` | Regenerate with a different approach: `/redo use a recursive solution` |
| `/undo` | Remove the last user+assistant exchange from history |
| `/more` | Ask the AI to expand and go deeper on its last response |
| `/rewrite` | Rewrite the last response with a different structure or angle |
| `/tl;dr` | Summarize the last response in one sentence (max 20 words) |
| `/summarize` | Bullet-point summary of the entire conversation so far |
| `/diff` | Diff the current reply against the previous one (unified format) |
| `/multi` | Toggle multiline input — Enter adds a newline, Ctrl+D submits |

### Response Formatting

| Command | Description |
|---------|-------------|
| `/short` | Next reply only: concise, 2–3 sentences max |
| `/detailed` | Next reply only: comprehensive, leave nothing out |
| `/bullets` | Next reply only: bullet points only, no prose |
| `/translate <lang>` | Translate the last response into any language |

### Code Quality

| Command | Description |
|---------|-------------|
| `/fix <error>` | Root cause analysis, exact fix, and how to prevent it |
| `/debug [error]` | Deep debug: root cause + stack trace explanation + fix + regression test |
| `/explain [file]` | Line-by-line walkthrough — on last reply or a file path |
| `/review [file]` | Full code review: correctness, security, performance, readability |
| `/improve [file]` | Fix bugs, improve readability, add error handling — full rewrite |
| `/optimize [file]` | Performance analysis with bottleneck identification and before/after estimates |
| `/security [file]` | Security audit with critical / high / medium / low severity ratings |
| `/refactor [file]` | SOLID principles + design patterns refactor with explanation |
| `/test [file]` | Comprehensive pytest unit tests: happy path, edge cases, mocks, fixtures |
| `/docs [file]` | Google-style docstrings, module docstring, usage examples |
| `/types [file]` | Add complete Python 3.10+ type hints to all functions and class attributes |
| `/comment [file]` | Add clear, non-redundant inline comments |
| `/run` | Execute the Python code block from the last reply (15s timeout) |
| `/apply <file>` | Interactive diff + patch application for the last code block |

### File Operations

| Command | Description |
|---------|-------------|
| `/edit <file>` | AI-rewrite a file: fix bugs, add types, improve structure — full output |
| `/file <path>` | Load any file into context (8,000 char limit with truncation notice) |
| `/pdf <path>` | Extract and load a PDF document into context |
| `/project <path>` | Load an entire project directory into context with a structure summary |
| `/browse [path]` | Visual file tree navigator — arrow keys to move, Enter to inject into context |

### Shell & System

| Command | Description |
|---------|-------------|
| `/shell <cmd>` | Run any shell command and show output as a shell block |
| `/pane <cmd>` | Open a live-streaming split-screen pane for long-running commands |
| `/pane close` | Close the active pane |
| `/grep <pattern> [path]` | Search codebase (py/js/ts/go/rs/md) with line numbers |
| `/find <name>` | Find files by name pattern — excludes `.git`, `node_modules`, `__pycache__` |
| `/tree [path]` | Directory tree (uses `tree` binary, falls back to pure Python) |
| `/lint [path]` | Run `ruff check` or `flake8` — results as a shell block |
| `/fmt [path]` | Format with `black` or `prettier` |

### Git

| Command | Description |
|---------|-------------|
| `/git status` | Git status + last 10 commits |
| `/git log` | Graph log of last 20 commits |
| `/git diff` | Full diff vs HEAD |
| `/git branch` | List branches with tracking info |
| `/git commit` | AI-generate a conventional commit message from staged diff |
| `/git commit-confirm` | Stage all (`git add -A`) and commit with the generated message |
| `/git push` / `/git pull` | Push or pull current branch |
| `/pr` | Write a full GitHub PR description from diff + commit log |
| `/changelog` | Generate CHANGELOG grouped by Added / Changed / Fixed / Removed |
| `/standup` | Daily standup (Yesterday / Today / Blockers) from commits + todos |

### Web & Research

| Command | Description |
|---------|-------------|
| `/web <url> [question]` | Fetch a URL's content and ask a question about it |
| `/search <query>` | Live web search + AI summary of results (requires Tavily key) |
| `/image <path> [question]` | Vision: describe an image or ask about it (requires vision-capable model) |
| `/data <file>` | Analyze a CSV or JSON file — key stats, patterns, anomalies |

### Scaffolding

| Command | Description |
|---------|-------------|
| `/scaffold <type>` | Full project scaffold: `fastapi`, `react`, `cli`, `flask`, `django`, `nextjs`, `rust-cli`, `go-api` |
| `/readme [path]` | Generate a comprehensive README.md for the current or specified project |

### Codebase RAG

| Command | Description |
|---------|-------------|
| `/index [path]` | Build FTS5 SQLite index of codebase (default: current directory) |
| `/index --watch` | Auto-reindex on file changes |
| `/rag <query>` | Search indexed codebase and inject top results into the next prompt |

### Memory & Persona

| Command | Description |
|---------|-------------|
| `/remember <fact>` | Save a fact to long-term memory |
| `/memory` | Show all stored facts (numbered) |
| `/forget [n]` | Remove fact by number — without a number, shows the list |
| `/persona [key=value]` | Change persona: `/persona name=Aria`, `/persona style=concise` |
| `/persona reset` | Restore the default Lumi persona |
| `/sys` | Show the full current system prompt |

### Tools & Productivity

| Command | Description |
|---------|-------------|
| `/todo add <text>` | Add a todo item |
| `/todo list` | List all todos (with done/pending status) |
| `/todo done <n>` | Mark todo #n as done |
| `/todo rm <n>` | Remove todo #n |
| `/note add <text>` | Save a note |
| `/note list` | List all notes |
| `/note search <query>` | Full-text search notes |
| `/draft <details>` | Draft a professional email, Slack message, or text |
| `/weather [location]` | Current weather (uses wttr.in) |
| `/timer <duration>` | Countdown timer: `/timer 25m`, `/timer 90s`, `/timer 1h30m` |
| `/copy` | Copy the last reply to clipboard |
| `/paste` | Paste clipboard contents as your next message |
| `/voice` | Voice input — record, transcribe with Whisper, inject at cursor |

### Sessions

| Command | Description |
|---------|-------------|
| `/save [name]` | Save current session |
| `/load [name]` | Load a saved session |
| `/sessions` | List all saved sessions |
| `/export` | Export conversation as Markdown |
| `/tokens` | Estimated token usage for current session |
| `/context` | Full context window breakdown: system prompt + history |

### Mode & System

| Command | Description |
|---------|-------------|
| `/model` | Open provider + model picker popup (`Ctrl+N`) |
| `/council` | Switch to 8-agent Council mode |
| `/mode <cli>` | Subprocess TTY handoff to `gemini`, `opencode`, or `qwen` |
| `/mode vessel <name>` | API-level vessel mode (no local binary required) |
| `/mode normal` | Restore full Lumi persona |
| `/godmode <objective>` | Autonomous agent loop until objective is met |
| `/offline [model]` | Switch to local Ollama — air-gapped mode |
| `/offline off` | Restore cloud providers |
| `/guardian off` | Disable background Guardian agent |
| `/index [path]` | Build codebase RAG index |
| `/compact` | Toggle compact display mode |
| `/plugins` | List all loaded plugins with their commands |
| `/help` | Show all commands |
| `/exit` | Quit Lumi (`Ctrl+Q`) |

---

## ⌨️ Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+N` | Open model / provider picker |
| `Ctrl+L` | Clear chat, memory, and all state |
| `Ctrl+R` | Retry last message |
| `Ctrl+W` | Delete previous word |
| `Ctrl+U` | Clear entire input line |
| `Ctrl+D` | Submit multiline input (when in `/multi` mode) |
| `Ctrl+K` | Close active pane |
| `Ctrl+Q` / `Ctrl+C` | Quit |
| `↑ / ↓` | Input history (when input has text) |
| `↑ / ↓` | Scroll chat (when input is empty) |
| `PgUp / PgDn` | Scroll chat by full page |
| `Ctrl+← / →` | Jump word-by-word in input |
| `Home / End` | Jump to start / end of input |
| `Tab` | Autocomplete slash command |
| `Esc` | Close popup / cancel picker |

---

## 📁 Project Context (LUMI.md)

Create a `LUMI.md` file in your project root. Lumi finds it on startup and appends it to every system prompt — giving the AI complete, persistent knowledge of your project without you having to re-explain anything.

```markdown
# Project Context

## Stack
Python 3.12, FastAPI 0.115, PostgreSQL 16, Redis 7, Docker, Alembic

## Architecture
- src/api/routes/     → FastAPI routers, one file per domain
- src/db/models.py    → SQLAlchemy 2.0 ORM models
- src/db/repos/       → Repository pattern, all DB queries here
- src/core/config.py  → pydantic-settings, reads from .env
- src/core/auth.py    → JWT with RS256, 15min access / 7d refresh
- tests/              → pytest + httpx AsyncClient

## Conventions
- All endpoints return {"data": <payload>, "error": null} or {"data": null, "error": "<msg>"}
- Use logger.info() / logger.error() — never print()
- Type hints required on every function signature
- Docstrings required on all public methods
- Database errors must be caught at the repo layer, never leak to routes

## Do Not Touch
- migrations/    (Alembic manages these)
- src/vendor/    (third-party code, do not modify)

## Current Work In Progress
- Implementing WebSocket notifications (src/api/ws.py)
- Redis-based job queue (src/jobs/)
```

---

## 🔌 Plugin System

Drop a `.py` file into `~/Lumi/plugins/` and it's auto-loaded every time Lumi starts.

```python
# ~/Lumi/plugins/deploy.py

def register(registry):

    @registry.register("/deploy", "Deploy to staging or production")
    def cmd_deploy(tui, arg):
        env = arg.strip() or "staging"
        tui._sys(f"Deploying to {env}...")
        import subprocess
        r = subprocess.run(["./scripts/deploy.sh", env],
                          capture_output=True, text=True)
        tui.store.add(tui.Msg("shell", r.stdout + r.stderr, f"deploy {env}"))

    @registry.register("/logs", "Tail production logs")
    def cmd_logs(tui, arg):
        tui._slash("/pane", f"ssh prod 'tail -f /var/log/app.log'")
```

**API available to plugins:**

| Method | Description |
|--------|-------------|
| `tui._sys(text)` | Show a system message in chat |
| `tui._err(text)` | Show a red error message |
| `tui._notify(text)` | Show a timed notification in the corner |
| `tui.store.add(Msg(...))` | Add any message to the chat store |
| `tui.memory.add(role, content)` | Add to short-term memory |
| `tui.set_busy(True/False)` | Control the busy spinner |
| `tui._tui_stream(messages, model)` | Stream an LLM response into chat |
| `tui.client` | The active provider client |
| `tui.current_model` | The active model string |
| `tui.last_reply` | The last assistant response |
| `tui.redraw()` | Force a full TUI redraw |

List all loaded plugins: `/plugins`

---

## 📂 File Structure

```
~/Lumi/
├── .env                          API keys (not committed)
├── pyproject.toml                Project config, deps, ruff & pytest settings
├── .pre-commit-config.yaml       Pre-commit hooks (ruff + standard checks)
├── LUMI.md                       Project context (optional, per-directory)
├── CONTRIBUTING.md               Developer guide
├── main.py                       CLI + TUI launcher
├── requirements.txt              Legacy dependency list
├── install.sh
├── README.md
│
├── .github/workflows/
│   └── ci.yml                    Lint + Test CI (Python 3.10 & 3.12)
│
├── tests/                        182 unit tests
│   ├── test_short_term_memory.py  Memory system tests
│   ├── test_longterm_memory.py
│   ├── test_conversation_store.py
│   ├── test_prompts_builder.py    Prompt builder tests
│   ├── test_intelligence.py       Intelligence module tests
│   ├── test_agent.py             Agent tests
│   ├── test_council.py           Council tests
│   ├── test_themes.py            Utility tests
│   ├── test_web.py
│   ├── test_markdown.py
│   ├── test_highlight.py
│   ├── test_filesystem.py
│   ├── test_export.py
│   └── test_log.py               Logging module tests
│
├── src/
│   ├── tui/
│   │   └── app.py                Full TUI — renderer, input engine,
│   │                             CommandRegistry, Vessel Mode, 50+ commands
│   ├── chat/
│   │   └── hf_client.py          Multi-provider unified client
│   ├── agents/
│   │   ├── agent.py              God Mode autonomous agent
│   │   └── council.py            8-agent council with debate loop
│   ├── memory/
│   │   ├── short_term.py         Rolling window + background compression
│   │   ├── longterm.py           Persistent facts + persona + episodic memory
│   │   └── conversation_store.py Named session save/load
│   ├── prompts/
│   │   └── builder.py            System prompt builder + task classifier
│   ├── tools/
│   │   ├── search.py             Web search + top-page fetch
│   │   └── mcp.py                MCP server manager
│   └── utils/
│       ├── intelligence.py       Emotion + topic detection, search triggers
│       ├── log.py                Centralized logging module
│       ├── web.py                URL fetcher
│       ├── filesystem.py         File plan generator + writer
│       ├── autoremember.py       Silent background fact extraction
│       ├── export.py             Markdown session export
│       ├── plugins.py            Plugin loader + dispatcher
│       ├── tools.py              Weather, clipboard, PDF, data analysis
│       ├── todo.py               Persistent SQLite todo list
│       ├── notes.py              Persistent notes with search
│       └── voice.py              arecord/sox capture + Whisper API
│
├── data/
│   ├── memory/                   Long-term memory store + mood log
│   └── sessions/                 Auto-saved conversation snapshots
│
└── plugins/                      Drop .py files here
```

---

## 🎨 Design Philosophy

Lumi is built with zero external UI libraries. Every border, gradient, spinner, and popup is raw ANSI escape code. This isn't a constraint — it's a deliberate choice:

**No dependencies that can break your terminal.** Rich, Textual, and Curses have their own event loops, their own rendering assumptions, and their own failure modes. Lumi's renderer is 300 lines of deterministic string concatenation. It works everywhere Python 3.10 runs.

**Zero startup overhead.** There's no TUI framework to initialize, no widget tree to build, no stylesheet to parse. Lumi is interactive in under 200ms on any machine.

**Complete visual control.** Tokyo Night isn't a theme applied to someone else's widgets. Every `_fg(PURPLE)`, `_bg(BG_DARK)`, and `_bold()` is a deliberate placement in the render loop. The code block borders, the Council sidebar spinner, the Vessel Mode red `λ` — all of it is exactly where it is because that's where the code puts it.

**The TUI and CLI are the same program.** `main.py` and `src/tui/app.py` import identical modules. Every feature available interactively is available in the TUI. Nothing is stripped down, nothing is shimmed.

---

## 🛠️ Development

Lumi uses modern Python tooling for development:

### Quick Setup

```bash
git clone https://github.com/SardorchikDev/Lumi.git ~/Lumi
cd ~/Lumi
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"    # installs ruff, pytest, pre-commit
pre-commit install         # enables git hooks
```

### Running Tests

```bash
pytest                     # run all 182 tests
pytest tests/ -v           # verbose output
pytest -k "memory"         # run only memory-related tests
pytest -m "not slow"       # skip slow tests
pytest --cov=src           # with coverage report
```

### Linting & Formatting

```bash
ruff check .               # lint (errors only)
ruff check . --fix         # auto-fix safe issues
ruff format .              # format all files
```

Ruff is configured in `pyproject.toml` with rules for pycodestyle, pyflakes, isort, pyupgrade, flake8-bugbear, and more. Line length is 120 characters.

### CI Pipeline

Every push and PR to `main` triggers the CI workflow (`.github/workflows/ci.yml`):

| Job | What it does |
|-----|-------------|
| **Lint** | `ruff check .` — must pass with zero errors |
| **Test (3.10)** | `pytest tests/ -v` on Python 3.10 |
| **Test (3.12)** | `pytest tests/ -v` on Python 3.12 |

### Logging

Lumi includes a centralized logging module (`src/utils/log.py`) that can be used in place of `print()` for error/debug output:

```python
from src.utils.log import get_logger
log = get_logger(__name__)

log.info("Provider switched to groq")
log.warning("Rate limit approaching")
log.error("Failed to connect to Ollama")
```

Configure via environment variables:
- `LUMI_LOG_LEVEL` — `DEBUG`, `INFO`, `WARNING` (default), `ERROR`
- `LUMI_LOG_FILE` — optional file path for log output

### Type Hints

Core modules (`src/memory/`, `src/prompts/builder.py`) use `from __future__ import annotations` and full type hints. New code should follow this pattern.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide. The short version:

1. Fork & clone
2. Create a branch: `git checkout -b feat/my-feature`
3. Install dev deps: `pip install -e ".[dev]" && pre-commit install`
4. Make changes, add tests
5. Run `ruff check .` and `pytest`
6. Commit with [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, etc.
7. Open a PR against `main`

---

<div align="center">

*Lumi v0.3.3 — built by* ***Sardor Sodiqov***

*Uncompromising autonomy. Seamless terminal integration.*

</div>
