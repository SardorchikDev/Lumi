# Contributing to Lumi AI

Thanks for your interest in contributing to Lumi! This guide will help you get set up and productive quickly.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/SardorchikDev/Lumi.git
cd Lumi
python3 -m venv venv
source venv/bin/activate

# Install dependencies (including dev tools)
pip install -r requirements.txt
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install
```

## Development Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines below.

3. **Run the checks** before committing:
   ```bash
   # Lint
   ruff check .

   # Format
   ruff format .

   # Tests
   pytest tests/ -v

   # Benchmark gate (offline contract checks)
   python scripts/benchmark_gate.py --config configs/benchmark_gate.json

   # Rebirth capability audit
   python scripts/rebirth_audit.py --strict
   ```

4. **Commit and push**:
   ```bash
   git add <files>
   git commit -m "feat: description of your change"
   git push origin feature/your-feature-name
   ```

5. **Open a Pull Request** against `main`.

## Code Style

- **Python 3.10+** — use modern syntax (`X | Y` unions, `match` statements where appropriate)
- **Type hints** on all public function signatures
- **Docstrings** on all public functions (one-liner for simple, Google-style for complex)
- **Ruff** for linting and formatting — configuration is in `pyproject.toml`
- Follow existing patterns in the codebase

## Project Structure

```
main.py              — CLI entry point and interactive loop
src/
  tui/app.py         — Full TUI renderer
  chat/hf_client.py  — Unified multi-provider API client
  agents/            — Autonomous agent and council system
  memory/            — Short-term, long-term, and session storage
  prompts/           — System prompt construction
  tools/             — Web search, MCP, RAG, voice
  utils/             — Themes, markdown, intelligence, filesystem, etc.
tests/               — Unit and integration tests
configs/             — YAML configuration
data/                — Runtime data (memory, sessions, personas)
```

## Writing Tests

- Tests live in `tests/` and follow the `test_*.py` naming convention
- Use `pytest` fixtures for shared setup
- Mock external API calls — never make real API requests in unit tests
- Aim for coverage on core logic (memory, prompts, utils)

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_memory.py -v
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or updating tests
- `chore:` — maintenance (deps, CI, tooling)

## Adding a New Provider

1. Add the model list to `src/chat/hf_client.py`
2. Add the provider config to `_make_client()` and `get_models()`
3. Add an agent entry in `src/agents/council.py` if it should participate in Council mode
4. Update the README provider table

## Adding a New Slash Command

1. Add the handler function in `main.py` (e.g., `cmd_yourcommand()`)
2. Add it to the command dispatch in the `main()` loop
3. Add it to `print_help()` under the appropriate section
4. Update the README command reference table

## Questions?

Open an issue or start a discussion on GitHub. We're happy to help!
