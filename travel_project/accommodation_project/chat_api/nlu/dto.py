"""
Central DTOs for the chat → recommendation pipeline.

Import order guarantee: this module imports stdlib only.
No Django, no project-local imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LocationMode(str, Enum):
    UNKNOWN = "unknown"
    ANYWHERE = "anywhere"
    AREA = "area"
    NEAR_ANCHOR = "near_anchor"
    NEAR_USER = "near_user"
    CITY_CENTER = "city_center"
    HOTEL_NAME = "hotel_name"
    MULTIPLE_CHOICE = "multiple_choice"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class LocationStatus(str, Enum):
    OK = "ok"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"
    MULTIPLE_CHOICE = "multiple_choice"
    GEOCODED = "geocoded"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


# ---------------------------------------------------------------------------
# ResolvedLocation — output of location resolution
# ---------------------------------------------------------------------------

@dataclass
class ResolvedLocation:
    """
    Fully resolved location data. Produced by LocationResolver,
    stored on SearchIntent.location.
    """
    status: LocationStatus = LocationStatus.NONE
    mode: LocationMode = LocationMode.UNKNOWN

    # Original text that triggered resolution
    raw_phrase: str | None = None

    # Area / place identity
    canonical_area: str | None = None
    display_label: str | None = None

    # Anchor point (landmark, POI, district centroid)
    anchor_name: str | None = None
    anchor_kind: str | None = None   # "landmark" | "district" | "city" | "user_location"

    # Coordinates
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float = 3.0   # standardized: matches DEFAULT_NEARBY_RADIUS_KM

    # Provenance
    provider: str | None = None      # "osm" | "nominatim" | "overpass" | "alias" | "none"
    nearby_poi_key: str | None = None
    nearby_poi_label: str | None = None
    cache_hit: bool = False

    debug: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# UserLocationInput — GPS signal from the browser/client
# ---------------------------------------------------------------------------

@dataclass
class UserLocationInput:
    lat: float
    lon: float
    accuracy: float | None = None
    radius_km: float = 10.0


# ---------------------------------------------------------------------------
# SearchIntent — central DTO between NLU and recommendation
# ---------------------------------------------------------------------------

@dataclass
class SearchIntent:
    """
    Typed representation of user search intent.
    Replaces raw parse_result dict as the contract between chat_api and recommendations.
    Not connected to runtime yet — Phase 1 skeleton only.
    """

    # --- Core input ---
    raw_text: str = ""
    locale: str = "vi"
    conversation_intent: str = "unknown"
    input_kind: str = "text"  # "text" | "quick_reply" | "confirmed" | "follow_up"

    # --- Location ---
    location: ResolvedLocation = field(default_factory=ResolvedLocation)
    selected_place: str | None = None     # set when user picks from multiple_choice
    user_location: UserLocationInput | None = None  # GPS from client

    # --- Accommodation filters ---
    area: str | None = None               # canonical area name
    hotel_name: str | None = None         # if user asked for a specific property
    accommodation_types: list[str] = field(default_factory=list)
    budget: int | None = None             # unified budget (fallback)
    budget_min: int | None = None
    budget_max: int | None = None
    guest_count: int | None = None
    trip_days: int | None = None
    required_amenities: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    special_requirements: list[str] = field(default_factory=list)
    rating_min: float | None = None

    # --- Meta ---
    confidence: float = 0.0
    assumptions: dict[str, Any] = field(default_factory=dict)
    used_default_slots: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form. Enums become their .value strings, nested
        dataclasses become plain dicts. Round-trips through
        recommendation_bridge._reconstruct_intent_from_dict."""
        data = asdict(self)
        loc = data.get("location") or {}
        if isinstance(loc.get("status"), Enum):
            loc["status"] = loc["status"].value
        if isinstance(loc.get("mode"), Enum):
            loc["mode"] = loc["mode"].value
        return data
