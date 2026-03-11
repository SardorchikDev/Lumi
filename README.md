<div align="center">

# ◆ Lumi AI 
**The Ultimate Terminal Development Environment**

An unapologetically native, high-performance, and feature-rich AI agent built exclusively for the CLI. No heavy Electron apps, no proprietary GUI wrappers, no telemetry. Just raw ANSI, extreme speed, and unprecedented agentic autonomy.

[![Python Version](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0%20packages-success?style=for-the-badge)](https://github.com/SardorchikDev/Lumi)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

</div>

---

## ⚡ Why Lumi? (vs. The Competition)

Most AI coding tools try to pull you out of the terminal. Lumi pulls the AI *into* it. 

### Lumi vs Cursor / IDE Extensions 
* **The Problem:** IDE extensions like Copilot and Cursor lock you into their editors. They abstract away the shell, making system-level tasks, deployment pipelines, and raw Git workflows clumsy.
* **The Lumi Advantage:** Lumi is a first-class citizen of the UNIX ecosystem. It runs alongside your `vim`, `tmux`, and `ssh` sessions. It can run shell commands, parse `pytest` output live, execute `ruff` in the background, and seamlessly integrate into existing pipelines. You don't leave your terminal.

### Lumi vs Aider
* **The Problem:** Aider is fantastic, but its UI is extremely basic (a linear chat log). It doesn't support interactive previews for diffs, and its agentic loops can't easily be paused or visualized in parallel.
* **The Lumi Advantage:** Lumi features a **Rich Minimalist TUI** built entirely in pure Python (no `rich` or `curses` wrappers required). You get beautifully rendered Tokyo Night colors, syntax-highlighted code blocks, interactive `[y/N]` Live Diff patching (`/apply`), and split-screen **Terminal Panes** (`/pane`) for live execution tracking. You can even run Aider *inside* Lumi using Subprocess Handoff.

### Lumi vs SWE-Agent / OpenDevin
* **The Problem:** These are massive, heavy frameworks running through Docker containers with complex web UI overheads.
* **The Lumi Advantage:** Lumi is insanely lightweight. A single `python3 main.py` triggers an ultra-fast, raw `tty.setraw` loop. Zero Docker containers required (unless you ask Lumi to build one for you via `/godmode`).

---

## 🔥 Premium Features

Lumi transcends standard AI chats with a suite of premium, native terminal integrations:

### 1. Subprocess Terminal Handoff (`/mode <cli>`)
Lumi can physically suspend its own event loop and hand full control of the terminal TTY over to another AI CLI tool (e.g., `gemini`, `opencode`, `qwen`). It records the entire interactive PTY session using `script`, cleans the ANSI tracking, and injects the transcript right back into Lumi's memory when the subprocess exits.

### 2. Live Split-Screen Multiplexing (`/pane`)
Run long-standing commands (like `npm run dev` or `pytest --watch`) inside a built-in terminal pane. The output streams live on the right side of the UI while you continue chatting with the AI about the errors on the left.

### 3. Local FTS5 Codebase RAG (`/index`, `/rag`)
Lumi builds incredibly fast, local SQLite FTS5 indexes of your active workspace. Zero vector database dependencies required. Query your codebase semantically, and Lumi auto-injects exactly the right context block directly into your LLM prompt.

### 4. Interactive Live Diff Application (`/apply`)
When the AI generates a code block, type `/apply <filename>`. Lumi suspends the TUI, visually maps the change to the file, and offers an interactive `[y/N]` preview. Upon approval, it surgically merges the update and wakes the UI back up seamlessly.

### 5. Native Voice Commands (`/voice`)
Hold your terminal workflow and speak naturally. Lumi taps into raw `arecord` to capture your microphone, pipes it through the HuggingFace Whisper API, and drops perfectly transcribed text right onto your typing cursor.

### 6. Background Guardian Agent
Lumi watches your back. Running on a separate background thread, Guardian silently monitors `ruff` linting and `pytest` status in your working directory. If it detects a broken build, a non-intrusive warning notification seamlessly pops into your TUI border.

### 7. Autonomous God Mode (`/godmode`)
Give Lumi an objective and let it run wild. God Mode puts the LLM into a self-feedback loop, generating autonomous shell commands, executing them, analyzing the stdout, and writing files until the specific goal is met.

### 8. Air-gapped Offline Privacy (`/offline`)
Working on sensitive proprietary code on an airplane? Run `/offline` to instantly sever all cloud API connections and route all LLM logic to a local Ollama instance (e.g., `llama3.1:8b`). Complete confidentiality.

---

## 🏗️ Supported Providers & Models
Lumi uses a modular OpenRouter/OpenAI-compatible backbone, maximizing context windows (up to 8,192 output tokens) to ensure it can write massive codebases without interruption. 

| Provider | Purpose |
|----------|---------|
| **Gemini API** | State of the art coding logic (`gemini-3.1-pro-preview`, `gemini-2.5-flash`). Huge context limits. |
| **OpenRouter** | Easy access to Qwen 72B Coder, Claude 3.5 Sonnet, and hundreds of others. |
| **Groq** | Blistering fast Llama 3.3 for real-time responsiveness. |
| **Mistral / Cohere / GitHub / HF** | Dozens of free-tier endpoints to ensure you never run out of credits. |

---

## 📥 Installation

Because Lumi is built defensively with zero third-party core dependencies, setup takes seconds.

**Requirements:** Python 3.10+ (Unix/macOS strongly recommended)

```bash
git clone https://github.com/SardorchikDev/Lumi.git ~/Lumi
cd ~/Lumi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt # Optional plugins only
```

Or just use the one-liner:
```bash
chmod +x install.sh && ./install.sh
```

---

## ⚙️ Quick Start

1. Set up your API keys in `~/Lumi/.env`:
```env
GEMINI_API_KEY=AIzaSy...
# Or any other supported provider: GROQ_API_KEY, OPENROUTER_API_KEY, etc.
```

2. Start the TUI:
```bash
lumi --tui
```

*(Tip: Add `alias lumi="source ~/Lumi/venv/bin/activate && python ~/Lumi/main.py"` to your `~/.bashrc` or `~/.zshrc`)*

---

## 📖 Essential Commands Reference

Inside the Lumi TUI, hit `Tab` to see all commands, or `Ctrl+N` to open the model picker popup. The UI uses an elegant Tokyo Night Storm palette.

* `/apply <file>` - Interactively deploy the last AI codeblock to a specific file.
* `/pane <command>` - Run a bash command in a split-screen side-pane.
* `/mode <cli>` - Subprocess handoff (e.g. `/mode opencode`, `/mode qwen`).
* `/rag <query>` - Use the local SQLite FTS5 database to embed codebase context.
* `/voice` - Dictate your prompt using your microphone.
* `/godmode` - Trigger autonomous loop for objective completion.
* `/offline` - Switch entirely to local Ollama inference.
* `/council` - Multi-agent debate mode (cross-validates across different AI providers).

---

<div align="center">
<i>Lumi — Uncompromising autonomy. Seamless terminal integration.</i>
</div>
