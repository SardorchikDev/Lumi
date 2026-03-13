"""
Lumi file system agent — detects and executes file/folder creation
from natural language. No slash command needed.
"""
import json
import os
import re

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

def write_file_plan(plan: dict, base_dir: str = ".") -> list[str]:
    """
    Execute a file plan — create folders and write files.
    Returns list of created paths.
    """
    created = []
    root = plan.get("root", ".").strip()

    if root and root != ".":
        root_path = os.path.join(base_dir, root)
        os.makedirs(root_path, exist_ok=True)
        created.append(root_path + "/")
    else:
        root_path = base_dir

    for f in plan.get("files", []):
        rel_path = f.get("path", "").strip().lstrip("/")
        content  = f.get("content", "")
        if not rel_path:
            continue

        full_path = os.path.join(root_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        created.append(full_path)

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
