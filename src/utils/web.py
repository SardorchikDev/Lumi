"""Web page fetcher — fetch URL, extract readable text."""

import re
import urllib.error
import urllib.request

MAX_CHARS = 12000  # ~3k tokens


def fetch_url(url: str) -> str:
    """Fetch a URL and return cleaned text content."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Lumi/2.0)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

            # Detect encoding
            enc = "utf-8"
            if "charset=" in content_type:
                enc = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                html = raw.decode(enc, errors="replace")
            except LookupError:
                html = raw.decode("utf-8", errors="replace")

    except urllib.error.HTTPError as e:
        return f"HTTP error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"Could not reach URL: {e.reason}"
    except Exception as e:
        return f"Fetch failed: {e}"

    return _extract_text(html)[:MAX_CHARS]


def _extract_text(html: str) -> str:
    """Strip HTML tags and extract readable text."""
    # Remove scripts and styles entirely
    html = re.sub(r"<(script|style|noscript|nav|footer|header)[^>]*>.*?</\1>",
                  "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    entities = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
                "&#39;": "'", "&nbsp;": " ", "&mdash;": "—", "&ndash;": "–"}
    for ent, char in entities.items():
        text = text.replace(ent, char)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()
