"""Curated model catalogs for Lumi providers."""

from __future__ import annotations

GEMINI_CONFIRMED = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro",
    "gemini-2.5-pro-preview-06-05",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite-preview",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-3.1-flash-lite-preview",
]

GEMINI_EXTENDED = [
    "gemini-2.0-flash-exp-image-generation",
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-generation",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "nano-banana-pro-preview",
    "nano-banana-2-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-live-2.5-flash-preview",
    "gemini-2.0-flash-live-001",
    "gemini-embedding-001",
    "gemini-embedding-exp-03-07",
    "aqa",
    "gemini-robotics-er-1.5-preview",
    "gemini-2.5-computer-use-preview-10-2025",
    "gemini-3-pro-preview",
    "gemini-pro-latest",
    "deep-research-pro-preview-12-2025",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemma-3-4b-it",
    "gemma-3n-e4b-it",
    "gemma-3n-e2b-it",
    "gemma-3-1b-it",
    "gemini-2.5-flash-lite-preview-09-2025",
]

GEMINI_SKIP = set(GEMINI_EXTENDED)
GEMINI_ALL_MODELS = GEMINI_CONFIRMED + [model for model in GEMINI_EXTENDED if model not in set(GEMINI_CONFIRMED)]

GROQ_FALLBACK = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "moonshotai/kimi-k2-instruct-0905",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen-3-32b",
]

GROQ_DECOMMISSIONED = {
    "llama3-70b-8192", "llama3-8b-8192", "llama2-70b-4096",
    "mixtral-8x7b-32768", "gemma-7b-it", "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b", "deepseek-r1-distill-qwen-32b",
    "llama-3.1-70b-versatile",
}

HF_MODELS = [
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.1-70B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "meta-llama/Llama-3.1-8B-Instruct",
]

HF_FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct",
]

OPENROUTER_MODELS = [
    "qwen/qwen3-coder-480b-a35b:free",
    "openai/gpt-oss-120b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-12b-it:free",
]

MISTRAL_MODELS = [
    "mistral-large-latest",
    "mistral-medium-latest",
    "mistral-small-latest",
    "open-mistral-nemo",
    "codestral-latest",
    "open-codestral-mamba",
]

GITHUB_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1-mini",
    "DeepSeek-R1",
    "DeepSeek-V3-0324",
    "Meta-Llama-3.1-70B-Instruct",
    "Phi-4",
    "Mistral-large",
]

CLAUDE_MODELS = [
    "claude-sonnet-4-5",
    "claude-opus-4",
    "claude-haiku-3-5",
    "claude-sonnet-3-7",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
]

COHERE_MODELS = [
    "command-a-03-2025",
    "command-a-reasoning-08-2025",
    "command-r-plus-08-2024",
    "command-r-08-2024",
    "c4ai-aya-expanse-32b",
    "command-r7b-12-2024",
]

CLOUDFLARE_MODELS = [
    "@cf/openai/gpt-oss-120b",
    "@cf/openai/gpt-oss-20b",
    "@cf/qwen/qwen3-30b-a3b-fp8",
    "@cf/zai-org/glm-4.7-flash",
    "@cf/ibm-granite/granite-4.0-h-micro",
    "@cf/aisingapore/gemma-sea-lion-v4-27b-it",
    "@hf/nousresearch/hermes-2-pro-mistral-7b",
    "qwen/qwq-32b",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
    "@cf/meta/llama-3.3-70b-instruct-fp8",
    "@cf/meta/llama-3.2-3b-instruct",
]

BYTEZ_MODELS = [
    "Qwen/Qwen3-32B",
    "Qwen/Qwen3-235B-A22B",
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-R1",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mixtral-8x22B-Instruct-v0.1",
    "google/gemma-3-27b-it",
    "microsoft/Phi-4",
]

BYTEZ_SKIP_PATTERNS = (
    "embed", "embedding", "rerank", "whisper", "tts", "asr",
    "stable-diffusion", "flux", "dall-e", "image-gen", "speech", "video", "depth",
)

BYTEZ_CLOSED_PREFIXES = ("openai/", "anthropic/", "google/gemini", "mistral/")

AIRFORCE_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "claude-3-5-sonnet",
    "gemini-2.0-flash",
    "llama-3.3-70b-instruct",
]

POLLINATIONS_MODELS = [
    "kimi",
    "deepseek",
    "glm",
    "claude-fast",
    "gemini-large",
    "gemini-search",
]

VERCEL_MODELS = [
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
    "openai/o3",
    "anthropic/claude-sonnet-4-5",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "meta/llama-3.3-70b-instruct",
    "xai/grok-3",
    "mistral/mistral-large-latest",
    "mistral/codestral-latest",
    "deepseek/deepseek-r1",
]

VERCEL_SKIP = (
    "embed", "embedding", "tts", "whisper", "dall-e", "image",
    "flux", "stable-diffusion", "audio", "rerank", "moderation",
)

VERTEX_MODELS = [
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.0-flash-001",
    "claude-sonnet-4-5@20250514",
    "claude-opus-4@20250514",
    "claude-haiku-3-5@20241022",
    "claude-sonnet-3-7@20250219",
    "llama-3.3-70b-instruct-maas",
    "llama-3.1-405b-instruct-maas",
    "llama-3.1-8b-instruct-maas",
    "mistral-large@2407",
    "mistral-nemo@2407",
    "codestral@2405",
]

OPENROUTER_SKIP = {
    "embed", "audio", "tts", "whisper",
    "dall-e", "stable-diffusion", "midjourney", "flux",
    "rerank", "moderation", "classify",
    "sourceful",
    "venice/uncensored",
}

OPENROUTER_SKIP_PATTERNS = (
    "flux", "dall-e", "stable-diffusion", "sourceful",
)
