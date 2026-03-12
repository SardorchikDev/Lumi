"""
◆ Council — Overpowered 5-agent parallel system for Lumi AI

New in this version:
  • Task classifier    — detects code/debug/analysis/creative/factual/design
  • Specialist prompts — each agent gets a custom system prompt for their strength
  • Lead agent         — strongest agent for task type gets extra authority
  • Confidence scoring — each agent self-rates 1–10, judge weights accordingly
  • Debate round       — if agents disagree, they see each other and argue first
  • Speed tiers        — fast agents (Gemini, Groq, Mistral) show first
  • Second-pass refine — judge reviews its own synthesis for gaps/errors
  • Council stats      — shows who contributed, confidence, timing, task type
  • Full fallback chain — only auth errors hard-stop; everything else tries next model
"""

import os
import re
import sys
import threading
import time

from openai import OpenAI
from src.utils.intelligence import classify_request

# ── ANSI ──────────────────────────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
DG = "\033[38;5;238m"
GN = "\033[38;5;114m"
RE = "\033[38;5;203m"
YE = "\033[38;5;179m"
GR = "\033[38;5;245m"
PU = "\033[38;5;141m"
CY = "\033[38;5;117m"
WH = "\033[97m"
MU = "\033[38;5;183m"

# ── Task types ────────────────────────────────────────────────────────────────
TASK_CODE     = "code"
TASK_ANALYSIS = "analysis"
TASK_CREATIVE = "creative"
TASK_FACTUAL  = "factual"
TASK_DEBUG    = "debug"
TASK_DESIGN   = "design"
TASK_GENERAL  = "general"

# ── Agent roster ──────────────────────────────────────────────────────────────
AGENTS = [
    {
        "id":       "gemini",
        "name":     "Gemini",
        "models":   [
            "gemini-3.1-pro-preview",         # most advanced
            "gemini-3-flash-preview",         # frontier-class
            "gemini-2.5-pro",                 # deepest reasoning, stable
            "gemini-2.5-pro-preview-06-05",   # adaptive thinking
            "gemini-2.5-flash",               # fast + smart
            "gemini-flash-latest",            # alias fallback
            "gemini-2.0-flash",               # stable fallback
        ],
        "provider": "gemini",
        "role":     "reasoning",
        "strengths": [TASK_FACTUAL, TASK_ANALYSIS, TASK_GENERAL],
        "tier":     "fast",
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
        "strengths": [TASK_ANALYSIS, TASK_DEBUG, TASK_FACTUAL],
        "tier":     "fast",
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
        "strengths": [TASK_GENERAL, TASK_CREATIVE, TASK_CODE],
        "tier":     "slow",
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
        "strengths": [TASK_CODE, TASK_DEBUG, TASK_DESIGN],
        "tier":     "fast",
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
        "strengths": [TASK_CREATIVE, TASK_GENERAL, TASK_FACTUAL],
        "tier":     "slow",
        "base_url": "https://router.huggingface.co/v1",
        "key_env":  "HF_TOKEN",
        "color":    "\033[38;5;179m",
    },
    {
        "id":       "github",
        "name":     "GPT-4o",
        "models":   [
            "gpt-4o",
            "DeepSeek-R1",
            "o1-mini",
            "DeepSeek-V3-0324",
            "Meta-Llama-3.1-70B-Instruct",
            "gpt-4o-mini",
        ],
        "provider": "github",
        "role":     "precision",
        "strengths": [TASK_CODE, TASK_FACTUAL, TASK_ANALYSIS, TASK_DEBUG],
        "tier":     "fast",
        "base_url": "https://models.inference.ai.azure.com",
        "key_env":  "GITHUB_API_KEY",
        "color":    "\033[38;5;252m",
    },
    {
        "id":       "cohere",
        "name":     "Command A",
        "models":   [
            "command-a-03-2025",
            "command-a-reasoning-08-2025",
            "command-r-plus-08-2024",
            "command-r-08-2024",
        ],
        "provider": "cohere",
        "role":     "language",
        "strengths": [TASK_CREATIVE, TASK_ANALYSIS, TASK_GENERAL, TASK_FACTUAL],
        "tier":     "slow",
        "base_url": "https://api.cohere.com/compatibility/v1",
        "key_env":  "COHERE_API_KEY",
        "color":    "\033[38;5;86m",
    },
    {
        "id":       "cloudflare",
        "name":     "Cloudflare",
        "models":   [
            "@cf/openai/gpt-oss-120b",
            "@cf/qwen/qwen3-30b-a3b-fp8",
            "qwen/qwq-32b",
            "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
            "@cf/meta/llama-3.3-70b-instruct-fp8",
            "@cf/openai/gpt-oss-20b",
            "@cf/meta/llama-3.2-3b-instruct",
        ],
        "provider":  "cloudflare",
        "role":      "diversity",
        "strengths": [TASK_GENERAL, TASK_CODE, TASK_FACTUAL],
        "tier":      "slow",
        "base_url":  "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        "key_env":   "CLOUDFLARE_API_KEY",
        "extra_env": "CLOUDFLARE_ACCOUNT_ID",   # both required
        "color":     "\033[38;5;208m",
    },
]

