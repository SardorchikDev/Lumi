"""Provider-specific OpenAI client construction for Lumi."""

from __future__ import annotations

import os
import time

from openai import OpenAI

from src.chat.claude_compat import AnthropicCompatClient
from src.chat.providers import get_provider_spec


def _validate_provider(provider: str) -> None:
    if provider == "ollama":
        return
    if not get_provider_spec(provider):
        raise ValueError(f"Unknown provider: {provider}")


def _cloudflare_base_url() -> str:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def _vertex_base_url() -> str:
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    project_id = os.getenv("VERTEX_PROJECT_ID", "")
    return (
        f"https://{location}-aiplatform.googleapis.com/v1beta1"
        f"/projects/{project_id}/locations/{location}/endpoints/openapi"
    )


def make_client(provider: str, *, ollama_base: str = "http://localhost:11434") -> OpenAI:
    _validate_provider(provider)
    if provider == "claude":
        return AnthropicCompatClient(
            base_url=os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com/v1"),
            api_key=os.getenv("CLAUDE_API_KEY", ""),
        )
    if provider == "gemini":
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY"),
        )
    if provider == "groq":
        return OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    if provider == "openrouter":
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    if provider == "mistral":
        return OpenAI(
            base_url="https://api.mistral.ai/v1",
            api_key=os.getenv("MISTRAL_API_KEY"),
        )
    if provider == "github":
        return OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=os.getenv("GITHUB_API_KEY"),
        )
    if provider == "cohere":
        return OpenAI(
            base_url="https://api.cohere.com/compatibility/v1",
            api_key=os.getenv("COHERE_API_KEY"),
        )
    if provider == "bytez":
        return OpenAI(
            base_url="https://api.bytez.com/models/v2/openai/v1",
            api_key=os.getenv("BYTEZ_API_KEY"),
        )
    if provider == "airforce":
        return OpenAI(
            base_url="https://api.airforce/v1",
            api_key=os.getenv("AIRFORCE_API_KEY"),
        )
    if provider == "cloudflare":
        return OpenAI(
            base_url=_cloudflare_base_url(),
            api_key=os.getenv("CLOUDFLARE_API_KEY"),
        )
    if provider == "vercel":
        return OpenAI(
            base_url="https://ai-gateway.vercel.sh/v1",
            api_key=os.getenv("VERCEL_API_KEY"),
        )
    if provider == "pollinations":
        return OpenAI(
            base_url="https://gen.pollinations.ai/v1",
            api_key=os.getenv("POLLINATIONS_API_KEY"),
        )
    if provider == "ollama":
        return OpenAI(
            base_url=f"{ollama_base}/v1",
            api_key="ollama",
        )
    if provider == "huggingface":
        return OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=os.getenv("HF_TOKEN"),
        )
    if provider == "vertex":
        raise RuntimeError("Vertex clients must be created through make_vertex_client()")
    raise ValueError(f"Unsupported provider: {provider}")


def make_vertex_client() -> tuple[OpenAI, float]:
    import google.auth
    from google.auth.transport.requests import Request as _GRequest

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(_GRequest())
    expiry = getattr(creds, "expiry", None)
    expiry_ts = expiry.timestamp() if expiry is not None else (time.time() + 3000)
    client = OpenAI(
        base_url=_vertex_base_url(),
        api_key=creds.token,
    )
    return client, expiry_ts
