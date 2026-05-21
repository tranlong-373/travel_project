"""
LocationContext — input bundle passed to location resolution strategies.

Extended in v2 with input_kind and extracted hints from InputClassifierV2,
so strategies can make routing decisions without re-parsing the raw text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..nlu.dto import UserLocationInput


@dataclass
class LocationContext:
    """
    All inputs a LocationStrategy needs to attempt resolution.
    Constructed once per request and passed through the strategy chain unchanged.

    Fields set by InputClassifierV2 (via pipeline):
        input_kind      — routing signal: "area", "landmark_or_poi", "hotel_name", …
        location_phrase — cleaned text fragment describing the location
        hotel_name      — original text when input_kind == "hotel_name"
        area_hint       — normalized area name (no accents) if detected
        amenity_terms   — canonical amenity names (e.g. ["wifi", "pool"])
        poi_category    — canonical POI category for generic_poi_in_area
        selected_place  — canonical place name chosen from multiple_choice
    """

    # ── Core input ──────────────────────────────────────────────────────────
    raw_text: str
    locale: str = "vi"

    # ── Classifier output ────────────────────────────────────────────────────
    input_kind: str = "unknown"
    location_phrase: str | None = None       # normalized (no accents) — for regex / alias match
    location_phrase_raw: str | None = None   # original accented substring — for external geocoder
    hotel_name: str | None = None
    area_hint: str | None = None
    amenity_terms: list[str] = field(default_factory=list)
    poi_category: str | None = None     # e.g. "cafe", "hospital" (generic_poi_in_area)
    selected_place: str | None = None   # user picked from multiple_choice list

    # ── Client-side GPS ──────────────────────────────────────────────────────
    user_location: UserLocationInput | None = None

    # ── Conversation context ─────────────────────────────────────────────────
    context_slots: dict[str, Any] = field(default_factory=dict)
    prior_canonical_area: str | None = None
    prior_anchor_lat: float | None = None
    prior_anchor_lon: float | None = None

    debug: bool = False