# ── Specialist system prompts ─────────────────────────────────────────────────
SPECIALIST_PROMPTS = {
    "gemini": (
        "You are Gemini — the reasoning and synthesis expert in this council.\n"
        "Excel at: deep accurate explanations, logical flow, factual nuance, big-picture thinking.\n"
        "Be thorough but not verbose. Think before you write."
    ),
    "groq": (
        "You are Kimi K2 — the structured analysis expert in this council.\n"
        "Excel at: step-by-step breakdowns, comparing options with tradeoffs, root-cause analysis.\n"
        "Be direct and structured. Use headers/lists where they help clarity."
    ),
    "openrouter": (
        "You are GPT-OSS — the breadth and creativity expert in this council.\n"
        "Excel at: wide knowledge, lateral thinking, creative solutions, covering angles others miss.\n"
        "Think broadly. Challenge assumptions."
    ),
    "mistral": (
        "You are Codestral — the code and technical precision expert in this council.\n"
        "Excel at: complete working code, error handling, best practices, debugging root causes.\n"
        "Write code that works on the first try. No placeholders. No stubs."
    ),
    "hf": (
        "You are Llama 3.3 — the clarity and communication expert in this council.\n"
        "Excel at: simple accessible explanations, concrete examples, analogies, engaging writing.\n"
        "Write like explaining to a smart friend, not a textbook."
    ),
    "github": (
        "You are GPT-4o — the precision and reliability expert in this council.\n"
        "Excel at: factual accuracy, rigorous reasoning, clean concise code, catching subtle bugs.\n"
        "Be direct and authoritative. Prioritize correctness above all else."
    ),
    "cohere": (
        "You are Command A — the language and nuance expert in this council.\n"
        "Excel at: precise wording, well-structured arguments, nuanced analysis, and clear explanations.\n"
        "Bring depth and clarity. Notice what others miss in the phrasing of the question."
    ),
    "cloudflare": (
        "You are Cloudflare AI — the diversity and independence expert in this council.\n"
        "Excel at: providing a genuinely independent perspective from a different model stack.\n"
        "Be direct and efficient. Your unique model mix brings views others may not surface."
    ),
}

TASK_PROMPTS = {
    TASK_CODE:     "\n\nCODE task: write complete, working code with error handling and type hints.",
    TASK_DEBUG:    "\n\nDEBUG task: find the root cause (not symptoms), explain WHY it breaks, show the fix.",
    TASK_ANALYSIS: "\n\nANALYSIS task: structured breakdown, weigh evidence, clear conclusions with reasoning.",
    TASK_CREATIVE: "\n\nCREATIVE task: original, engaging, vivid. Do not be generic.",
    TASK_FACTUAL:  "\n\nFACTUAL task: accuracy above all. If uncertain say so clearly. No hallucination.",
    TASK_DESIGN:   "\n\nDESIGN task: discuss tradeoffs, scalability, real-world constraints.",
    TASK_GENERAL:  "",
}

LEAD_AGENTS = {
    TASK_CODE:     "mistral",
    TASK_DEBUG:    "github",
    TASK_ANALYSIS: "groq",
    TASK_CREATIVE: "hf",
    TASK_FACTUAL:  "github",
    TASK_DESIGN:   "mistral",
    TASK_GENERAL:  "gemini",
}

LEAD_EXTENSION = (
    "\n\nYou are the LEAD agent for this task type. Your answer carries extra weight in synthesis. "
    "Be especially thorough and authoritative."
)

