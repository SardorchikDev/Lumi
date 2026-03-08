```
██╗     ██╗   ██╗███╗   ███╗██╗
██║     ██║   ██║████╗ ████║██║
██║     ██║   ██║██╔████╔██║██║
██║     ██║   ██║██║╚██╔╝██║██║
███████╗╚██████╔╝██║ ╚═╝ ██║██║
╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝

A R T I F I C I A L   I N T E L L I G E N C E
```

<div align="center">

**A chill, open-source AI coding assistant that lives in your terminal.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Free](https://img.shields.io/badge/Cost-100%25%20Free-brightgreen?style=flat-square)](#api-keys)
[![Providers](https://img.shields.io/badge/Providers-5-purple?style=flat-square)](#providers--models)

[Quick Start](#quick-start) · [Features](#features) · [Commands](#commands) · [Models](#providers--models) · [Config](#configuration)

</div>

---

## What is Lumi?

Lumi is a terminal-based AI assistant built for developers. It's not just a chatbot — it can **read and edit your files**, **run code**, **write commit messages**, **search the web**, and **remember things about you** across sessions.

It's free. It works with 5 different AI providers and 40+ models. You don't need to pay for anything.

```
  ›  /edit src/api/routes.py
  ✦  File loaded: routes.py (203 lines)
     What should Lumi do to this file?
  ›  add rate limiting to all POST endpoints

  ✦ Lumi  streaming...

  Diff ─────────────────────────────────────────────
  + from flask_limiter import Limiter
  + limiter = Limiter(app, default_limits=["100/hour"])
  + @limiter.limit("10/minute")
    @app.route('/api/submit', methods=['POST'])

  ! Write changes to routes.py? [y/N]  y
  ✓  Written → routes.py  (backup: routes.py.lumi.bak)
```

---

## Features

### 🤖 5 Providers, 40+ Free Models
Connect Gemini, Groq, OpenRouter, Mistral, and HuggingFace all at once. Switch providers and models mid-session with `/model`. Lumi fetches live model lists and filters out broken ones automatically.

### 📝 File Editing
Give Lumi any file path. Tell it what to change. It shows a colored diff and writes the file back — always with a `.lumi.bak` backup. Works on HTML, Python, JS, CSS, JSON, config files, markdown — any text file.

### ⚡ Auto-Fallback
Hit Gemini's free quota? Lumi automatically switches to your next available provider and keeps going without crashing or asking you to do anything.

### 💻 Full Coding Toolkit
`/fix` error messages, `/review` entire files, `/explain` code, `/run` code blocks directly in terminal, `/diff` between replies, and `/git` helpers for status, commits, and logs.

### 🧬 Long-term Memory
Lumi extracts facts from your conversations every 8 turns and saves them. It remembers your stack, preferences, and projects across sessions. You can also manually `/remember` anything.

### 🌐 Smart Web Search
Lumi automatically searches the web when your question needs current information. You can also use `/search` for explicit lookups. Results are fed directly into the conversation as context.

### 🎨 Syntax Highlighting
Code blocks in Lumi's replies render with full ANSI color in your terminal. Supports Python, JavaScript, Bash, and JSON — no extra setup.

### 🔄 Short-term Memory
Keeps the last 20 turns of conversation in context. Full multi-turn awareness — Lumi knows what you said 10 messages ago.

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/SardorchikDev/lumi
cd lumi
```

### 2. Create a virtual environment

```bash
# Standard
python -m venv venv
source venv/bin/activate

# Fish shell
source venv/bin/activate.fish

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add at least one API key to `.env`

```bash
touch .env
```

Add any or all of these (you only need one to start):

```env
GEMINI_API_KEY=AIza...          # https://aistudio.google.com/apikey
GROQ_API_KEY=gsk_...            # https://console.groq.com
OPENROUTER_API_KEY=sk-or-...    # https://openrouter.ai/keys
MISTRAL_API_KEY=...             # https://console.mistral.ai
HF_TOKEN=hf_...                 # https://huggingface.co/settings/tokens
```

> All of these are **free**. No credit card required for any of them.

### 5. Run Lumi

```bash
python main.py
```

---

## API Keys

| Provider | Free Tier | Get Key | Best For |
|---|---|---|---|
| **Gemini** | 15 req/min, 1M context | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Long context, coding |
| **Groq** | 30 req/min, very fast | [console.groq.com](https://console.groq.com) | Speed, Llama models |
| **OpenRouter** | 30+ free models | [openrouter.ai/keys](https://openrouter.ai/keys) | Most model variety |
| **Mistral** | Free "Experiment" plan | [console.mistral.ai](https://console.mistral.ai) | Code, European AI |
| **HuggingFace** | Free inference API | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | Open models |

**Recommended setup:** Add Gemini + Groq + OpenRouter. That gives you the best coverage and auto-fallback between providers when one hits rate limits.

---

## Providers & Models

### Gemini (Google)
| Model | Context | Notes |
|---|---|---|
| `gemini-2.5-flash` | 1M tokens | Smart, capable |
| `gemini-2.0-flash` | 1M tokens | Fast, reliable |
| `gemini-2.0-flash-lite` | 1M tokens | Fastest, lightest |
| `gemini-3.1-flash-lite-preview` | 1M tokens | Free tier confirmed |

### Groq
| Model | Notes |
|---|---|
| `openai/gpt-oss-120b` | OpenAI open-weight 120B |
| `llama-3.3-70b-versatile` | Best all-rounder |
| `meta-llama/llama-4-maverick` | Latest Llama 4 |
| `qwen/qwen3-32b` | Great for coding |
| `llama-3.1-8b-instant` | Fastest responses |

### OpenRouter (30+ free models)
| Model | Notes |
|---|---|
| `deepseek/deepseek-r1:free` | 671B deep reasoning |
| `qwen/qwen3-235b-a22b:free` | Massive MoE |
| `hermes-3-llama-3.1-405b:free` | Largest free model |
| `qwen3-coder:free` | Best for pure coding |
| `gpt-oss-120b:free` | OpenAI open-weight |

### Mistral
| Model | Notes |
|---|---|
| `mistral-small-latest` | General use, fast |
| `open-mistral-nemo` | Multilingual, 12B |
| `open-codestral-mamba` | Code completion |

### HuggingFace
| Model | Notes |
|---|---|
| `Qwen/Qwen2.5-72B-Instruct` | Smart, capable |
| `meta-llama/Llama-3.3-70B-Instruct` | Strong reasoning |
| `meta-llama/Llama-3.1-8B-Instruct` | Fast, reliable |

---

## Commands

### Chat
| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/clear` | Reset the conversation |
| `/undo` | Remove the last exchange |
| `/retry` | Resend your last message |
| `/more` | Expand on the last reply |
| `/tl;dr` | One-sentence summary of the last reply |
| `/rewrite` | Rewrite the last reply differently |
| `/summarize` | Summarize the whole conversation |
| `/multi` | Toggle multi-line input mode |

### Coding
| Command | Description |
|---|---|
| `/edit <path>` | Edit a file — Lumi writes changes back with diff preview |
| `/file <path>` | Load a file into the conversation as context |
| `/fix <error>` | Diagnose and fix an error message |
| `/review [file]` | Full code review — bugs, performance, security, style |
| `/explain [file]` | Explain last reply or a specific file |
| `/run` | Execute the code block from the last reply |
| `/diff` | Colored diff — previous reply vs latest |

### Git
| Command | Description |
|---|---|
| `/git status` | Show git status + last 5 commits |
| `/git commit` | AI writes your commit message, asks to confirm |
| `/git log` | Last 15 commits with color |

### Web & Tools
| Command | Description |
|---|---|
| `/search <query>` | Explicit web search with results |
| `/imagine <prompt>` | Generate an image (opens browser) |
| `/translate <lang>` | Translate the last reply |

### Memory & Persona
| Command | Description |
|---|---|
| `/remember <fact>` | Save a fact to long-term memory |
| `/memory` | View all saved long-term memories |
| `/forget` | Manage and delete memories |
| `/persona` | Change Lumi's name, tone, and traits |

### Sessions
| Command | Description |
|---|---|
| `/save` | Save the current conversation |
| `/load` | Load the most recent saved session |
| `/sessions` | List all saved sessions |
| `/export` | Export the conversation as a `.md` file |
| `/find <keyword>` | Search through all saved sessions |

### Settings
| Command | Description |
|---|---|
| `/model` | 2-step picker — choose provider first, then model |
| `/theme` | Switch color theme (5 themes) |
| `/cost` | Show session token usage |
| `/quit` | Save and exit |

### Response Modifiers (one-shot)
| Command | Description |
|---|---|
| `/short` | Next reply: 2-3 sentences |
| `/detailed` | Next reply: thorough and comprehensive |
| `/bullets` | Next reply: bullet points only |

---

## File Editing

```bash
# Edit any file by path
/edit src/index.html
/edit ~/projects/myapp/config.py
/edit ./README.md
```

**How it works:**
1. Lumi loads the file (up to 300KB)
2. You type your instruction in plain English
3. Lumi generates and streams the edit
4. A colored diff is shown — green for additions, red for removals
5. You type `y` to write, anything else to discard
6. A `.lumi.bak` backup is always created before writing

**Examples:**
```
/edit src/components/Navbar.jsx
› make the navbar sticky and add a hamburger menu for mobile

/edit server.py
› add proper error handling to all the API endpoints

/edit styles.css
› convert all px values to rem and add CSS variables for colors

/edit package.json
› add a build:prod script that minifies and sets NODE_ENV=production
```

---

## Running Code

```
  ›  write me a script to find all duplicate files in a folder

  ✦ Lumi  [writes Python script]

  ›  /run

  Running code  (python)
  ────────────────────────────────────────
  Found 3 duplicate groups:
  - photo_copy.jpg == photo.jpg
  - backup.zip == archive.zip

  ✓  Exit 0
```

Supported: **Python**, **Bash/sh**, **JavaScript (Node.js)**

---

## Long-term Memory

```
  ›  /remember I use Python 3.11 and FastAPI for all my backend projects
  ✓  Saved to long-term memory

  ›  /memory

  Long-term memory (4 facts)
  ──────────────────────────────────────────
  1. Uses Python 3.11 and FastAPI for backend
  2. Prefers type hints and async/await patterns
  3. Working on a SaaS project called Lumi
  4. Fish shell user on CachyOS Linux
```

Lumi also silently extracts facts from your conversation every 8 turns automatically — no manual input needed. These facts persist across sessions and are used to give you more relevant answers.

---

## Themes

Switch with `/theme`:

| Theme | Description |
|---|---|
| `tokyo` | Tokyo Night Storm (default) |
| `dracula` | Classic dark with purple and pink |
| `nord` | Arctic blues and muted tones |
| `gruvbox` | Warm retro with earthy colors |
| `monokai` | High-contrast vivid greens and yellows |

---

## Auto-Fallback

```
  ›  explain this algorithm

  ◆  Quota hit on gemini — switching to groq automatically

  ✦ Lumi  [continues seamlessly on Groq]
```

With multiple providers in `.env`, Lumi never crashes on quota errors — it silently switches to the next available provider.

---

## Pipe Mode

```bash
# Pipe code directly in
cat src/buggy.py | python main.py

# One-off question
echo "explain what a Merkle tree is" | python main.py

# Feed error logs
npm run build 2>&1 | python main.py
```

---

## Project Structure

```
lumi/
├── main.py                    # Entry point — all commands and main loop
├── .env                       # Your API keys (never commit this)
├── requirements.txt
├── data/
│   ├── memory/
│   │   ├── longterm.json      # Persisted long-term memories
│   │   └── theme.json         # Saved theme preference
│   ├── personas/
│   │   └── default.json       # Lumi's personality config
│   └── sessions/              # Saved conversation history
└── src/
    ├── chat/
    │   └── hf_client.py       # Multi-provider API client
    ├── memory/
    │   ├── longterm.py
    │   ├── short_term.py
    │   └── conversation_store.py
    ├── prompts/
    │   └── builder.py         # System prompt construction
    ├── tools/
    │   └── search.py          # Web search (stdlib only)
    └── utils/
        ├── highlight.py       # ANSI syntax highlighter
        ├── markdown.py        # Terminal markdown renderer
        ├── themes.py          # Theme system
        ├── intelligence.py    # Emotion detection, topic tracking
        ├── autoremember.py    # Background fact extraction
        ├── history.py         # Readline input history
        └── export.py          # Export to .md
```

---

## Persona

Edit `data/personas/default.json` or use `/persona`:

```json
{
  "name": "Lumi",
  "creator": "Sardor Sodiqov (SardorchikDev)",
  "tone": "chill, warm, and real — like texting a close friend",
  "traits": ["supportive", "elite programmer", "honest", "laid-back", "encouraging"]
}
```

---

## Troubleshooting

**`No API key found in .env`**
Make sure `.env` is in the project root and formatted as `KEY=value` with no spaces around `=`.

**`Error code: 429` — Rate limit**
Free tier limit hit. Wait a moment or use `/model` to switch providers. With multiple providers configured, Lumi auto-switches for you.

**`Error code: 400 — Developer instruction is not enabled`**
That model doesn't support system prompts (usually Gemma models). Run `/model` and pick a different one.

**`Error code: 401 — Invalid API key`**
Check your key in `.env`. Gemini keys start with `AIza`, Groq with `gsk_`, OpenRouter with `sk-or-`.

**`404 — Model not found`**
Model was decommissioned. Run `/model` to see the current working list.

**Terminal looks broken**
Use a modern terminal with 256-color ANSI support: Alacritty, Kitty, WezTerm, iTerm2. Avoid Windows CMD (use Windows Terminal).

---

## Contributing

PRs welcome. The code is intentionally simple.

**Add a new provider:** Follow the pattern in `src/chat/hf_client.py` — add model list, client in `_make_client()`, key detection in `get_available_providers()`, label in `PROVIDER_LABELS`.

**Add a new command:** Add the function before `main()`, add the handler in the main loop, add the entry to `print_help()`.

---

## Requirements

- Python 3.9+
- `huggingface_hub`
- `python-dotenv`
- `openai`

No GPU. No Docker. No heavy ML libraries.

---

## License

MIT — do whatever you want with it.

---

<div align="center">

Built by **[Sardor Sodiqov (SardorchikDev)](https://github.com/SardorchikDev)**

If this saved you time, give it a ⭐

</div>
