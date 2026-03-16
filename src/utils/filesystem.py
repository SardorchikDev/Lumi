"""
Lumi file system agent — detects and executes file/folder creation
from natural language. No slash command needed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# ── Intent detection ──────────────────────────────────────────────────────────

CREATE_PATTERNS = [
    r"\bcreate\b.{0,60}\bfolder\b",
    r"\bcreate\b.{0,60}\bdir(ectory)?\b",
    r"\bmake\b.{0,60}\bfolder\b",
    r"\bmake\b.{0,60}\bproject\b",
    r"\bset up\b.{0,60}\bfolder\b",
    r"\bset up\b.{0,60}\bproject\b",
    r"\binitialize\b.{0,60}\bproject\b",
    r"\binit\b.{0,60}\bproject\b",
    r"\bscaffold\b",
    r"\bcreate\b.{0,30}\b(index\.html|style\.css|script\.js|main\.py|app\.py|README\.md)\b",
    r"\badd\b.{0,30}\b(index\.html|style\.css|script\.js|main\.py|app\.py)\b.{0,30}\bto it\b",
    r"\bcreate\b.{0,40}\bfiles?\b.{0,40}\bcode\b",
    r"\bgenerate\b.{0,40}\bfiles?\b",
    r"\bbootstrap\b.{0,40}\bproject\b",
]

def is_create_request(text: str) -> bool:
    """Return True if the message is asking to create files/folders."""
    t = text.lower()
    return any(re.search(p, t) for p in CREATE_PATTERNS)


# ── AI-powered file plan generation ──────────────────────────────────────────

SYSTEM_PROMPT = """You are a file system agent. When asked to create files and folders, 
you respond ONLY with a valid JSON object describing what to create.

Format:
{
  "root": "folder_name_or_dot",
  "files": [
    {
      "path": "relative/path/to/file.ext",
      "content": "full file content here"
    }
  ]
}

Rules:
- "root" is the top-level folder to create (use "." if no folder needed)
- "path" is relative to root
- "content" must be real, working, production-quality code — not placeholder comments
- For HTML: semantic structure, meta tags, link to CSS/JS
- For CSS: modern variables, reset, actual styles that look good
- For JS: real functionality, event listeners, no lorem ipsum
- For Python: real imports, real logic
- NEVER return anything except the JSON object — no explanation, no markdown fences
"""

def generate_file_plan(request: str, client, model: str) -> dict | None:
    """Ask AI to generate a JSON file plan. Three-strategy robust JSON extraction."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": request}
            ],
            max_tokens=4000,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()

        # Strategy 1: strip fences and parse
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```\s*$",       "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract first {...} block
        m = re.search(r"\{[\s\S]+\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        # Strategy 3: retry with stricter instruction
        retry = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": request},
                {"role": "assistant", "content": raw},
                {"role": "user",      "content":
                    "Output ONLY a raw JSON object. No markdown, no explanation. Start with { end with }."}
            ],
            max_tokens=4000,
            temperature=0.1,
        )
        raw2 = retry.choices[0].message.content.strip()
        m2 = re.search(r"\{[\s\S]+\}", raw2)
        if m2:
            return json.loads(m2.group())
        return None
    except Exception:
        return None


# ── File writing ──────────────────────────────────────────────────────────────

def write_file_plan(plan: dict, base_dir: str | Path = ".") -> list[str]:
    """
    Execute a file plan — create folders and write files.
    Returns list of created paths.

    Args:
        plan: Dictionary with 'root' and 'files' keys
        base_dir: Base directory to create files in

    Returns:
        List of created file/directory paths

    Raises:
        ValueError: If plan is invalid or missing required keys
        PermissionError: If unable to write to directory
    """
    created = []
    base_path = Path(base_dir).expanduser().resolve()

    root = plan.get("root", ".").strip()

    if root and root != ".":
        root_path = base_path / root
        root_path.mkdir(parents=True, exist_ok=True)
        created.append(str(root_path) + "/")
    else:
        root_path = base_path

    files = plan.get("files")
    if not isinstance(files, list):
        raise ValueError("Plan must contain a 'files' list")

    for f in files:
        if not isinstance(f, dict):
            continue

        rel_path = f.get("path", "").strip().lstrip("/")
        content = f.get("content", "")

        if not rel_path:
            continue

        # Security: prevent path traversal
        full_path = (root_path / rel_path).resolve()
        if not str(full_path).startswith(str(root_path)):
            raise ValueError(f"Invalid path: {rel_path} (path traversal detected)")

        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            full_path.write_text(content, encoding="utf-8")
            created.append(str(full_path))
        except PermissionError as e:
            raise PermissionError(f"Cannot write to {full_path}: {e}")
        except OSError as e:
            raise OSError(f"Failed to write {full_path}: {e}")

    return created


# ── Summary formatter ─────────────────────────────────────────────────────────

def format_creation_summary(plan: dict, created: list[str]) -> str:
    """Return a human-readable summary of what was created."""
    root  = plan.get("root", ".")
    files = plan.get("files", [])
    lines = []
    if root != ".":
        lines.append(f"📁 {root}/")
    for f in files:
        path = f.get("path", "")
        size = len(f.get("content", "").encode())
        lines.append(f"   📄 {path}  ({size:,} bytes)")
    return "\n".join(lines)
