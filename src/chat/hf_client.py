"""HuggingFace Inference API client — OpenAI-compatible router."""

import os
import time
from openai import OpenAI

# ── Verified working models on HF router (as of 2025) ─────────────────────────
# Source: https://huggingface.co/inference/models
MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",        # fast, reliable, great default
    "meta-llama/Llama-3.3-70B-Instruct",        # much smarter, slower
    "Qwen/Qwen2.5-72B-Instruct",                # strong, multilingual
    "Qwen/Qwen2.5-7B-Instruct",                 # lightweight Qwen
    "mistralai/Mistral-7B-Instruct-v0.3",       # compact, reliable
    "mistralai/Mixtral-8x7B-Instruct-v0.1",     # MoE, fast for its quality
    "google/gemma-2-9b-it",                     # Google, solid quality
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B", # reasoning model
]

FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]


def get_client() -> OpenAI:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN not set. Add it to your .env file.")
    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=token,
    )


def chat_stream(
    client: OpenAI,
    messages: list,
    model: str = MODELS[0],
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Stream a reply, auto-retrying with fallback models on 429/503/400."""
    attempt_models = [model] + [m for m in FALLBACKS if m != model]

    for i, m in enumerate(attempt_models):
        try:
            stream = client.chat.completions.create(
                model=m,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            full = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    full += delta
            print()
            return full.strip()

        except Exception as e:
            msg = str(e)

            # Rate limit — wait and retry same model once
            if "429" in msg and i == 0:
                time.sleep(3)
                try:
                    stream = client.chat.completions.create(
                        model=m, messages=messages,
                        max_tokens=max_tokens, temperature=temperature, stream=True,
                    )
                    full = ""
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            print(delta, end="", flush=True)
                            full += delta
                    print()
                    return full.strip()
                except Exception:
                    pass

            # Model unsupported or unavailable — silently try next fallback
            if any(code in msg for code in ("400", "503")) or "not supported" in msg.lower():
                if i < len(attempt_models) - 1:
                    continue

            raise

    raise RuntimeError("All models failed.")
