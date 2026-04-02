"""Grouped TUI command registrations extracted from the app monolith."""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from src.agents.benchmark import load_benchmark_scenarios, render_benchmark_catalog
from src.tui.review_cards import file_review_card
from src.tui.state import Msg
from src.utils.git_tools import GIT_USAGE, run_git_subcommand
from src.utils.system_reports import build_onboarding_report
from src.utils.workbench import WORKBENCH_TITLE, prepare_workbench_plan, render_workbench_plan, render_workbench_report

HELP_CATEGORIES = {
    "💬 Chat": ["/clear", "/retry", "/redo", "/undo", "/more", "/rewrite", "/tl;dr", "/summarize", "/translate", "/short", "/detailed", "/bullets", "/multi"],
    "🔧 Code": ["/build", "/review", "/learn", "/fixci", "/ship", "/fix", "/debug", "/explain", "/improve", "/optimize", "/security", "/refactor", "/test", "/docs", "/types", "/comment", "/run", "/edit"],
    "📁 Files": ["/file", "/browse", "/find", "/grep", "/tree", "/project", "/fs"],
    "🔀 Git": ["/git", "/pr", "/changelog", "/standup", "/readme"],
    "🌐 Web": ["/search", "/web", "/image", "/imagine", "/data"],
    "🧠 Memory": ["/remember", "/memory", "/forget", "/save", "/load", "/sessions", "/export", "/tokens", "/context"],
    "🛠️ Tools": ["/shell", "/scaffold", "/lint", "/fmt", "/todo", "/note", "/draft", "/weather", "/timer", "/copy", "/paste", "/diff", "/pdf", "/jobs"],
    "⚙️ System": ["/status", "/doctor", "/onboard", "/rebirth", "/benchmark", "/permissions", "/model", "/council", "/mode", "/offline", "/godmode", "/pane", "/apply", "/index", "/rag", "/voice", "/persona", "/sys", "/plugins", "/compact", "/help", "/exit"],
}


def _start_thread(worker) -> None:
    threading.Thread(target=worker, daemon=True).start()


def _finalize_stream(tui, raw: str, *, user_label: str | None = None) -> None:
    if user_label is not None:
        tui.memory.replace_last("user", user_label)
    tui.memory.add("assistant", raw)
    tui.last_reply = raw
    tui.turns += 1
    tui.redraw()


def _run_memory_prompt(tui, prompt: str, spinner_label: str, *, build_messages, user_label: str | None = None) -> None:
    try:
        tui.set_busy(True)
        tui.memory.add("user", prompt)
        msgs = build_messages(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(msgs, tui.current_model, spinner_label)
        _finalize_stream(tui, raw, user_label=user_label)
    except Exception as exc:
        tui._err(str(exc))
    finally:
        tui.set_busy(False)
        tui.redraw()


def _resolve_content_target(tui, arg: str, read_file, *, missing_error: str, label_prefix: str = "File") -> str | None:
    target = arg.strip() if arg.strip() else None
    if target and Path(target).expanduser().exists():
        try:
            path = Path(target).expanduser()
            return f"{label_prefix} `{path.name}`:\n\n```\n{read_file(target)}\n```"
        except Exception as exc:
            tui._err(str(exc))
            return None
    if tui.last_reply:
        return tui.last_reply
    tui._err(missing_error)
    return None


def _project_file_snapshot(target: Path, limit: int = 30) -> list[tuple[str, str]]:
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".md", ".toml", ".yaml", ".yml", ".json", ".sh"}
    files = [
        path
        for path in target.rglob("*")
        if path.is_file()
        and path.suffix in exts
        and ".git" not in str(path)
        and "node_modules" not in str(path)
    ][:limit]
    parts: list[tuple[str, str]] = []
    for path in files:
        try:
            parts.append((str(path.relative_to(target)), path.read_text(errors="replace")[:3000]))
        except Exception:
            continue
    return parts


def _readme_structure(path: Path) -> str:
    lines: list[str] = []
    count = 0
    for candidate in sorted(path.rglob("*")):
        if count >= 40:
            break
        if ".git" in candidate.parts or "__pycache__" in candidate.parts or "node_modules" in candidate.parts:
            continue
        if candidate.is_file():
            try:
                lines.append(str(candidate.relative_to(path)))
                count += 1
            except Exception:
                continue
    return "\n".join(lines)


