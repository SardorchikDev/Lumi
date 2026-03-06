"""HuggingFace Inference API — streaming, auto-retry, fallback model."""

import os
import time
import sys
from openai import OpenAI

R  = "\033[0m"
YE = "\033[93m"
GR = "\033[38;5;245m"

MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "microsoft/Phi-3.5-mini-instruct",
]

DEBUG = "--debug" in sys.argv


def get_client() -> OpenAI:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN not set. Add it to your .env file.")
    return OpenAI(base_url="https://router.huggingface.co/v1", api_key=token)


def chat_stream(
    client: OpenAI,
    messages: list[dict],
    model: str = MODELS[0],
    max_tokens: int = 1024,
    temperature: float = 0.7,
    retries: int = 3,
) -> str:
    """Stream with auto-retry on 429 and automatic model fallback."""
    model_list = [model] + [m for m in MODELS if m != model]
    last_err = ""

    for model_attempt in model_list:
        for attempt in range(retries):
            try:
                if DEBUG:
                    print(f"\n{GR}[debug] model={model_attempt} attempt={attempt+1}{R}")

                stream = client.chat.completions.create(
                    model=model_attempt,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )

                reply = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        print(delta, end="", flush=True)
                        reply += delta
                print()
                return reply.strip()

            except Exception as e:
                last_err = str(e)
                is_429 = "429" in last_err or "queue" in last_err.lower() or "too_many" in last_err

                if DEBUG:
                    print(f"\n{GR}[debug] error: {last_err}{R}")

                if is_429 and attempt < retries - 1:
                    wait = (attempt + 1) * 5
                    for i in range(wait, 0, -1):
                        print(f"\r  {YE}⏳ Rate limited — retrying in {i}s...{R}   ", end="", flush=True)
                        time.sleep(1)
                    print(f"\r{' '*48}\r", end="", flush=True)
                elif is_429:
                    print(f"\n  {YE}⚡ Switching to next model...{R}")
                    break
                else:
                    raise

    raise Exception(f"All models failed. Last error: {last_err}")
