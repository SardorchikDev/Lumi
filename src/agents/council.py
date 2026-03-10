"""
Lumi Council — 5-agent parallel consensus system.

5 specialist models answer simultaneously via threads.
A judge model synthesizes the best answer from all responses.

Agents:
  gemini     → gemini-2.5-flash              (Google)      — reasoning
  groq       → moonshotai/kimi-k2-instruct   (Groq)        — analysis
  openrouter → openai/gpt-oss-120b:free      (OpenRouter)  — general
  mistral    → codestral-latest              (Mistral)     — code
  hf         → meta-llama/Llama-3.3-70B-Instruct (HF)     — writing
"""

import os
import sys
import time
import threading
from openai import OpenAI

# ── Agent definitions ─────────────────────────────────────────────────────────

AGENTS = [
    {
        "id":       "gemini",
        "name":     "Gemini",
        "models":   [
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ],
        "provider": "gemini",
        "role":     "reasoning",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env":  "GEMINI_API_KEY",
        "color":    "\033[38;5;75m",
    },
    {
        "id":       "groq",
        "name":     "Kimi K2",
        "models":   [
            "kimi-k2-instruct-0905",
            "gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "qwen-3-32b",
            "llama-3.1-8b-instant",
        ],
        "provider": "groq",
        "role":     "analysis",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env":  "GROQ_API_KEY",
        "color":    "\033[38;5;215m",
    },
    {
        "id":       "openrouter",
        "name":     "GPT-OSS",
        "models":   [
            "openai/gpt-oss-20b:free",
            "openai/gpt-oss-120b:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen3-coder:free",
            "google/gemma-3-27b-it:free",
        ],
        "provider": "openrouter",
        "role":     "general",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env":  "OPENROUTER_API_KEY",
        "color":    "\033[38;5;141m",
    },
    {
        "id":       "mistral",
        "name":     "Codestral",
        "models":   [
            "codestral-latest",
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "open-mistral-nemo",
        ],
        "provider": "mistral",
        "role":     "code",
        "base_url": "https://api.mistral.ai/v1",
        "key_env":  "MISTRAL_API_KEY",
        "color":    "\033[38;5;210m",
    },
    {
        "id":       "hf",
        "name":     "Llama 3.3",
        "models":   [
            "meta-llama/Llama-3.3-70B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "meta-llama/Llama-3.1-70B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
        ],
        "provider": "huggingface",
        "role":     "writing",
        "base_url": "https://router.huggingface.co/v1",
        "key_env":  "HF_TOKEN",
        "color":    "\033[38;5;179m",
    },
]

# ── Colors ────────────────────────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
DG = "\033[38;5;238m"
GN = "\033[38;5;114m"
RE = "\033[38;5;203m"
YE = "\033[38;5;179m"
GR = "\033[38;5;245m"
PU = "\033[38;5;141m"


def _get_available_agents() -> list:
    """Return only agents whose API key is set in env."""
    return [a for a in AGENTS if os.getenv(a["key_env"])]


def _make_agent_client(agent: dict) -> OpenAI:
    return OpenAI(
        base_url=agent["base_url"],
        api_key=os.getenv(agent["key_env"], ""),
    )


# Track which model each agent ended up using
_agent_used_model: dict = {}

# Errors that should trigger a fallback to next model
_FALLBACK_ERRORS = (
    "429", "rate_limit", "quota", "limit: 0",
    "resource_exhausted", "overloaded",
    "503", "502", "500",
    "model_not_found", "404", "decommissioned",
    "no endpoints", "unavailable", "not found",
    "context length", "content policy", "moderation",
)

def _call_agent(agent: dict, messages: list, results: dict, errors: dict,
                spinner=None):
    """Try each model in the agent's fallback list. Store result or error."""
    client = _make_agent_client(agent)
    models = agent.get("models", [agent.get("model", "")])
    last_error = ""

    for model in models:
        # Update spinner label to show current model attempt
        if spinner:
            spinner.set_model(agent["id"], model.split("/")[-1])
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
                stream=False,
            )
            if not resp.choices:
                last_error = "no choices returned"
                continue
            text = resp.choices[0].message.content
            if text and text.strip():
                results[agent["id"]] = text.strip()
                _agent_used_model[agent["id"]] = model.split("/")[-1]
                return   # success — stop trying
            else:
                last_error = "empty response"
        except Exception as e:
            last_error = str(e)[:160]
            # Only fallback on quota/availability errors
            if any(x in last_error.lower() for x in _FALLBACK_ERRORS):
                continue   # try next model
            else:
                break      # hard error — don't bother with fallbacks

    # All models failed
    errors[agent["id"]] = last_error


