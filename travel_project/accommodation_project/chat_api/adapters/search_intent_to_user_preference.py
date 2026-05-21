"""
Adapter: SearchIntent → UserPreference.

Four public functions:
  search_intent_to_legacy_slots(intent)     → slots dict for build_filter_tree
  search_intent_to_location_result(intent)  → location_result dict (legacy shape)
  build_user_preference_kwargs(intent)      → full kwargs for UserPreference.objects.create()
  create_user_preference_from_intent(intent)→ performs the DB write, returns UserPreference

Design rules:
  - Reuses build_filter_tree() for filter node logic; does NOT rewrite it.
  - Never re-calls the geocoder — SearchIntent already carries resolved coordinates.
  - Never fabricates area/location for amenity_only or hotel_name modes.
  - All Django imports are lazy so this module is usable in test environments
    without a configured Django app.
"""
from __future__ import annotations

from typing import Any

from ..nlu.dto import LocationMode, LocationStatus, SearchIntent

# Modes where anchor coords should be stored as user_latitude/user_longitude
_ANCHOR_MODES: frozenset[LocationMode] = frozenset({
    LocationMode.NEAR_ANCHOR,
    LocationMode.CITY_CENTER,
})

# Modes where area name is NOT meaningful (coords drive the search)
_COORD_ONLY_MODES: frozenset[LocationMode] = frozenset({
    LocationMode.NEAR_USER,
    LocationMode.NEAR_ANCHOR,
    LocationMode.CITY_CENTER,
})

# Types accepted by UserPreference.preferred_type
_VALID_TYPES: frozenset[str] = frozenset({"hotel", "homestay", "hostel", "apartment"})

# Default radius when none is resolved
_DEFAULT_RADIUS_KM = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# 1. search_intent_to_legacy_slots
# ─────────────────────────────────────────────────────────────────────────────

def search_intent_to_legacy_slots(intent: SearchIntent) -> dict[str, Any]:
    """
    Convert a SearchIntent into the flat 'slots' dict consumed by
    build_filter_tree() and the downstream filter node builder.

    Only includes keys with non-None values so callers don't have to guard
    against None in .get() chains.
    """
    loc = intent.location

    slots: dict[str, Any] = {}

    # ── filter slots ──────────────────────────────────────────────────────────
    if intent.budget is not None:
        slots["budget"] = intent.budget
    if intent.budget_min is not None:
        slots["budget_min"] = intent.budget_min
    if intent.budget_max is not None:
        slots["budget_max"] = intent.budget_max
    if intent.guest_count is not None:
        slots["guest_count"] = intent.guest_count
    if intent.trip_days is not None:
        slots["trip_days"] = intent.trip_days
    if intent.accommodation_types:
        slots["accommodation_types"] = list(intent.accommodation_types)
        slots["preferred_type"] = intent.accommodation_types[0]
    if intent.required_amenities:
        slots["required_amenities"] = list(intent.required_amenities)
    if intent.priorities:
        slots["priorities"] = list(intent.priorities)
    if intent.special_requirements:
        slots["special_requirements"] = list(intent.special_requirements)
    if intent.rating_min is not None:
        slots["rating"] = intent.rating_min

    # ── location hints ────────────────────────────────────────────────────────
    if loc.mode == LocationMode.AREA and loc.canonical_area:
        slots["area"] = loc.canonical_area
    elif intent.area and loc.mode not in _COORD_ONLY_MODES:
        slots["area"] = intent.area

    if loc.raw_phrase:
        slots["location_phrase"] = loc.raw_phrase

    # Pass location_mode hint so build_location_branch can take short-circuits
    slots["location_mode"] = loc.mode.value

    # near_user: pass GPS so build_location_branch picks it up without geocoding
    if loc.mode == LocationMode.NEAR_USER and intent.user_location:
        slots["user_location"] = {
            "lat": intent.user_location.lat,
            "lon": intent.user_location.lon,
            "radius_km": intent.user_location.radius_km,
        }

    return slots


# ─────────────────────────────────────────────────────────────────────────────
# 2. search_intent_to_location_result
# ─────────────────────────────────────────────────────────────────────────────

