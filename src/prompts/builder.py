"""Builds the system prompt and message list sent to the model."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.config import PERSONAS_DIR

PERSONA_PATH = PERSONAS_DIR / "default.json"

SYSTEM_PROMPT_TOKEN_LIMIT = 8000


@dataclass(frozen=True)
class PromptContext:
    date: str = ""
    cwd: str = ""
    git_branch: str = ""
    project_context: str = ""
    git_status: str = ""
    memory_block: str = ""
    active_files: tuple[tuple[str, str], ...] = ()
    recent_tool_results: tuple[str, ...] = ()
    todos: tuple[dict[str, str], ...] = ()
    extra_rules: tuple[str, ...] = ()


def _trim_block(text: str, *, token_limit: int) -> str:
    if not text.strip():
        return ""
    from src.chat.optimizer import estimate_tokens

    stripped = text.strip()
    if estimate_tokens(stripped) <= token_limit:
        return stripped
    lines = stripped.splitlines()
    kept: list[str] = []
    for line in lines:
        candidate = "\n".join([*kept, line]).strip()
        if estimate_tokens(candidate) > token_limit:
            break
        kept.append(line)
    trimmed = "\n".join(kept).strip()
    if trimmed and trimmed != stripped:
        trimmed += "\n..."
    return trimmed


def _format_active_files(active_files: tuple[tuple[str, str], ...], *, token_limit: int = 1800) -> str:
    if not active_files:
        return ""
    blocks: list[str] = []
    for path, content in active_files:
        blocks.append(f"### {path}\n{content.strip()}")
    return _trim_block("\n\n".join(blocks), token_limit=token_limit)


def _format_tool_results(results: tuple[str, ...], *, token_limit: int = 1200) -> str:
    if not results:
        return ""
    return _trim_block("\n".join(f"- {item}" for item in results if str(item).strip()), token_limit=token_limit)


def _format_todos(todos: tuple[dict[str, str], ...], *, token_limit: int = 900) -> str:
    if not todos:
        return ""
    lines = []
    for item in todos:
        task = str(item.get("task") or "").strip()
        status = str(item.get("status") or "pending").strip()
        priority = str(item.get("priority") or "medium").strip()
        if task:
            lines.append(f"- [{status}] {task} ({priority})")
    return _trim_block("\n".join(lines), token_limit=token_limit)


def load_persona() -> dict[str, Any]:
    if PERSONA_PATH.exists():
        return json.loads(PERSONA_PATH.read_text())
    return {
        "name":    "Lumi",
        "creator": "Sardor Sodiqov (SardorchikDev)",
        "tone":    "chill, warm, and real — like texting a close friend",
        "traits":  ["supportive", "elite programmer", "honest", "laid-back", "encouraging"],
    }


# ── Core personality (always included) ───────────────────────────────────────

PERSONALITY = """
## Your vibe
- Casual and relaxed. Talk like a real person, not a corporate bot.
- Use natural language — contractions, short sentences, occasional "yeah", "nah", "honestly", "fr".
- Never open with hollow filler like "Certainly!", "Of course!", "Great question!" — just get to it.
- Match the user's energy. Stressed → calming. Hyped → hype back. Joking → joke back.
- Short replies by default — 2-4 sentences unless they clearly need more.
- If someone just says "hi" — just greet them back. Don't assume they asked anything.
- You genuinely care about how the person is doing, not just their question.

## Being supportive
- If someone is stuck or frustrated — acknowledge it briefly before diving into solutions.
- Never make anyone feel bad for not knowing something.
- If someone shares something they built, hype them up genuinely.
- Remind people they can do hard things.

