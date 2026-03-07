"""
Lumi web search — DuckDuckGo + page content fetching.
No API key needed.
"""

import re
import urllib.request
import urllib.parse
import urllib.error
import json
import sys
import html

DEBUG = "--debug" in sys.argv

SEARCH_TRIGGERS = [
    # Questions
    r"\bwhat is\b", r"\bwho is\b", r"\bwhere is\b", r"\bwhen (is|was|did)\b",
    r"\bhow (do|does|did|to)\b", r"\bwhy (is|does|did)\b",
    # Action phrases
    r"\bsearch\b", r"\blook up\b", r"\bfind out\b", r"\btell me about\b",
    r"\blatest\b", r"\bnews\b", r"\bcurrent\b", r"\brecent\b", r"\btoday\b",
    r"\bprice of\b", r"\bweather\b", r"\bpopulation\b", r"\bcapital of\b",
    r"\bwho won\b", r"\bwhat happened\b", r"\bdefinition of\b",
    r"\bmeaning of\b", r"\bexplain\b.*\binternet\b",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def should_search(text: str) -> bool:
    """Return True if this message likely needs a web search."""
    t = text.lower()
    return any(re.search(p, t) for p in SEARCH_TRIGGERS)


def _fetch(url: str, timeout: int = 6) -> str:
    """Fetch a URL, return text content."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            charset = "utf-8"
            ct = r.headers.get_content_charset()
            if ct: charset = ct
            return r.read().decode(charset, errors="replace")
    except Exception as e:
        if DEBUG: print(f"[search debug] fetch error: {e}", file=sys.stderr)
        return ""


def _strip_html(raw: str, max_chars: int = 1200) -> str:
    """Strip HTML tags and clean up whitespace."""
    # Remove script/style blocks
    raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", raw, flags=re.S | re.I)
    # Remove all tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode HTML entities
    raw = html.unescape(raw)
    # Collapse whitespace
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:max_chars]


def ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo and return list of {title, url, snippet}.
    Uses DDG's HTML interface — no API key needed.
    """
    q  = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"

    raw = _fetch(url)
    if not raw:
        return []

    results = []

    # Parse result blocks
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        raw, re.S
    )

    for href, title_html, snippet_html in blocks[:max_results]:
        # DDG wraps real URLs in redirects — extract uddg param
        uddg = re.search(r"uddg=([^&]+)", href)
        real_url = urllib.parse.unquote(uddg.group(1)) if uddg else href
        if not real_url.startswith("http"):
            continue

        title   = _strip_html(title_html, 120)
        snippet = _strip_html(snippet_html, 300)

        results.append({"title": title, "url": real_url, "snippet": snippet})

    if DEBUG:
        print(f"[search debug] '{query}' → {len(results)} results", file=sys.stderr)

    return results


def fetch_page_summary(url: str, max_chars: int = 1500) -> str:
    """Fetch a page and return its readable text summary."""
    raw = _fetch(url, timeout=8)
    if not raw:
        return ""

    # Try to grab main content areas
    for tag in ["article", "main", r'div[^>]+id="content"', r'div[^>]+class="[^"]*content[^"]*"']:
        m = re.search(f"<{tag}[^>]*>(.*?)</{tag.split('[')[0]}>", raw, re.S | re.I)
        if m:
            return _strip_html(m.group(1), max_chars)

    return _strip_html(raw, max_chars)


def search(query: str, fetch_top: bool = True) -> str:
    """
    Run a search and return a formatted string for the model.
    If fetch_top=True, also fetches the first result page for richer context.
    """
    results = ddg_search(query, max_results=5)

    if not results:
        return "[No search results found]"

    lines = [f"Search results for: {query}\n"]

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        lines.append("")

    # Fetch first result for deeper context
    if fetch_top and results:
        page_text = fetch_page_summary(results[0]["url"])
        if page_text:
            lines.append(f"--- Full content from top result ({results[0]['url']}) ---")
            lines.append(page_text)

    return "\n".join(lines)


def search_display(query: str) -> tuple[list[dict], str]:
    """
    For the /search command — returns (results_list, page_text).
    Results list has title/url/snippet for display.
    Page_text is from the top result.
    """
    results = ddg_search(query, max_results=6)
    page_text = ""
    if results:
        page_text = fetch_page_summary(results[0]["url"])
    return results, page_text