CONFIDENCE_SUFFIX = (
    "\n\n---\n"
    "At the very end of your response, on its own line, write exactly:\n"
    "CONFIDENCE: X/10\n"
    "Where X is your honest confidence (1=guessing, 10=certain). Just the line, no explanation."
)

# ── Task classifier ────────────────────────────────────────────────────────────
_CODE_KW     = ["code","function","class","bug","error","debug","fix","implement",
                "script","program","api","endpoint","database","query","sql","html",
                "css","javascript","typescript","python","rust","go","bash","regex",
                "algorithm","async","await","hook","component","refactor","test",
                "compile","build","deploy","git","write a","create a","build a"]
_DEBUG_KW    = ["error","bug","crash","exception","traceback","fails","broken",
                "not working","doesn't work","why does","what's wrong","fix this",
                "stack trace","undefined","null","typeerror","attributeerror"]
_ANALYSIS_KW = ["analyze","compare","difference","vs","versus","pros and cons",
                "tradeoffs","evaluate","assess","review","critique","breakdown",
                "explain why","how does","what is the best","should i use"]
_CREATIVE_KW = ["write","story","poem","essay","blog","draft","compose","creative",
                "imagine","fiction","narrative","dialogue","marketing","email",
                "tweet","post","caption","describe"]
_DESIGN_KW   = ["architecture","design","structure","pattern","schema",
                "database design","api design","microservice","scalable",
                "infrastructure","pipeline","data model"]


def classify_task(question: str) -> str:
    q = question.lower()
    scores = {
        TASK_CODE:     sum(1 for w in _CODE_KW     if w in q),
        TASK_DEBUG:    sum(1 for w in _DEBUG_KW    if w in q),
        TASK_ANALYSIS: sum(1 for w in _ANALYSIS_KW if w in q),
        TASK_CREATIVE: sum(1 for w in _CREATIVE_KW if w in q),
        TASK_DESIGN:   sum(1 for w in _DESIGN_KW   if w in q),
    }
    if scores[TASK_DEBUG] >= 2:
        return TASK_DEBUG
    best  = max(scores, key=scores.get)
    score = scores[best]
    if score < 2:
        return TASK_FACTUAL if "?" in question else TASK_GENERAL
    return best


def _extract_confidence(text: str) -> "tuple[str, int]":
    m = re.search(r"CONFIDENCE:\s*(\d+)\s*/\s*10", text, re.IGNORECASE)
    if m:
        score = max(1, min(10, int(m.group(1))))
        return text[:m.start()].rstrip(), score
    return text, 7


# ── Fallback lists ────────────────────────────────────────────────────────────
_FALLBACK_ERRORS = (
    "429","rate_limit","quota","limit: 0","resource_exhausted","overloaded",
    "503","502","500","504","524","model_not_found","404","decommissioned",
    "no endpoints","unavailable","not found","context length","content policy",
    "moderation","timeout","timed out","connection","network","currently loading",
    "loading","warming up","too many requests","capacity","busy",
    "model is not available","model unavailable","does not exist","invalid model",
    "internal server","bad gateway","service unavailable",
)
_HARD_STOP_ERRORS = (
    "401","unauthorized","invalid api key","invalid_api_key",
    "authentication","permission denied","forbidden","403",
)

# ── Shared state ──────────────────────────────────────────────────────────────
_agent_used_model: dict = {}
_agent_confidence: dict = {}
_agent_timing:     dict = {}


def _get_available_agents() -> list:
    def _available(a: dict) -> bool:
        if not os.getenv(a["key_env"]):
            return False
        if a.get("extra_env") and not os.getenv(a["extra_env"]):
            return False
        return True
    return [a for a in AGENTS if _available(a)]


def _make_client(agent: dict) -> OpenAI:
    base_url = agent["base_url"]
    # Cloudflare needs account ID resolved at runtime
    if agent["provider"] == "cloudflare":
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
    return OpenAI(api_key=os.getenv(agent["key_env"]), base_url=base_url)


