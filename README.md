```
    ██╗      ██╗   ██╗  ███╗   ███╗  ██╗
    ██║      ██║   ██║  ████╗ ████║  ██║
    ██║      ██║   ██║  ██╔████╔██║  ██║
    ██║      ██║   ██║  ██║╚██╔╝██║  ██║
    ███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║
    ╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝
```

<div align="center">

**The terminal AI that doesn't lock you in, doesn't charge you, and doesn't need permission to think.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Free](https://img.shields.io/badge/Cost-100%25%20Free-brightgreen?style=flat-square)](#api-keys)
[![Providers](https://img.shields.io/badge/Providers-5%2B-purple?style=flat-square)](#providers--models)
[![Council](https://img.shields.io/badge/Council-5%20Agents-orange?style=flat-square)](#council-mode)

[Quick Start](#quick-start) · [Why Lumi](#why-lumi-beats-the-alternatives) · [Council Mode](#council-mode) · [Commands](#commands) · [Models](#providers--models)

</div>

---

## Why Lumi Beats the Alternatives

Everyone's shipping AI CLIs now. Here's why Lumi is different.

| Feature | **Lumi** | Claude Code | Gemini CLI | Aider | GitHub Copilot CLI |
|---|:---:|:---:|:---:|:---:|:---:|
| **100% free** | ✅ | ❌ $20/mo | ❌ limited | ❌ needs paid key | ❌ $10/mo |
| **5+ providers** | ✅ | ❌ Claude only | ❌ Gemini only | ⚠️ needs your key | ❌ OpenAI only |
| **5-agent council** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Auto-fallback** | ✅ | ❌ just fails | ❌ just fails | ❌ | ❌ |
| **Long-term memory** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Voice input** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Todo + Notes** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Custom persona** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **5 color themes** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Offline (Ollama)** | ✅ | ❌ | ❌ | ⚠️ limited | ❌ |
| **Open source** | ✅ | ❌ | ❌ | ✅ | ❌ |

### The real difference

**Claude Code** is brilliant but costs money and only runs Claude. Hit your quota — you're done. No memory across sessions, no voice, no productivity tools, no personality.

**Gemini CLI** just dropped. It's Google's official CLI. One model, one provider, no fallback, no memory, no council.

**Aider** is great for git-integrated coding but requires a paid API key. No council mode, no memory, no productivity layer.

**Lumi** runs on 5 providers and 40+ free models simultaneously. When one hits rate limits it switches automatically. When you need maximum intelligence, Council mode puts 5 models to work at the same time. Built by one developer — no pricing sheet.

---

## Council Mode

This is Lumi's killer feature. No other terminal AI has it.

```
  /model → ⚡ Council

  ◆ Council  │  5 agents
```

Switch to Council mode and every message goes to **all 5 agents simultaneously** — Gemini, Kimi K2, GPT-OSS, Codestral, and Llama 3.3. They all answer in parallel. Then the best judge model reads all 5 responses and synthesizes one definitive answer.

```
  ›  explain how database indexing works

  council  5 agents  →  asking in parallel...

  ✓Gemini  ✓Kimi K2  ✓GPT-OSS  ✓Codestral  ✓Llama 3.3

  synthesizing 5 responses...

  ✦ Lumi  [council]
  Database indexing is a data structure technique...
```

Different models excel at different things. Gemini reasons deeply. Kimi K2 excels at analysis. Codestral knows code. By running all of them and synthesizing you get an answer that's better than any single model could produce. Switch back to a single model anytime with `/model`.

---

## What is Lumi?

Lumi is a terminal-based AI assistant built for developers who want maximum intelligence at zero cost. It reads and edits your files, runs code, writes commit messages, tracks todos, remembers you across sessions, and can put 5 AI models to work simultaneously.

```
  ›  /edit src/api/routes.py
  ✦  File loaded: routes.py (203 lines)
  ›  add rate limiting to all POST endpoints

  + from flask_limiter import Limiter
  + limiter = Limiter(app, default_limits=["100/hour"])
  + @limiter.limit("10/minute")
    @app.route('/api/submit', methods=['POST'])

  Write changes to routes.py? [y/N]  y
  ✓  Written → routes.py (backup: routes.py.lumi.bak)
```

---

## Install (One Line)

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash
```

That's it. The script will:
- Clone the repo to `~/Lumi`
- Create a Python virtual environment
- Install all dependencies
- Add `lumi` to your PATH
- Create a `.env` template for your API keys

After it finishes:
```bash
# 1. Add at least one free API key
nano ~/Lumi/.env

# 2. Reload your shell
source ~/.bashrc   # or ~/.zshrc or ~/.config/fish/config.fish

# 3. Run from anywhere
lumi
```

> Already installed? Running the same curl again pulls the latest version automatically.

---

## Manual Install

```bash
# 1. Clone
git clone https://github.com/SardorchikDev/lumi
cd lumi

# 2. Virtual environment
python -m venv venv
source venv/bin/activate        # bash/zsh
source venv/bin/activate.fish   # fish shell

# 3. Install
pip install -r requirements.txt

# 4. Add API keys to .env (you only need one to start)
GEMINI_API_KEY=AIza...          # https://aistudio.google.com/apikey
GROQ_API_KEY=gsk_...            # https://console.groq.com
OPENROUTER_API_KEY=sk-or-...    # https://openrouter.ai/keys
MISTRAL_API_KEY=...             # https://console.mistral.ai
HF_TOKEN=hf_...                 # https://huggingface.co/settings/tokens

# 5. Run
python main.py
```

**Run from anywhere:**
```bash
# Fish shell — add once
echo 'alias lumi="cd ~/Lumi && source venv/bin/activate.fish && python main.py"' >> ~/.config/fish/config.fish
source ~/.config/fish/config.fish

# Then just type:
lumi
```

---

## API Keys

Every key here is free. No credit card required.

| Provider | Free Tier | Get Key | Best Model |
|---|---|---|---|
| **Gemini** | 15 req/min, 1M context | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `gemini-2.5-flash` |
| **Groq** | 30 req/min, very fast | [console.groq.com](https://console.groq.com) | `kimi-k2-instruct` |
| **OpenRouter** | 40+ free models | [openrouter.ai/keys](https://openrouter.ai/keys) | `hermes-3-405b:free` |
| **Mistral** | Free experiment plan | [console.mistral.ai](https://console.mistral.ai) | `codestral-latest` |
| **HuggingFace** | Free inference API | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | `Llama-3.3-70B` |

> **OpenRouter setup:** Go to [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy) → enable *"Allow free endpoints that may train on inputs"* and *"Allow free endpoints that may publish prompts"*.

---

## Providers & Models

Lumi fetches live model lists on startup and filters out broken or decommissioned models automatically.

### Gemini
- `gemini-2.5-flash` — smartest, 1M context
- `gemini-2.0-flash` — fast, capable
- `gemini-2.0-flash-lite` — fastest Gemini

### Groq
- `moonshotai/kimi-k2-instruct` — 1T MoE, best on Groq
- `llama-3.3-70b-versatile` — reliable all-rounder
- `qwen/qwen3-32b` — strong at coding

### OpenRouter (40+ free models)
- `qwen/qwen3-coder-480b-a35b:free` — 480B coding specialist
- `openai/gpt-oss-120b:free` — OpenAI open-weight 120B
- `nousresearch/hermes-3-llama-3.1-405b:free` — 405B, best general
- `zhipuai/glm-4.5-air:free` — massive weekly quota
- `meta-llama/llama-3.3-70b-instruct:free` — solid all-rounder

### Mistral
- `codestral-latest` — best coding model on Mistral
- `mistral-large-latest` — most capable
- `mistral-small-latest` — fast, free

### HuggingFace
- `meta-llama/Llama-3.3-70B-Instruct` — default
- `Qwen/Qwen2.5-72B-Instruct` — great at reasoning
- `meta-llama/Llama-3.1-70B-Instruct` — reliable fallback

### Ollama (offline)
- Any locally installed model
- Zero API limits, fully offline
- Auto-detected at `localhost:11434`

---

## Commands

### Chat
| Command | Description |
|---|---|
| `/council <q>` | Ask all 5 agents simultaneously — best answer synthesized |
| `/council --show <q>` | Same but show each agent's raw response |
| `/help` | Show all commands |
| `/clear` | Reset conversation |
| `/undo` · `/retry` | Remove last turn or resend it |
| `/more` · `/tl;dr` | Expand or one-line summarize |
| `/rewrite` · `/summarize` | Rewrite reply or summarize chat |
| `/short` · `/detailed` · `/bullets` | One-shot reply format |
| `/multi` | Toggle multi-line input |

### Code
| Command | Description |
|---|---|
| `/edit <path>` | Edit file — shows diff, writes with backup |
| `/file <path>` | Load file as context |
| `/project <dir>` | Load entire codebase |
| `/fix <error>` | Diagnose and fix an error |
| `/review [file]` | Full code review — bugs, security, performance |
| `/explain [file]` | Explain code or last reply |
| `/comment [file]` | Add docstrings and inline comments |
| `/run` | Execute code block from last reply |
| `/diff` | Diff previous vs latest reply |
| `/git status\|commit\|log` | Git helpers |

### Files & Data
| Command | Description |
|---|---|
| `/pdf <path>` | Read and analyze a PDF |
| `/data <path>` | Analyze CSV or JSON |
| `/screenshot` | Capture screen → AI analysis |
| `/paste` · `/copy` | Clipboard into chat / copy reply out |

### Voice
| Command | Description |
|---|---|
| `/listen [secs]` | Record mic → Groq Whisper → send as message |
| `/speak` | Read last reply aloud |

### Productivity
| Command | Description |
|---|---|
| `/todo add\|list\|done\|remove` | Persistent task tracker |
| `/note [#tag] <text>` | Timestamped notes with tags |
| `/standup` | Daily standup from git log + todos |
| `/timer <25m\|5s\|1h>` | Countdown + desktop notification |
| `/draft <description>` | Draft email, Slack message, or text |
| `/weather [city]` | Current weather |

### Memory & Persona
| Command | Description |
|---|---|
| `/remember <fact>` | Save to long-term memory |
| `/memory` · `/forget` | View or delete memories |
| `/persona` | Edit name, tone, and traits |

### Sessions
| Command | Description |
|---|---|
| `/save` · `/load` | Save or load conversation |
| `/sessions` | List all saved sessions |
| `/export` | Export as markdown |
| `/find <keyword>` | Search past sessions |

### Settings
| Command | Description |
|---|---|
| `/model` | 2-step picker — provider then model |
| `/theme` | Switch color theme (5 themes) |
| `/cost` | Token usage this session |
| `/quit` | Save and exit |

---

## Long-term Memory

Lumi remembers you across sessions. It auto-extracts facts from conversations every 8 turns.

```
  ›  /remember I use Python 3.11, FastAPI, and Fish shell on CachyOS

  ✓  Saved

  ›  /memory
  1.  Uses Python 3.11 and FastAPI for backend
  2.  Fish shell on CachyOS Linux
  3.  Working on an AI CLI called Lumi
```

Next session Lumi already knows your stack without you repeating yourself. Claude Code, Gemini CLI, and every other terminal AI starts from zero every time.

---

## Auto-Fallback

```
  ◆  Quota hit on gemini — switching to groq automatically
  ✦  Lumi  [continues without interruption]
```

Configure multiple providers and Lumi cascades through them automatically when one hits limits. No crashes, no manual intervention.

---

## Themes

Switch with `/theme` — color swatches previewed in the picker:

| Theme | Vibe |
|---|---|
| `tokyo` | Tokyo Night Storm — purple and cyan (default) |
| `dracula` | Dark purple and hot pink |
| `nord` | Arctic blues and soft whites |
| `gruvbox` | Warm earthy retro |
| `catppuccin` | Pastel mocha |

---

## Project Structure

```
lumi/
├── main.py                     # Entry point — all commands, main loop
├── .env                        # API keys (never commit this)
├── requirements.txt
├── data/
│   ├── memory/                 # Persisted memories, mood log, theme
│   ├── personas/default.json   # Lumi's personality
│   └── sessions/               # Saved conversations
└── src/
    ├── agents/council.py       # 5-agent parallel council
    ├── chat/hf_client.py       # Multi-provider API client
    ├── memory/                 # Short-term, long-term, session store
    ├── prompts/builder.py      # Dynamic system prompt with coding mode
    ├── tools/search.py         # Web search
    └── utils/
        ├── filesystem.py       # Natural language file creation agent
        ├── intelligence.py     # Emotion + coding task detection
        ├── autoremember.py     # Background fact extraction
        ├── todo.py · notes.py  # Productivity tools
        ├── voice.py            # Mic + Whisper transcription
        └── themes.py           # 5 color themes
```

---

## Troubleshooting

**`No API key found in .env`**
Ensure `.env` is in the project root. Format: `KEY=value` with no spaces around `=`.

**`Error 429` — Rate limited**
Hit free tier limit. Lumi switches providers automatically if you have multiple configured.

**`Error 404 — No endpoints matching data policy`**
OpenRouter privacy setting. Enable free endpoints at [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy).

**`Error 400 — Developer instruction not enabled`**
Model doesn't support system prompts (usually Gemma). Run `/model` and pick another.

**Terminal looks garbled**
Use a terminal with 256-color ANSI support: Alacritty, Kitty, WezTerm, iTerm2.

---

## Requirements

```
Python 3.9+
openai
python-dotenv
huggingface_hub
pdfplumber          # for /pdf
```

Optional: `alsa-utils` + `espeak-ng` for voice · `scrot` + `xclip` for screenshot

No GPU. No Docker. Runs on anything.

---

## Contributing

PRs welcome.

- **Add a provider:** Follow the pattern in `src/chat/hf_client.py`
- **Add a command:** Add the function, wire it in the main loop, add it to `print_help()`
- **Add a council agent:** Add an entry to `AGENTS` in `src/agents/council.py`

---

## License

MIT — do whatever you want with it.

---

<div align="center">

Built by **[Sardor Sodiqov (SardorchikDev)](https://github.com/SardorchikDev)**

*Claude Code costs $20/mo and only runs Claude.*
*Gemini CLI only runs Gemini.*
*Lumi runs everything, remembers you, and is free.*

If this saved you money or time, give it a ⭐

</div>
