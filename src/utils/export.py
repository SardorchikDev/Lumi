"""Export conversation history to a markdown file."""

from datetime import datetime
from pathlib import Path

from src.config import CONVERSATIONS_DIR


def export_md(history: list[dict], name: str = "Lumi") -> Path:
    exports_dir = CONVERSATIONS_DIR / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = exports_dir / f"lumi_{timestamp}.md"
    lines = [f"# {name} Conversation\n", f"*Exported {datetime.now().strftime('%B %d, %Y at %H:%M')}*\n\n---\n"]
    for msg in history:
        role = "**You**" if msg["role"] == "user" else f"**{name}**"
        lines.append(f"### {role}\n\n{msg['content']}\n\n---\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
