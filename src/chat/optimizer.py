"""Context packing, retrieval, routing, and telemetry for Lumi requests."""

from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from src.agents.task_memory import render_task_memory_context
from src.chat.providers import get_provider_spec, provider_context_limit, provider_model_hints, provider_supports

_TOKEN_ESTIMATE_LOCK = threading.Lock()
_AVG_CHARS_PER_TOKEN = 4.0
_AVG_WORDS_PER_TOKEN = 0.77


def _record_token_sample(text: str, tokens: int) -> None:
    global _AVG_CHARS_PER_TOKEN, _AVG_WORDS_PER_TOKEN
    if not text or tokens <= 0:
        return
    char_ratio = max(1.0, len(text) / tokens)
    word_ratio = max(0.2, len(text.split()) / tokens)
    with _TOKEN_ESTIMATE_LOCK:
        _AVG_CHARS_PER_TOKEN = (_AVG_CHARS_PER_TOKEN * 0.85) + (char_ratio * 0.15)
        _AVG_WORDS_PER_TOKEN = (_AVG_WORDS_PER_TOKEN * 0.85) + (word_ratio * 0.15)


def estimate_tokens(text: str) -> int:
    text = text or ""
    with _TOKEN_ESTIMATE_LOCK:
        chars_per_token = _AVG_CHARS_PER_TOKEN
        words_per_token = _AVG_WORDS_PER_TOKEN
    char_estimate = len(text) / chars_per_token
    word_estimate = len(text.split()) / words_per_token
    return max(1, math.ceil(max(char_estimate, word_estimate)))


def estimate_message_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(str(message.get("content", ""))) + 4 for message in messages)


def model_context_limit(model: str, provider: str = "") -> int:
    lowered = (model or "").lower()
    limits = (
        ("gemini-2.5-pro", 1_000_000),
        ("gemini-2.5-flash", 1_000_000),
        ("gemini", 1_000_000),
        ("council", 256_000),
        ("gpt-5", 256_000),
        ("gpt-4", 128_000),
        ("gpt-oss", 131_072),
        ("openai/gpt-oss", 131_072),
        ("qwen3-coder-480b", 262_000),
        ("qwen3-next", 262_000),
        ("llama-4", 128_000),
        ("llama-3.3", 128_000),
        ("llama", 128_000),
        ("deepseek", 128_000),
        ("codestral", 256_000),
        ("mistral-large", 128_000),
        ("mistral", 32_000),
        ("kimi", 131_072),
        ("qwen", 32_768),
        ("phi", 128_000),
        ("default", 8_192),
    )
    model_limit = next((value for needle, value in limits if needle in lowered), limits[-1][1])
    if not provider:
        return model_limit
    provider_limit = provider_context_limit(provider)
    if provider_supports(provider, "long_context"):
        provider_limit = max(provider_limit, 256_000)
    return max(model_limit, provider_limit)


def infer_request_mode(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ("/review", "code review", "review this", "security review")):
        return "review"
    if any(token in lowered for token in ("/agent", "fix failing", "traceback", "stack trace", "assert", "test failed", "mypy", "ruff")):
        return "debug"
    if any(token in lowered for token in ("/search", "/web", "search for", "web page", "url:", "page content")):
        return "search"
    if any(token in lowered for token in ("/tl;dr", "summarize", "summary", "one sentence")):
        return "summary"
    if any(token in lowered for token in ("/edit", "/file", "/project", "write code", "fix code", "python", "javascript", "typescript", "bug", "refactor")):
        return "code"
    if any(token in lowered for token in ("create a folder", "create a file", "scaffold", "project loaded", "<file path=")):
        return "files"
    return "chat"


MODE_RESPONSE_BUDGETS = {
    "chat": 900,
    "summary": 220,
    "search": 900,
    "code": 1400,
    "files": 1200,
    "review": 1600,
    "debug": 1400,
}


