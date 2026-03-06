"""Web search tool using DuckDuckGo — no API key needed."""

import urllib.request
import urllib.parse
import json


def search(query: str, max_results: int = 3) -> str:
    encoded = urllib.parse.quote(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lumi/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return f"[Search failed: {e}]"

    results = []
    if data.get("AbstractText"):
        results.append(f"Summary: {data['AbstractText']}")
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append(f"- {topic['Text']}")

    return "\n".join(results) if results else "[No results found]"


def should_search(user_input: str) -> bool:
    triggers = [
        "search", "look up", "find", "what is", "who is", "latest",
        "news", "current", "today", "weather", "price", "when did",
        "how much", "where is", "tell me about",
    ]
    return any(t in user_input.lower() for t in triggers)
