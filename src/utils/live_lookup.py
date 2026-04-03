"""Live lookup helpers for dynamic, current-information questions."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from src.tools.search import search
from src.utils.tools import get_weather, get_weather_detailed

TIME_QUERY_PATTERNS = (
    re.compile(r"\bwhat time\b", re.IGNORECASE),
    re.compile(r"\btime in\b", re.IGNORECASE),
    re.compile(r"\blocal time\b", re.IGNORECASE),
    re.compile(r"\btime zone\b", re.IGNORECASE),
    re.compile(r"\btimezone\b", re.IGNORECASE),
    re.compile(r"\bdate in\b", re.IGNORECASE),
    re.compile(r"\bcurrent time\b", re.IGNORECASE),
)
TIME_QUERY_BLOCKLIST = (
    "time complexity",
    "time travel",
    "time series",
    "timer",
    "runtime",
)
WEATHER_QUERY_PATTERNS = (
    re.compile(r"\bweather\b", re.IGNORECASE),
    re.compile(r"\bforecast\b", re.IGNORECASE),
    re.compile(r"\btemperature\b", re.IGNORECASE),
    re.compile(r"\brain\b", re.IGNORECASE),
    re.compile(r"\bsnow\b", re.IGNORECASE),
)
LIVE_LOOKUP_RULE = (
    "For questions about the latest/current facts, time, timezone, date, weather, or other changing information, "
    "use live lookup before answering instead of relying on memory."
)

_TIMEZONE_ALIASES: dict[str, str] = {
    "utc": "UTC",
    "gmt": "Etc/GMT",
    "london": "Europe/London",
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "rome": "Europe/Rome",
    "italy": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "lisbon": "Europe/Lisbon",
    "portugal": "Europe/Lisbon",
    "amsterdam": "Europe/Amsterdam",
    "netherlands": "Europe/Amsterdam",
    "brussels": "Europe/Brussels",
    "belgium": "Europe/Brussels",
    "zurich": "Europe/Zurich",
    "switzerland": "Europe/Zurich",
    "warsaw": "Europe/Warsaw",
    "poland": "Europe/Warsaw",
    "athens": "Europe/Athens",
    "greece": "Europe/Athens",
    "istanbul": "Europe/Istanbul",
    "turkey": "Europe/Istanbul",
    "moscow": "Europe/Moscow",
    "russia": "Europe/Moscow",
    "kyiv": "Europe/Kyiv",
    "ukraine": "Europe/Kyiv",
    "tbilisi": "Asia/Tbilisi",
    "georgia": "Asia/Tbilisi",
    "baku": "Asia/Baku",
    "azerbaijan": "Asia/Baku",
    "yerevan": "Asia/Yerevan",
    "armenia": "Asia/Yerevan",
    "tashkent": "Asia/Tashkent",
    "samarkand": "Asia/Tashkent",
    "uzbekistan": "Asia/Tashkent",
    "almaty": "Asia/Almaty",
    "kazakhstan": "Asia/Almaty",
    "bishkek": "Asia/Bishkek",
    "kyrgyzstan": "Asia/Bishkek",
    "dushanbe": "Asia/Dushanbe",
    "tajikistan": "Asia/Dushanbe",
    "ashgabat": "Asia/Ashgabat",
    "turkmenistan": "Asia/Ashgabat",
    "karachi": "Asia/Karachi",
    "pakistan": "Asia/Karachi",
    "lahore": "Asia/Karachi",
    "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "dhaka": "Asia/Dhaka",
    "bangladesh": "Asia/Dhaka",
    "colombo": "Asia/Colombo",
    "sri lanka": "Asia/Colombo",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "united arab emirates": "Asia/Dubai",
    "riyadh": "Asia/Riyadh",
    "saudi arabia": "Asia/Riyadh",
    "doha": "Asia/Qatar",
    "qatar": "Asia/Qatar",
    "tehran": "Asia/Tehran",
    "iran": "Asia/Tehran",
    "jerusalem": "Asia/Jerusalem",
    "israel": "Asia/Jerusalem",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "taipei": "Asia/Taipei",
    "taiwan": "Asia/Taipei",
    "seoul": "Asia/Seoul",
    "south korea": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "singapore": "Asia/Singapore",
    "bangkok": "Asia/Bangkok",
    "thailand": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "indonesia": "Asia/Jakarta",
    "manila": "Asia/Manila",
    "philippines": "Asia/Manila",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "australia": "Australia/Sydney",
    "auckland": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",
    "new york": "America/New_York",
    "washington": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "toronto": "America/Toronto",
    "canada": "America/Toronto",
    "chicago": "America/Chicago",
    "dallas": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "vancouver": "America/Vancouver",
    "united states": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "mexico city": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "brazil": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "argentina": "America/Argentina/Buenos_Aires",
    "santiago": "America/Santiago",
    "chile": "America/Santiago",
    "bogota": "America/Bogota",
    "colombia": "America/Bogota",
    "lima": "America/Lima",
    "peru": "America/Lima",
    "cape town": "Africa/Johannesburg",
    "johannesburg": "Africa/Johannesburg",
    "south africa": "Africa/Johannesburg",
    "lagos": "Africa/Lagos",
    "nigeria": "Africa/Lagos",
    "nairobi": "Africa/Nairobi",
    "kenya": "Africa/Nairobi",
    "cairo": "Africa/Cairo",
    "egypt": "Africa/Cairo",
}

_AMBIGUOUS_COUNTRY_HINTS = {
    "united states": "Country spans multiple time zones. Showing New York time.",
    "usa": "Country spans multiple time zones. Showing New York time.",
    "us": "Country spans multiple time zones. Showing New York time.",
    "canada": "Country spans multiple time zones. Showing Toronto time.",
    "australia": "Country spans multiple time zones. Showing Sydney time.",
    "russia": "Country spans multiple time zones. Showing Moscow time.",
}


def _normalize_query(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def is_time_query(text: str) -> bool:
    normalized = _normalize_query(text)
    if not normalized or any(token in normalized for token in TIME_QUERY_BLOCKLIST):
        return False
    return any(pattern.search(normalized) for pattern in TIME_QUERY_PATTERNS)


def is_weather_query(text: str) -> bool:
    normalized = _normalize_query(text)
    return bool(normalized and any(pattern.search(normalized) for pattern in WEATHER_QUERY_PATTERNS))


def needs_live_lookup(text: str) -> bool:
    normalized = _normalize_query(text)
    if not normalized:
        return False
    if is_time_query(normalized) or is_weather_query(normalized):
        return True
    live_markers = (
        "latest",
        "current",
        "today",
        "tonight",
        "right now",
        "news",
        "breaking",
        "update",
        "price of",
        "stock price",
        "exchange rate",
        "who is the current",
        "what is the current",
        "what happened today",
    )
    return any(marker in normalized for marker in live_markers)


def _extract_location(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"\b(right now|now|today|tonight)\b", "", raw, flags=re.IGNORECASE).strip(" ?.,")
    patterns = (
        r"\b(?:in|for|at)\s+([A-Za-z][A-Za-z .,'-]{1,60})$",
        r"\b(?:of|near)\s+([A-Za-z][A-Za-z .,'-]{1,60})$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.,")
    return ""


def _format_offset(delta: timedelta | None) -> str:
    total_minutes = int((delta or timedelta()).total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _best_timezone_match(query: str) -> str:
    normalized = _normalize_query(query)
    if not normalized:
        return "UTC"
    if normalized in _TIMEZONE_ALIASES:
        return _TIMEZONE_ALIASES[normalized]

    zones = sorted(available_timezones())
    exact_suffix = [zone for zone in zones if _normalize_query(zone.split("/")[-1]) == normalized]
    if exact_suffix:
        return exact_suffix[0]

    partial_matches = [
        zone
        for zone in zones
        if normalized in _normalize_query(zone.split("/")[-1]) or normalized in _normalize_query(zone)
    ]
    if partial_matches:
        return partial_matches[0]

    normalized_suffixes = {_normalize_query(zone.split("/")[-1]): zone for zone in zones}
    close = difflib.get_close_matches(normalized, list(normalized_suffixes), n=1, cutoff=0.78)
    if close:
        return normalized_suffixes[close[0]]
    raise ValueError(f"Unknown location or timezone: {query}")


def lookup_time(location: str = "") -> str:
    query = str(location or "").strip()
    zone_name = _best_timezone_match(query or "UTC")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Timezone unavailable: {zone_name}") from exc
    now = datetime.now(zone)
    display_location = query or zone_name
    lines = []
    hint = _AMBIGUOUS_COUNTRY_HINTS.get(_normalize_query(query))
    if hint:
        lines.append(hint)
    lines.append(
        f"{display_location}: {now.strftime('%A, %Y-%m-%d %H:%M:%S')} "
        f"({now.tzname() or zone_name}, {_format_offset(now.utcoffset())})"
    )
    return "\n".join(lines)


def lookup_weather(location: str = "", *, detailed: bool = True) -> str:
    query = str(location or "").strip() or "Tashkent"
    if detailed:
        detailed_result = get_weather_detailed(query)
        if detailed_result:
            return detailed_result
    return get_weather(query)


def run_live_lookup(query: str) -> str:
    if is_weather_query(query):
        location = _extract_location(query) or query
        return f"[Weather]\n{lookup_weather(location)}"
    if is_time_query(query):
        location = _extract_location(query) or query
        return f"[Time]\n{lookup_time(location)}"
    return f"[Web search]\n{search(query, fetch_top=True)}"


__all__ = [
    "LIVE_LOOKUP_RULE",
    "is_time_query",
    "is_weather_query",
    "needs_live_lookup",
    "lookup_time",
    "lookup_weather",
    "run_live_lookup",
]