# ── Core agent call ────────────────────────────────────────────────────────────
def _call_agent(agent: dict, messages: list, results: dict, errors: dict,
                spinner=None, task_type: str = TASK_GENERAL, lead_id: str = ""):
    t0  = time.time()
    aid = agent["id"]

    # Build specialist system prompt
    sys_content = SPECIALIST_PROMPTS.get(aid, "")
    sys_content += TASK_PROMPTS.get(task_type, "")
    if aid == lead_id:
        sys_content += LEAD_EXTENSION

    # Rebuild messages with specialist system prompt
    augmented = []
    replaced  = False
    for m in messages:
        if m["role"] == "system" and not replaced:
            augmented.append({"role": "system", "content": sys_content + "\n\n" + m["content"]})
            replaced = True
        else:
            augmented.append(m)
    if not replaced:
        augmented = [{"role": "system", "content": sys_content}] + list(messages)

    # Inject confidence request into last user message
    final = []
    injected = False
    for m in reversed(augmented):
        if m["role"] == "user" and not injected:
            final.insert(0, {"role": "user", "content": m["content"] + CONFIDENCE_SUFFIX})
            injected = True
        else:
            final.insert(0, m)

    client = _make_client(agent)
    models = agent.get("models", [agent.get("model", "")])
    last_error = ""

    for model in models:
        if spinner:
            spinner.set_model(aid, model.split("/")[-1])
        try:
            resp = client.chat.completions.create(
                model=model, messages=final,
                max_tokens=2048, temperature=0.7, stream=False,
            )
            if not resp.choices:
                last_error = "no choices"
                continue
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                last_error = "empty response"
                continue
            clean, conf = _extract_confidence(text)
            results[aid]           = clean
            _agent_used_model[aid] = model.split("/")[-1]
            _agent_confidence[aid] = conf
            _agent_timing[aid]     = round(time.time() - t0, 1)
            return
        except Exception as e:
            last_error = str(e)[:200]
            if any(x in last_error.lower() for x in _HARD_STOP_ERRORS):
                break
            continue

    errors[aid] = last_error


# ── Disagreement detector ──────────────────────────────────────────────────────
def _detect_disagreement(responses: dict) -> bool:
    if len(responses) < 3:
        return False
    texts = list(responses.values())
    pos = sum(1 for t in texts if re.search(r'\b(yes|correct|should|recommend|use)\b',   t[:300], re.I))
    neg = sum(1 for t in texts if re.search(r'\b(no|incorrect|avoid|don\'t|shouldn\'t)\b', t[:300], re.I))
    if pos >= 2 and neg >= 1: return True
    if neg >= 2 and pos >= 1: return True
    # Check if leading content is totally different across agents
    sets = [set(t.lower().split()[:60]) for t in texts]
    overlap_avg = sum(len(sets[0] & s) for s in sets[1:]) / max(len(sets) - 1, 1)
    if overlap_avg < 8 and len(texts) >= 3:
        return True
    return False


# ── Debate round ──────────────────────────────────────────────────────────────
def _debate_round(responses: dict, question: str, available: list) -> dict:
    peer_parts = []
    for aid, text in responses.items():
        agent = next((a for a in AGENTS if a["id"] == aid), None)
        label = f"{agent['name']} ({agent['role']})" if agent else aid
        peer_parts.append(f"[{label}]:\n{text[:500]}...")
    peer_summary = "\n\n---\n\n".join(peer_parts)

    debate_results: dict = {}

    def _run(agent):
        if agent["id"] not in responses:
            return
        my_prev = responses[agent["id"]]
        prompt  = (
            f'You previously answered: "{question}"\n\n'
            f"Your answer:\n{my_prev}\n\n"
            f"Other agents said:\n{peer_summary}\n\n"
            "Revise your answer if any agent made a better point. "
            "If you still agree with your original, restate it concisely. "
            "Do not mention other agents in your final answer."
        )
        client = _make_client(agent)
        for model in agent["models"][:2]:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SPECIALIST_PROMPTS.get(agent["id"], "")},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=1200, temperature=0.4, stream=False,
                )
                if resp.choices and resp.choices[0].message.content:
                    text = resp.choices[0].message.content.strip()
                    if text:
                        clean, conf = _extract_confidence(text)
                        debate_results[agent["id"]] = clean
                        _agent_confidence[agent["id"]] = min(10, conf + 1)
                        return
            except Exception:
                continue

    threads = [threading.Thread(target=_run, args=(a,), daemon=True)
               for a in available if a["id"] in responses]
    for t in threads: t.start()
    for t in threads: t.join(timeout=18)

    return {**responses, **debate_results}


