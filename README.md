<h1 align="center">Lumi - rebirth</h1>

<p align="center">
  Keyboard-first AI terminal for coding, repo work, grounded agent tasks, and multimodal context.
</p>

<p align="center">
  <strong>Minimal surface. Heavyweight workflow.</strong>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#what-lumi-does">What Lumi Does</a> ·
  <a href="#tui">TUI</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#development">Development</a>
</p>

<p align="center">
  <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/SardorchikDev/Lumi/ci.yml?branch=main&style=flat-square&label=ci">
  <img alt="License" src="https://img.shields.io/github/license/SardorchikDev/Lumi?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-0f1720?style=flat-square">
  <img alt="Interface" src="https://img.shields.io/badge/interface-TUI%20%2B%20CLI-10322c?style=flat-square">
</p>

> Repo-aware terminal AI that stays sharp, grounded, and fast enough to live in your shell full time.

<table>
  <tr>
    <td width="50%" valign="top">
      <strong>Prompt-first TUI</strong><br>
      Claude-style top rail, command palette, model picker, shortcuts overlay, review cards, and inline approval flows.
    </td>
    <td width="50%" valign="top">
      <strong>Grounded Agent Mode</strong><br>
      Structured action plans, rollback-aware file edits, verification passes, and benchmarked filesystem tasks.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <strong>Model Control</strong><br>
      Boots into Gemini 2.5 Flash when Gemini is configured, supports `/effort`, and only shows configured providers in `/model`.
    </td>
    <td width="50%" valign="top">
      <strong>Real Context</strong><br>
      Web, files, images, PDFs, data, voice, notes, todos, and long-term memory all feed back into the same workflow.
    </td>
  </tr>
</table>

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/Lumi/main/install.sh | bash
```

Useful variants:

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/Lumi/main/install.sh | bash -s -- --dev
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/Lumi/main/install.sh | bash -s -- --dir ~/apps/Lumi
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/Lumi/main/install.sh | bash -s -- --help
```

The installer:

- clones Lumi into `~/Lumi`
- creates `venv`
- installs dependencies
- creates a `lumi` launcher in `~/.local/bin`
- creates `~/Lumi/.env` if it does not exist
- initializes runtime state under `~/.codex/memories/lumi`

## Quick Start

1. Add at least one provider key to `~/Lumi/.env`
2. Open a new shell or reload your shell config
3. Launch Lumi

```bash
lumi
```

