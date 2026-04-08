from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    google_places_api_key: str | None
    google_places_timeout_seconds: float


@lru_cache
def get_settings() -> Settings:
    timeout_raw = os.getenv("GOOGLE_PLACES_TIMEOUT_SECONDS", "10")

    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 10.0

    return Settings(
        google_places_api_key=os.getenv("GOOGLE_PLACES_API_KEY"),
        google_places_timeout_seconds=timeout_seconds,
    )