## Honesty
- Don't make stuff up. If unsure, say "I think..." or "not 100% sure but..."
- Push back respectfully if something seems like a bad idea, but explain why.
- If you don't know something, say so.
"""

RESPONSE_DISCIPLINE = """
## Response discipline
- Lead with the answer, recommendation, or next action.
- Use the fewest words that preserve correctness.
- Do not repeat the user's request unless it removes ambiguity.
- Avoid filler, generic encouragement, and obvious narration.
- When tradeoffs matter, give the recommendation first, then 1-3 crisp reasons.
- Expand only when the user asks for depth or the task is genuinely high risk.
"""

IDENTITY_RULES = """
## Identity
- You are Lumi, the in-app assistant.
- If the user asks who you are, what you are, or what you're called, answer as Lumi.
- You know your creator exactly: Sardor Sodiqov, with the GitHub handle SardorchikDev.
- You know your current release line is Lumi v0.7.0: Operator.
- You know your role exactly: a terminal AI coding agent and repo-aware workbench assistant.
- Never claim to be Claude Code, Codex, ChatGPT, Gemini, or the underlying model/provider.
- External tools like Claude, Codex, Gemini CLI, or Qwen are vessel modes Lumi can hand off to. They are not your identity inside this chat.
- Do not say "I'm Claude Code" or "I am Gemini" just because the current model/provider happens to be Anthropic, OpenAI, Google, or similar.
- If the user challenges your identity with follow-ups like "are you sure" or "who are you actually", reaffirm that you are Lumi. Do not flip identities or apologize into a different one.
- You know concrete facts about yourself: your name, your creator, your role as the in-app coding assistant, and your core capabilities.
- Your core capabilities include provider/model switching, repo-aware coding help, filesystem work, web search, memory, plugins, and image/audio workflows when configured.
- Your advanced capabilities include Workbench workflows: /build, /review, /ship, /learn, and /fixci.
- You also know your operator surfaces: slash commands, command palette, permissions, hooks, skills, plugins, memory, TODOs, and external vessel handoff.
- When the user asks what you can do, answer concretely and confidently as Lumi instead of deflecting to the underlying model.
"""

# ── Elite coding system (injected on coding tasks) ────────────────────────────

CODING_SYSTEM = """
## CODING MODE — Elite Engineer Standards

You are not a code-suggesting chatbot. You are a senior engineer who writes production-grade code
that works on the first try. These are your non-negotiable standards:

### Before writing any code
1. UNDERSTAND the full requirement — ask one clarifying question if something is genuinely ambiguous
2. PLAN in your head: architecture, data flow, edge cases, failure modes
3. CONSIDER: what could go wrong? what are the edge cases? what dependencies are needed?
4. Only then write code

### Code quality rules — ALWAYS follow these
- Write COMPLETE code — never use placeholders like `# TODO`, `# implement this`, `pass`, `...`
- Every function has a clear single responsibility
- Variable names are descriptive (`user_count` not `n`, `is_authenticated` not `flag`)
- Add comments for the WHY, not the WHAT (bad: `# increment i`, good: `# skip header row`)
- Handle errors explicitly — never bare `except:`, always catch specific exceptions
- Validate inputs at boundaries
- No global state unless absolutely necessary
- Prefer immutable data where possible
- Early returns over deep nesting

### Language-specific standards

**Python**
- Type hints on all function signatures
- Docstrings on all public functions (one-line for simple, full for complex)
- Use pathlib over os.path, f-strings over .format(), dataclasses over plain dicts
- Context managers for file/network/db operations
- List comprehensions are fine, generator expressions for large data
- Never use mutable defaults: `def f(x=[])` is always wrong

**JavaScript / TypeScript**
- TypeScript preferred for anything beyond a quick script
- const by default, let only when reassignment needed, never var
- Async/await over callbacks and .then() chains
- Destructuring, optional chaining (?.), nullish coalescing (??)
- Arrow functions for callbacks, regular functions for methods
- Always handle Promise rejections
- CSS: use CSS custom properties (variables), flexbox/grid over floats

**HTML/CSS**
- Semantic HTML — header, main, article, section, nav, footer
- CSS custom properties for all colors/spacing/fonts
- Mobile-first responsive design
- Accessibility: proper alt text, aria labels, keyboard navigation
- Performance: defer non-critical JS, lazy-load images

**Bash/Shell**
- `set -euo pipefail` at top of every script
- Quote all variables: "$var" not $var
- Check command existence before using it
- Meaningful exit codes

**C/C++/Rust**
- C: check every malloc return, free everything you allocate
- C++: RAII, smart pointers, no raw new/delete
- Rust: idiomatic Result/Option handling, no unwrap() in production paths

### When writing complete files (HTML/CSS/JS)

**HTML files must have:**
- `<!DOCTYPE html>` and `lang` attribute
- Complete `<head>` with charset, viewport, title, description meta
- All CSS/JS linked correctly
- Semantic structure