# ── Judge ─────────────────────────────────────────────────────────────────────
_JUDGE_ORDER = ["gemini", "github", "groq", "openrouter", "mistral", "hf"]

TASK_JUDGE_NOTES = {
    TASK_CODE:     "CODE question — prioritize the most complete and correct code. Merge the best implementations.",
    TASK_DEBUG:    "DEBUG question — prioritize the most accurate root-cause analysis and clearest fix.",
    TASK_ANALYSIS: "ANALYSIS question — prioritize the most rigorous reasoning and tradeoff coverage.",
    TASK_CREATIVE: "CREATIVE question — prioritize the most original and engaging writing.",
    TASK_FACTUAL:  "FACTUAL question — weight higher-confidence answers more. Flag disagreements explicitly.",
    TASK_DESIGN:   "DESIGN question — prioritize practical architecture with real tradeoffs.",
    TASK_GENERAL:  "Weight answers by confidence score.",
}


def _get_judge(available: list, task_type: str):
    lead_id = LEAD_AGENTS.get(task_type, "gemini")
    lead    = next((a for a in available if a["id"] == lead_id), None)
    if lead:
        return lead, _make_client(lead), lead["models"][0]
    for jid in _JUDGE_ORDER:
        a = next((x for x in available if x["id"] == jid), None)
        if a:
            return a, _make_client(a), a["models"][0]
    return None, None, None


def _build_judge_prompt(responses: dict, question: str, task_type: str,
                        had_debate: bool) -> str:
    parts = []
    for aid, text in responses.items():
        agent = next((a for a in AGENTS if a["id"] == aid), None)
        label = f"{agent['name']} ({agent['role']})" if agent else aid
        conf  = _agent_confidence.get(aid, 7)
        parts.append(f"[{label} — confidence {conf}/10]:\n{text}")
    combined   = "\n\n---\n\n".join(parts)
    debate_tag = "\nNote: agents already debated and revised based on peer review.\n" if had_debate else ""
    note       = TASK_JUDGE_NOTES.get(task_type, "")
    return (
        f'You are the synthesis judge for {len(responses)} AI experts.\n\n'
        f'Question: "{question}"\n\n'
        f"{note}{debate_tag}\n\n"
        f"Expert responses:\n\n{combined}\n\n---\n\n"
        "Synthesize ONE definitive best answer.\n"
        "Rules:\n"
        "- Weight higher-confidence answers more heavily\n"
        "- Take the best/most complete code if code is involved\n"
        "- If experts agree: write the consensus cleanly\n"
        "- If they disagree: pick the best-reasoned position\n"
        "- Do NOT mention agents, confidence scores, or the synthesis process\n"
        "- Write as if YOU are answering directly — confident and complete\n"
        "- Match format to task: code block for code, prose for explanations\n\n"
        "Write the best possible answer now."
    )


def _refine(synthesis: str, question: str, client: OpenAI, model: str) -> str:
    prompt = (
        f'You wrote this answer to: "{question}"\n\n'
        f"Your answer:\n{synthesis}\n\n"
        "Self-review:\n"
        "- Anything factually wrong?\n"
        "- Any important part missing?\n"
        "- Is the code complete and correct (if code was involved)?\n"
        "- Is the explanation clear?\n\n"
        "If everything is good, respond with exactly: LGTM\n"
        "If something needs fixing, respond with the FULL corrected answer only."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500, temperature=0.2, stream=False,
        )
        if resp.choices:
            rev = (resp.choices[0].message.content or "").strip()
            if rev and rev != "LGTM" and len(rev) > 30:
                return rev
    except Exception:
        pass
    return synthesis


def _judge_stream(responses: dict, question: str, task_type: str,
                  had_debate: bool, do_refine: bool):
    if len(responses) == 1:
        yield next(iter(responses.values()))
        return

    available = _get_available_agents()
    judge, client, model = _get_judge(available, task_type)
    if not judge:
        yield max(responses.values(), key=len)
        return

    prompt    = _build_judge_prompt(responses, question, task_type, had_debate)
    full_text = ""
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000, temperature=0.3, stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                full_text += delta
                yield delta
    except Exception:
        yield max(responses.values(), key=len)
        return

    if do_refine and len(full_text) > 80:
        refined = _refine(full_text, question, client, model)
        if refined != full_text:
            yield "\n\n__REFINED__\n\n" + refined


