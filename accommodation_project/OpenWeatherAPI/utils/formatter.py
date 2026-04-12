"""Normalize OpenWeatherMap JSON into a small, stable shape for callers."""

from __future__ import annotations

from typing import Any, Mapping


def format_weather(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Build a compact weather payload from the raw `/data/2.5/weather` JSON.

    Expected keys follow OpenWeatherMap's schema; missing sections degrade gracefully.
    """
    if not data:
        return _empty_payload()

    city = data.get("name")
    main = data.get("main") or {}
    weather_block = data.get("weather") or []

    description = ""
    if weather_block and isinstance(weather_block[0], dict):
        description = str(weather_block[0].get("description") or "")

    temperature = main.get("temp")
    humidity = main.get("humidity")

    return {
        "city": city,
        "temperature": temperature,
        "description": description,
        "humidity": humidity,
    }


def _empty_payload() -> dict[str, Any]:
    return {
        "city": None,
        "temperature": None,
        "description": "",
        "humidity": None,
    }