def _build_judge_prompt(responses: dict, original_question: str) -> str:
    parts = []
    for aid, text in responses.items():
        agent = next((a for a in AGENTS if a["id"] == aid), None)
        label = f"{agent['name']} ({agent['role']})" if agent else aid
        parts.append(f"[{label}]:\n{text}")
    combined = "\n\n---\n\n".join(parts)
    return f"""You received responses from {len(responses)} AI models answering this:

"{original_question}"

Their responses:

{combined}

---

Synthesize the BEST possible final answer:
- Take the most accurate and complete information from each
- Resolve contradictions by picking the most reliable answer
- Keep the best code example if any (prefer most complete/correct)
- Write one clean, well-structured answer

Do NOT say "according to the models" or mention the synthesis process.
Just write the best direct answer."""


def _judge(responses: dict, original_question: str) -> str:
    """Synthesize all responses into one answer (non-streaming fallback)."""
    if len(responses) == 1:
        return next(iter(responses.values()))
    JUDGE_ORDER = ["gemini", "groq", "openrouter", "mistral", "hf"]
    judge_agent = None
    for jid in JUDGE_ORDER:
        candidate = next((a for a in AGENTS if a["id"] == jid), None)
        if candidate and os.getenv(candidate["key_env"]):
            judge_agent = candidate
            break
    if not judge_agent:
        return max(responses.values(), key=len)
    try:
        client = _make_agent_client(judge_agent)
        resp   = client.chat.completions.create(
            model=judge_agent["models"][0],
            messages=[{"role": "user", "content": _build_judge_prompt(responses, original_question)}],
            max_tokens=2048, temperature=0.3, stream=False,
        )
        if resp.choices and resp.choices[0].message.content:
            return resp.choices[0].message.content.strip()
    except Exception:
        pass
    return max(responses.values(), key=len)


def _judge_stream(responses: dict, original_question: str):
    """Stream synthesized answer token by token. Yields str chunks."""
    if len(responses) == 1:
        yield next(iter(responses.values()))
        return
    JUDGE_ORDER = ["gemini", "groq", "openrouter", "mistral", "hf"]
    judge_agent = None
    for jid in JUDGE_ORDER:
        candidate = next((a for a in AGENTS if a["id"] == jid), None)
        if candidate and os.getenv(candidate["key_env"]):
            judge_agent = candidate
            break
    if not judge_agent:
        yield max(responses.values(), key=len)
        return
    try:
        client = _make_agent_client(judge_agent)
        stream = client.chat.completions.create(
            model=judge_agent["models"][0],
            messages=[{"role": "user", "content": _build_judge_prompt(responses, original_question)}],
            max_tokens=2048, temperature=0.3, stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        yield max(responses.values(), key=len)


# ── Animated progress display ─────────────────────────────────────────────────

class CouncilSpinner:
    FRAMES = ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"]

    def __init__(self, agents: list):
        self._agents       = agents
        self._done         = {}   # id → True/False
        self._current_model = {}  # id → short model name being tried
        self._running      = False
        self._thread       = None
        self._lock         = threading.Lock()

    def mark_done(self, agent_id: str, success: bool):
        with self._lock:
            self._done[agent_id] = success

    def set_model(self, agent_id: str, model_short: str):
        """Show which fallback model is being tried."""
        with self._lock:
            self._current_model[agent_id] = model_short

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._render, daemon=True)
        self._thread.start()

    @staticmethod
    def _strip_ansi(s: str) -> str:
        import re
        return re.sub(r"\033\[[0-9;]*m", "", s)

    def _fit(self, line: str) -> str:
        """Truncate line to terminal width, accounting for ANSI codes."""
        try:
            import shutil
            w = shutil.get_terminal_size().columns - 2
        except Exception:
            w = 80
        visible = self._strip_ansi(line)
        if len(visible) <= w:
            return line + " " * (w - len(visible))   # pad to clear leftovers
        # Trim: walk char by char keeping count of visible chars
        out = ""
        count = 0
        i = 0
        import re
        while i < len(line):
            # Skip ANSI escape
            m = re.match(r"\033\[[0-9;]*m", line[i:])
            if m:
                out += m.group()
                i += len(m.group())
                continue
            if count >= w:
                break
            out += line[i]
            count += 1
            i += 1
        return out + "\033[0m"

    def _render(self):
        import itertools
        for f in itertools.cycle(self.FRAMES):
            if not self._running:
                break
            parts = []
            with self._lock:
                for a in self._agents:
                    col = a["color"]
                    aid = a["id"]
                    if aid in self._done:
                        icon  = f"{GN}✓{R}" if self._done[aid] else f"{RE}✗{R}"
                        label = f"{icon}{col}{a['name']}{R}"
                    else:
                        label = f"{col}{f} {a['name']}{R}"
                    parts.append(label)
            line = "  " + "   ".join(parts)
            sys.stdout.write("\r" + self._fit(line))
            sys.stdout.flush()
            time.sleep(0.09)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        # Clear spinner line
        try:
            import shutil
            w = shutil.get_terminal_size().columns
        except Exception:
            w = 80
        sys.stdout.write("\r" + " " * w + "\r")
        # Print clean final state on a new line
        parts = []
        for a in self._agents:
            col  = a["color"]
            aid  = a["id"]
            icon = f"{GN}✓{R}" if self._done.get(aid) else f"{RE}✗{R}"
            parts.append(f"{icon}{col}{a['name']}{R}")
        sys.stdout.write("  " + "   ".join(parts) + "\n")
        sys.stdout.flush()