MODE_PROMPT_SUFFIXES = {
    "chat": (
        "## Reply shape\n"
        "- Be concise by default.\n"
        "- Prefer direct answers over scene-setting.\n"
        "- Keep continuity with the active task if one exists.\n"
    ),
    "summary": (
        "## Reply shape\n"
        "- Summarize only the essential result.\n"
        "- Prefer one short paragraph or a single sentence when asked.\n"
    ),
    "search": (
        "## Reply shape\n"
        "- Answer from the supplied context only.\n"
        "- Be explicit about uncertainty or missing facts.\n"
        "- Prefer a short synthesis over copying raw context.\n"
    ),
    "code": (
        "## Reply shape\n"
        "- Prefer concrete edits, commands, or code over long theory.\n"
        "- Preserve existing repo conventions.\n"
        "- If reviewing code, mention risks before polish.\n"
    ),
    "files": (
        "## Reply shape\n"
        "- Be explicit about files, folders, and paths.\n"
        "- Prefer exact file names and minimal ambiguity.\n"
    ),
    "review": (
        "## Reply shape\n"
        "- Findings first, ordered by severity.\n"
        "- Include concrete bugs, regressions, and missing verification.\n"
        "- Keep overview secondary.\n"
    ),
    "debug": (
        "## Reply shape\n"
        "- Start from the root cause.\n"
        "- Use failing checks or tracebacks as the primary signal.\n"
        "- Prefer the smallest correct fix and mention how to verify it.\n"
    ),
}


def augment_system_prompt(base_prompt: str, mode: str, failure_digest: str = "") -> str:
    suffix = MODE_PROMPT_SUFFIXES.get(mode, MODE_PROMPT_SUFFIXES["chat"])
    if failure_digest:
        suffix += "\n## Recent failures\n" + failure_digest.strip() + "\n"
    return (base_prompt.rstrip() + "\n\n" + suffix).strip()


def route_model(current_model: str, available_models: list[str], mode: str, provider: str = "") -> str:
    if not available_models:
        return current_model
    if current_model == "council":
        current_model = available_models[0]

    lowered_models = {model: model.lower() for model in available_models}
    current_lower = (current_model or "").lower()

    helper_needles = ("lite", "mini", "flash", "small", "8b", "instant")
    heavy_needles = ("pro", "70b", "120b", "72b", "large", "coder", "reasoning", "r1", "4o", "3.3")
    provider_helper_needles, provider_heavy_needles = provider_model_hints(provider)
    helper_needles = tuple(dict.fromkeys(helper_needles + provider_helper_needles))
    heavy_needles = tuple(dict.fromkeys(heavy_needles + provider_heavy_needles))

    def has_signal(lowered: str, needles: tuple[str, ...]) -> bool:
        parts = set(re.split(r"[^a-z0-9]+", lowered))
        return any((needle in parts) or (needle == "3.3" and "3.3" in lowered) for needle in needles)

    if mode in {"summary", "search"}:
        for model, lowered in lowered_models.items():
            if has_signal(lowered, helper_needles):
                return model
    if mode in {"code", "review", "debug", "files"}:
        for model, lowered in lowered_models.items():
            if has_signal(lowered, heavy_needles):
                return model
    if provider:
        spec = get_provider_spec(provider)
        if spec and "fast" in spec.capabilities and mode in {"summary", "search"}:
            for model, lowered in lowered_models.items():
                if any(token in lowered for token in ("flash", "instant", "mini")):
                    return model
    for model in available_models:
        if lowered_models[model] == current_lower:
            return model
    return available_models[0]


def _keywords(text: str) -> list[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "what", "when",
        "where", "there", "about", "your", "have", "just", "then", "they", "them",
    }
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_./-]{2,}", (text or "").lower())
    return [word for word in words if word not in stop][:16]


