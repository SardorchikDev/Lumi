"""CLI argument parsing helpers for Lumi's classic mode entrypoint."""

from __future__ import annotations

import argparse


def parse_cli_args(version: str):
    """Return parsed CLI options for the Lumi entrypoint."""
    ap = argparse.ArgumentParser(
        prog="lumi",
        description=f"Lumi AI {version} — terminal assistant",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
    )
    ap.add_argument("query", nargs="?", default=None, help="Send a message and start interactive session")
    ap.add_argument("-p", "--print", dest="print_mode", action="store_true", help="Non-interactive: send query, print response, exit")
    ap.add_argument("-c", "--continue", dest="resume_latest", action="store_true", help="Continue most recent conversation")
    ap.add_argument("-r", "--resume", metavar="SESSION", help="Resume session by name or id")
    ap.add_argument("-v", "--version", action="store_true", help="Show version and exit")
    ap.add_argument("-h", "--help", action="store_true", help="Show this help and exit")
    ap.add_argument("--model", "-m", metavar="MODEL", help="Set model  (e.g. gemini-2.5-flash, council)")
    ap.add_argument("--provider", metavar="PROVIDER", help="Force provider  (gemini|groq|openrouter|mistral|huggingface|ollama)")
    ap.add_argument("--system-prompt", metavar="TEXT", help="Replace system prompt with custom text")
    ap.add_argument("--append-system-prompt", metavar="TEXT", help="Append text to the default system prompt")
    ap.add_argument("--system-prompt-file", metavar="FILE", help="Replace system prompt with contents of a file")
    ap.add_argument("--append-system-prompt-file", metavar="FILE", help="Append file contents to default system prompt")
    ap.add_argument("--yolo", action="store_true", help="Auto-approve all file writes — no confirmations")
    ap.add_argument("--max-turns", metavar="N", type=int, default=None, help="Exit after N conversation turns")
    ap.add_argument("--output-format", metavar="FMT", choices=["text", "json"], default="text", help="Output format for --print mode: text (default) or json")
    ap.add_argument("--no-tui", action="store_true", help="Disable TUI, use classic CLI mode")
    ap.add_argument("--verbose", action="store_true", help="Show full API errors")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--list-sessions", action="store_true", help="List sessions and exit")
    ap.add_argument("--delete-session", metavar="ID", help="Delete a session by id and exit")
    ap.add_argument("--rebirth", action="store_true", help="Start with Lumi - rebirth defaults")
    return ap.parse_known_args()[0]


def print_cli_help(version: str, *, bold: str = "", reset: str = "") -> None:
    """Print help output used by `lumi --help`."""
    print(f"  Lumi AI {version}")
    print("  Usage: lumi [query] [flags]\\n")
    print(f"  {bold}Core flags:{reset}")
    print("   -p  --print                non-interactive mode")
    print("   -c  --continue             resume last conversation")
    print("   -r  --resume SESSION       resume by name/id")
    print("   -m  --model MODEL          set model")
    print("       --provider PROVIDER    set provider")
    print("       --system-prompt TEXT   replace system prompt")
    print("       --append-system-prompt TEXT  append to prompt")
    print("       --yolo                 auto-approve file writes")
    print("       --max-turns N          exit after N turns")
    print("       --output-format FMT    text or json (--print only)")
    print("       --verbose              show full API errors")
    print("       --list-sessions        list sessions and exit")
    print("       --rebirth              start with rebirth defaults")
    print("       --no-tui               disable TUI, use classic CLI")
    print("   -v  --version              show version\\n")
    print(f"  {bold}Examples:{reset}")
    print("   lumi -p \"explain this\" < file.py")
    print("   lumi -c --model council")
    print("   lumi --rebirth")
    print("   lumi --yolo --append-system-prompt \"always use TypeScript\"")
