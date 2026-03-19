# lumi

Minimal terminal AI for coding, repo work, file management, and agent tasks.

```text
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

[Install](#install) · [Quick Start](#quick-start) · [What Lumi Does](#what-lumi-does) · [Agent Mode](#agent-mode) · [Commands](#commands) · [Plugins](#plugins) · [Development](#development) · [Roadmap](ROADMAP.md)

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

## Quick Start

1. Add at least one provider key to `~/Lumi/.env`
2. Open a new shell or reload your shell config
3. Run:

```bash
lumi
```

Recommended first steps inside Lumi:

```text
/onboard
/doctor
/model
/status
```

Useful first prompts:

```text
/agent add tests for this module
/review src/main.py
/git status
/search latest FastAPI release notes
```

If you want the classic non-TUI mode:

```bash
lumi --no-tui
```

If you want to skip confirmations:

```bash
lumi --yolo
```

## What Lumi Does

- terminal chat with a full-screen TUI and classic CLI mode
- council mode for multi-model answers
- grounded agent mode with structured actions, previews, and rollback
- natural-language file and folder operations
- repo-aware workflows with git helpers, project context, and session memory
- cached web, file, PDF, image, and data context
- local notes, todos, saved sessions, and long-term memory
- optional plugins with explicit approval

## TUI

The default interface is a minimal terminal UI built for keyboard-first use:

- stable prompt and transcript layout
- slash-command picker
- prompt history
- transcript scrolling
- side pane support
- starter panel with recent commands and actions
- confirmation flow for file operations

Useful keys:

- `Esc` closes transient UI and cancels pending file plans
- `Ctrl+G` toggles the starter panel
- `Up` / `Down` navigate prompt history
- `Shift+Up` / `Shift+Down` scroll the transcript
- `Tab` accepts slash-command or path suggestions

## Agent Mode

Lumi agent mode is built around structured actions, not arbitrary shell execution.

Current agent capabilities include:

- inspect the repo before acting
- read files and search code
- create folders and structured files
- patch files with previews
- run repo-aware verification
- show grouped preflight summaries
- roll back file mutations on failure

Typical agent flow:

1. inspect workspace and relevant files
2. build a grounded plan
3. show preflight summary
4. preview edits
5. execute
6. verify
7. roll back if the run fails

Example:

```text
/agent add login validation and tests
```

## File Workflows

Lumi can handle natural-language file operations directly in chat, and you can also use `/fs`.

Examples:

```text
create a folder named api and add main.py inside it
delete the folder docs
rename app.py to main.py
move config.yaml into app/config
```

Useful slash commands:

- `/fs ls [path]`
- `/fs cat <file>`
- `/fs mkdir <dir>`
- `/fs mv <src> <dst>`
- `/fs rm <path>`
- `/fs write <file> [text]`
- `/fs append <file> [text]`
- `/undo`

## Git Workflows

Lumi includes git helpers inside the TUI:

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
HF_TOKEN=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
AIRFORCE_API_KEY=
POLLINATIONS_API_KEY=
```

Lumi can also work with local providers like Ollama depending on your setup.

After changing `.env`, run:

```text
/doctor
```

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

Plugin loading is approval-based now:

- Lumi scans plugin files before import
- plugins must declare `PLUGIN_META`
- plugins are not imported until approved
- changing a plugin file invalidates its approval

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

Lumi includes a small benchmark harness for agent work.

It now scores real outcomes instead of summary text only:

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
```

## License

[MIT](LICENSE)