def search_intent_to_location_result(intent: SearchIntent) -> dict[str, Any]:
    """
    Convert SearchIntent.location into the legacy 'location_result' dict shape
    consumed by build_search_origin() and used as a hint in build_filter_tree().

    Keys mirror what parser_service.parse_user_text() used to produce.
    """
    loc = intent.location
    ul = intent.user_location

    result: dict[str, Any] = {
        "location_mode": loc.mode.value,
        "location_status": loc.status.value,
        "canonical_area": loc.canonical_area,
        "location_display_label": loc.display_label,
        "location_phrase": loc.raw_phrase,
        "anchor_name": loc.anchor_name,
        "anchor_kind": loc.anchor_kind,
        "anchor_lat": loc.latitude,
        "anchor_lon": loc.longitude,
        "anchor_radius_km": loc.radius_km,
        "search_radius_km": loc.radius_km,
        "location_confidence": intent.confidence,
        "nearby_poi_key": loc.nearby_poi_key,
        "nearby_place": loc.nearby_poi_label,
        "provider": loc.provider,
        "cache_hit": loc.cache_hit,
        "unresolved_location": loc.status in {LocationStatus.UNRESOLVED, LocationStatus.NONE},
        "ambiguous_location": loc.status == LocationStatus.AMBIGUOUS,
    }

    if ul:
        result["user_location"] = {
            "lat": ul.lat,
            "lon": ul.lon,
            "radius_km": ul.radius_km,
        }

    return {k: v for k, v in result.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Internal: build location branch from resolved SearchIntent
# ─────────────────────────────────────────────────────────────────────────────

def _build_location_branch_from_intent(intent: SearchIntent) -> dict[str, Any]:
    """
    Construct the filter_tree location branch dict from SearchIntent's already-
    resolved location. Never calls the geocoder — all coordinates come from the
    SearchIntent produced by LocationResolver.

    Follows the same dict structure as _empty_location_branch() in filter_tree.py.
    """
    loc = intent.location
    mode = loc.mode
    status = loc.status

    # Base empty branch (mirrors filter_tree._empty_location_branch)
    branch: dict[str, Any] = {
        "mode": "unknown",
        "explicit_anywhere": False,
        "strength": "soft",
        "location_phrase": loc.raw_phrase,
        "canonical_area": None,
        "anchor_name": None,
        "anchor_kind": None,
        "anchor_lat": None,
        "anchor_lon": None,
        "anchor_radius_km": None,
        "search_radius_km": None,
        "location_display_label": None,
        "nearby_place": None,
        "nearby_poi_key": None,
        "location_source": "search_intent_v2",
        "provider": loc.provider,
        "cache_hit": loc.cache_hit,
        "map_area": None,
        "map_display_name": None,
        "map_address": {},
        "geocode_query": None,
        "geocoder_queries": [],
        "resolved_place": None,
        "unresolved_location": False,
        "needs_city_clarification": False,
        "ambiguous_location": False,
        "ambiguous_location_question": None,
        "location_candidates": [],
        "rejected_geocoder_results": [],
        "confidence": intent.confidence,
        "geocoder_called": False,
    }

    if mode == LocationMode.ANYWHERE:
        branch.update({
            "mode": "anywhere",
            "explicit_anywhere": True,
            "strength": "none",
            "location_display_label": "Ở đâu cũng được",
            "location_source": "search_intent_v2",
            "confidence": 0.98,
            "geocoder_reason": "explicit_anywhere",
        })

    elif mode == LocationMode.NEAR_USER:
        ul = intent.user_location
        if ul:
            branch.update({
                "mode": "near_user",
                "anchor_name": "Vị trí hiện tại",
                "anchor_kind": "user_location",
                "anchor_lat": ul.lat,
                "anchor_lon": ul.lon,
                "anchor_radius_km": ul.radius_km,
                "location_display_label": loc.display_label or "Gần vị trí hiện tại",
                "location_source": "browser_geolocation",
                "confidence": 1.0,
                "unresolved_location": False,
            })
        else:
            # "gần tôi" but no GPS provided
            branch.update({
                "mode": "unknown",
                "unresolved_location": True,
                "ambiguous_location": False,
                "geocoder_reason": "near_me_no_gps",
                "ambiguous_location_question": (
                    "Bạn có thể bật định vị hoặc cho biết khu vực bạn đang ở không?"
                ),
            })

    elif mode == LocationMode.AREA:
        branch.update({
            "mode": "area",
            "canonical_area": loc.canonical_area,
            "location_display_label": loc.display_label or loc.canonical_area,
            "location_source": loc.provider or "search_intent_v2",
            "confidence": max(intent.confidence, 0.75),
            "unresolved_location": False,
            "nearby_poi_key": loc.nearby_poi_key,
            "nearby_place": loc.nearby_poi_label,
        })

    elif mode == LocationMode.NEAR_ANCHOR:
        has_coords = loc.latitude is not None and loc.longitude is not None
        display = (
            loc.display_label
            or (f"Gần {loc.anchor_name}" if loc.anchor_name else loc.raw_phrase)
        )
        branch.update({
            "mode": "near_anchor",
            "location_phrase": loc.raw_phrase,
            "anchor_name": loc.anchor_name,
            "anchor_kind": loc.anchor_kind or "geocoded",
            "anchor_lat": loc.latitude,
            "anchor_lon": loc.longitude,
            "anchor_radius_km": loc.radius_km,
            "location_display_label": display,
            "location_source": loc.provider or "search_intent_v2",
            "confidence": max(intent.confidence, 0.80),
            "cache_hit": loc.cache_hit,
            "unresolved_location": not has_coords,
            "geocoder_reason": "pre_resolved_by_location_resolver",
        })

    elif mode == LocationMode.CITY_CENTER:
        branch.update({
            "mode": "city_center",
            "canonical_area": loc.canonical_area,
            "anchor_name": loc.anchor_name or "Trung tâm thành phố",
            "anchor_kind": "city_center",
            "anchor_lat": loc.latitude,
            "anchor_lon": loc.longitude,
            "anchor_radius_km": loc.radius_km,
            "location_display_label": loc.display_label or "Trung tâm thành phố",
            "location_source": loc.provider or "semantic_city_center",
            "confidence": max(intent.confidence, 0.90),
            "unresolved_location": False,
        })

    elif mode == LocationMode.HOTEL_NAME:
        # Hotel name: represent as near_anchor if coords resolved, unknown otherwise.
        # Do NOT convert hotel name to area — that would be wrong.
        has_coords = loc.latitude is not None and loc.longitude is not None
        effective_mode = "near_anchor" if has_coords else "unknown"
        branch.update({
            "mode": effective_mode,
            "location_phrase": intent.hotel_name,
            "anchor_name": loc.anchor_name or intent.hotel_name,
            "anchor_kind": "hotel",
            "anchor_lat": loc.latitude,
            "anchor_lon": loc.longitude,
            "anchor_radius_km": loc.radius_km,
            "location_display_label": loc.display_label or intent.hotel_name,
            "location_source": loc.provider or "accommodation_db",
            "confidence": max(intent.confidence, 0.70),
            "cache_hit": loc.cache_hit,
            "unresolved_location": not has_coords,
        })

    else:
        # UNKNOWN / UNRESOLVED / AMBIGUOUS / MULTIPLE_CHOICE
        is_amenity_only = bool(intent.required_amenities) and not loc.canonical_area
        needs_area = loc.debug.get("needs_area_clarification", False) or is_amenity_only
        branch.update({
            "mode": "unknown",
            "unresolved_location": status in {LocationStatus.UNRESOLVED, LocationStatus.NONE},
            "ambiguous_location": status == LocationStatus.AMBIGUOUS,
            "geocoder_reason": loc.debug.get("reason", "unresolved"),
        })
        if needs_area:
            branch.update({
                "ambiguous_location_question": (
                    "Bạn muốn tìm ở khu vực nào? "
                    "Hoặc bật định vị để tìm gần vị trí hiện tại."
                ),
                "needs_area_clarification": True,
            })

    return branch


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers for filter_tree_json assembly
# ─────────────────────────────────────────────────────────────────────────────

def _recompute_available_slots(location_branch: dict[str, Any], filter_nodes: list[dict[str, Any]]) -> list[str]:
    slots: list[str] = []
    if location_branch.get("mode") != "unknown" or location_branch.get("explicit_anywhere"):
        slots.append("location")
    for node in filter_nodes:
        key = node.get("key") if isinstance(node, dict) else getattr(node, "key", None)
        if key and key not in slots:
            slots.append(key)
    return slots


def _recompute_usable_filter_count(location_branch: dict[str, Any], filter_nodes: list[dict[str, Any]]) -> int:
    loc_mode = location_branch.get("mode")
    has_coords = (
        location_branch.get("anchor_lat") is not None
        and location_branch.get("anchor_lon") is not None
    )
    loc_count = 1 if (
        loc_mode == "area"
        or loc_mode == "anywhere"
        or (loc_mode in {"near_anchor", "near_user", "city_center"} and has_coords)
    ) else 0
    return len(filter_nodes) + loc_count


# ─────────────────────────────────────────────────────────────────────────────
# 4. build_user_preference_kwargs
# ─────────────────────────────────────────────────────────────────────────────

def build_user_preference_kwargs(intent: SearchIntent) -> dict[str, Any]:
    """
    Build the complete kwargs dict for UserPreference.objects.create().

    Strategy:
      1. Build legacy slots from SearchIntent.
      2. Call build_filter_tree() with text="" + slots for filter nodes only
         (empty text avoids geocoder; location branch will be "unknown").
      3. Replace the location branch with data from the resolved SearchIntent.
      4. Recompute usable counts and build soft_filter_summary.
      5. Build search_origin via the existing build_search_origin().
    """
    from ..filter_tree import build_filter_tree, soft_filter_summary as _soft_filter_summary
    from ..search_origin import build_search_origin

    loc = intent.location
    legacy_slots = search_intent_to_legacy_slots(intent)

    # ── filter nodes via existing build_filter_tree ───────────────────────────
    # Use text="" + location_result={} to get filter nodes without re-geocoding.
    filter_tree = build_filter_tree(
        text="",
        slots=legacy_slots,
        location_result={},
    )
    filter_tree_dict = filter_tree.to_dict()
    filter_nodes: list[dict[str, Any]] = filter_tree_dict.get("filters") or []

    # ── replace location branch with pre-resolved data ────────────────────────
    location_branch = _build_location_branch_from_intent(intent)
    filter_tree_dict["location"] = location_branch

    # ── fix computed counts that depend on location branch ────────────────────
    available_slots = _recompute_available_slots(location_branch, filter_nodes)
    usable_count = _recompute_usable_filter_count(location_branch, filter_nodes)
    filter_tree_dict["available_slots"] = available_slots
    filter_tree_dict["usable_filter_count"] = usable_count

    # ── search_origin: reuse existing logic via legacy dict shape ─────────────
    loc_result_hint = search_intent_to_location_result(intent)
    search_origin = build_search_origin(loc_result_hint)
    filter_tree_dict["search_origin"] = search_origin

    # ── soft filter summary ───────────────────────────────────────────────────
    summary = _soft_filter_summary(filter_tree_dict)

    # ── coordinates ───────────────────────────────────────────────────────────
    user_lat: float | None = None
    user_lon: float | None = None
    radius_km: float = loc.radius_km or _DEFAULT_RADIUS_KM

    if loc.mode == LocationMode.NEAR_USER and intent.user_location:
        user_lat = intent.user_location.lat
        user_lon = intent.user_location.lon
        radius_km = intent.user_location.radius_km
    elif loc.mode in _ANCHOR_MODES and loc.latitude is not None:
        user_lat = loc.latitude
        user_lon = loc.longitude
    elif loc.mode == LocationMode.HOTEL_NAME and loc.latitude is not None:
        user_lat = loc.latitude
        user_lon = loc.longitude

    # ── area: only when coords do NOT drive the search ────────────────────────
    area: str | None = None
    if loc.mode not in _COORD_ONLY_MODES and loc.mode != LocationMode.HOTEL_NAME:
        area = loc.canonical_area or intent.area

    # ── budget: single cap for the model ─────────────────────────────────────
    budget = int(intent.budget_max or intent.budget_min or intent.budget or 0)

    # ── guest_count: minimum 1 ────────────────────────────────────────────────
    guest_count = intent.guest_count or 1

    # ── preferred_type: only validated types ─────────────────────────────────
    preferred_type: str | None = None
    for t in (intent.accommodation_types or []):
        if t in _VALID_TYPES:
            preferred_type = t
            break

    # ── location_label ────────────────────────────────────────────────────────
    location_label = (
        loc.display_label
        or search_origin.get("label")
        or loc.canonical_area
        or area
    )

    kwargs: dict[str, Any] = {
        "area": area,
        "budget": budget,
        "guest_count": guest_count,
        "preferred_type": preferred_type,
        "required_amenities": list(intent.required_amenities),
        "location_mode": loc.mode.value,
        "location_label": location_label,
        "anchor_kind": loc.anchor_kind,
        "filter_tree_json": filter_tree_dict,
        "soft_filter_summary": summary,
        "search_radius_km": radius_km,
    }

    if user_lat is not None:
        kwargs["user_latitude"] = user_lat
        kwargs["user_longitude"] = user_lon

    return kwargs


# ─────────────────────────────────────────────────────────────────────────────
# 5. create_user_preference_from_intent
# ─────────────────────────────────────────────────────────────────────────────

def create_user_preference_from_intent(intent: SearchIntent) -> Any:
    """
    Build kwargs and create a UserPreference in the DB.
    Returns the created UserPreference instance.
    """
    from preferences.models import UserPreference

    kwargs = build_user_preference_kwargs(intent)
    return UserPreference.objects.create(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible alias (used by existing code)
# ─────────────────────────────────────────────────────────────────────────────

def to_preference_kwargs(
    intent: SearchIntent,
    *,
    filter_tree_json: dict[str, Any] | None = None,
    soft_filter_summary: str = "",
) -> dict[str, Any]:
    """
    Backward-compatible shim. Callers that pass filter_tree_json / soft_filter_summary
    from a previous parse_result can still inject them; otherwise build_user_preference_kwargs
    is used to derive them from the SearchIntent.
    """
    kwargs = build_user_preference_kwargs(intent)
    if filter_tree_json is not None:
        kwargs["filter_tree_json"] = filter_tree_json
    if soft_filter_summary:
        kwargs["soft_filter_summary"] = soft_filter_summary
    return kwargs