Minimal `.env` example:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
HF_TOKEN=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
AIRFORCE_API_KEY=
POLLINATIONS_API_KEY=
```

Good first commands:

```text
/onboard
/doctor
/model
/rebirth
/status
```

Good first prompts:

```text
/agent add tests for this module
/review src/main.py
/git summary
/search latest FastAPI release notes
```

Useful launch flags:

```bash
lumi --no-tui
lumi --yolo
```

## What Lumi Does

- full-screen TUI plus classic CLI mode
- grounded agent mode with repo-aware planning, edits, verification, and rollback
- natural-language file and folder operations plus explicit `/fs` commands
- model switching, reasoning effort control, and strict provider-aware `/model` menus
- session memory, long-term memory, notes, todos, and task memory
- web, file, PDF, image, voice, and structured-data context helpers
- plugin loading with approval, trust checks, and permission reporting

## Default Behavior

When configured, Lumi starts with these defaults:

- provider preference: Gemini first
- startup model: `gemini-2.5-flash`
- startup effort: `medium`
- `/model` only shows configured providers
- `?` opens the shortcuts overlay when the prompt is empty

Optional model allowlists:

```env
LUMI_GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-pro
LUMI_HUGGINGFACE_MODELS=meta-llama/Llama-3.3-70B-Instruct
LUMI_ALLOWED_MODELS=gemini-2.5-flash
```

Useful runtime overrides:

```env
LUMI_HOME=~/Lumi
LUMI_STATE_DIR=~/.codex/memories/lumi/state
LUMI_CACHE_DIR=~/.codex/memories/lumi/cache
```

## TUI

Lumi's default interface is built around a prompt-first workflow:

- top welcome card and prompt rail
- dense transcript with compact `you` and `lumi` labels
- slash-command palette under the prompt
- model picker with provider filtering and Nerd Font icons
- boxed notifications and inline review blocks
- workspace trust prompt and closeable side panes

Useful keys:

- `?` shows shortcuts
- `/` opens the command menu
- `Ctrl+N` opens the model picker
- `Ctrl+G` toggles the starter card
- `Tab` accepts slash-command or path suggestions
- `Shift+Up` / `Shift+Down` scroll the transcript
- `Esc` closes transient UI and cancels pending file plans

## Common Workflows

### Agent Work

```text
/agent add login validation and tests
/review src/auth.py
/fix type errors in src/api
```

### File Operations

Lumi understands direct natural-language file tasks:

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

Use Lumi to pull context directly into the conversation:

- `/file <path>`
- `/project <dir>`
- `/browse [dir]`
- `/search <query>`
- `/web <url> [question]`
- `/pdf <path>`
- `/data <path>`
- `/image <path> [question]`
- `/voice [seconds]`

## Commands

### Core

| Command | Description |
|---|---|
| `/model` | Switch provider and model |
| `/effort [low\|medium\|high\|ehigh]` | Set reasoning effort |
| `/clear` | Clear the current conversation |
| `/status` | Show session and workspace status |
| `/doctor` | Check provider and workspace health |
| `/rebirth` | Show capability matrix and apply rebirth defaults |
| `/benchmark` | Show benchmark scenarios |
| `/exit` | Exit Lumi |

### Chat and Writing

| Command | Description |
|---|---|
| `/council <prompt>` | Ask council mode |
| `/retry` | Retry the last prompt |
| `/more` | Expand the last answer |
| `/rewrite` | Rewrite the last answer |
| `/tl;dr` | Summarize the last answer |
| `/short` | Make the next answer concise |
| `/detailed` | Make the next answer detailed |
| `/bullets` | Make the next answer bullet-based |

### Code and Context

| Command | Description |
|---|---|
| `/agent <task>` | Run grounded agent mode |
| `/review [file]` | Review code |
| `/fix <problem>` | Diagnose and fix an issue |
| `/debug <problem>` | Debug a failure |
| `/file <path>` | Load a file into context |
| `/project <dir>` | Load a project into context |
| `/search <query>` | Search the web |
| `/image <path> [question]` | Ask Lumi about an image |
| `/voice [seconds]` | Record and transcribe voice into the prompt |

### Productivity

| Command | Description |
|---|---|
| `/remember <fact>` | Save a long-term memory |
| `/memory` | View stored memories |
| `/note add\|list\|search` | Manage notes |
| `/todo add\|list\|done\|rm` | Manage todos |
| `/plugins` | Show plugin status |
| `/permissions [all\|plugins]` | Show plugin permission info |

## Rebirth Profile

Use `/rebirth` to view the capability matrix and readiness score for core coding-agent workflows.

Use `/rebirth on` to apply the rebirth defaults:

- detailed response mode
- compact mode off
- guardian watcher on

## Plugins

Plugins live in `~/Lumi/plugins/` and are approval-based:

- Lumi scans plugin files before import
- plugins must declare `PLUGIN_META`
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

## Benchmarks and CI

Lumi includes a benchmark harness for grounded agent work:

- temporary workspaces per scenario
- scenario setup files and expected outcomes
- verification-command support
- changed-file tracking and recovery metrics
- CI regression gate via `scripts/benchmark_gate.py`

Use:

```text
/benchmark
```

## Project Context

If a repo contains `LUMI.md`, Lumi loads it automatically as project context.

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
python scripts/rebirth_audit.py --strict
```

## License

[MIT](LICENSE)