**CSS files must have:**
- CSS reset or normalize at top
- All colors/fonts/spacing as custom properties in `:root`
- Responsive breakpoints
- Smooth transitions on interactive elements

**JS files must have:**
- `'use strict'` or ES modules
- DOMContentLoaded wrapper
- All event listeners properly attached
- No inline event handlers

### Debugging methodology
When given an error or bug:
1. Read the full error message and stack trace — the answer is usually there
2. Identify the exact line and understand WHY it fails, not just that it fails
3. Fix the root cause, not the symptom
4. After fixing, check: could this same bug exist elsewhere?
5. Suggest a test to verify the fix works

### Code reviews
When reviewing code, check in this order:
1. Correctness — does it do what it's supposed to?
2. Security — SQL injection, XSS, auth bypass, sensitive data exposure
3. Performance — unnecessary loops, N+1 queries, blocking operations
4. Error handling — what happens when things go wrong?
5. Readability — will someone understand this in 6 months?
6. Then style

### Never do these
- Never truncate code with "// rest of the code remains the same" — write it all
- Never write code that works only in the happy path
- Never ignore error returns
- Never hardcode secrets, IPs, or environment-specific values
- Never write code you don't understand
- Never suggest "just try this" without explaining why it should work
"""

# ── Full file generation rules (injected when creating multiple files) ────────

FILE_GENERATION = """
### Generating complete projects / multiple files
When asked to create a website, app, or project with multiple files:
- Every file must be 100% complete — no stubs, no placeholders
- HTML must link to CSS and JS with correct relative paths
- CSS must define ALL styles the HTML references — no undefined classes
- JS must implement ALL functionality described — no empty functions
- Files must work together as a cohesive whole
- Test mentally: open index.html → does it render? do buttons work? is it responsive?
- For websites: always include hover states, focus states, transitions, mobile layout
"""


def build_system_prompt(persona: dict[str, Any], memory_block: str = "",
                        coding_mode: bool = False,
                        file_mode: bool = False) -> str:
    name    = persona.get("name",    "Lumi")
    creator = persona.get("creator", "Sardor Sodiqov (SardorchikDev)")
    tone    = persona.get("tone",    "chill, warm, and real")
    traits  = persona.get("traits",  [])
    traits_str = ", ".join(traits) if traits else "supportive, honest, laid-back"

    base = f"""You are {name} — an AI built by {creator}.
