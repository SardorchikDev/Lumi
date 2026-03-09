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
        "model":    "gemini-2.5-flash",
        "provider": "gemini",
        "role":     "reasoning",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env":  "GEMINI_API_KEY",
        "color":    "\033[38;5;75m",
    },
    {
        "id":       "groq",
        "name":     "Kimi K2",
        "model":    "moonshotai/kimi-k2-instruct",
        "provider": "groq",
        "role":     "analysis",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env":  "GROQ_API_KEY",
        "color":    "\033[38;5;215m",
    },
    {
        "id":       "openrouter",
        "name":     "GPT-OSS",
        "model":    "openai/gpt-oss-20b:free",
        "provider": "openrouter",
        "role":     "general",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env":  "OPENROUTER_API_KEY",
        "color":    "\033[38;5;141m",
    },
    {
        "id":       "mistral",
        "name":     "Codestral",
        "model":    "codestral-latest",
        "provider": "mistral",
        "role":     "code",
        "base_url": "https://api.mistral.ai/v1",
        "key_env":  "MISTRAL_API_KEY",
        "color":    "\033[38;5;210m",
    },
    {
        "id":       "hf",
        "name":     "Llama 3.3",
        "model":    "meta-llama/Llama-3.3-70B-Instruct",
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


def _call_agent(agent: dict, messages: list, results: dict, errors: dict):
    """Call one agent in a thread. Stores result or error by agent id."""
    try:
        client = _make_agent_client(agent)
        resp   = client.chat.completions.create(
            model=agent["model"],
            messages=messages,
            max_tokens=1500,
            temperature=0.7,
            stream=False,
        )
        if not resp.choices:
            errors[agent["id"]] = "no choices returned"
            return
        text = resp.choices[0].message.content
        if text and text.strip():
            results[agent["id"]] = text.strip()
        else:
            errors[agent["id"]] = "empty response"
    except Exception as e:
        errors[agent["id"]] = str(e)[:120]


def _judge(responses: dict, original_question: str) -> str:
    """
    Use the best available agent as judge to synthesize all responses
    into one definitive answer.
    """
    if len(responses) == 1:
        return next(iter(responses.values()))

    # Judge preference: Gemini > Groq > OpenRouter > Mistral > HF
    JUDGE_ORDER = ["gemini", "groq", "openrouter", "mistral", "hf"]
    judge_agent = None
    for jid in JUDGE_ORDER:
        candidate = next((a for a in AGENTS if a["id"] == jid), None)
        if candidate and os.getenv(candidate["key_env"]):
            judge_agent = candidate
            break

    if not judge_agent:
        return max(responses.values(), key=len)

    # Build synthesis prompt
    parts = []
    for aid, text in responses.items():
        agent = next((a for a in AGENTS if a["id"] == aid), None)
        label = f"{agent['name']} ({agent['role']})" if agent else aid
        parts.append(f"[{label}]:\n{text}")

    combined = "\n\n---\n\n".join(parts)

    judge_prompt = f"""You received responses from {len(responses)} AI models answering this:

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

    try:
        client = _make_agent_client(judge_agent)
        resp   = client.chat.completions.create(
            model=judge_agent["model"],
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=2048,
            temperature=0.3,
            stream=False,
        )
        if resp.choices and resp.choices[0].message.content:
            return resp.choices[0].message.content.strip()
    except Exception:
        pass

    # Judge failed — return the longest response
    return max(responses.values(), key=len)


# ── Animated progress display ─────────────────────────────────────────────────

class CouncilSpinner:
    FRAMES = ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"]

    def __init__(self, agents: list):
        self._agents  = agents
        self._done    = {}
        self._running = False
        self._thread  = None
        self._lock    = threading.Lock()

    def mark_done(self, agent_id: str, success: bool):
        with self._lock:
            self._done[agent_id] = success

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._render, daemon=True)
        self._thread.start()

    def _render(self):
        import itertools
        for f in itertools.cycle(self.FRAMES):
            if not self._running:
                break
            parts = []
            with self._lock:
                for a in self._agents:
                    col = a["color"]
                    if a["id"] in self._done:
                        icon = f"{GN}✓{R}" if self._done[a["id"]] else f"{RE}✗{R}"
                    else:
                        icon = f"{col}{f}{R}"
                    parts.append(f"{icon}{col}{a['name']}{R}")
            sys.stdout.write(f"\r  {('  ').join(parts)}  ")
            sys.stdout.flush()
            time.sleep(0.09)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        # Print final state
        parts = []
        for a in self._agents:
            col  = a["color"]
            icon = f"{GN}✓{R}" if self._done.get(a["id"]) else f"{RE}✗{R}"
            parts.append(f"{icon}{col}{a['name']}{R}")
        sys.stdout.write(f"\r  {'  '.join(parts)}\n")
        sys.stdout.flush()


# ── Main public function ──────────────────────────────────────────────────────

def council_ask(messages: list, user_question: str,
                show_individual: bool = False) -> str:
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
        _call_agent(agent, messages, results, errors)
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

    return _judge(results, user_question)
