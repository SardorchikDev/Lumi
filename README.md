<div align="center">

```
                                  \
                                  `\,/
                                  .-'-.
                                 '     `
                                 `.   .'
                          `._  .-~     ~-.   _,'
                           ( )'           '.( )
             `._    _       /               .'
              ( )--' `-.  .'                 ;
         .    .'        '.;                  ()
          `.-.`           '                 .'
----*-----;                                .'
          .`-'.           ,                `.
         '    '.        .';                  ()
              (_)-   .-'  `.                 ;
             ,'   `-'       \               `.
                           (_).           .'(_)
                          .'   '-._   _.-'    `.
                                 .'   `.
                                 '     ;
                                  `-,-'
                                   /`\
                                 /`
```

# lumi

**A terminal AI with an 8-model council, grounded agent mode, long-term memory, and a cleaner TUI.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![CI](https://img.shields.io/github/actions/workflow/status/SardorchikDev/Lumi/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/SardorchikDev/Lumi/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-passing-22c55e?style=flat-square)](https://github.com/SardorchikDev/Lumi/actions)
[![Providers](https://img.shields.io/badge/Providers-9%2B-8b5cf6?style=flat-square)](#-api-keys)

[Install](#-installation) · [Quick Start](#-quick-start) · [API Keys](#-api-keys) · [Council Mode](#-council-mode) · [Agent Mode](#-agent-mode) · [Commands](#-commands) · [MCP](#-mcp-servers)

</div>

---

## ⚡ Installation

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash
```

That's it. Lumi installs itself and is available system-wide as `lumi`.

---

## 🚀 Quick Start

```bash
# 1. Add at least one API key
nano ~/Lumi/.env

# 2. Run from anywhere
lumi
```

> **Free key in 30 seconds:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (Gemini) or [console.groq.com](https://console.groq.com) (Groq) — no credit card required.

---

## 🔑 API Keys

All providers have a free tier. No credit card needed.

| Provider | Get Key | Best Free Model |
|---|---|---|
| **Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `gemini-2.5-flash` |
| **Groq** | [console.groq.com](https://console.groq.com) | `kimi-k2-instruct` |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | `hermes-3-405b:free` |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai) | `codestral-latest` |
| **HuggingFace** | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | `Llama-3.3-70B-Instruct` |
| **GitHub Models** | [github.com/settings/tokens](https://github.com/settings/tokens) | `gpt-4o` |
| **Cohere** | [dashboard.cohere.com/api-keys](https://dashboard.cohere.com/api-keys) | `command-a-03-2025` |
| **Cloudflare** | [dash.cloudflare.com](https://dash.cloudflare.com/profile/api-tokens) | `gpt-oss-120b` |
| **Ollama** | [ollama.ai](https://ollama.ai) | any local model |

Add your keys to `~/Lumi/.env`:

```env
GEMINI_API_KEY=AIza...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
MISTRAL_API_KEY=...
HF_TOKEN=hf_...
```

> **OpenRouter free endpoints:** Enable them at [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy).

---

## 🏆 Why Lumi

| Feature | **Lumi** | Claude Code | Gemini CLI | Aider | Copilot CLI |
|---|:---:|:---:|:---:|:---:|:---:|
| 100% free | ✅ | ❌ $20/mo | ❌ limited | ❌ | ❌ $10/mo |
| 9+ providers | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| 8-agent council | ✅ | ❌ | ❌ | ❌ | ❌ |
| Auto-fallback | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| Long-term memory | ✅ | ❌ | ❌ | ❌ | ❌ |
| Autonomous agent | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Grounded planning | ✅ | ✅ | ⚠️ | ❌ | ❌ |
| Safer file patching | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| MCP servers | ✅ | ✅ | ✅ | ❌ | ❌ |
| Plugin system | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| Vision / images | ✅ | ❌ | ❌ | ❌ | ❌ |
| Web fetch | ✅ | ❌ | ✅ | ❌ | ❌ |
| Project context | ✅ | ✅ | ✅ | ❌ | ❌ |
| Named sessions | ✅ | ✅ | ✅ | ❌ | ❌ |
| Custom persona | ✅ | ❌ | ❌ | ❌ | ❌ |
| Voice input | ✅ | ❌ | ❌ | ❌ | ❌ |
| Offline (Ollama) | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| Minimal TUI | ✅ | ✅ | ⚠️ | ❌ | ❌ |
| Open source | ✅ | ❌ | ❌ | ✅ | ❌ |

---

## 🧠 Council Mode

Eight AI models answer your question simultaneously. A judge model synthesizes the best response and streams it back. If one model hits a rate limit, the next fallback fires automatically.

```
❯ lumi --model council

◆ Lumi  │  Council  │  8 agents

›  explain async vs parallel execution in Python

  council  8 agents  →  asking in parallel...

  ✓ Gemini     ✓ Kimi K2    ✓ GPT-OSS
  ✓ Codestral  ✓ Llama 3.3  ✓ GPT-4o
  ✓ Command A  ✓ Cloudflare

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
| **GPT-4o** | GitHub Models | Precision & reliability |
| **Command A** | Cohere | Language & nuance |
| **Cloudflare AI** | Cloudflare | Diversity & independence |

---

## 🤖 Agent Mode

Give Lumi a goal. It inspects the workspace, builds a grounded plan, previews file changes, and executes with rollback support if a run fails.

```
›  /agent build a FastAPI project with JWT auth and Postgres

  Plan  (6 steps)

  1. [action]     list_dir .
  2. [action]     read_file pyproject.toml
  3. [action]     mkdir app/auth
  4. [file_write] Write app/main.py
  5. [action]     patch_file app/config.py
  6. [action]     run_tests tests/

  Summary  2 file changes  1 patch  1 dir  1 check  2 reads  0 risky
  diff preview for app/config.py:
  -DEBUG = False
  +DEBUG = True

  Execute 6 preflighted steps? [y/N]  y

  ✓  Agent completed 6/6 steps
```

Agent mode now uses structured actions such as `list_dir`, `read_file`, `search_code`, `run_tests`, `run_ruff`, `run_mypy`, `mkdir`, `write_json`, `patch_file`, and `patch_lines` instead of arbitrary shell execution.

Use `--yolo` to skip confirmations and rollback prompts.

---

## 🖥️ TUI

Lumi ships with a more minimal terminal UI:

- Fractal splash logo, cleaner chrome
- Compact status bar and calmer colors
- Better code block presentation
- Split pane for live shell output with `/pane <cmd>`
- Prompt history on `↑` / `↓`
- Transcript scrolling on `Shift+↑` / `Shift+↓`, `Ctrl+↑` / `Ctrl+↓`, `PgUp` / `PgDn`

---

## 📁 LUMI.md — Project Context

Place a `LUMI.md` file in any project directory. Lumi auto-loads it on startup — no config needed.

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
```

---

## 🔌 MCP Servers

Connect Lumi to GitHub, Postgres, Filesystem, Slack, and hundreds more tools.

```bash
/mcp add github npx @modelcontextprotocol/server-github
/mcp add postgres npx @modelcontextprotocol/server-postgres
/mcp list           # show all configured servers
/mcp tools github   # list available tools on a server
```

---

## 🚩 CLI Flags

```bash
lumi                                      # interactive session
lumi "explain this code"                  # start with a prompt
lumi -p "what is a closure"               # print answer and exit
lumi -p "fix this" < broken.py            # pipe a file in
cat error.log | lumi -p "explain"         # pipe from any command
lumi -c                                   # continue last session
lumi -r my-project                        # resume named session
lumi --model council                      # start in council mode
lumi --model gemini-2.5-flash             # use a specific model
lumi --provider groq                      # force a provider
lumi --system-prompt "Be concise"         # replace system prompt
lumi --append-system-prompt "Use TS"      # append to default prompt
lumi --yolo                               # skip all confirmations
lumi --max-turns 10                       # exit after N turns
lumi -p "query" --output-format json      # JSON output for scripts
lumi --list-sessions                      # list sessions and exit
lumi --verbose                            # full error output
lumi -v                                   # show version
```

---

## 💬 Commands

### Chat
| Command | Description |
|---|---|
| `/council <q>` | Ask all 8 agents — streams synthesized best answer |
| `/council --show <q>` | Same + each agent's raw response |
| `/redo [hint]` | Regenerate with a different approach |
| `/more` | Expand the last reply |
| `/tl;dr` | One-sentence summary |
| `/rewrite` | Rewrite in a different structure |
| `/short` · `/detailed` · `/bullets` | Format modifiers |
| `/context` | Token usage breakdown |
| `/multi` | Toggle multi-line input |
| `/clear` · `/undo` · `/retry` | Reset, undo turn, or resend |

### Code
| Command | Description |
|---|---|
| `/edit <path>` | AI-rewrite a file with diff + backup |
| `/file <path>` | Load file into context |
| `/project <dir>` | Load entire codebase into context |
| `/fix <e>` | Diagnose and fix an error |
| `/review [file]` | Full code review |
| `/improve [file]` | Fix bugs, improve readability |
| `/optimize [file]` | Performance analysis with before/after |
| `/security [file]` | Security audit with severity ratings |
| `/refactor [file]` | SOLID principles refactor |
| `/test [file]` | Generate pytest unit tests |
| `/explain [file]` | Explain code line by line |
| `/comment [file]` | Add docstrings and inline comments |
| `/run` | Execute code from last reply |
| `/git status\|commit\|log` | Git helpers |
| `/pr` | Write a PR description from git diff |
| `/changelog` | Generate CHANGELOG from git log |

### Web & Vision
| Command | Description |
|---|---|
| `/web <url> [question]` | Fetch a webpage and ask questions |
| `/search <query>` | Web search with AI summary |
| `/image <path> [question]` | Vision support |
| `/pdf <path>` | Analyze a PDF |
| `/data <path>` | Analyze CSV or JSON |

### Autonomous
| Command | Description |
|---|---|
| `/agent <task>` | Grounded plan + preflight + rollback-capable execution |
| `/godmode <goal>` | Fully autonomous loop until goal is met |
| `/scaffold <type>` | Full project scaffold (fastapi, react, cli...) |
| `/lumi.md create` | Create a project context file |
| `/lumi.md show` | View current LUMI.md |

### Sessions & Memory
| Command | Description |
|---|---|
| `/save [name]` | Save session with optional name |
| `/load [name]` | Load session by name or latest |
| `/sessions` | List all saved sessions |
| `/remember <fact>` | Save a fact to long-term memory |
| `/memory` | View all saved memories |
| `/forget` | Delete memories interactively |
| `/export` | Export session as Markdown |
| `/find <keyword>` | Search through past sessions |

### MCP Servers
| Command | Description |
|---|---|
| `/mcp list` | Show configured MCP servers |
| `/mcp add <n> <cmd>` | Add a new MCP server |
| `/mcp remove <n>` | Remove a server |
| `/mcp tools <server>` | List tools on a server |
| `/mcp call <server> <tool>` | Call a tool directly |

### Tools & Productivity
| Command | Description |
|---|---|
| `/todo add\|list\|done\|rm` | Persistent task tracker |
| `/note add\|list\|search` | Timestamped notes |
| `/draft <details>` | Draft an email or message |
| `/weather [location]` | Current weather |
| `/timer <25m\|90s>` | Countdown timer |
| `/standup` | Daily standup from git + todos |
| `/copy` · `/paste` | Clipboard integration |
| `/voice` | Voice input via Whisper |
| `/pane <cmd>` | Live split-screen terminal pane |

### Settings
| Command | Description |
|---|---|
| `/model` | Pick provider and model |
| `/theme` | Switch color theme |
| `/persona` | Edit Lumi's name, tone, and traits |
| `/offline [model]` | Switch to local Ollama |
| `/plugins` · `/plugins reload` | Manage plugins |
| `/cost` | Show token usage this session |
| `/quit` | Save and exit |

---

## 🔌 Plugin System

Drop a `.py` file into `~/Lumi/plugins/` and it's auto-loaded on startup.

```python
# ~/Lumi/plugins/deploy.py

COMMANDS = {"/deploy": deploy}
DESCRIPTION = {"/deploy": "Deploy to staging or production"}

def deploy(args, client, model, memory, system_prompt, name):
    env = args.strip() or "staging"
    print(f"Deploying to {env}...")
```

---

## 🛠️ Development

```bash
git clone https://github.com/SardorchikDev/Lumi.git ~/Lumi
cd ~/Lumi
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

```bash
pytest tests/ -v
ruff check .
ruff format .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide. Follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, etc.

---

## 📄 License

MIT © [SardorchikDev](https://github.com/SardorchikDev)