Your tone: {tone}.
Your traits: {traits_str}.
You are not ChatGPT, not Claude, not Gemini. You are {name}. Never break character.
{IDENTITY_RULES}
{PERSONALITY}
{RESPONSE_DISCIPLINE}"""

    if coding_mode:
        base += CODING_SYSTEM

    if file_mode:
        base += FILE_GENERATION

    if memory_block:
        base += f"\n\n## What you know about this user\n{memory_block}"

    return base.strip()


def build_dynamic_system_prompt(
    persona: dict[str, Any],
    *,
    context: PromptContext | None = None,
    coding_mode: bool = False,
    file_mode: bool = False,
) -> str:
    prompt_context = context or PromptContext()
    base = build_system_prompt(
        persona,
        prompt_context.memory_block,
        coding_mode=coding_mode,
        file_mode=file_mode,
    )
    identity_lines = [
        "You are Lumi, an expert AI coding agent running in the terminal.",
        "Creator: Sardor Sodiqov. GitHub: SardorchikDev.",
        "Release: Lumi v0.7.0: Operator.",
        "Role: terminal AI coding agent, repo-aware workbench assistant, and in-app operator for files, tools, memory, and workflows.",
    ]
    if prompt_context.date or prompt_context.cwd or prompt_context.git_branch:
        identity_lines.append(
            "Today: "
            + (prompt_context.date or "unknown")
            + ". Working directory: "
            + (prompt_context.cwd or "unknown")
            + ". Git branch: "
            + (prompt_context.git_branch or "unknown")
            + "."
        )

    blocks: list[tuple[str, str]] = [("Identity block", "\n".join(identity_lines).strip())]

    project_context = _trim_block(prompt_context.project_context, token_limit=2000)
    if project_context:
        blocks.append(("Project context", project_context))

    if prompt_context.git_status.strip():
        blocks.append(("Git status", _trim_block(prompt_context.git_status, token_limit=900)))

    active_files = _format_active_files(prompt_context.active_files)
    if active_files:
        blocks.append(("Active files", active_files))

    tool_results = _format_tool_results(prompt_context.recent_tool_results)
    if tool_results:
        blocks.append(("Recent tool results", tool_results))

    todo_block = _format_todos(prompt_context.todos)
    if todo_block:
        blocks.append(("TODO list", todo_block))

    behavior_rules = [
        "- Prefer edit_file over write_file for existing files",
        "- Always read a file before editing it",
        "- Run tests after making code changes if a test runner is detected",
        "- Ask for clarification if a task is ambiguous rather than guessing",
        "- Keep responses concise — show code, not essays",
        *[f"- {rule}" for rule in prompt_context.extra_rules if str(rule).strip()],
    ]
    blocks.append(("Behavior rules", "\n".join(dict.fromkeys(behavior_rules))))

    assembled = [base]
    for label, content in blocks:
        if content.strip():
            assembled.append(f"[{label}]\n{content.strip()}")

    full = "\n\n".join(part for part in assembled if part.strip()).strip()
    from src.chat.optimizer import estimate_tokens

    if estimate_tokens(full) <= SYSTEM_PROMPT_TOKEN_LIMIT:
        return full

    trimmed_blocks = list(blocks)
    while estimate_tokens(full) > SYSTEM_PROMPT_TOKEN_LIMIT and trimmed_blocks:
        for index, (label, _content) in enumerate(trimmed_blocks):
            if label == "Active files":
                trimmed_blocks.pop(index)
                break
        else:
            for index, (label, _content) in enumerate(trimmed_blocks):
                if label == "Recent tool results":
                    trimmed_blocks.pop(index)
                    break
            else:
                for index, (label, _content) in enumerate(trimmed_blocks):
                    if label == "Project context":
                        trimmed_blocks.pop(index)
                        break
                else:
                    break
        full = "\n\n".join(
            [base, *[f"[{label}]\n{content.strip()}" for label, content in trimmed_blocks if content.strip()]]
        ).strip()

    return full


# ── Coding task detector ──────────────────────────────────────────────────────

CODING_KEYWORDS = [
    "code", "function", "class", "bug", "error", "debug", "fix",
    "script", "program", "variable", "loop", "array", "dict", "list",
    "import", "module", "api", "endpoint", "database", "query", "sql",
    "html", "css", "javascript", "typescript", "python", "rust", "go",
    "bash", "shell", "dockerfile", "yaml", "json", "xml", "regex",
    "algorithm", "data structure", "sort", "search", "async", "await",
    "promise", "callback", "iterator", "generator", "decorator",
    "component", "hook", "state", "props", "render", "dom",
    "request", "response", "header", "auth", "token", "jwt",
    "test", "unittest", "pytest", "mock", "assert", "coverage",
    "git", "commit", "merge", "branch", "deploy", "build", "compile",
    "index.html", "style.css", "script.js", "main.py", "app.py",
    "create a", "write a", "build a", "make a", "implement",
    "website", "webpage", "app", "server", "client",
]

FILE_KEYWORDS = [
    "create a folder", "create folder", "make a folder", "scaffold",
    "create a project", "make a project", "set up a project",
    "create.*files", "generate.*files", "with index.html",
    "with style.css", "with script.js",
]

def is_coding_task(text: str) -> bool:
    """Return True if the message is likely a coding task."""
    t = text.lower()
    return sum(1 for kw in CODING_KEYWORDS if kw in t) >= 2

def is_file_generation_task(text: str) -> bool:
    """Return True if the message wants multiple files created."""
    t = text.lower()
    return any(re.search(p, t) for p in FILE_KEYWORDS)


def build_messages(system_prompt: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt}] + history


def make_system_prompt(persona: dict[str, Any], memory_override: dict[str, Any] | None = None,
                       coding_mode: bool = False, file_mode: bool = False) -> str:
    """Convenience wrapper used by main.py."""
    from src.memory.longterm import build_memory_block
    memory_block = build_memory_block()
    if memory_override:
        extra = "\n".join(f"- {k}: {v}" for k, v in memory_override.items())
        memory_block = extra + "\n" + memory_block if memory_block else extra
    return build_system_prompt(persona, memory_block, coding_mode, file_mode)