def _extract_symbols(text: str) -> list[str]:
    matches = re.findall(r"^\s*(?:def|class|function|const|let|var|type|interface)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M)
    return matches[:12]


def _extract_imports(text: str) -> list[str]:
    imports = re.findall(r"^\s*(?:from\s+([A-Za-z0-9_./]+)\s+import|import\s+([A-Za-z0-9_., ]+))", text, re.M)
    flat: list[str] = []
    for left, right in imports[:12]:
        chunk = left or right
        if chunk:
            flat.extend(part.strip() for part in chunk.split(",") if part.strip())
    return flat[:12]


def _compact_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return " | ".join(lines[:5])[:240]


def _chunk_text(content: str, *, chunk_chars: int = 900, overlap_chars: int = 160) -> list[str]:
    if not content.strip():
        return []
    lines = content.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) > chunk_chars:
            chunks.append(current)
            carry = current[-overlap_chars:] if overlap_chars and len(current) > overlap_chars else current
            current = carry + line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks[:64] or [content[:chunk_chars]]


@dataclass(frozen=True)
class CachedContext:
    key: str
    label: str
    kind: str
    content: str
    summary: str
    symbols: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    snippets: tuple[str, ...] = ()


class ContextCache:
    def __init__(self) -> None:
        self._docs: dict[str, CachedContext] = {}
        self._lock = threading.Lock()

    def remember_text(self, key: str, label: str, content: str, *, kind: str = "text") -> None:
        summary = _compact_summary(content)
        doc = CachedContext(
            key=key,
            label=label,
            kind=kind,
            content=content,
            summary=summary,
            symbols=tuple(_extract_symbols(content)),
            imports=tuple(_extract_imports(content)),
            snippets=(),
        )
        with self._lock:
            self._docs[key] = doc

    def remember_file(self, path: str | Path, content: str) -> None:
        resolved = str(Path(path))
        self.remember_text(f"file:{resolved}", resolved, content, kind="file")

    def remember_project(self, root: str | Path, files: list[tuple[str, str]]) -> None:
        root_path = str(Path(root))
        combined = []
        for rel_path, content in files[:20]:
            combined.append(f"{rel_path}\n{_compact_summary(content)}")
            self.remember_text(f"file:{root_path}:{rel_path}", rel_path, content, kind="project-file")
        if combined:
            self.remember_text(
                f"project:{root_path}",
                root_path,
                "\n".join(combined),
                kind="project",
            )

    def retrieve(self, query: str, *, limit: int = 3, max_chars: int = 2200) -> list[CachedContext]:
        words = _keywords(query)
        with self._lock:
            docs = list(self._docs.values())
        if not docs:
            return []
        scored: list[tuple[int, CachedContext, tuple[str, ...]]] = []
        for doc in docs:
            haystack = f"{doc.label}\n{doc.summary}\n{' '.join(doc.symbols)}\n{' '.join(doc.imports)}".lower()
            base_score = 0
            for word in words:
                if word in doc.label.lower():
                    base_score += 4
                if word in haystack:
                    base_score += 2
            chunk_hits: list[tuple[int, str]] = []
            for chunk in _chunk_text(doc.content, chunk_chars=min(900, max_chars), overlap_chars=160):
                score = base_score
                lowered_chunk = chunk.lower()
                for word in words:
                    if word in lowered_chunk:
                        score += 3 if "." in word or "/" in word else 2
                if score > 0:
                    chunk_hits.append((score, chunk))
            if chunk_hits:
                chunk_hits.sort(key=lambda item: item[0], reverse=True)
                snippets = tuple(chunk[: max_chars // 2].rstrip() for _, chunk in chunk_hits[:2])
                scored.append((chunk_hits[0][0], doc, snippets))
        scored.sort(key=lambda item: (-item[0], item[1].label))
        picked = scored[:limit]
        trimmed: list[CachedContext] = []
        for _, doc, snippets in picked:
            merged = "\n\n".join(snippets)[:max_chars].rstrip()
            trimmed.append(
                CachedContext(
                    key=doc.key,
                    label=doc.label,
                    kind=doc.kind,
                    content=merged,
                    summary=doc.summary,
                    symbols=doc.symbols,
                    imports=doc.imports,
                    snippets=snippets,
                )
            )
        return trimmed


def _extract_failed_checks(history: list[dict[str, str]]) -> list[str]:
    failures: list[str] = []
    for message in reversed(history[-8:]):
        content = str(message.get("content", ""))
        lowered = content.lower()
        if any(token in lowered for token in ("traceback", "assert", "failed", "error:", "mypy", "ruff")):
            failures.append(_compact_summary(content))
    return failures[:3]


def _message_relevance(message: dict[str, str], keywords: list[str]) -> int:
    content = str(message.get("content", "")).lower()
    if not content:
        return 0
    score = 0
    for keyword in keywords:
        if keyword in content:
            score += 3 if "." in keyword or "/" in keyword else 2
    if message.get("role") == "user":
        score += 1
    if re.search(r"/[a-zA-Z0-9._-]+", content):
        score += 1
    if re.search(r"[\w./-]+\.[A-Za-z0-9]+", content):
        score += 1
    return score


def structured_history_summary(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    older = [msg for msg in history if isinstance(msg.get("content"), str)]
    user_goals = []
    files = set()
    commands = set()
    unresolved = []
    for message in older:
        content = message["content"]
        if message.get("role") == "user" and content.strip():
            user_goals.append(content.strip().splitlines()[0][:120])
        for file_match in re.findall(r"[\w./-]+\.[A-Za-z0-9]+", content):
            files.add(file_match)
        for cmd_match in re.findall(r"/[a-zA-Z0-9._-]+", content):
            commands.add(cmd_match)
        if any(token in content.lower() for token in ("todo", "need to", "follow up", "next step", "failing", "error")):
            unresolved.append(content.strip().splitlines()[0][:120])

    lines = ["Conversation summary:"]
    if user_goals:
        lines.append("- goals: " + " | ".join(user_goals[-3:]))
    if files:
        lines.append("- files: " + ", ".join(sorted(files)[:8]))
    if commands:
        lines.append("- commands: " + ", ".join(sorted(commands)[:6]))
    if unresolved:
        lines.append("- unresolved: " + " | ".join(unresolved[-2:]))
    return "\n".join(lines) if len(lines) > 1 else ""


@dataclass(frozen=True)
class BudgetSnapshot:
    model: str
    mode: str
    context_limit: int
    response_budget: int
    prompt_budget: int
    system_tokens: int
    history_tokens: int
    summary_tokens: int
    task_memory_tokens: int
    retrieval_tokens: int
    total_prompt_tokens: int
    kept_messages: int
    dropped_messages: int
    retrieved_documents: int


@dataclass
class TelemetryRecord:
    timestamp: float
    budget: BudgetSnapshot
    output_tokens: int = 0


class SessionTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.records: list[TelemetryRecord] = []
        self.last_budget: BudgetSnapshot | None = None

    def record_request(self, budget: BudgetSnapshot) -> None:
        with self._lock:
            self.calls += 1
            self.input_tokens += budget.total_prompt_tokens
            self.last_budget = budget
            self.records.append(TelemetryRecord(timestamp=time.time(), budget=budget))
            self.records = self.records[-50:]

    def record_response(self, output_text: str, *, actual_tokens: int | None = None) -> None:
        output_tokens = actual_tokens if actual_tokens is not None else estimate_tokens(output_text)
        if actual_tokens is not None:
            _record_token_sample(output_text, actual_tokens)
        with self._lock:
            self.output_tokens += output_tokens
            if self.records:
                self.records[-1].output_tokens = output_tokens

    def suggest_response_budget(self, mode: str, fallback: int) -> int:
        with self._lock:
            relevant = [
                record.output_tokens
                for record in self.records[-12:]
                if record.budget.mode == mode and record.output_tokens
            ]
        if not relevant:
            return fallback
        average = sum(relevant) / len(relevant)
        return max(fallback, int(average * 1.4))

    def render_usage_report(self) -> str:
        with self._lock:
            total = self.input_tokens + self.output_tokens
            return (
                "Session token usage\n"
                f"  Input:  ~{self.input_tokens:,}tk\n"
                f"  Output: ~{self.output_tokens:,}tk\n"
                f"  Total:  ~{total:,}tk\n"
                f"  Calls:  {self.calls}"
            )

    def render_context_report(self) -> str:
        with self._lock:
            budget = self.last_budget
        if budget is None:
            return "No request telemetry yet."
        return (
            "Context breakdown\n"
            f"  Model:      {budget.model}\n"
            f"  Mode:       {budget.mode}\n"
            f"  Limit:      ~{budget.context_limit:,}tk\n"
            f"  Reserved:   ~{budget.response_budget:,}tk reply\n"
            f"  System:     ~{budget.system_tokens:,}tk\n"
            f"  History:    ~{budget.history_tokens:,}tk\n"
            f"  Summary:    ~{budget.summary_tokens:,}tk\n"
            f"  Task mem:   ~{budget.task_memory_tokens:,}tk\n"
            f"  Retrieval:  ~{budget.retrieval_tokens:,}tk\n"
            f"  Prompt:     ~{budget.total_prompt_tokens:,}tk\n"
            f"  Messages:   kept {budget.kept_messages}, dropped {budget.dropped_messages}\n"
            f"  Context:    {budget.retrieved_documents} cached doc(s)"
        )


def _select_history(
    history: list[dict[str, str]],
    prompt_budget: int,
    reserved_tokens: int,
    *,
    query: str = "",
) -> tuple[list[dict[str, str]], str, int, int]:
    selected: list[dict[str, str]] = []
    used = reserved_tokens
    recent_history = [msg for msg in history if msg.get("role") != "system"]
    keywords = _keywords(query)
    if not recent_history:
        return [], "", used, 0

    tail_count = min(4, len(recent_history))
    tail = recent_history[-tail_count:]
    older = recent_history[:-tail_count]

    # Always try to keep the freshest turns first.
    for message in tail:
        msg_tokens = estimate_tokens(str(message.get("content", ""))) + 4
        if selected and used + msg_tokens > prompt_budget:
            continue
        selected.append(message)
        used += msg_tokens

    remaining: list[tuple[int, int, dict[str, str]]] = []
    for index, message in enumerate(older):
        remaining.append((_message_relevance(message, keywords), index, message))
    remaining.sort(key=lambda item: (-item[0], -item[1]))

    chosen_older: list[tuple[int, dict[str, str]]] = []
    for score, index, message in remaining:
        if score <= 0:
            continue
        msg_tokens = estimate_tokens(str(message.get("content", ""))) + 4
        if used + msg_tokens > prompt_budget:
            continue
        chosen_older.append((index, message))
        used += msg_tokens

    # If there is still room, backfill with newer context from the omitted range.
    chosen_indexes = {index for index, _ in chosen_older}
    for index in range(len(older) - 1, -1, -1):
        if index in chosen_indexes:
            continue
        message = older[index]
        msg_tokens = estimate_tokens(str(message.get("content", ""))) + 4
        if used + msg_tokens > prompt_budget:
            continue
        chosen_older.append((index, message))
        used += msg_tokens

    selected = [message for _, message in sorted(chosen_older, key=lambda item: item[0])] + selected

    dropped = max(0, len(recent_history) - len(selected))
    summary = ""
    if dropped:
        selected_ids = {id(message) for message in selected}
        omitted = [message for message in recent_history if id(message) not in selected_ids]
        summary = structured_history_summary(omitted)
        summary_tokens = estimate_tokens(summary) if summary else 0
        if summary and used + summary_tokens <= prompt_budget:
            used += summary_tokens
        else:
            summary = ""
    return selected, summary, used, dropped


def optimize_messages(
    messages: list[dict[str, str]],
    model: str,
    *,
    mode: str = "",
    provider: str = "",
    context_cache: ContextCache | None = None,
    telemetry: SessionTelemetry | None = None,
) -> list[dict[str, str]]:
    if not messages:
        return messages

    context_cache = context_cache or get_global_context_cache()
    telemetry = telemetry or get_global_telemetry()

    system_prompt = str(messages[0].get("content", "")) if messages[0].get("role") == "system" else ""
    history = messages[1:] if system_prompt else messages[:]
    query = next((str(msg.get("content", "")) for msg in reversed(history) if msg.get("role") == "user"), "")
    mode = mode or infer_request_mode(query)

    failure_digest = "\n".join(_extract_failed_checks(history))
    system_prompt = augment_system_prompt(system_prompt, mode, failure_digest=failure_digest)
    system_tokens = estimate_tokens(system_prompt)

    limit = model_context_limit(model, provider)
    base_response_budget = MODE_RESPONSE_BUDGETS.get(mode, MODE_RESPONSE_BUDGETS["chat"])
    capability_multiplier = 1.0
    if provider_supports(provider, "long_context") and mode in {"code", "review", "debug", "files"}:
        capability_multiplier += 0.15
    if provider_supports(provider, "fast") and mode in {"summary", "search"}:
        capability_multiplier -= 0.10
    response_budget = min(
        limit // 3,
        max(128, int(telemetry.suggest_response_budget(mode, base_response_budget) * capability_multiplier)),
    )
    prompt_budget = max(1_024, limit - response_budget)

    retrieval_docs = context_cache.retrieve(query, limit=3)
    task_memory_block = ""
    if mode in {"code", "debug", "review", "files"} and query.strip():
        task_memory_block = render_task_memory_context(query, limit=2, base_dir=Path.cwd())
    retrieval_block = ""
    if retrieval_docs:
        parts = []
        for doc in retrieval_docs:
            detail = [f"{doc.label} [{doc.kind}]"]
            if doc.summary:
                detail.append(f"summary: {doc.summary}")
            if doc.symbols:
                detail.append(f"symbols: {', '.join(doc.symbols[:6])}")
            if doc.imports:
                detail.append(f"imports: {', '.join(doc.imports[:6])}")
            if doc.snippets:
                for index, snippet in enumerate(doc.snippets, start=1):
                    detail.append(f"snippet {index}:\n{snippet}")
            else:
                detail.append(doc.content)
            parts.append("\n".join(detail))
        retrieval_block = "Relevant cached context:\n\n" + "\n\n---\n\n".join(parts)
    task_memory_tokens = estimate_tokens(task_memory_block) if task_memory_block else 0
    retrieval_tokens = estimate_tokens(retrieval_block) if retrieval_block else 0

    reserved = system_tokens + task_memory_tokens + retrieval_tokens
    selected_history, summary, _, dropped_messages = _select_history(
        history,
        prompt_budget,
        reserved,
        query=query,
    )
    summary_tokens = estimate_tokens(summary) if summary else 0
    history_tokens = estimate_message_tokens(selected_history)

    optimized = [{"role": "system", "content": system_prompt}]
    if summary:
        optimized.append({"role": "system", "content": summary})
    if task_memory_block:
        optimized.append({"role": "system", "content": "Relevant task memory:\n" + task_memory_block})
    if retrieval_block:
        optimized.append({"role": "system", "content": retrieval_block})
    optimized.extend(selected_history)

    total_prompt_tokens = estimate_message_tokens(optimized)
    snapshot = BudgetSnapshot(
        model=model,
        mode=mode,
        context_limit=limit,
        response_budget=response_budget,
        prompt_budget=prompt_budget,
        system_tokens=system_tokens,
        history_tokens=history_tokens,
        summary_tokens=summary_tokens,
        task_memory_tokens=task_memory_tokens,
        retrieval_tokens=retrieval_tokens,
        total_prompt_tokens=total_prompt_tokens,
        kept_messages=len(selected_history),
        dropped_messages=dropped_messages,
        retrieved_documents=len(retrieval_docs),
    )
    telemetry.record_request(snapshot)
    return optimized


_GLOBAL_CONTEXT_CACHE = ContextCache()
_GLOBAL_TELEMETRY = SessionTelemetry()


def get_global_context_cache() -> ContextCache:
    return _GLOBAL_CONTEXT_CACHE


def get_global_telemetry() -> SessionTelemetry:
    return _GLOBAL_TELEMETRY
