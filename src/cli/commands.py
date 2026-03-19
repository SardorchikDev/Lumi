"""
CLI command implementations for Lumi.

All cmd_* functions are moved here from main.py to modularize the codebase.
"""

import sys

from src.agents.council import _get_available_agents as get_council_agents
from src.agents.council import council_ask
from src.utils.markdown import render as md_render

from .render import (
    DG,
    GR,
    MU,
    R,
    Spinner,
    print_lumi_label,
)
from .render import (
    word_count as wc,
)

# Re-export for backward compatibility
_PROVIDER_LABELS = {
    "gemini":      ("Gemini",        "Google Gemini — 2.5 Pro · Flash · 1M context"),
    "groq":        ("Groq",          "Groq — fastest, Llama / Qwen / GPT-OSS"),
    "openrouter":  ("OpenRouter",    "30+ free models — DeepSeek R1, Llama 4, Qwen3"),
    "mistral":     ("Mistral",       "Mistral free tier — great for coding"),
    "huggingface": ("HuggingFace",   "HuggingFace — free tier, rate limited"),
    "github":      ("GitHub Models", "GPT-4o, o1, DeepSeek R1, Phi-4 — free with GitHub"),
    "cohere":      ("Cohere",        "Cohere — free 1,000 req/month"),
    "bytez":       ("Bytez",         "Bytez — 100,000+ open-source models, full HuggingFace catalog"),
    "cloudflare":  ("Cloudflare",    "Cloudflare Workers AI — free 10 k neurons/day"),
    "ollama":      ("Ollama",        "Local Ollama — fully offline, no API limits"),
    "council":     ("⚡ Council",    "All agents in parallel — synthesized best answer"),
}

# Helper functions moved from main.py
def stream_and_render(
    client, messages: list, model: str, name: str = "Lumi"
) -> str:
    """Stream a response from the model and render it with markdown."""

    # ── Council mode ──────────────────────────────────────────────────────────
    if model == "council":
        user_q = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        avail = get_council_agents()
        print(f"\n  {DG}council  {GR}{len(avail)} agents  {DG}→  asking in parallel...{R}\n")

        gen        = council_ask(messages, user_q, show_individual=False,
                                 stream=True, debate=True, refine=True, client=client)
        raw_reply  = ""
        stats_line = ""
        refined    = ""

        print_lumi_label(name + f"  {DG}[council]{R}")
        for chunk in gen:
            if chunk.startswith("\n\n__STATS__\n"):
                stats_line = chunk[len("\n\n__STATS__\n"):]
                continue
            if chunk.startswith("\n\n__REFINED__\n\n"):
                refined = chunk[len("\n\n__REFINED__\n\n"):]
                continue
            print(chunk, end="", flush=True)
            raw_reply += chunk
        print()

        final = refined if refined else raw_reply
        # Re-render with markdown (erase raw stream first)
        for _ in range(final.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name + f"  {DG}[council]{R}")
        from src.utils.markdown import render as _mdr
        print("\n".join("  " + l for l in _mdr(final).split("\n")))
        print(f"\n  {MU}{wc(final)} words  {DG}{len(avail)} agents{R}")
        if stats_line:
            print(f"  {stats_line}")
        return final

    # ── Normal streaming ──────────────────────────────────────────────────────
    spinner   = Spinner("thinking")
    spinner.start()
    raw_reply = ""
    first     = True

    try:
        stream = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=1024, temperature=0.7, stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                if first:
                    spinner.stop()
                    print_lumi_label(name)
                    first = False
                print(delta, end="", flush=True)
                raw_reply += delta
        if first:
            spinner.stop()
        print()
    except Exception as exc:
        spinner.stop()
        raise exc

    if raw_reply:
        for _ in range(raw_reply.count("\n") + 4):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        print_lumi_label(name)
        indented = "\n".join("  " + l for l in md_render(raw_reply).split("\n"))
        print(indented)
        print(f"\n  {MU}{wc(raw_reply)} words{R}")

    return raw_reply
