from __future__ import annotations

from src.utils import live_lookup


def test_needs_live_lookup_detects_time_and_weather_queries():
    assert live_lookup.needs_live_lookup("what time is it in Tokyo right now") is True
    assert live_lookup.needs_live_lookup("weather in Tashkent today") is True
    assert live_lookup.needs_live_lookup("latest python release news") is True
    assert live_lookup.needs_live_lookup("explain recursion") is False


def test_lookup_time_supports_common_city_alias():
    text = live_lookup.lookup_time("Tokyo")
    assert "Tokyo" in text
    assert "UTC+" in text or "UTC-" in text


def test_run_live_lookup_routes_weather_and_web(monkeypatch):
    monkeypatch.setattr(live_lookup, "lookup_weather", lambda location, detailed=True: f"weather:{location}")
    monkeypatch.setattr(live_lookup, "lookup_time", lambda location: f"time:{location}")
    monkeypatch.setattr(live_lookup, "search", lambda query, fetch_top=True: f"search:{query}:{fetch_top}")

    assert live_lookup.run_live_lookup("weather in Samarkand") == "[Weather]\nweather:Samarkand"
    assert live_lookup.run_live_lookup("what time is it in Tokyo right now") == "[Time]\ntime:Tokyo"
    assert live_lookup.run_live_lookup("latest lumi release") == "[Web search]\nsearch:latest lumi release:True"
