"""
SearchIntentBuilder — translates inputs into a typed SearchIntent.

Two entry points:
  from_parse_result()  — wraps an already-parsed dict from parser_service
  build()              — full NLU pipeline: classify → extract slots → resolve location

build() does NOT create UserPreference, does NOT call the recommendation engine.
"""
from __future__ import annotations

import re
from typing import Any

from .dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)
from .input_classifier_v2 import classify_v2
from ..location.context import LocationContext
from ..location.resolver import LocationResolver
from ..slot_pipeline import (
    ANYWHERE_INTENT_PATTERN,
    find_accommodation_type_spans,
    find_amenity_spans,
)
from ..extractors import extract_budget, extract_guest_count, extract_trip_days
from ..location_gazetteer import canonicalize_area_name
from ..normalizers import normalize_key

# Build lookup maps once at import time
_MODE_MAP: dict[str, LocationMode] = {m.value: m for m in LocationMode}
_STATUS_MAP: dict[str, LocationStatus] = {s.value: s for s in LocationStatus}

# Detects "gần tôi" / "near me" / "gần đây" intent (normalized no-accent text).
_NEAR_ME_RE = re.compile(
    r"\b(?:"
    r"gan toi|gan minh|near me"
    r"|o day|gan day|quanh day|o gan day"
    r"|gan vi tri|gan vi tri hien tai|vi tri cua toi"
    r")\b"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value:
        return [value]
    return []


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class SearchIntentBuilder:
    """
    Converts parse_result dict → SearchIntent.

    All dict.get() cascade logic is centralised here so it does not
    leak into recommendation_bridge or views. Phase 2 will wire this
    into create_preference_from_parse().
    """

    def from_parse_result(
        self,
        parse_result: dict[str, Any],
        *,
        raw_text: str = "",
        locale: str = "vi",
    ) -> SearchIntent:
        slots = parse_result.get("slots") or {}
        filter_tree = parse_result.get("filter_tree") or {}
        location_node = filter_tree.get("location") or {}

        return SearchIntent(
            raw_text=raw_text,
            locale=locale,
            conversation_intent=(
                parse_result.get("conversation_intent")
                or parse_result.get("intent")
                or "unknown"
            ),
            input_kind=parse_result.get("input_kind") or "text",

            # Location
            location=self._build_location(parse_result, slots, location_node),
            user_location=self._build_user_location(slots, parse_result),
            selected_place=parse_result.get("selected_place"),

            # Filters
            area=slots.get("area") or parse_result.get("canonical_area"),
            hotel_name=slots.get("hotel_name"),
            accommodation_types=_coerce_list(
                slots.get("accommodation_types")
                or slots.get("preferred_type")
                or slots.get("accommodation_type")
            ),
            budget=_safe_int(slots.get("budget")),
            budget_min=_safe_int(slots.get("budget_min")),
            budget_max=_safe_int(slots.get("budget_max")),
            guest_count=_safe_int(slots.get("guest_count")),
            trip_days=_safe_int(slots.get("trip_days")),
            required_amenities=_coerce_list(slots.get("required_amenities")),
            priorities=_coerce_list(slots.get("priorities")),
            special_requirements=_coerce_list(slots.get("special_requirements")),
            rating_min=_safe_float(slots.get("rating")),

            # Meta
            confidence=_safe_float(parse_result.get("location_confidence")) or 0.0,
            assumptions={},
            used_default_slots=parse_result.get("used_default_slots") or {},
            debug=parse_result.get("_debug") or {},
        )

    def build(
        self,
        text: str,
        *,
        locale: str = "vi",
        context_slots: dict[str, Any] | None = None,
        selected_place: str | None = None,
        user_location: UserLocationInput | None = None,
        include_debug: bool = False,
    ) -> SearchIntent:
        """
        Full NLU pipeline in one call.

        Calls classify_v2 → extracts slots → resolves location → returns SearchIntent.
        Never raises; on any internal error returns a SearchIntent with status UNRESOLVED.
        """
        ctx = context_slots or {}
        norm = normalize_key(text)

        # ── 1. classify ────────────────────────────────────────────────────────
        classification = classify_v2(text, context_slots=ctx)

        # ── 2. detect special location intents ────────────────────────────────
        is_anywhere = bool(ANYWHERE_INTENT_PATTERN.search(norm))
        is_near_me = bool(_NEAR_ME_RE.search(norm))

        # ── 3. slot extraction ─────────────────────────────────────────────────
        budget = extract_budget(text) or _safe_int(ctx.get("budget"))
        budget_min = _safe_int(ctx.get("budget_min"))
        budget_max = _safe_int(ctx.get("budget_max")) or budget

        guest_count = extract_guest_count(text) or _safe_int(ctx.get("guest_count"))
        trip_days = extract_trip_days(text) or _safe_int(ctx.get("trip_days"))

        acc_spans = find_accommodation_type_spans(text)
        accommodation_types: list[str] = []
        for s in acc_spans:
            v = str(s.value)
            if v not in accommodation_types:
                accommodation_types.append(v)
        if not accommodation_types:
            accommodation_types = _coerce_list(ctx.get("accommodation_types"))

        amenity_spans = find_amenity_spans(text)
        required_amenities: list[str] = []
        for s in amenity_spans:
            v = str(s.value)
            if v not in required_amenities:
                required_amenities.append(v)
        if not required_amenities:
            required_amenities = _coerce_list(ctx.get("required_amenities"))

        # ── 4. resolve location ────────────────────────────────────────────────
        if is_anywhere:
            resolved = ResolvedLocation(
                status=LocationStatus.OK,
                mode=LocationMode.ANYWHERE,
                raw_phrase=text,
                display_label="Anywhere",
                debug={"source": "anywhere_pattern"},
            )
        elif is_near_me and user_location is not None:
            # "gần tôi" + GPS → resolve directly without going through strategies
            resolved = ResolvedLocation(
                status=LocationStatus.OK,
                mode=LocationMode.NEAR_USER,
                raw_phrase=text,
                display_label="Gần vị trí của bạn",
                latitude=user_location.lat,
                longitude=user_location.lon,
                radius_km=user_location.radius_km,
                provider="browser_gps",
                cache_hit=False,
                debug={"source": "near_me_with_gps"},
            )
        elif is_near_me and user_location is None:
            resolved = ResolvedLocation(
                status=LocationStatus.UNRESOLVED,
                mode=LocationMode.NEAR_USER,
                raw_phrase=text,
                debug={"needs_user_location": True, "reason": "near_me_without_gps"},
            )
        else:
            loc_ctx = LocationContext(
                raw_text=text,
                locale=locale,
                input_kind=classification.input_kind,
                location_phrase=classification.location_phrase,
                location_phrase_raw=classification.location_phrase_raw,
                hotel_name=classification.hotel_name,
                area_hint=classification.area_hint,
                amenity_terms=classification.amenity_terms,
                poi_category=classification.debug.get("poi_category"),
                selected_place=selected_place,
                user_location=user_location,
                context_slots=ctx,
                prior_canonical_area=_safe_str(ctx.get("area")),
                debug=include_debug,
            )
            resolved = LocationResolver.default().resolve(loc_ctx)

        # ── 5. assemble SearchIntent ───────────────────────────────────────────
        debug: dict[str, Any] = {}
        if include_debug:
            debug = {
                "classification": classification.to_dict(),
                "is_anywhere": is_anywhere,
                "is_near_me": is_near_me,
            }

        # Map area to canonical display form ("quan 3" → "Quận 3") using the
        # gazetteer.  Fall back to raw value when no canonical match exists
        # (e.g. unsupported province) so we don't lose data.
        # IMPORTANT: when the user query is a landmark/POI (Chợ Tân Bình,
        # Snow Town Sài Gòn, ...), classifier.area_hint is just a city-suffix
        # qualifier — don't promote it to `intent.area`, otherwise downstream
        # filter_tree collapses the response to area mode instead of near_anchor.
        if classification.input_kind in {"landmark_or_poi", "specific_address"}:
            raw_area = resolved.canonical_area
        else:
            raw_area = resolved.canonical_area or classification.area_hint
        canonical_area = canonicalize_area_name(raw_area) or raw_area
        # Also canonicalize on the resolved location so to_parse_result emits
        # the proper display form in `canonical_area` / `filter_tree`.
        if resolved.canonical_area:
            resolved.canonical_area = canonicalize_area_name(resolved.canonical_area) or resolved.canonical_area
        if resolved.display_label:
            resolved.display_label = canonicalize_area_name(resolved.display_label) or resolved.display_label

        return SearchIntent(
            raw_text=text,
            locale=locale,
            conversation_intent="search",
            input_kind=classification.input_kind,
            location=resolved,
            selected_place=selected_place,
            user_location=user_location,
            area=canonical_area,
            hotel_name=classification.hotel_name,
            accommodation_types=accommodation_types,
            budget=budget_max,
            budget_min=budget_min,
            budget_max=budget_max,
            guest_count=guest_count,
            trip_days=trip_days,
            required_amenities=required_amenities,
            confidence=classification.confidence,
            debug=debug,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _build_location(
        self,
        parse_result: dict[str, Any],
        slots: dict[str, Any],
        location_node: dict[str, Any],
    ) -> ResolvedLocation:
        raw_mode = (
            parse_result.get("location_mode")
            or slots.get("location_mode")
            or location_node.get("mode")
            or "unknown"
        )
        mode = _MODE_MAP.get(raw_mode, LocationMode.UNKNOWN)

        raw_status = parse_result.get("location_status") or "none"
        status = _STATUS_MAP.get(raw_status, LocationStatus.NONE)

        # Coordinates — check parse_result first, then filter_tree.location
        anchor_lat = _safe_float(
            parse_result.get("anchor_lat") or location_node.get("anchor_lat")
        )
        anchor_lon = _safe_float(
            parse_result.get("anchor_lon") or location_node.get("anchor_lon")
        )
        radius_km = (
            _safe_float(parse_result.get("search_radius_km"))
            or _safe_float(location_node.get("search_radius_km"))
            or 10.0
        )

        return ResolvedLocation(
            status=status,
            mode=mode,
            raw_phrase=slots.get("location_phrase"),
            canonical_area=(
                parse_result.get("canonical_area")
                or slots.get("area")
                or location_node.get("canonical_area")
            ),
            display_label=(
                parse_result.get("location_display_label")
                or location_node.get("location_display_label")
            ),
            anchor_name=(
                parse_result.get("anchor_name")
                or location_node.get("anchor_name")
            ),
            anchor_kind=(
                parse_result.get("anchor_kind")
                or location_node.get("anchor_kind")
            ),
            latitude=anchor_lat,
            longitude=anchor_lon,
            radius_km=radius_km,
            nearby_poi_key=location_node.get("nearby_poi_key"),
            nearby_poi_label=location_node.get("nearby_place"),
            cache_hit=False,
        )

    def _build_user_location(
        self,
        slots: dict[str, Any],
        parse_result: dict[str, Any],
    ) -> UserLocationInput | None:
        raw = slots.get("user_location") or parse_result.get("user_location")
        if not isinstance(raw, dict):
            return None
        lat = _safe_float(raw.get("lat"))
        lon = _safe_float(raw.get("lon"))
        if lat is None or lon is None:
            return None
        return UserLocationInput(
            lat=lat,
            lon=lon,
            accuracy=_safe_float(raw.get("accuracy")),
            radius_km=_safe_float(raw.get("radius_km")) or 10.0,
        )
