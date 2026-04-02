# Lumi - rebirth

Minimal terminal AI for coding, repo work, file management, and grounded agent tasks.

[Install](#install) · [Quick Start](#quick-start) · [What Lumi Does](#what-lumi-does) · [Common Workflows](#common-workflows) · [Commands](#commands) · [Plugins](#plugins) · [Development](#development) · [Roadmap](ROADMAP.md)

## Why Lumi

- keyboard-first TUI and classic CLI mode
- grounded agent flow with previews, confirmations, and rollback
- natural-language file and folder operations
- repo-aware workflows for git, files, and verification
- cached context for web pages, files, PDFs, images, and data
- optional plugins with approval and permission reporting

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash
```

The installer:

- clones Lumi into `~/Lumi`
- creates `venv`
- installs dependencies
- creates a `lumi` launcher in `~/.local/bin`
- creates `~/Lumi/.env` if it does not exist
- initializes runtime state outside the repo under `~/.codex/memories/lumi` by default

Useful variants:

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash -s -- --dev
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash -s -- --dir ~/apps/Lumi
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash -s -- --help
```

## Quick Start

1. Add at least one provider key to `~/Lumi/.env`
2. Open a new shell or reload your shell config
3. Run:

```bash
lumi
```

Good first commands inside Lumi:

```text
/onboard
/rebirth
/doctor
/model
/status
```

Good first prompts:

```text
/agent add tests for this module
/review src/main.py
/git status
/search latest FastAPI release notes
```

Useful launch flags:

```bash
lumi --no-tui
lumi --yolo
```

## What Lumi Does

- full-screen TUI plus classic CLI mode
- multi-model chat and council mode
- grounded agent mode with repo-aware planning and verification
- natural-language file operations and structured `/fs` commands
- git helpers inside the app
- session memory, saved chats, notes, todos, and long-term memory
- web, file, PDF, image, voice, and structured data helpers
- plugin loading with approval, audit, and permission reporting

## Lumi - rebirth Profile

Use `/rebirth` to view a capability matrix and readiness score for core coding-agent workflows.
Use `/rebirth on` to apply the rebirth defaults:

- detailed response mode
- compact mode off
- guardian watcher on

## TUI

The default interface is built for keyboard-first use:

- stable transcript and prompt layout
- slash-command picker and model picker
- prompt history and transcript scrolling
- starter panel and side pane
- inline review blocks for pending filesystem actions

Useful keys:

- `Esc` closes transient UI and cancels pending file plans
- `Ctrl+G` toggles the starter panel
- `Ctrl+N` opens the model picker
- `Up` / `Down` navigate prompt history
- `Shift+Up` / `Shift+Down` scroll the transcript
- `Tab` accepts slash-command or path suggestions

## Common Workflows

### Agent Work

```text
/agent add login validation and tests
/review src/auth.py
/fix type errors in src/api
```

Lumi agent mode is built around structured actions rather than arbitrary shell execution. It can inspect the repo, plan changes, patch files, run repo-aware verification, and roll back file mutations on failure.

### File Operations

Lumi understands natural-language file tasks directly in chat:

```text
create a folder named api and add main.py inside it
delete the folder docs
rename app.py to main.py
move config.yaml into app/config
```

Or use explicit filesystem commands:

- `/fs ls [path]`
- `/fs cat <file>`
- `/fs mkdir <dir>`
- `/fs mv <src> <dst>`
- `/fs rm <path>`
- `/fs write <file> [text]`
- `/fs append <file> [text]`
- `/undo`

### Git Work

Built-in git helpers include:

- `/git status`
- `/git diff`
- `/git log`
- `/git remote`
- `/git fetch`
- `/git sync`
- `/git branches`
- `/git summary`
- `/git review`
- `/git prepare`
- `/git commit`
- `/git commit-confirm`

### Context Helpers

Use Lumi to pull focused context into the conversation:

- `/file <path>`
- `/project <dir>`
- `/browse [dir]`
- `/web <url> [question]`
- `/search <query>`
- `/pdf <path>`
- `/data <path>`
- `/image <path> [question]`
- `/voice [seconds]`

## Commands

### Core

| Command | Description |
|---|---|
| `/model` | Switch provider and model |
| `/clear` | Clear the current conversation |
| `/save [name]` | Save the current session |
| `/load [name]` | Load a saved session |
| `/sessions` | List saved sessions |
| `/status` | Show Lumi session and workspace status |
| `/doctor` | Check provider and workspace health |
| `/onboard` | Show first-run guidance |
| `/rebirth` | Show capability matrix and apply rebirth defaults |
| `/benchmark` | Show benchmark scenarios |
| `/exit` | Exit Lumi |

### Chat and Writing

| Command | Description |
|---|---|
| `/council <prompt>` | Ask council mode |
| `/retry` | Retry the last prompt |
| `/redo [hint]` | Retry from a different angle |
| `/more` | Expand the last answer |
| `/rewrite` | Rewrite the last answer |
| `/tl;dr` | Summarize the last answer |
| `/short` | Make the next answer concise |
| `/detailed` | Make the next answer detailed |
| `/bullets` | Make the next answer bullet-based |
| `/draft <prompt>` | Draft a message |
| `/translate <text>` | Translate text |
| `/summarize [file]` | Summarize content |

### Code and Context

| Command | Description |
|---|---|
| `/agent <task>` | Run grounded agent mode |
| `/review [file]` | Review code |
| `/fix <problem>` | Diagnose and fix an issue |
| `/debug <problem>` | Debug a failure |
| `/test [file]` | Generate tests |
| `/docs [file]` | Generate docs/comments |
| `/types [file]` | Add typing hints |
| `/comment <file>` | Add inline comments |
| `/file <path>` | Load a file into context |
| `/project <dir>` | Load a project into context |
| `/browse [dir]` | Open the file browser |
| `/search <query>` | Search the web |
| `/web <url> [question]` | Fetch and analyze a page |
| `/pdf <path>` | Load PDF text |
| `/data <path>` | Analyze CSV or JSON |
| `/image <path> [question]` | Ask Lumi about an image |
| `/voice [seconds]` | Record and transcribe voice into the prompt |

### Productivity

| Command | Description |
|---|---|
| `/remember <fact>` | Save a long-term memory |
| `/memory` | View stored memories |
| `/forget` | Remove memories |
| `/note add|list|search` | Notes |
| `/todo add|list|done|rm` | Todos |
| `/export` | Export the current chat |
| `/tokens` | Show token telemetry |
| `/context` | Show prompt/context usage |
| `/permissions [all|plugins]` | Show plugin permission info |
| `/plugins` | Show plugin status |

## Config

Provider keys live in:

```bash
~/Lumi/.env
```

Example:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
HF_TOKEN=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
AIRFORCE_API_KEY=
POLLINATIONS_API_KEY=
```

Useful runtime overrides:

```env
LUMI_HOME=~/Lumi
LUMI_STATE_DIR=~/.codex/memories/lumi/state
LUMI_CACHE_DIR=~/.codex/memories/lumi/cache
```

Optional model picker allowlists (`/model` will only show these when set):

```env
LUMI_GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-pro
LUMI_HUGGINGFACE_MODELS=meta-llama/Llama-3.3-70B-Instruct
# optional global fallback
LUMI_ALLOWED_MODELS=gemini-2.5-flash
```

After changing `.env`, run:

```text
/doctor
```

`/model` only shows providers that are configured in your current `.env`.

## Project Context

If a repo contains `LUMI.md`, Lumi loads it as project context.

Example:

```markdown
# Project Context

## Stack
Python 3.11, FastAPI, PostgreSQL

## Conventions
- Type hints everywhere
- Use pytest
- Keep functions small
```

## Plugins

Plugins live in:

```bash
~/Lumi/plugins/
```

Plugin loading is approval-based:

- Lumi scans plugin files before import
- plugins must declare `PLUGIN_META`
- plugins are not imported until approved
- changing a plugin file invalidates its approval
- runtime dispatches are logged under `~/.codex/memories/lumi/state/plugins/`

Useful commands:

```text
/plugins inspect
/plugins pending
/plugins approve <name>
/plugins revoke <name>
/plugins audit
/permissions all
```

Minimal plugin example:

```python
PLUGIN_META = {
    "name": "Greeter",
    "version": "0.1.0",
    "description": "Simple greeting helper",
    "permissions": ["read_workspace"],
}

DESCRIPTION = {"/greet": "Say hello"}

def greet(args, client, model, memory, system_prompt, name):
    return f"hello {args or 'there'}"

COMMANDS = {"/greet": greet}
```

## Benchmarks

Lumi includes a benchmark harness for agent work.

It measures real outcomes rather than summary text alone:

- temp workspaces per scenario
- setup files per scenario
- expected file and patch outcomes
- optional verification commands
- changed-file tracking

Use:

```text
/benchmark
```

## Development

```bash
git clone https://github.com/SardorchikDev/Lumi.git ~/Lumi
cd ~/Lumi
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Checks:

```bash
pytest tests -q
ruff check .
ruff format .
python scripts/benchmark_gate.py --config configs/benchmark_gate.json
```

## License

[MIT](LICENSE)
