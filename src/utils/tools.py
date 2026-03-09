"""
Lumi extra tools — weather, clipboard, PDF, image analysis, project loader.
All use stdlib or lightweight deps only.
"""
import os, subprocess, shutil, json

# ── Weather (wttr.in — no API key needed) ─────────────────────

def get_weather(location: str = "") -> str:
    """Fetch weather from wttr.in. No API key needed."""
    try:
        import urllib.request
        loc = location.strip().replace(" ", "+") or "Tashkent"
        url = f"https://wttr.in/{loc}?format=3"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read().decode("utf-8").strip()
    except Exception as e:
        return f"Weather unavailable: {e}"

def get_weather_detailed(location: str = "") -> str:
    """Get full weather report."""
    try:
        import urllib.request
        loc = location.strip().replace(" ", "+") or "Tashkent"
        url = f"https://wttr.in/{loc}?format=%l:+%C+%t+feels+like+%f+💧%h+💨%w"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return ""

# ── Clipboard ─────────────────────────────────────────────────

def clipboard_get() -> str:
    """Read from system clipboard."""
    try:
        if shutil.which("xclip"):
            return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"],
                                           text=True, timeout=3)
        if shutil.which("xsel"):
            return subprocess.check_output(["xsel", "--clipboard", "--output"],
                                           text=True, timeout=3)
        if shutil.which("wl-paste"):
            return subprocess.check_output(["wl-paste"], text=True, timeout=3)
        if shutil.which("pbpaste"):  # macOS
            return subprocess.check_output(["pbpaste"], text=True, timeout=3)
        # Windows
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        return root.clipboard_get()
    except Exception:
        return ""

def clipboard_set(text: str) -> bool:
    """Write to system clipboard."""
    try:
        if shutil.which("xclip"):
            p = subprocess.Popen(["xclip", "-selection", "clipboard"],
                                  stdin=subprocess.PIPE)
            p.communicate(text.encode()); return True
        if shutil.which("xsel"):
            p = subprocess.Popen(["xsel", "--clipboard", "--input"],
                                  stdin=subprocess.PIPE)
            p.communicate(text.encode()); return True
        if shutil.which("wl-copy"):
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            p.communicate(text.encode()); return True
        if shutil.which("pbcopy"):  # macOS
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode()); return True
    except Exception:
        pass
    return False

# ── PDF Reading ───────────────────────────────────────────────

def read_pdf(path: str) -> str:
    """Extract text from PDF. Uses pdfplumber if available, else pdfminer."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"File not found: {path}"
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages[:20]):  # max 20 pages
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- Page {i+1} ---\n{text}")
            return "\n\n".join(pages)[:15000]
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path)[:15000]
    except ImportError:
        pass
    # Raw fallback — strings from binary
    try:
        import re
        raw = open(path, "rb").read()
        text = raw.decode("latin-1", errors="ignore")
        # Extract readable strings
        strings = re.findall(r'[\x20-\x7e]{4,}', text)
        return " ".join(strings)[:8000]
    except Exception as e:
        return f"Could not read PDF: {e}"

# ── Screenshot ────────────────────────────────────────────────

def take_screenshot() -> str | None:
    """Take a screenshot and return the file path."""
    import tempfile
    path = tempfile.mktemp(suffix=".png")
    try:
        if shutil.which("scrot"):
            subprocess.run(["scrot", path], check=True, capture_output=True)
            return path
        if shutil.which("import"):  # ImageMagick
            subprocess.run(["import", "-window", "root", path],
                           check=True, capture_output=True)
            return path
        if shutil.which("gnome-screenshot"):
            subprocess.run(["gnome-screenshot", "-f", path],
                           check=True, capture_output=True)
            return path
        if shutil.which("screencapture"):  # macOS
            subprocess.run(["screencapture", path],
                           check=True, capture_output=True)
            return path
    except Exception:
        pass
    return None

def encode_image_base64(path: str) -> str:
    """Encode image to base64 for vision API."""
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ── Project / Directory Context ───────────────────────────────

def load_project(path: str, max_files: int = 30, max_size: int = 100_000) -> str:
    """
    Load a project directory into a single context string.
    Returns a structured representation of the codebase.
    """
    path = os.path.expanduser(path.strip())
    if not os.path.isdir(path):
        return f"Not a directory: {path}"

    SKIP_DIRS  = {".git", "node_modules", "__pycache__", ".venv", "venv",
                  "dist", "build", ".next", ".cache", "vendor", "target"}
    SKIP_EXTS  = {".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
                  ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".woff",
                  ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz",
                  ".lock", ".sum"}
    CODE_EXTS  = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                  ".json", ".yaml", ".yml", ".toml", ".rs", ".c", ".cpp",
                  ".h", ".go", ".rb", ".php", ".sh", ".md", ".txt", ".env.example"}

    files_loaded = []
    total_size   = 0

    # Build tree
    tree_lines = [f"Project: {os.path.basename(path)}\n"]
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS and not d.startswith(".")]
        level  = root.replace(path, "").count(os.sep)
        indent = "  " * level
        rel    = os.path.relpath(root, path)
        if rel != ".":
            tree_lines.append(f"{indent}📁 {os.path.basename(root)}/")
        for file in sorted(files):
            ext = os.path.splitext(file)[1].lower()
            if ext in SKIP_EXTS: continue
            tree_lines.append(f"{indent}  📄 {file}")

    # Load file contents
    content_parts = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS and not d.startswith(".")]
        for file in sorted(files):
            if len(files_loaded) >= max_files: break
            if total_size >= max_size: break
            fpath = os.path.join(root, file)
            ext   = os.path.splitext(file)[1].lower()
            if ext not in CODE_EXTS: continue
            try:
                text = open(fpath, encoding="utf-8", errors="replace").read()
                rel  = os.path.relpath(fpath, path)
                content_parts.append(f"\n### {rel}\n```{ext.lstrip('.')}\n{text[:3000]}\n```")
                files_loaded.append(rel)
                total_size += len(text)
            except Exception:
                continue

    tree   = "\n".join(tree_lines)
    files_text = "\n".join(content_parts)
    summary = (
        f"Project directory: `{path}`\n"
        f"Files loaded: {len(files_loaded)} / {max_files} max\n\n"
        f"## Directory Structure\n```\n{tree}\n```\n"
        f"\n## File Contents\n{files_text}"
    )
    return summary[:20000]  # cap for context window

# ── CSV/JSON Analysis ─────────────────────────────────────────

def analyze_data_file(path: str) -> str:
    """Load CSV or JSON and return a summary for Lumi to analyze."""
    path = os.path.expanduser(path.strip())
    ext  = os.path.splitext(path)[1].lower()
    if not os.path.exists(path):
        return f"File not found: {path}"
    try:
        if ext == ".json":
            data = json.loads(open(path).read())
            preview = json.dumps(data, indent=2)[:3000]
            return f"JSON file: {path}\n\nContent preview:\n```json\n{preview}\n```"
        elif ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            lines = open(path, encoding="utf-8", errors="replace").readlines()
            header = lines[0].strip() if lines else ""
            row_count = len(lines) - 1
            preview = "".join(lines[:20])
            return (
                f"CSV file: {path}\n"
                f"Rows: {row_count}  |  Columns: {header}\n\n"
                f"First 20 rows:\n```\n{preview}\n```"
            )
    except Exception as e:
        return f"Could not parse file: {e}"
    return open(path).read()[:5000]
