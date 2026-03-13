"""
Auto-extract memorable facts from conversation and save to long-term memory.
Uses a small AI call — only runs every N turns to avoid spam.
"""

from src.memory.longterm import add_fact, get_facts

EXTRACT_PROMPT = """You are a memory assistant. Read this conversation excerpt and extract any personal facts about the USER (not the assistant) worth remembering long-term.

Examples of good facts to extract:
- Name, job, location, hobbies, preferences
- Goals they mentioned
- Technical skills or stack they use
- Preferences about how they like things explained

Rules:
- Only extract clear, stated facts. Don't infer or guess.
- Only facts about the USER, not the assistant.
- Each fact should be a short, standalone sentence.
- If there are no clear facts to extract, return exactly: NONE
- Return one fact per line, no bullets, no numbers, no extra text.

Conversation:
{conversation}

Facts to remember (or NONE):"""


def auto_extract_facts(client, model: str, history: list, silent: bool = True) -> list:
    """
    Extract memorable facts from the last few turns.
    Returns list of new facts added.
    """
    if len(history) < 4:
        return []

    # Only look at the last 6 messages to keep it focused
    recent = history[-6:]
    conversation = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Lumi'}: {m['content'][:300]}"
        for m in recent
        if m.get("content")
    )

    existing = get_facts()
    existing_str = "\n".join(existing) if existing else "None yet."

    prompt = EXTRACT_PROMPT.format(conversation=conversation)
    if existing:
        prompt += f"\n\nAlready stored (don't duplicate):\n{existing_str}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
            stream=False,
        )
        raw = response.choices[0].message.content.strip()
    except Exception:
        return []

    if raw.upper() == "NONE" or not raw:
        return []

    added = []
    for line in raw.split("\n"):
        line = line.strip().lstrip("-•*0123456789. ")
        if not line or len(line) < 5:
            continue
        # Don't add duplicates
        if not any(line.lower() in f.lower() or f.lower() in line.lower() for f in existing):
            add_fact(line)
            added.append(line)

    return added
