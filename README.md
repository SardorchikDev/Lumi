<div align="center">

```
██╗      ██╗   ██╗  ███╗   ███╗  ██╗
██║      ██║   ██║  ████╗ ████║  ██║
██║      ██║   ██║  ██╔████╔██║  ██║
██║      ██║   ██║  ██║╚██╔╝██║  ██║
███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║
╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝
```

### The terminal AI that runs 5 models at once, remembers you, edits your files, and costs nothing.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Free](https://img.shields.io/badge/Cost-100%25%20Free-22c55e?style=flat-square)](#-api-keys)
[![Providers](https://img.shields.io/badge/Providers-5%2B-8b5cf6?style=flat-square)](#-api-keys)
[![Council](https://img.shields.io/badge/Council-5%20Agents-f97316?style=flat-square)](#-council-mode)

[Quick Start](#-quick-start) · [Why Lumi](#-why-lumi) · [Council Mode](#-council-mode) · [Commands](#-commands) · [Agent Mode](#-agent-mode) · [MCP](#-mcp-servers) · [Plugins](#-plugin-system)

</div>

---

## ⚡ Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash
nano ~/Lumi/.env    # add at least one API key
lumi                # run from anywhere
```

Free key in 30 seconds: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (Gemini) or [console.groq.com](https://console.groq.com) (Groq). No credit card.

---

## 🏆 Why Lumi

| | **Lumi** | Claude Code | Gemini CLI | Aider | Copilot CLI |
|---|:---:|:---:|:---:|:---:|:---:|
| 100% free | ✅ | ❌ $20/mo | ❌ limited | ❌ | ❌ $10/mo |
| 5+ providers | ✅ | ❌ Claude only | ❌ Gemini only | ⚠️ | ❌ |
| 5-agent council | ✅ | ❌ | ❌ | ❌ | ❌ |
| Auto-fallback | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| Long-term memory | ✅ | ❌ | ❌ | ❌ | ❌ |
| Autonomous agent | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| MCP servers | ✅ | ✅ | ✅ | ❌ | ❌ |
| Plugin system | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| Vision / images | ✅ | ❌ | ❌ | ❌ | ❌ |
| Web fetch | ✅ | ❌ | ✅ | ❌ | ❌ |
| Project context | ✅ | ✅ | ✅ | ❌ | ❌ |
| Named sessions | ✅ | ✅ | ✅ | ❌ | ❌ |
| Custom persona | ✅ | ❌ | ❌ | ❌ | ❌ |
| 5 color themes | ✅ | ❌ | ✅ | ❌ | ❌ |
| Voice input | ✅ | ❌ | ❌ | ❌ | ❌ |
| Offline (Ollama) | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| Open source | ✅ | ❌ | ❌ | ✅ | ❌ |

> Claude Code costs $20/mo and only runs Claude. Gemini CLI only runs Gemini. **Lumi runs everything, remembers you, and is free.**

---

## 🧠 Council Mode

Five AI models answer simultaneously. A judge synthesizes the best answer and streams it back token by token. Fallbacks are automatic — quota hit on one model, next one fires.

```
❯ lumi --model council

◆ Lumi  │  Council  │  5 agents

›  explain async vs parallel execution in Python

  council  5 agents  →  asking in parallel...

  ✓ Gemini     ✓ Kimi K2    ✓ GPT-OSS
  ✓ Codestral  ✓ Llama 3.3

  synthesizing 5 responses...

✦ Lumi  [council]
  Async and parallel solve different problems. Async is about
  waiting efficiently — when one task blocks on I/O, other
  tasks run in the meantime...
```

| Agent | Provider | Specialty |
|---|---|---|
| **Gemini** | Google AI | Reasoning, long context |
| **Kimi K2** | Groq | Analysis, structured thinking |
| **GPT-OSS** | OpenRouter | General purpose |
| **Codestral** | Mistral | Code generation & review |
| **Llama 3.3** | HuggingFace | Writing & explanation |

Each agent has a fallback chain. You only see `✗` when every fallback fails.

---

## 🔑 API Keys

All free. No credit card.

| Provider | Get Key | Best Free Model |
|---|---|---|
| **Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `gemini-flash-latest` |
| **Groq** | [console.groq.com](https://console.groq.com) | `kimi-k2-instruct` |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | `hermes-3-405b:free` |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai) | `codestral-latest` |
| **HuggingFace** | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | `Llama-3.3-70B-Instruct` |

```env
# ~/Lumi/.env
GEMINI_API_KEY=AIza...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
MISTRAL_API_KEY=...
HF_TOKEN=hf_...
```

> **OpenRouter:** Visit [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy) and enable free endpoints.

---

## 🚀 CLI Flags

```bash
lumi                                      # interactive session
lumi "explain this code"                  # start with a message
lumi -p "what is a closure"               # print answer and exit
lumi -p "fix this" < broken.py            # pipe + print
cat error.log | lumi -p "explain"         # pipe from any command
lumi -c                                   # continue last session
lumi -r my-project                        # resume named session
lumi --model council                      # start in council mode
lumi --model gemini-2.5-flash             # specific model
lumi --provider groq                      # force provider
lumi --system-prompt "Be concise"         # replace system prompt
lumi --append-system-prompt "Use TS"      # append to default prompt
lumi --system-prompt-file ./rules.txt     # load prompt from file
lumi --yolo                               # auto-approve all file writes
lumi --max-turns 10                       # exit after N turns
lumi -p "query" --output-format json      # JSON output for scripts
lumi --list-sessions                      # list sessions and exit
lumi --verbose                            # full error output
lumi -v                                   # version
```

---

## 💬 Commands

### Chat
| Command | Description |
|---|---|
| `/council <q>` | Ask all 5 agents — streams synthesized best answer |
| `/council --show <q>` | Same + each agent's raw response |
| `/context` | Token usage bar for current conversation |
| `/redo [model]` | Regenerate last answer, optionally with a different model |
| `/more` | Expand the last reply |
| `/tl;dr` | One-sentence summary |
| `/rewrite` | Rewrite in a different style |
| `/short` · `/detailed` · `/bullets` | Format modifiers |
| `/multi` | Toggle multi-line input |
| `/clear` · `/undo` · `/retry` | Reset, undo turn, or resend |

### Code
| Command | Description |
|---|---|
| `/edit <path>` | Edit file — diff + backup |
| `/file <path>` | Load file into context |
| `/project <dir>` | Load entire codebase |
| `/fix <error>` | Diagnose and fix an error |
| `/review [file]` | Full code review |
| `/explain [file]` | Explain code or last reply |
| `/comment [file]` | Add docstrings and comments |
| `/run` | Execute code from last reply |
| `/git status\|commit\|log` | Git helpers |

### Autonomous
| Command | Description |
|---|---|
| `/agent <task>` | Plan + execute multi-step task autonomously |
| `/lumi.md create` | Create project context file |
| `/lumi.md show` | View current LUMI.md |

### Web & Vision
| Command | Description |
|---|---|
| `/web <url> [question]` | Fetch full webpage, ask questions |
| `/image <path> [question]` | Send image — vision support |
| `/search <query>` | Web search with AI summary |
| `/pdf <path>` | Analyze PDF |
| `/data <path>` | Analyze CSV/JSON |

### MCP Servers
| Command | Description |
|---|---|
| `/mcp list` | Show configured servers |
| `/mcp add <n> <cmd>` | Add server |
| `/mcp remove <n>` | Remove server |
| `/mcp tools <server>` | List tools |
| `/mcp call <srv> <tool>` | Call tool directly |

### Sessions & Memory
| Command | Description |
|---|---|
| `/save [name]` | Save with optional name |
| `/load [name]` | Load by name or latest |
| `/sessions` | Table of all sessions |
| `/remember <fact>` | Save to long-term memory |
| `/memory` · `/forget` | View or delete memories |
| `/export` · `/find <kw>` | Export or search sessions |

### Settings
| Command | Description |
|---|---|
| `/model` | Pick provider + model (with speed tags) |
| `/theme` | Switch color theme |
| `/persona` | Edit name, tone, traits |
| `/plugins` · `/plugins reload` | Manage plugins |
| `/quit` | Save and exit |

---

## 🤖 Agent Mode

Give Lumi a goal. It plans, shows you the plan, then executes — asking before anything risky.

```
›  /agent build a FastAPI project with JWT auth and Postgres

  Plan  (8 steps)

  1. [shell]      Create project structure
  2. [file_write] Write main.py
  3. [file_write] Write models.py — SQLAlchemy
  4. [file_write] Write auth.py — JWT logic
  5. [ai_task]    Generate requirements.txt
  6. [shell]      git init                    ▲ risky
  7. [file_write] Write .env template
  8. [shell]      pip install -r requirements  ▲ risky

  Execute 8 steps? [y/N]  y

  step 1/8  Create project structure
  ✓  Created ./myapi/
  ...
  ✓  Agent completed 8/8 steps
```

Use `--yolo` to skip all confirmation prompts.

---

## 📁 LUMI.md Project Context

Put `LUMI.md` in any project directory. Lumi auto-loads it on startup — no config needed.

```bash
cd ~/projects/myapp && lumi
# Loaded LUMI.md project context (312 chars)
```

Create one with `/lumi.md create` or write it manually:

```markdown
# Project Context

## Stack
Python 3.11 · FastAPI · PostgreSQL · Redis

## Conventions
- Type hints everywhere
- async/await for DB calls
- Pydantic v2 models

## Rules
- Never use print() — use the logger
- Docstrings on all public functions

## Key files
- main.py   — FastAPI entry point
- models.py — SQLAlchemy ORM models
- auth.py   — JWT authentication
```

---

## 🔌 MCP Servers

Connect Lumi to GitHub, Postgres, filesystem, Slack, and hundreds more.

```bash
/mcp add github npx -y @modelcontextprotocol/server-github
/mcp add fs     npx -y @modelcontextprotocol/server-filesystem /home/user
/mcp add db     npx -y @modelcontextprotocol/server-postgres postgresql://localhost/mydb

/mcp tools github
/mcp call github search_repositories {"query": "fastapi"}
```

Config in `~/Lumi/mcp.json`. Available tools are injected into the system prompt automatically.

---

## 🧩 Plugin System

Drop a `.py` in `~/Lumi/plugins/` → instant new slash command. No restart.

```python
# ~/Lumi/plugins/joke.py
COMMANDS    = {"/joke": tell_joke}
DESCRIPTION = {"/joke": "tell a programming joke"}

def tell_joke(args, client, model, memory, system_prompt, name):
    print("  Why do programmers prefer dark mode?")
    print("  Because light attracts bugs 🐛")
```

```bash
/plugins reload   # hot-reload
/joke             # works immediately
```

---

## 🎨 Themes

| Theme | Style |
|---|---|
| `tokyo` | Tokyo Night — purple & cyan *(default)* |
| `dracula` | Dark purple, hot pink |
| `nord` | Arctic blues |
| `gruvbox` | Warm earthy retro |
| `catppuccin` | Soft pastel mocha |

---

## ❓ Troubleshooting

**`No API key found`** — Add keys to `~/Lumi/.env`, format `KEY=value`

**`Error 429`** — Hit free quota. Add more API keys, Lumi auto-switches.

**`Error 404 — No endpoints matching data policy`** *(OpenRouter)* — Enable free endpoints at [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy)

**`Error 400 — Developer instruction not enabled`** — Model doesn't support system prompts (Gemma etc). Use `/model` to pick another.

**Council spinner garbled** — Use Alacritty, Kitty, WezTerm, or iTerm2.

---

## 📦 Requirements

```
Python 3.9+ · openai · python-dotenv · huggingface_hub
```

Optional: `pdfplumber` (PDF) · `sounddevice` + `openai-whisper` (voice) · `node` + `npx` (MCP servers)

No GPU. No Docker. Runs anywhere.

---

## 🤝 Contributing

- **New provider** → `src/chat/hf_client.py`
- **New command** → add fn in `main.py` → wire in dispatch loop → add to `print_help()`
- **New council agent** → add to `AGENTS` in `src/agents/council.py`
- **New plugin** → drop `.py` in `~/Lumi/plugins/` — no code changes needed

---

## 📄 License

MIT — use it, fork it, ship it.

---

<div align="center">

Built by **[Sardor Sodiqov](https://github.com/SardorchikDev)**

*One terminal. Five AIs. Zero cost.*

**[⭐ Star on GitHub](https://github.com/SardorchikDev/lumi)**

</div>