def _judge_sync(responses: dict, question: str, task_type: str) -> str:
    if len(responses) == 1:
        return next(iter(responses.values()))
    available = _get_available_agents()
    judge, client, model = _get_judge(available, task_type)
    if not judge:
        return max(responses.values(), key=len)
    prompt = _build_judge_prompt(responses, question, task_type, False)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000, temperature=0.3, stream=False,
        )
        if resp.choices and resp.choices[0].message.content:
            synthesis = resp.choices[0].message.content.strip()
            return _refine(synthesis, question, client, model)
    except Exception:
        pass
    return max(responses.values(), key=len)


# ── Stats formatter ────────────────────────────────────────────────────────────
def format_council_stats(responses: dict, task_type: str,
                         had_debate: bool = False) -> str:
    parts = []
    for aid, _ in responses.items():
        agent = next((a for a in AGENTS if a["id"] == aid), None)
        if not agent:
            continue
        conf      = _agent_confidence.get(aid, "?")
        t         = _agent_timing.get(aid, "?")
        is_lead   = LEAD_AGENTS.get(task_type) == aid
        lead_tag  = f" {GN}★{R}" if is_lead else ""
        parts.append(
            f"{agent['color']}{agent['name']}{R}"
            f"{DG}({conf}/10·{t}s){R}{lead_tag}"
        )
    debate_tag = f"  {YE}[debated]{R}" if had_debate else ""
    task_tag   = f"  {MU}[{task_type}]{R}"
    return "  ".join(parts) + debate_tag + task_tag


# ── Spinner ───────────────────────────────────────────────────────────────────
class CouncilSpinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, agents: list):
        self._agents  = agents
        self._status  = {a["id"]: "spin" for a in agents}
        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None
        self._frame   = 0

    def mark_done(self, agent_id: str, success: bool):
        with self._lock:
            self._status[agent_id] = "ok" if success else "fail"

    def set_model(self, agent_id: str, model_short: str):
        pass  # intentionally silent

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            self._render()
            time.sleep(0.08)
            self._frame = (self._frame + 1) % len(self.FRAMES)

    @staticmethod
    def _strip_ansi(s):
        return re.sub(r"\033\[[0-9;]*m", "", s)

    def _cols(self):
        try:    return os.get_terminal_size().columns - 2
        except: return 100

    def _render(self):
        with self._lock:
            parts = []
            for a in self._agents:
                aid, color, name = a["id"], a["color"], a["name"]
                s = self._status.get(aid, "spin")
                if   s == "ok":   parts.append(f"{GN}✓{R}{color}{name}{R}")
                elif s == "fail": parts.append(f"{RE}✗{R}{GR}{name}{R}")
                else:
                    f = self.FRAMES[self._frame]
                    parts.append(f"{YE}{f}{R}{color}{name}{R}")
            line = "  " + "   ".join(parts)
        raw = self._strip_ansi(line)
        if len(raw) > self._cols():
            line = line[:self._cols()]
        sys.stdout.write("\r" + line + "  ")
        sys.stdout.flush()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        try:    cols = os.get_terminal_size().columns
        except: cols = 100
        sys.stdout.write("\r" + " " * cols + "\r")
        sys.stdout.flush()
        # Final static line
        with self._lock:
            parts = []
            for a in self._agents:
                aid, color, name = a["id"], a["color"], a["name"]
                s = self._status.get(aid)
                if   s == "ok":   parts.append(f"{GN}✓{color}{name}{R}")
                elif s == "fail": parts.append(f"{RE}✗{GR}{name}{R}")
                else:             parts.append(f"{DG}—{GR}{name}{R}")
        print("  " + "   ".join(parts))


