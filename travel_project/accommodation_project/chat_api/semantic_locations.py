from __future__ import annotations

from typing import Any

from .city_center import detect_city_center_intent, resolve_city_center


def detect_semantic_location(text: str | None) -> dict[str, Any] | None:
    return detect_city_center_intent(text)


__all__ = ["detect_semantic_location", "detect_city_center_intent", "resolve_city_center"]

