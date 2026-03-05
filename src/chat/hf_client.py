"""HuggingFace Inference API client."""

import os
from openai import OpenAI


def get_client() -> OpenAI:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN not set. Add it to your .env file.")
    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=token,
    )


def chat(
    client: OpenAI,
    messages: list[dict],
    model: str = "meta-llama/Llama-3.1-8B-Instruct",
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