# ── Main entry point ───────────────────────────────────────────────────────────
def council_ask(messages: list, user_question: str,
                show_individual: bool = False,
                stream: bool = True,
                debate: bool = True,
                refine: bool = True,
                silent: bool = False,
                agent_callback=None,
                client=None,
                model: str = "gemini-2.0-flash-lite"):
    """
    Full overpowered council call.

    stream=True        → returns a generator yielding string chunks
    stream=False       → returns (synthesis_str, stats_str)
    silent=True        → suppress all terminal output (for TUI mode)
    agent_callback     → called as agent_callback(aid, success, conf, timing)
                         when each agent finishes (useful for TUI sidebar updates)
    """
    _agent_used_model.clear()
    _agent_confidence.clear()
    _agent_timing.clear()

    available = _get_available_agents()
    if not available:
        raise RuntimeError(
            "No API keys found. Set at least one of: "
            "GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, HF_TOKEN"
        )

    # ── Classification & Routing ──────────────────────────────────────────────
    task_type = "general"
    routing   = []

    if client:
        try:
            cls = classify_request(user_question, client, model)
            raw_intent = cls.get("intent", "general")
            # Map LLM intent to internal task types
            intent_map = {
                "coding":   TASK_CODE,
                "debug":    TASK_DEBUG,
                "creative": TASK_CREATIVE,
                "analysis": TASK_ANALYSIS,
                "search":   TASK_FACTUAL,
                "chat":     TASK_GENERAL,
            }
            task_type = intent_map.get(raw_intent, TASK_GENERAL)
            routing   = cls.get("routing", [])
        except Exception:
            task_type = classify_task(user_question)
    else:
        task_type = classify_task(user_question)

    # Filter agents if routing is specific
    if routing:
        # always keep reasoning as anchor
        filtered = [a for a in available if a["role"] in routing or a["role"] == "reasoning"]
        if filtered:
            available = filtered

    lead_id = LEAD_AGENTS.get(task_type, "gemini")

    results: dict = {}
    errors:  dict = {}

    if not silent:
        spinner = CouncilSpinner(available)
        spinner.start()
    else:
        spinner = None

    # ── Parallel agent calls ──────────────────────────────────────────────────
    def _wrap(agent):
        _call_agent(agent, messages, results, errors, spinner, task_type, lead_id)
        success = agent["id"] in results
        if spinner:
            spinner.mark_done(agent["id"], success)
        if agent_callback:
            aid  = agent["id"]
            conf = str(_agent_confidence.get(aid, ""))
            t    = str(_agent_timing.get(aid, ""))
            agent_callback(aid, success, conf, t)

    fast = [a for a in available if a.get("tier") == "fast"]
    slow = [a for a in available if a.get("tier") != "fast"]

    fast_threads = [threading.Thread(target=_wrap, args=(a,), daemon=True) for a in fast]
    slow_threads = [threading.Thread(target=_wrap, args=(a,), daemon=True) for a in slow]

    for t in fast_threads + slow_threads: t.start()
    for t in fast_threads: t.join(timeout=22)
    for t in slow_threads: t.join(timeout=28)

    if spinner:
        spinner.stop()

    if not results:
        raise RuntimeError("All council agents failed — check your API keys and connection.")

    if errors and not silent:
        print(f"  {YE}▲  unavailable: {', '.join(errors)}{R}")

    # ── Debate round ──────────────────────────────────────────────────────────
    had_debate = False
    if debate and len(results) >= 3 and _detect_disagreement(results):
        if not silent:
            print(f"\n  {YE}⚔  disagreement detected — debating...{R}")
        results    = _debate_round(results, user_question, available)
        had_debate = True

    # ── Show individual responses ─────────────────────────────────────────────
    if show_individual and not silent:
        print()
        for aid, text in results.items():
            agent = next((a for a in AGENTS if a["id"] == aid), None)
            color = agent["color"] if agent else ""
            name  = agent["name"]  if agent else aid
            conf  = _agent_confidence.get(aid, "?")
            lines = text.split("\n")
            print(f"\n  {color}{B}{name}{R}  {DG}({conf}/10){R}")
            for line in lines[:10]:
                print(f"  {GR}{line}{R}")
            if len(lines) > 10:
                print(f"  {DG}... (+{len(lines)-10} more lines){R}")

    n = len(results)
    if not silent:
        print(f"\n  {DG}synthesizing {n} response{'s' if n > 1 else ''}  [{task_type}]"
              f"{'  [debated]' if had_debate else ''}{R}\n")

    if stream:
        def _gen():
            for chunk in _judge_stream(results, user_question, task_type, had_debate, refine):
                yield chunk
            yield "\n\n__STATS__\n" + format_council_stats(results, task_type, had_debate)
        return _gen()

    synthesis = _judge_sync(results, user_question, task_type)
    return synthesis, format_council_stats(results, task_type, had_debate)