def _parse_workbench_arg(arg: str, *, default_objective: str) -> tuple[str, bool, bool]:
    parts = [part for part in arg.split() if part.strip()]
    dry_run = False
    plan_only = False
    filtered: list[str] = []
    for part in parts:
        if part in {"--dry-run", "--plan"}:
            dry_run = True
            plan_only = True
            continue
        filtered.append(part)
    objective = " ".join(filtered).strip() or default_objective
    return objective, dry_run, plan_only


def register_command_groups(
    registry,
    *,
    build_messages,
    read_file,
    context_cache,
    get_available_providers,
    log,
) -> dict[str, list[str]]:
    @registry.register("/benchmark", "Show the built-in benchmark suite")
    def cmd_benchmark(tui, arg: str):
        if arg.strip() not in {"", "list"}:
            tui._err("Usage: /benchmark [list]")
            return
        tui._sys(render_benchmark_catalog(load_benchmark_scenarios()))

    @registry.register("/comment", "Add inline comments to file")
    def cmd_comment(tui, arg: str):
        if not arg.strip():
            tui._err("Usage: /comment <filepath>")
            return
        path = Path(arg.strip()).expanduser()
        if not path.is_file():
            tui._err(f"Not found: {path}")
            return
        content = path.read_text(errors="replace")

        def _go():
            try:
                tui.set_busy(True)
                prompt = f"Add clear inline comments to this code. Return ONLY the commented code:\n\n```\n{content}\n```"
                msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
                tui.last_reply = tui._tui_stream(msgs, tui.current_model, f"commenting {path.name}")
            finally:
                tui.set_busy(False)

        _start_thread(_go)

    @registry.register("/git", f"Git: /git {GIT_USAGE}|commit|commit-confirm")
    def cmd_git(tui, arg: str):
        sub = arg.strip().split()[0] if arg.strip() else "status"
        if sub == "commit":
            diff = subprocess.run(["git", "diff", "--cached", "--stat"], capture_output=True, text=True).stdout
            if not diff.strip():
                diff = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True).stdout
            if not diff.strip():
                tui._err("No changes to commit")
                return

            def _go():
                try:
                    tui.set_busy(True)
                    prompt = f"Generate a concise commit message for:\n{diff}\nReturn ONLY the message."
                    msgs = [{"role": "system", "content": tui.system_prompt}, {"role": "user", "content": prompt}]
                    tui.last_reply = tui._tui_stream(msgs, tui.current_model, "git commit")
                finally:
                    tui.set_busy(False)

            _start_thread(_go)
            return

        if sub == "commit-confirm":
            subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
            if tui.last_reply:
                msg = tui.last_reply.strip().strip("`").strip()
                result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
                tui._sys(result.stdout.strip() or result.stderr.strip())
                return
            tui._err("Run /git commit first")
            return

        ok, output = run_git_subcommand(sub)
        tui._sys(output if ok else f"Usage: /git {GIT_USAGE}|commit|commit-confirm")

    @registry.register("/pdf", "Load PDF text into context")
    def cmd_pdf(tui, arg: str):
        if not arg.strip():
            tui._err("Usage: /pdf <path.pdf>")
            return
        tui._sys("PDF loading requires PyPDF2 — pip install PyPDF2")

    @registry.register("/project", "Load entire project into context")
    def cmd_project(tui, arg: str):
        target = Path(arg.strip() or ".").expanduser()
        if not target.is_dir():
            tui._err(f"Not a directory: {target}")
            return
        cached_parts = _project_file_snapshot(target)
        if not cached_parts:
            tui._sys("No recognizable source files found")
            return
        context_cache.remember_project(target, cached_parts)
        tui.memory.add("user", f"[project loaded: {target}] Cached project files for retrieval.")
        tui._sys(f"Loaded {len(cached_parts)} files from {target} into context")

    @registry.register("/help", "Show all commands organized by category")
    def cmd_help(tui, arg: str):
        lines = []
        for category, commands in HELP_CATEGORIES.items():
            lines.append(f"\n  {category}")
            for command in commands:
                data = registry.commands.get(command)
                if data:
                    desc = data["desc"][:52]
                    lines.append(f"    {command:<16} {desc}")
        lines.append(f"\n  {len(registry.commands)} commands available. Tab to autocomplete.")
        lines.append("\n  Shortcuts: Ctrl+N=model picker | Ctrl+L=clear | Ctrl+R=retry | Tab=complete")
        tui._sys("\n".join(lines))

    @registry.register("/build", "Workbench: inspect, edit, test, review, and prepare artifacts")
    def cmd_build(tui, arg: str):
        objective, dry_run, plan_only = _parse_workbench_arg(
            arg.strip(),
            default_objective="Implement the requested feature in this workspace.",
        )
        if plan_only:
            plan = prepare_workbench_plan("build", objective, dry_run=dry_run)
            tui.set_pane(
                title="build plan",
                subtitle=WORKBENCH_TITLE,
                lines=render_workbench_plan(plan).splitlines(),
                footer="Esc close  ·  /build <objective>",
                close_on_escape=True,
            )
            tui.redraw()
            return
        tui.launch_workbench("build", objective, dry_run=dry_run)
        tui._sys(f"Queued build job: {objective}")

    @registry.register("/learn", "Workbench: index the repo and explain architecture, impact, and conventions")
    def cmd_learn(tui, arg: str):
        objective, dry_run, plan_only = _parse_workbench_arg(
            arg.strip(),
            default_objective="Map the architecture, dependencies, and repo conventions.",
        )
        if plan_only:
            plan = prepare_workbench_plan("learn", objective, dry_run=dry_run)
            tui.set_pane(
                title="learn plan",
                subtitle=WORKBENCH_TITLE,
                lines=render_workbench_plan(plan).splitlines(),
                footer="Esc close  ·  /learn [topic]",
                close_on_escape=True,
            )
            tui.redraw()
            return
        tui.set_pane(
            title="workbench learn",
            subtitle=WORKBENCH_TITLE,
            lines=render_workbench_report(Path.cwd(), task=objective).splitlines(),
            footer="Esc close  ·  /learn --plan",
            close_on_escape=True,
        )
        tui.redraw()

    @registry.register("/ship", "Workbench: verify the repo and generate release artifacts")
    def cmd_ship(tui, arg: str):
        objective, dry_run, plan_only = _parse_workbench_arg(
            arg.strip(),
            default_objective="Prepare this workspace for release with artifacts and verification.",
        )
        if plan_only:
            plan = prepare_workbench_plan("ship", objective, dry_run=dry_run)
            tui.set_pane(
                title="ship plan",
                subtitle=WORKBENCH_TITLE,
                lines=render_workbench_plan(plan).splitlines(),
                footer="Esc close  ·  /ship",
                close_on_escape=True,
            )
            tui.redraw()
            return
        tui.launch_workbench("ship", objective, dry_run=dry_run)
        tui._sys("Queued ship job")

    @registry.register("/fixci", "Workbench: repair CI, lint, type, and test failures")
    def cmd_fixci(tui, arg: str):
        objective, dry_run, plan_only = _parse_workbench_arg(
            arg.strip(),
            default_objective="Investigate and repair failing CI, lint, type, or test issues.",
        )
        if plan_only:
            plan = prepare_workbench_plan("fixci", objective, dry_run=dry_run)
            tui.set_pane(
                title="fixci plan",
                subtitle=WORKBENCH_TITLE,
                lines=render_workbench_plan(plan).splitlines(),
                footer="Esc close  ·  /fixci [objective]",
                close_on_escape=True,
            )
            tui.redraw()
            return
        tui.launch_workbench("fixci", objective, dry_run=dry_run)
        tui._sys(f"Queued fixci job: {objective}")

    @registry.register("/jobs", "Show background Workbench jobs")
    def cmd_jobs(tui, arg: str):
        tui._refresh_workbench_pane()

    @registry.register("/fix", "Diagnose error and fix it")
    def cmd_fix(tui, arg: str):
        if not arg:
            tui._err("Usage: /fix <error message>")
            return

        def _go():
            ctx = f"\n\nContext:\n{tui.last_reply}" if tui.last_reply else ""
            msg = (
                f"I'm getting this error:\n\n```\n{arg}\n```{ctx}\n\n"
                "1. What's causing it\n2. The exact fix\n3. How to avoid it next time"
            )
            _run_memory_prompt(
                tui,
                msg,
                f"◆ {tui.name}  [fix]",
                build_messages=build_messages,
                user_label=f"/fix: {arg[:200]}",
            )

        _start_thread(_go)

    @registry.register("/debug", "Deep debug with root cause + test")
    def cmd_debug(tui, arg: str):
        def _go():
            error = arg or "the issue in the last message"
            ctx = f"\n\nLast reply:\n{tui.last_reply}" if tui.last_reply else ""
            msg = (
                f"Deep debug:\n\n```\n{error}\n```{ctx}\n\n"
                "1. Root cause\n2. Stack trace explanation\n"
                "3. Step-by-step fix\n4. Regression test\n5. Alternative approaches"
            )
            _run_memory_prompt(
                tui,
                msg,
                f"◆ {tui.name}  [debug]",
                build_messages=build_messages,
                user_label=f"/debug: {error[:200]}",
            )

        _start_thread(_go)

    @registry.register("/improve", "Improve code quality and readability")
    def cmd_improve(tui, arg: str):
        def _go():
            content = _resolve_content_target(
                tui,
                arg,
                read_file,
                missing_error="Nothing to improve. Pass a file path or ask something first.",
            )
            if not content:
                return
            msg = (
                "Improve this code. Fix bugs, improve readability, add error handling, "
                f"clean up style. Output the COMPLETE improved version:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [improve]", build_messages=build_messages, user_label="/improve")

        _start_thread(_go)

    @registry.register("/optimize", "Performance optimize with before/after")
    def cmd_optimize(tui, arg: str):
        def _go():
            content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to optimize.", label_prefix="File")
            if not content:
                return
            msg = (
                "Optimize for performance. Find bottlenecks, improve algorithmic complexity, "
                f"show before/after with estimates:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [optimize]", build_messages=build_messages, user_label="/optimize")

        _start_thread(_go)

    @registry.register("/security", "Security audit with severity ratings")
    def cmd_security(tui, arg: str):
        def _go():
            content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to audit.", label_prefix="File")
            if not content:
                return
            msg = (
                "Security audit. Find: injection, auth issues, data exposure, input validation gaps, "
                f"hardcoded secrets. Rate each critical/high/medium/low:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [security]", build_messages=build_messages, user_label="/security")

        _start_thread(_go)

    @registry.register("/refactor", "Refactor with SOLID principles")
    def cmd_refactor(tui, arg: str):
        def _go():
            content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to refactor.", label_prefix="File")
            if not content:
                return
            msg = (
                "Refactor using SOLID principles and design patterns. Reduce duplication, improve abstractions. "
                f"Output the complete refactored version with a brief explanation:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [refactor]", build_messages=build_messages, user_label="/refactor")

        _start_thread(_go)

    @registry.register("/test", "Generate pytest unit tests")
    def cmd_test(tui, arg: str):
        def _go():
            content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to test.", label_prefix="File")
            if not content:
                return
            msg = (
                "Write comprehensive pytest unit tests. Cover: happy path, edge cases, errors, "
                f"boundary conditions. Include fixtures and mocks where needed:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [tests]", build_messages=build_messages, user_label="/test")

        _start_thread(_go)

    @registry.register("/explain", "Explain code line by line")
    def cmd_explain(tui, arg: str):
        def _go():
            content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to explain.")
            if not content:
                return
            msg = (
                "Explain this code line by line. Walk through every function, why it's written that way, "
                f"and what a developer needs to understand:\n\n{content}"
            )
            _run_memory_prompt(tui, msg, f"◆ {tui.name}  [explain]", build_messages=build_messages, user_label="/explain")

        _start_thread(_go)

    @registry.register("/review", "Full code review with specifics")
    def cmd_review(tui, arg: str):
        review_target = arg.strip().lower()
        if (not arg.strip() and not tui.last_reply) or review_target in {"workspace", "repo", "workbench"}:
            objective = arg.strip() or "Review the current workspace changes, call out bugs, risks, and missing tests."
            tui.launch_workbench("review", objective, dry_run=True)
            tui._sys(f"Queued review job: {objective}")
            return

        def _go():
            path_arg = arg.strip()
            target_path = Path(path_arg).expanduser() if path_arg else None
            if target_path and target_path.exists() and target_path.is_file():
                card = file_review_card(target_path, mode="review")
                tui.set_review_card(
                    title=str(card["title"]),
                    summary_lines=list(card["summary_lines"]),
                    preview_lines=list(card["preview_lines"]),
                    footer=str(card["footer"]),
                )
            try:
                content = _resolve_content_target(tui, arg, read_file, missing_error="Nothing to review.")
                if not content:
                    return
                msg = (
                    "Thorough code review. Findings first. Cover: correctness, edge cases, performance, security, "
                    f"readability, maintainability. Be specific with line numbers and variable names:\n\n{content}"
                )
                _run_memory_prompt(tui, msg, f"◆ {tui.name}  [review]", build_messages=build_messages, user_label="/review")
            finally:
                tui.clear_review_card()

        _start_thread(_go)

    @registry.register("/scaffold", "Generate complete project scaffold")
    def cmd_scaffold(tui, arg: str):
        if not arg:
            tui._err("Usage: /scaffold <type>  e.g. fastapi, react, cli, flask")
            return

        def _go():
            msg = (
                f"Generate a complete, production-ready {arg} project scaffold. "
                "Full file contents — no placeholders, no TODOs. Include: folder structure, "
                "requirements/package.json, entry point, routes/components, README, .gitignore, tests."
            )
            _run_memory_prompt(
                tui,
                msg,
                f"◆ {tui.name}  [scaffold: {arg}]",
                build_messages=build_messages,
                user_label=f"/scaffold: {arg}",
            )

        _start_thread(_go)

    @registry.register("/readme", "Generate README for project/path")
    def cmd_readme(tui, arg: str):
        def _go():
            try:
                tui.set_busy(True)
                path = Path(arg.strip() or ".").expanduser()
                structure = _readme_structure(path) if path.exists() else ""
                main_code = ""
                for file_name in ("main.py", "app.py", "index.js", "src/main.py"):
                    candidate = path / file_name
                    if candidate.exists():
                        try:
                            main_code = f"\n\n{file_name}:\n```\n{candidate.read_text()[:2000]}\n```"
                        except Exception:
                            log.debug("Could not read main file for readme")
                        break
                msg = (
                    f"Generate a comprehensive README.md.\n\nFiles:\n{structure}{main_code}\n\n"
                    "Include: title, description, features, installation, usage, API docs, contributing, license."
                )
                tui.memory.add("user", msg)
                msgs = build_messages(tui.system_prompt, tui.memory.get())
                raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [README]")
                _finalize_stream(tui, raw, user_label="[readme]")
            except Exception as exc:
                tui._err(str(exc))
            finally:
                tui.set_busy(False)
                tui.redraw()

        _start_thread(_go)

    @registry.register("/pr", "Write PR description from git diff")
    def cmd_pr(tui, arg: str):
        def _go():
            try:
                tui.set_busy(True)
                diff_result = subprocess.run(["git", "diff", "origin/HEAD...HEAD"], capture_output=True, text=True)
                log_result = subprocess.run(["git", "log", "origin/HEAD...HEAD", "--oneline"], capture_output=True, text=True)
                diff = diff_result.stdout.strip()
                history = log_result.stdout.strip()
                if not diff:
                    diff = subprocess.run(["git", "diff", "HEAD~1", "HEAD"], capture_output=True, text=True).stdout.strip()
                    history = subprocess.run(["git", "log", "HEAD~1..HEAD", "--oneline"], capture_output=True, text=True).stdout.strip()
                if not diff and not history:
                    tui._err("No diff found. Commit something first.")
                    return
                msg = (
                    f"Write a GitHub PR description.\n\nCommits:\n{history}\n\nDiff:\n{diff[:3000]}\n\n"
                    "Include: Title, What changed, Why, How to test. Use Markdown."
                )
                tui.memory.add("user", msg)
                msgs = build_messages(tui.system_prompt, tui.memory.get())
                raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [PR]")
                _finalize_stream(tui, raw, user_label="[pr]")
            except Exception as exc:
                tui._err(str(exc))
            finally:
                tui.set_busy(False)
                tui.redraw()

        _start_thread(_go)

    @registry.register("/changelog", "Generate CHANGELOG from git log")
    def cmd_changelog(tui, arg: str):
        def _go():
            try:
                tui.set_busy(True)
                git_log = subprocess.run(["git", "log", "--oneline", "-60"], capture_output=True, text=True).stdout.strip()
                if not git_log:
                    tui._err("No git history found.")
                    return
                msg = f"Generate a CHANGELOG from these git commits. Group by: Added, Changed, Fixed, Removed. Use Markdown:\n\n{git_log}"
                tui.memory.add("user", msg)
                msgs = build_messages(tui.system_prompt, tui.memory.get())
                raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [CHANGELOG]")
                _finalize_stream(tui, raw, user_label="[changelog]")
            except Exception as exc:
                tui._err(str(exc))
            finally:
                tui.set_busy(False)
                tui.redraw()

        _start_thread(_go)

    @registry.register("/standup", "Daily standup from git + todos")
    def cmd_standup(tui, arg: str):
        def _go():
            try:
                tui.set_busy(True)
                git_log = subprocess.run(
                    ["git", "log", "--oneline", "--since=24 hours ago"],
                    capture_output=True,
                    text=True,
                ).stdout.strip() or "No commits in the last 24 hours"
                try:
                    from src.utils.todo import todo_list as _tlist

                    todos = [todo for todo in _tlist() if not todo.get("done")]
                    todo_text = "\n".join(f"- {todo['text']}" for todo in todos[:10]) or "No pending todos"
                except Exception:
                    log.debug("Could not read todo file")
                    todo_text = "No pending todos"
                msg = (
                    "Generate a short daily standup (Yesterday / Today / Blockers).\n\n"
                    f"Recent commits:\n{git_log}\n\nPending todos:\n{todo_text}"
                )
                tui.memory.add("user", msg)
                msgs = build_messages(tui.system_prompt, tui.memory.get())
                raw = tui._tui_stream(msgs, tui.current_model, f"◆ {tui.name}  [standup]")
                _finalize_stream(tui, raw, user_label="[standup]")
            except Exception as exc:
                tui._err(str(exc))
            finally:
                tui.set_busy(False)
                tui.redraw()

        _start_thread(_go)

    @registry.register("/grep", "Search codebase for pattern")
    def cmd_grep(tui, arg: str):
        if not arg:
            tui._err("Usage: /grep <pattern> [path]")
            return
        parts = arg.split(None, 1)
        pattern = parts[0]
        path = parts[1] if len(parts) > 1 else "."
        if shutil.which("rg"):
            result = subprocess.run(
                ["rg", "-n", pattern, path],
                capture_output=True,
                text=True,
            )
            command = f"rg -n {pattern} {path}"
        else:
            result = subprocess.run(
                [
                    "grep",
                    "-rn",
                    "--include=*.py",
                    "--include=*.js",
                    "--include=*.ts",
                    "--include=*.go",
                    "--include=*.rs",
                    "--include=*.md",
                    pattern,
                    path,
                ],
                capture_output=True,
                text=True,
            )
            command = f"grep -rn '{pattern}' {path}"
        out = (result.stdout or result.stderr).strip()
        tui.store.add(Msg("shell", out[:3000] if out else "No matches found.", command))

    @registry.register("/tree", "Directory tree view")
    def cmd_tree(tui, arg: str):
        path = arg.strip() if arg.strip() else "."
        if shutil.which("tree"):
            result = subprocess.run(
                ["tree", path, "-L", "3", "--noreport", "-I", "__pycache__|*.pyc|.git|node_modules|.venv|venv"],
                capture_output=True,
                text=True,
            )
            out = result.stdout.strip()
        else:
            lines = [path + "/"]

            def _walk(current, prefix="", depth=0):
                if depth > 3:
                    return
                try:
                    entries = sorted(Path(current).iterdir(), key=lambda item: (item.is_file(), item.name))
                except Exception:
                    log.debug("Tree walk failed")
                    return
                for index, entry in enumerate(entries):
                    if entry.name in (".git", "__pycache__", "node_modules", ".venv", "venv"):
                        continue
                    connector = "└── " if index == len(entries) - 1 else "├── "
                    lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
                    if entry.is_dir():
                        _walk(entry, prefix + ("    " if index == len(entries) - 1 else "│   "), depth + 1)

            _walk(path)
            out = "\n".join(lines[:80])
        tui.store.add(Msg("shell", out, f"tree {path}"))

    @registry.register("/lint", "Lint with ruff or flake8")
    def cmd_lint(tui, arg: str):
        path = arg.strip() if arg.strip() else "."
        if shutil.which("ruff"):
            result = subprocess.run(["ruff", "check", path, "--output-format=concise"], capture_output=True, text=True)
            out = (result.stdout + result.stderr).strip()
        elif shutil.which("flake8"):
            result = subprocess.run(["flake8", path, "--max-line-length=120"], capture_output=True, text=True)
            out = (result.stdout + result.stderr).strip()
        else:
            tui._err("ruff or flake8 not installed. Run: pip install ruff")
            return
        tui.store.add(Msg("shell", out if out else "✓ No lint errors.", f"lint {path}"))

    @registry.register("/fmt", "Format with black or prettier")
    def cmd_fmt(tui, arg: str):
        path = arg.strip() if arg.strip() else "."
        if shutil.which("black"):
            result = subprocess.run(["black", path, "--quiet"], capture_output=True, text=True)
            out = (result.stdout + result.stderr).strip()
            tui.store.add(Msg("shell", out if out else "✓ Formatted.", f"black {path}"))
        elif shutil.which("prettier"):
            result = subprocess.run(["prettier", "--write", path], capture_output=True, text=True)
            out = ((result.stdout or "") + (result.stderr or "")).strip()
            tui.store.add(Msg("shell", out or "✓ Formatted.", f"prettier {path}"))
        else:
            tui._err("black or prettier not found. Run: pip install black")

    @registry.register("/redo", "Regenerate with different approach")
    def cmd_redo(tui, arg: str):
        if not tui.last_msg:
            tui._err("Nothing to redo.")
            return

        def _go():
            try:
                tui.set_busy(True)
                alt = arg.strip()
                q = f"{tui.last_msg}\n\n[This time: {alt}]" if alt else f"{tui.last_msg}\n\n[Rephrase — different approach, same quality.]"
                if tui.memory.remove_last_exchange():
                    tui.turns = max(0, tui.turns - 1)
                tui.store.add(Msg("user", f"↺ redo{' — ' + alt if alt else ''}"))
                tui.memory.add("user", q)
                msgs = build_messages(tui.system_prompt, tui.memory.get())
                raw = tui._tui_stream(msgs, tui.current_model)
                tui.memory.replace_last("user", tui.last_msg)
                tui.memory.add("assistant", raw)
                tui.prev_reply = tui.last_reply
                tui.last_reply = raw
                tui.turns += 1
            except Exception as exc:
                tui._err(str(exc))
            finally:
                tui.set_busy(False)
                tui.redraw()

        _start_thread(_go)

    @registry.register("/translate", "Translate last reply to a language")
    def cmd_translate(tui, arg: str):
        if not arg:
            tui._err("Usage: /translate <language>")
            return
        if not tui.last_reply:
            tui._err("No reply to translate yet.")
            return

        def _go():
            q = f"Translate your last response into {arg}. Output only the translation."
            _run_memory_prompt(
                tui,
                q,
                f"◆ {tui.name}  [→ {arg}]",
                build_messages=build_messages,
                user_label=f"Translate to {arg}",
            )

        _start_thread(_go)

    @registry.register("/summarize", "Summarize the conversation")
    def cmd_summarize(tui, arg: str):
        def _go():
            _run_memory_prompt(
                tui,
                "Summarize our conversation so far in concise bullet points.",
                f"◆ {tui.name}  [summarize]",
                build_messages=build_messages,
            )

        _start_thread(_go)

    @registry.register("/onboard", "Show first-run and workspace guidance")
    def cmd_onboard(tui, arg: str):
        try:
            configured = get_available_providers()
        except Exception:
            configured = []
        tui._sys(
            build_onboarding_report(
                base_dir=Path.cwd(),
                configured_providers=configured,
            )
        )

    return HELP_CATEGORIES
