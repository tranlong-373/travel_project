"""HTTP client for OpenWeatherMap current weather (raw + formatted entrypoints)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from OpenWeatherAPI.utils.formatter import format_weather

_OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
_ENV_KEY_NAMES = ("OPENWEATHER_API_KEY", "OPENWEATHERMAP_API_KEY")


def _load_dotenv_files() -> None:
    """Load `.env` from common locations (repo root or Django project folder)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


_load_dotenv_files()


class OpenWeatherService:
    """Thin wrapper around the OpenWeather current-weather endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key or self._read_api_key_from_env()
        self._session = session or requests.Session()
        self._timeout = timeout

    @staticmethod
    def _read_api_key_from_env() -> str:
        for name in _ENV_KEY_NAMES:
            value = os.environ.get(name)
            if value:
                return value.strip()
        raise RuntimeError(
            "Missing OpenWeather API key. Set OPENWEATHER_API_KEY in your environment "
            "or `.env` file (see OpenWeatherAPI/README.md)."
        )

    def get_current_weather(self, city: str) -> dict[str, Any]:
        """
        Call OpenWeatherMap and return the parsed JSON body (same shape as the API).

        Uses metric units (°C) for temperatures.
        """
        city = (city or "").strip()
        if not city:
            raise ValueError("city must be a non-empty string")

        params = {
            "q": city,
            "appid": self._api_key,
            "units": "metric",
        }
        response = self._session.get(
            _OPENWEATHER_URL,
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload


def get_current_weather(city: str) -> dict[str, Any]:
    """Module-level helper returning raw JSON from OpenWeatherMap."""
    return OpenWeatherService().get_current_weather(city)


def get_weather(city: str) -> dict[str, Any]:
    """
    Primary integration API: fetch current weather and return the formatted payload.

    Other apps should import this function.
    """
    raw = get_current_weather(city)
    return format_weather(raw)
