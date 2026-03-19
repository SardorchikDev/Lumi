# lumi

Minimal terminal AI with a council mode, grounded agent mode, memory, and a cleaner TUI.

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

[Install](#install) · [Quick Start](#quick-start) · [Modes](#modes) · [Commands](#commands) · [Config](#config) · [Development](#development) · [Roadmap](ROADMAP.md)

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash
```

The installer:
- clones Lumi into `~/Lumi`
- creates a virtual environment
- installs dependencies
- creates a `lumi` launcher in `~/.local/bin`
- creates `~/Lumi/.env` if it does not exist

## Quick Start

1. Add at least one API key to `~/Lumi/.env`
2. Reload your shell or open a new terminal
3. Run:

```bash
lumi
```

Useful first commands:

```bash
/model
/council explain async vs threads
/agent add tests for this module
/search latest FastAPI release notes
```

## What Lumi Does

- Interactive terminal chat with TUI and classic CLI modes
- Council mode that asks multiple models in parallel and synthesizes a response
- Grounded agent mode with structured actions, preflight checks, diff previews, and rollback support
- Long-term memory, saved sessions, notes, and todos
- File loading, project context, web search, PDF/image/data helpers
- MCP server support and a simple plugin system

## Modes

### TUI

The default interface is a minimal full-screen terminal UI with:
- compact status bar
- prompt history
- transcript scrolling
- code block rendering
- slash-command picker
- optional side pane output

If you want the classic CLI instead:

```bash
lumi --no-tui
```

### Council

Council mode asks the available council agents in parallel, then returns a synthesized answer.

```bash
lumi --model council
```

Or inside Lumi:

```bash
/council explain Rust ownership simply
```

### Agent

Agent mode is built around structured actions rather than arbitrary shell execution.

Current safe actions include:
- `list_dir`
- `read_file`
- `search_code`
- `mkdir`
- `write_json`
- `patch_file`
- `patch_lines`
- `run_tests`
- `run_ruff`
- `run_mypy`
- `git_status`
- `git_diff`

Typical flow:
- inspect workspace
- build grounded plan
- show preflight summary
- preview file changes
- execute
- roll back file mutations if the run fails

Use:

```bash
/agent add login validation and tests
```

Use `--yolo` if you want to skip confirmations:

```bash
lumi --yolo
```

## Commands

Core commands:

| Command | Description |
|---|---|
| `/model` | Pick provider and model |
| `/clear` | Clear the current chat |
| `/undo` | Remove the last exchange |
| `/save [name]` | Save the current session |
| `/load [name]` | Load a saved session |
| `/sessions` | List saved sessions |
| `/context` | Show context usage |
| `/quit` | Save and exit |

Chat and writing:

| Command | Description |
|---|---|
| `/council <prompt>` | Ask all council agents |
| `/redo [hint]` | Retry with a different angle |
| `/more` | Expand the last answer |
| `/tl;dr` | Summarize the last answer |
| `/rewrite` | Rewrite the last answer |
| `/short` | Shorter responses |
| `/detailed` | More detailed responses |
| `/bullets` | Bullet-style responses |

Code and files:

| Command | Description |
|---|---|
| `/agent <task>` | Grounded agent execution |
| `/file <path>` | Load a file into context |
| `/project <dir>` | Load a project into context |
| `/edit <path>` | AI-assisted file rewrite |
| `/review [file]` | Code review |
| `/fix <error>` | Diagnose and fix an error |
| `/test [file]` | Generate tests |
| `/run` | Run code from the last reply |
| `/git status|commit|log|remote|fetch|sync|branches` | Git helpers |

Search and tools:

| Command | Description |
|---|---|
| `/search <query>` | Search the web |
| `/web <url> [question]` | Fetch a page and analyze it |
| `/image <path> [question]` | Analyze an image |
| `/pdf <path>` | Analyze a PDF |
| `/data <path>` | Analyze CSV or JSON |
| `/pane <cmd>` | Open a side pane command |

Memory and productivity:

| Command | Description |
|---|---|
| `/remember <fact>` | Save a memory |
| `/memory` | View stored memories |
| `/forget` | Remove memories |
| `/note add|list|search` | Notes |
| `/todo add|list|done|rm` | Todos |
| `/export` | Export the current session |
| `/find <keyword>` | Search past sessions |

## Config

API keys live in:

```bash
~/Lumi/.env
```

Example:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
HF_TOKEN=
```

Lumi also supports additional providers and local models depending on your setup.

## Project Context

If a project contains a `LUMI.md`, Lumi loads it as project context.

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

You can create one with:

```bash
/lumi.md create
```

## Plugins

Drop a Python file into `~/Lumi/plugins/` and Lumi loads it on startup.

Minimal example:

```python
COMMANDS = {"/deploy": deploy}
DESCRIPTION = {"/deploy": "Deploy to staging"}

def deploy(args, client, model, memory, system_prompt, name):
    print("deploying...")
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
pytest tests/ -q
ruff check .
ruff format .
```

## License

[MIT](LICENSE)
