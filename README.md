<div align="center">

```
██╗      ██╗   ██╗  ███╗   ███╗  ██╗
██║      ██║   ██║  ████╗ ████║  ██║
██║      ██║   ██║  ██╔████╔██║  ██║
██║      ██║   ██║  ██║╚██╔╝██║  ██║
███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║
╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝
```

### The terminal AI that runs 8 models at once, remembers you, edits your files, and costs nothing.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Free](https://img.shields.io/badge/Cost-100%25%20Free-22c55e?style=flat-square)](#-api-keys)
[![Providers](https://img.shields.io/badge/Providers-8%2B-8b5cf6?style=flat-square)](#-api-keys)
[![Council](https://img.shields.io/badge/Council-8%20Agents-f97316?style=flat-square)](#-council-mode)
[![TUI](https://img.shields.io/badge/TUI-Pure%20Python-7dcfff?style=flat-square)](#-tui)

[Quick Start](#-quick-start) · [TUI](#-tui) · [Council](#-council-mode) · [Commands](#-commands) · [Providers](#-api-keys) · [Agent Mode](#-agent-mode) · [MCP](#-mcp-servers)

</div>

---

## What is Lumi?

Lumi is a **pure Python terminal AI assistant** with a hand-built TUI — no Electron, no web UI, no bloat. Zero UI framework dependencies. It runs in your terminal using raw ANSI escape codes and Tokyo Night colors.

You type. It thinks. Eight AI models argue about the answer simultaneously. The best response wins.

---

## ✨ Highlights

- **⚡ 8-Agent Council** — Gemini, Kimi, GPT-OSS, Codestral, Llama, GPT-4o, Command A, Cloudflare run in parallel. They debate. A judge synthesizes the best answer.
- **🎨 Pure Python TUI** — Tokyo Night theme. Zero UI library dependencies. Built from scratch with ANSI escape codes and `termios`.
- **🧠 Conversation memory** — Remembers context across sessions. Named sessions you can resume.
- **🤖 Autonomous Agent** — Plans and executes multi-step tasks. Reads/writes files, runs code, searches the web.
- **🔌 MCP Support** — Connect any MCP server via stdio. Use tools from your own servers.
- **💾 100% Free** — Every provider has a free tier. You can run Lumi entirely for free.
- **🔌 Plugin System** — Drop Python files into `~/Lumi/plugins/`. Auto-loaded as slash commands.

---

## 🚀 Quick Start

```bash
git clone https://github.com/SardorchikDev/lumi
cd lumi
bash install.sh
```

Then add at least one API key to `~/Lumi/.env`:

```env
GEMINI_API_KEY=your_key_here
```

Run:
```bash
lumi
```

The TUI launches automatically. That's it.

---

## 🖥 TUI

Lumi's terminal interface is built from scratch — no Textual, no prompt_toolkit, no curses. Pure Python: `termios`, `tty`, `threading`, `signal`, and ANSI escape codes.

```
┌─ ◆ Lumi AI  ─  terminal assistant ─────────── ~1,240tk  Gemini / gemini-3.1-pro ─┐
│                                                                                      │
│  you  21:04                                                                          │
│  write me a binary search in python                                                  │
│                                                                                      │
│  ◆ lumi  21:04                                                                       │
│  ┌─ python──────────────────────────────────────────────────────────────────────┐   │
│  │ def binary_search(arr, target):                                               │   │
│  │     left, right = 0, len(arr) - 1                                            │   │
│  │     while left <= right:                                                      │   │
│  │         mid = (left + right) // 2                                            │   │
│  │         if arr[mid] == target: return mid                                    │   │
│  │         elif arr[mid] < target: left = mid + 1                               │   │
│  │         else: right = mid - 1                                                │   │
│  │     return -1                                                                 │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│──────────────────────────────────────────────────────────────────────────────────── │
│ ›  ask lumi anything…   ( / for commands )                                           │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Features
- **Markdown rendering** — headings, bullets, numbered lists, blockquotes, **bold**, *italic*, `inline code`
- **Syntax-highlighted code blocks** — keywords, numbers, strings, comments each a different color
- **Scroll** — `↑↓` when input empty, `PgUp/PgDn` for pages, scroll indicator in title bar
- **Input history** — `↑↓` inside input recalls previous messages
- **Slash command popup** — type `/` for a floating menu, `Tab` to complete, `Enter` to run
- **Model picker modal** — `Ctrl+N` opens an inline picker for providers and models
- **Council sidebar** — live agent spinners with confidence scores when in council mode
- **Notification toasts** — brief messages for copy/save/export confirmations
- **Resize aware** — `SIGWINCH` triggers instant redraw at new terminal size
- **Tokyo Night** — exact 24-bit color palette throughout

### Keybinds

| Key | Action |
|-----|--------|
| `Enter` | Send message / confirm selection |
| `↑↓` | Scroll (empty input) or input history |
| `PgUp / PgDn` | Scroll pages |
| `Tab` | Complete slash command |
| `Ctrl+N` | Open model picker |
| `Ctrl+L` | Clear chat |
| `Ctrl+R` | Retry last message |
| `Ctrl+W` | Delete word backwards |
| `Ctrl+U` | Clear entire input |
| `Ctrl+← / →` | Jump word |
| `Home / End` | Jump to start/end of input |
| `Ctrl+Q` | Quit |
| `Esc` | Close popup |

---

## ⚡ Council Mode

Switch with `/council` or `Ctrl+N → ⚡ Council`.

All available agents fire simultaneously. Each gets a specialist system prompt tuned to their strength. A judge model synthesizes the final answer. If 3+ agents disagree, a debate round fires before synthesis. The result is then refined in a second pass.

```
◆ council  8 agents · code   21:09
┌─────────────────────────────────────────────────────────────────┐
│  ✓ Gemini    9/10 · 3.1s     ★ lead                            │
│  ✓ Kimi K2   8/10 · 4.2s                                        │
│  ✓ Codestral 9/10 · 2.8s                                        │
│  ⠸ GPT-OSS   thinking…                                          │
│  ✓ Llama 3.3 7/10 · 5.1s                                        │
│  ✓ GPT-4o    9/10 · 3.7s                                        │
│  ✓ Command A 8/10 · 6.2s                                        │
│  ✓ Cloudflare 7/10 · 2.4s                                       │
└─────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. **Task classification** — question type detected: `code / debug / analysis / creative / factual / design / general`
2. **Lead agent** — best agent for that task type is promoted to lead
3. **Parallel calls** — all agents fire simultaneously with specialist prompts
4. **Confidence scoring** — each agent rates their own answer 1–10
5. **Debate round** — fires if 3+ agents contradict each other
6. **Synthesis** — judge model weighs confidence scores and builds the best answer
7. **Refinement** — judge reviews its own synthesis, rewrites if gaps found

---

## 📋 Commands

Type `/` in the TUI to see the popup, or type any command directly:

| Command | Description |
|---------|-------------|
| `/council` | Switch to council mode |
| `/model` | Open model & provider picker |
| `/clear` | Clear conversation history |
| `/retry` | Retry the last message |
| `/web <query>` | Search the web |
| `/save [file]` | Save chat to `~/lumi_chat_<timestamp>.txt` |
| `/export [file]` | Export chat as Markdown |
| `/copy` | Copy last response to clipboard |
| `/tokens` | Show token usage for current session |
| `/sys` | Preview current system prompt |
| `/agent` | Autonomous agent mode |
| `/session` | Session management |
| `/help` | Show all commands and keybinds |
| `/exit` | Quit |

### Non-interactive / print mode

```bash
lumi -p "explain this" < file.py       # pipe stdin
lumi --no-tui                          # classic CLI
lumi -p "summarize" --model council    # one-shot council
```

---

## 🔑 API Keys

Add to `~/Lumi/.env`. You only need **one** to get started — everything else is optional.

| Provider | Env Var | Free Tier | Get Key |
|----------|---------|-----------|---------|
| **Gemini** | `GEMINI_API_KEY` | 1M ctx, generous limits | [aistudio.google.com](https://aistudio.google.com) |
| **Groq** | `GROQ_API_KEY` | Very fast, daily limits | [console.groq.com](https://console.groq.com) |
| **OpenRouter** | `OPENROUTER_API_KEY` | $1 free credit | [openrouter.ai](https://openrouter.ai) |
| **Mistral** | `MISTRAL_API_KEY` | Free tier available | [console.mistral.ai](https://console.mistral.ai) |
| **HuggingFace** | `HF_TOKEN` | Free, many models | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| **GitHub Models** | `GITHUB_API_KEY` | Free with GitHub account | [github.com/settings/tokens](https://github.com/settings/tokens) |
| **Cohere** | `COHERE_API_KEY` | 1000 req/month free | [dashboard.cohere.com](https://dashboard.cohere.com) |
| **Cloudflare AI** | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | 10k neurons/day free | [dash.cloudflare.com](https://dash.cloudflare.com) |
| **Ollama** | *(auto-detected)* | Fully local, unlimited | [ollama.ai](https://ollama.ai) |

---

## 🤖 Agent Mode

Lumi can plan and execute multi-step tasks autonomously.

```bash
lumi --yolo "refactor all Python files in this directory to use type hints"
```

Or in the TUI:
```
/agent
> add docstrings to every function in src/utils/
```

Agent capabilities:
- Read and write files
- Execute shell commands
- Search the web
- Call MCP tools
- Plan tasks into sub-steps and execute them in sequence

`--yolo` flag auto-approves all file writes. Without it, Lumi asks before each write.

---

## 🔌 MCP Servers

Lumi supports Model Context Protocol (MCP) via stdio.

Add servers to `~/Lumi/.env`:
```env
MCP_SERVERS=filesystem,github,slack
```

Or connect directly in the TUI:
```
/mcp connect filesystem
```

---

## 🔧 Plugin System

Drop any `.py` file into `~/Lumi/plugins/`. It gets auto-loaded and its functions become slash commands.

Example `~/Lumi/plugins/weather.py`:
```python
def weather(city: str = "Tokyo") -> str:
    """Get current weather for a city."""
    import urllib.request, json
    url = f"https://wttr.in/{city}?format=j1"
    with urllib.request.urlopen(url) as r:
        data = json.load(r)
    return data["current_condition"][0]["weatherDesc"][0]["value"]
```

Now `/weather London` works in Lumi.

---

## 📁 Project Structure

```
~/Lumi/
├── main.py                    # CLI entry point, all commands
├── lumi_system_instructions.md # system prompt (edit to customize Lumi's personality)
├── .env                       # API keys
├── requirements.txt
└── src/
    ├── agents/
    │   ├── council.py         # 8-agent council with debate + refinement
    │   └── agent.py           # autonomous multi-step agent
    ├── chat/
    │   └── hf_client.py       # multi-provider OpenAI-compatible client
    ├── memory/
    │   ├── conversation_store.py  # named sessions
    │   ├── longterm.py            # long-term memory
    │   └── short_term.py          # in-session context
    ├── prompts/
    │   └── builder.py         # loads + builds system prompt
    ├── tools/
    │   ├── mcp.py             # MCP stdio client
    │   └── search.py          # web search
    ├── tui/
    │   └── app.py             # pure Python TUI (zero UI library dependencies)
    └── utils/
        ├── filesystem.py      # file read/write tools
        ├── highlight.py       # syntax highlighting
        ├── markdown.py        # markdown → ANSI renderer
        ├── plugins.py         # plugin loader
        ├── themes.py          # Tokyo Night color system
        └── web.py             # stdlib web fetcher
```

---

## ⚙️ Configuration

Edit `lumi_system_instructions.md` to change Lumi's personality, behavior, and defaults. This file is the system prompt — it loads automatically on every session.

Common customizations:
- Change Lumi's name or personality
- Set default response style (concise vs. detailed)
- Add domain-specific knowledge
- Set default provider/model
- Add custom slash commands

---

## 🐛 Known Limitations

- MCP support is early — complex servers may need tweaking
- Scroll in very long conversations can get slow (building all lines each frame)
- Cloudflare models are experimental — some may return errors
- Council mode uses 7–8 API calls per message — burns free tier quotas faster

---

## 📄 License

MIT. Use it, fork it, build on it.

---

<div align="center">

Built by **SardorchikDev**

*Pure Python. Zero bloat. Tokyo Night.*

</div>
