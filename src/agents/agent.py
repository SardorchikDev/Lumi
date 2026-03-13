"""
Lumi Agent Mode — autonomous multi-step task execution.

Give Lumi a goal → it plans steps → executes them → asks confirmation on risky ones.
"""

import json
import os
import re
import subprocess

R  = "\033[0m"
B  = "\033[1m"
D  = "\033[2m"
GN = "\033[38;5;114m"
RE = "\033[38;5;203m"
YE = "\033[38;5;179m"
PU = "\033[38;5;141m"
CY = "\033[38;5;117m"
DG = "\033[38;5;238m"
WH = "\033[255m"
GR = "\033[38;5;245m"

# Steps that require user confirmation before running
RISKY_KEYWORDS = (
    "delete", "remove", "drop", "rm ", "overwrite", "truncate",
    "sudo", "chmod", "chown", "kill", "reboot", "shutdown",
    "git push", "deploy", "publish", "npm publish",
    "pip install", "curl", "wget", "format",
)

PLAN_SYSTEM_PROMPT = """You are an autonomous AI agent. Given a task, produce a step-by-step execution plan.

Return ONLY a JSON array of steps. Each step:
{
  "id": 1,
  "description": "Human-readable description",
  "type": "shell" | "file_write" | "ai_task" | "ask_user",
  "command": "bash command to run  (if type=shell)",
  "path": "file path  (if type=file_write)",
  "content": "file content  (if type=file_write)",
  "prompt": "what to ask AI  (if type=ai_task)",
  "question": "what to ask user  (if type=ask_user)",
  "risky": true | false
}

Rules:
- Keep steps atomic and small
- Mark risky=true for anything destructive, network-related, or system-modifying
- Use ai_task for steps that require reasoning or code generation
- Use ask_user when you genuinely need human input
- Max 10 steps
- Return ONLY the JSON array, nothing else"""


def make_plan(task: str, client, model: str) -> list[dict]:
    """Ask AI to break task into steps."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user",   "content": f"Task: {task}"},
            ],
            max_tokens=1500,
            temperature=0.2,
            stream=False,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$",       "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Could not generate plan: {e}")


def is_risky(step: dict) -> bool:
    if step.get("risky"):
        return True
    cmd = (step.get("command", "") + step.get("description", "")).lower()
    return any(k in cmd for k in RISKY_KEYWORDS)


def confirm(prompt_text: str) -> bool:
    try:
        ans = input(f"  {YE}?{R}  {prompt_text}  {DG}[y/N]{R}  ").strip().lower()
        return ans in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def run_step(step: dict, client, model: str,
             memory, system_prompt: str, yolo: bool = False) -> tuple[bool, str]:
    """
    Execute one step. Returns (success, output).
    """
    stype = step.get("type", "ai_task")
    desc  = step.get("description", "")

    if stype == "shell":
        cmd = step.get("command", "")
        if not cmd:
            return False, "No command specified"
        if is_risky(step) and not yolo:
            if not confirm(f"Run: {CY}{cmd}{R}"):
                return False, "Skipped by user"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return False, "Command timed out (30s)"
        except Exception as e:
            return False, str(e)

    elif stype == "file_write":
        path    = os.path.expanduser(step.get("path", ""))
        content = step.get("content", "")
        if not path:
            return False, "No path specified"
        if is_risky(step) and not yolo:
            if not confirm(f"Write file: {CY}{path}{R}"):
                return False, "Skipped by user"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return True, f"Written: {path}"
        except Exception as e:
            return False, str(e)

    elif stype == "ai_task":
        prompt = step.get("prompt", desc)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *memory.get(),
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.7,
                stream=False,
            )
            answer = resp.choices[0].message.content.strip()
            memory.add("user", prompt)
            memory.add("assistant", answer)
            return True, answer
        except Exception as e:
            return False, str(e)

    elif stype == "ask_user":
        question = step.get("question", desc)
        try:
            answer = input(f"  {PU}›{R}  {question}  ").strip()
            return True, answer
        except (KeyboardInterrupt, EOFError):
            return False, "User cancelled"

    return False, f"Unknown step type: {stype}"


def run_agent(task: str, client, model: str, memory,
              system_prompt: str, yolo: bool = False) -> str:
    """
    Full agent loop: plan → show plan → execute step by step.
    Returns summary of what was done.
    """
    from src.utils.markdown import render as md_render

    print(f"\n  {PU}agent{R}  {DG}planning...{R}\n")

    # Generate plan
    try:
        steps = make_plan(task, client, model)
    except RuntimeError as e:
        return str(e)

    if not steps:
        return "No steps generated."

    # Show plan
    print(f"  {B}{WH}Plan  ({len(steps)} steps){R}\n")
    for s in steps:
        risky_badge = f"  {YE}risky{R}" if is_risky(s) else ""
        stype = s.get("type", "?")
        type_col = {
            "shell":      CY,
            "file_write": GN,
            "ai_task":    PU,
            "ask_user":   YE,
        }.get(stype, GR)
        print(f"  {DG}{s['id']}.{R}  {type_col}[{stype}]{R}  {s['description']}{risky_badge}")
    print()

    if not yolo:
        if not confirm(f"Execute {len(steps)} steps?"):
            return "Agent cancelled."

    # Execute
    results = []
    for s in steps:
        stype    = s.get("type", "?")
        type_col = {"shell": CY, "file_write": GN, "ai_task": PU, "ask_user": YE}.get(stype, GR)
        print(f"\n  {DG}step {s['id']}/{len(steps)}{R}  {type_col}{s['description']}{R}")

        success, output = run_step(s, client, model, memory, system_prompt, yolo)

        if success:
            print(f"  {GN}✓{R}  ", end="")
            if output and len(output) < 300:
                print(output)
            elif output:
                # Render if it looks like markdown/code
                print()
                for line in md_render(output[:800]).split("\n"):
                    print(f"  {GR}{line}{R}")
        else:
            print(f"  {RE}✗{R}  {output}")

        results.append({
            "step":    s["description"],
            "success": success,
            "output":  output[:200],
        })

    # Summary
    done    = sum(1 for r in results if r["success"])
    failed  = len(results) - done
    summary = f"Agent completed {done}/{len(steps)} steps"
    if failed:
        summary += f" ({failed} failed)"

    print(f"\n  {GN if not failed else YE}{'✓' if not failed else '▲'}{R}  {summary}\n")
    return summary
