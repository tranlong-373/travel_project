from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GeocoderViewbox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def to_nominatim(self) -> str:
        return f"{self.min_lon},{self.max_lat},{self.max_lon},{self.min_lat}"


@dataclass(frozen=True)
class GeocoderQuery:
    text: str
    viewbox: GeocoderViewbox | None = None
    bounded: bool = True
    limit: int = 5


class GeocoderProvider(Protocol):
    name: str

    def search(self, query: GeocoderQuery) -> list[dict[str, Any]]:
        """Return provider-native result dictionaries."""