# ── Main public function ──────────────────────────────────────────────────────

def council_ask(messages: list, user_question: str,
                show_individual: bool = False,
                stream: bool = False):
    """
    stream=True  → returns a generator of string chunks
    stream=False → returns a full string (default)
    """
    """
    Send messages to all available agents in parallel, then synthesize.

    Args:
        messages:         Full message list (system prompt + history)
        user_question:    Raw user question string (used for judge prompt)
        show_individual:  Print each agent's raw response before synthesis

    Returns:
        Synthesized final answer string
    """
    agents = _get_available_agents()

    if not agents:
        raise RuntimeError(
            "No council agents available — add at least one API key:\n"
            "  GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, "
            "MISTRAL_API_KEY, or HF_TOKEN"
        )

    results: dict = {}
    errors:  dict = {}

    print(f"\n  {DG}council  {GR}{len(agents)} agents  {DG}→  asking in parallel...{R}\n")

    spinner = CouncilSpinner(agents)
    spinner.start()

    # Launch all agents simultaneously
    threads = []
    def _wrap(agent):
        _call_agent(agent, messages, results, errors, spinner)
        spinner.mark_done(agent["id"], agent["id"] in results)

    for agent in agents:
        t = threading.Thread(target=_wrap, args=(agent,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=45)

    spinner.stop()

    if not results:
        errs = " | ".join(f"{k}: {v[:60]}" for k, v in errors.items())
        raise RuntimeError(f"All agents failed.\n{errs}")

    # Show individual responses if requested
    if show_individual and len(results) > 1:
        print()
        for aid, text in results.items():
            agent = next((a for a in AGENTS if a["id"] == aid), None)
            col   = agent["color"] if agent else GR
            name  = f"{agent['name']} ({agent['role']})" if agent else aid
            print(f"\n  {col}{B}{name}{R}  {DG}──────────────────────────{R}")
            lines = text.split("\n")
            for line in lines[:10]:
                print(f"  {GR}{line}{R}")
            if len(lines) > 10:
                print(f"  {DG}... ({len(lines)-10} more lines){R}")

    # Report failed agents
    if errors:
        failed = ", ".join(errors.keys())
        print(f"\n  {YE}▲  unavailable: {failed}{R}")

    # Synthesize
    if len(results) > 1:
        print(f"\n  {DG}synthesizing {len(results)} responses...{R}\n")

    if stream:
        return _judge_stream(results, user_question)
    return _judge(results, user_question)
