from __future__ import annotations

from typing import Any

from django.urls import reverse

from preferences.models import UserPreference

from .search_origin import COORDINATE_ORIGIN_TYPES, build_search_origin


DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment", "villa", "resort", "bungalow"}
BLOCKED_INTENTS = {"off_topic", "greeting", "thanks", "help", "goodbye"}
BLOCKED_LOCATION_STATUSES = {"conflict", "multiple_choice", "ambiguous", "unsupported"}
DEFAULT_NEARBY_RADIUS_KM = 10.0


def usable_filters_from_intent(intent: Any) -> list[str]:
    """
    Build the same filter list as usable_filters_from_parse() but from a
    typed SearchIntent. Used by the v2 path and callable standalone.
    """
    from .nlu.dto import LocationMode

    loc = intent.location
    filters: list[str] = []

    if intent.accommodation_types:
        filters.append("accommodation_types")
    if intent.budget or intent.budget_max or intent.budget_min:
        filters.append("budget")
    if intent.guest_count:
        filters.append("guest_count")
    if intent.required_amenities:
        filters.append("amenities")
    if intent.rating_min:
        filters.append("rating")
    if intent.priorities:
        filters.append("sort")

    mode = loc.mode
    has_coords = loc.latitude is not None and loc.longitude is not None

    if mode == LocationMode.ANYWHERE:
        filters.append("location_anywhere")
    elif mode == LocationMode.AREA and loc.canonical_area:
        filters.append("location")
        if loc.nearby_poi_key:
            filters.append("nearby_poi")
    elif mode in {LocationMode.NEAR_ANCHOR, LocationMode.NEAR_USER, LocationMode.CITY_CENTER} and has_coords:
        filters.append("location")
    elif mode == LocationMode.HOTEL_NAME:
        filters.append("location")

    return list(dict.fromkeys(filters))


def usable_filters_from_parse(parse_result: dict[str, Any]) -> list[str]:
    # ── v2 path: delegate to typed function ──────────────────────────────────
    intent = _extract_search_intent(parse_result)
    if intent is not None:
        return usable_filters_from_intent(intent)

    # ── legacy path ───────────────────────────────────────────────────────────
    slots = parse_result.get("slots") or {}
    filters: list[str] = []
    if slots.get("accommodation_types") or slots.get("preferred_type") or slots.get("accommodation_type"):
        filters.append("accommodation_types")
    if slots.get("budget_min") or slots.get("budget_max") or slots.get("budget"):
        filters.append("budget")
    if slots.get("guest_count"):
        filters.append("guest_count")
    if slots.get("required_amenities"):
        filters.append("amenities")
    if slots.get("rating"):
        filters.append("rating")
    if slots.get("priorities"):
        filters.append("sort")

    location = (parse_result.get("filter_tree") or {}).get("location") or {}
    location_mode = parse_result.get("location_mode") or slots.get("location_mode") or location.get("mode")
    has_anchor_coordinates = (
        parse_result.get("anchor_lat") is not None
        and parse_result.get("anchor_lon") is not None
    ) or (
        location.get("anchor_lat") is not None
        and location.get("anchor_lon") is not None
    )
    if location_mode == "anywhere":
        filters.append("location_anywhere")
    elif location_mode == "area" and (parse_result.get("canonical_area") or slots.get("area") or location.get("canonical_area")):
        filters.append("location")
        if location.get("nearby_place"):
            filters.append("nearby_poi")
    elif location_mode in {"near_anchor", "near_user", "city_center"} and has_anchor_coordinates:
        filters.append("location")
    elif location_mode == "nearby_place" and location.get("nearby_place"):
        # POI category detected but no area yet — intent is valid, area clarification needed
        filters.append("nearby_poi_intent")

    return list(dict.fromkeys(filters))


def attach_recommendation_action(
    parse_result: dict[str, Any],
    bridge_result: dict[str, Any] | None = None,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    usable_filters = usable_filters_from_parse(parse_result)
    parse_result["usable_filters"] = usable_filters
    can_show = bool(parse_result.get("can_show_recommendations")) and bool(usable_filters)
    url = (bridge_result or {}).get("recommendation_url") or parse_result.get("recommendation_url")
    pref_id = (bridge_result or {}).get("pref_id") or parse_result.get("pref_id")
    failed_submit = reason == "preference_not_created"

    if can_show and url and not failed_submit:
        action = {
            "visible": True,
            "enabled": True,
            "eligible": True,
            "requires_submit": False,
            "pref_id": pref_id,
            "url": url,
            "reason": reason or "preference_created",
        }
    elif can_show and not failed_submit:
        action = {
            "visible": True,
            "enabled": True,
            "eligible": True,
            "requires_submit": True,
            "pref_id": None,
            "url": None,
            "reason": "has_usable_filters",
        }
    else:
        disabled_reason = reason
        if disabled_reason is None:
            disabled_reason = "ambiguous_location" if parse_result.get("ambiguous_location") else "no_usable_filter"
        action = {
            "visible": True,
            "enabled": False,
            "eligible": False,
            "requires_submit": False,
            "pref_id": pref_id,
            "url": None,
            "reason": disabled_reason,
        }

    parse_result["can_show_recommendations"] = can_show
    parse_result["recommendation_action"] = action
    return parse_result


def create_preference_from_parse(parse_result: dict[str, Any]) -> dict[str, Any]:
    # ── v2 path: SearchIntent present ─────────────────────────────────────────
    intent = _extract_search_intent(parse_result)
    if intent is not None:
        return _create_preference_from_intent_v2(intent, parse_result)

    # ── legacy path (unchanged) ───────────────────────────────────────────────
    user_location = _read_user_location(parse_result)
    search_origin = build_search_origin(parse_result)
    has_user_location = search_origin.get("type") == "user_location" and bool(user_location)
    anchor_location = _read_anchor_location(parse_result)
    origin_location = _read_search_origin_location(search_origin)
    has_anchor_location = bool(anchor_location or origin_location)
    filter_tree = parse_result.get("filter_tree") or {}
    location_mode = parse_result.get("location_mode") or (filter_tree.get("location") or {}).get("mode") or "unknown"
    has_usable_filter = int(filter_tree.get("usable_filter_count") or 0) > 0

    if not parse_result.get("can_show_recommendations", parse_result.get("ready_for_recommendation")) and not has_usable_filter:
        raise ValueError("Parse result is not ready for recommendation.")
    if parse_result.get("recommendation_level") == "none" and not (has_user_location or has_anchor_location or has_usable_filter):
        raise ValueError("Parse result has no recommendation level.")
    intent = parse_result.get("conversation_intent") or parse_result.get("intent")
    if intent in BLOCKED_INTENTS and not has_user_location:
        raise ValueError("Conversation intent is not eligible for recommendation.")
    if intent == "unknown" and not (has_user_location or has_anchor_location or has_usable_filter):
        raise ValueError("Conversation intent is not eligible for recommendation.")

    if parse_result.get("location_status") in BLOCKED_LOCATION_STATUSES and not has_user_location:
        raise ValueError("Location is not eligible for recommendation.")
    if parse_result.get("unresolved_location") or (location_mode in {"near_anchor", "city_center"} and not has_anchor_location):
        raise ValueError("Location could not be resolved to coordinates.")

    slots = parse_result.get("slots") or {}
    area = slots.get("area") or parse_result.get("canonical_area")
    if has_user_location:
        area = None
    elif location_mode == "anywhere":
        area = None
    elif location_mode == "near_anchor":
        area = parse_result.get("location_display_label") or parse_result.get("anchor_name") or area
    elif location_mode == "city_center":
        area = parse_result.get("canonical_area") or area

    # POI centroid: khi user nói "gần cafe" + cung cấp khu vực,
    # geocode khu vực → gọi Overpass lấy tất cả POI loại đó → dùng centroid làm anchor.
    # Fallback về area mode nếu Overpass fail hoặc không có kết quả.
    if location_mode == "area" and area and not has_anchor_location:
        nearby_poi_key = filter_tree.get("location", {}).get("nearby_poi_key")
        if nearby_poi_key:
            centroid = _resolve_poi_centroid(area, nearby_poi_key)
            if centroid:
                anchor_lat, anchor_lon = centroid
                location_mode = "near_anchor"
                anchor_location = {"lat": anchor_lat, "lon": anchor_lon, "radius_km": 2.0}
                has_anchor_location = True

    accommodation_types = slots.get("accommodation_types") or []
    if isinstance(accommodation_types, str):
        accommodation_types = [accommodation_types]
    preferred_type = (accommodation_types[0] if accommodation_types else None) or slots.get("preferred_type") or slots.get("accommodation_type") or None
    if preferred_type not in DOWNSTREAM_TYPES:
        preferred_type = None

    used_default_slots = dict(parse_result.get("used_default_slots") or {})
    budget = slots.get("budget") or slots.get("budget_max")
    if budget is None:
        budget = 0
        used_default_slots["budget"] = {
            "value": 0,
            "reason": "user_missing_budget_no_budget_filter",
        }

    guest_count = slots.get("guest_count")
    if guest_count is None:
        guest_count = 1
        used_default_slots["guest_count"] = {
            "value": 1,
            "reason": "user_missing_guest_count_safe_minimum",
        }

    filter_tree_json = dict(filter_tree)
    filter_tree_json["search_origin"] = search_origin

    preference_kwargs = {
        "area": area,
        "budget": budget,
        "guest_count": guest_count,
        "preferred_type": preferred_type,
        "required_amenities": slots.get("required_amenities") or [],
        "location_mode": location_mode,
        "location_label": search_origin.get("label") or parse_result.get("location_display_label") or area,
        "anchor_kind": parse_result.get("anchor_kind"),
        "filter_tree_json": filter_tree_json,
        "soft_filter_summary": parse_result.get("soft_filter_summary") or "",
    }
    if has_user_location and user_location:
        preference_kwargs.update(
            {
                "user_latitude": user_location["lat"],
                "user_longitude": user_location["lon"],
                "search_radius_km": user_location.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM,
            }
        )
    elif origin_location or anchor_location:
        location = origin_location or anchor_location
        preference_kwargs.update(
            {
                "user_latitude": location["lat"],
                "user_longitude": location["lon"],
                "search_radius_km": location.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM,
            }
        )

    preference = UserPreference.objects.create(**preference_kwargs)

    # Overpass enrichment disabled: was only used for coordinate backfilling, but:
    # 1. Overpass queries take 6+ seconds (major latency contributor)
    # 2. Coordinates should already be set during accommodation creation
    # 3. Results aren't included in the response anyway
    # TODO: Consider running as async task if coordinate backfilling becomes needed again

    return {
        "pref_id": preference.id,
        "recommendation_url": reverse("recommendation_result", kwargs={"pref_id": preference.id}),
        "used_default_slots": used_default_slots,
        "user_location_used": has_user_location,
        "search_origin": search_origin,
    }


def _read_user_location(parse_result: dict[str, Any]) -> dict[str, float] | None:
    raw_location = parse_result.get("user_location")
    if not isinstance(raw_location, dict):
        raw_location = (parse_result.get("slots") or {}).get("user_location")
    if not isinstance(raw_location, dict):
        return None

    try:
        lat = float(raw_location.get("lat"))
        lon = float(raw_location.get("lon"))
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    radius_km = raw_location.get("radius_km") or raw_location.get("radius")
    try:
        radius_km = float(radius_km) if radius_km is not None else DEFAULT_NEARBY_RADIUS_KM
    except (TypeError, ValueError):
        radius_km = DEFAULT_NEARBY_RADIUS_KM

    radius_km = min(max(radius_km, 1.0), 50.0)
    return {"lat": lat, "lon": lon, "radius_km": radius_km}


def _read_anchor_location(parse_result: dict[str, Any]) -> dict[str, float] | None:
    location_mode = parse_result.get("location_mode")
    if location_mode not in {"near_anchor", "near_user", "city_center"}:
        return None

    try:
        lat = float(parse_result.get("anchor_lat"))
        lon = float(parse_result.get("anchor_lon"))
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    slots = parse_result.get("slots") or {}
    try:
        radius_km = float(
            slots.get("search_radius_km")
            or parse_result.get("search_radius_km")
            or parse_result.get("anchor_radius_km")
            or DEFAULT_NEARBY_RADIUS_KM
        )
    except (TypeError, ValueError):
        radius_km = DEFAULT_NEARBY_RADIUS_KM

    radius_km = min(max(radius_km, 1.0), 50.0)
    return {"lat": lat, "lon": lon, "radius_km": radius_km}


def _resolve_poi_centroid(area: str, poi_type_key: str) -> tuple[float, float] | None:
    """
    Geocode an area name, then fetch POIs of poi_type_key in that area from Overpass.
    Returns the centroid of all found POIs, or None on any failure.
    """
    try:
        from .nominatim_geocoder import geocode_street_address
        from OpenStreetMap_API.services import get_poi_centroid

        coords = geocode_street_address(f"{area}, Việt Nam")
        if not coords:
            return None
        area_lat, area_lon = coords
        return get_poi_centroid(poi_type_key, area_lat, area_lon, radius=3000)
    except Exception:
        return None


def enrich_near_anchor_with_overpass(
    parse_result: dict[str, Any],
    *,
    radius_m: int = 3000,
) -> list[dict]:
    """
    Khi location_mode == "near_anchor" (user tìm gần một địa danh cụ thể),
    gọi Overpass tìm các khách sạn OSM quanh tọa độ đó rồi match với DB.

    Trả về list các kết quả (có thể rỗng nếu Overpass unavailable hoặc không tìm thấy).
    Kết quả được đính vào parse_result["overpass_nearby_hotels"].
    """
    if parse_result.get("location_mode") not in {"near_anchor", "near_user"}:
        return []

    anchor_lat = parse_result.get("anchor_lat")
    anchor_lon = parse_result.get("anchor_lon")
    if anchor_lat is None or anchor_lon is None:
        return []

    try:
        from OpenStreetMap_API.services import search_accommodations_near_coords
        results = search_accommodations_near_coords(anchor_lat, anchor_lon, radius_m=radius_m)
    except Exception:
        results = []

    parse_result["overpass_nearby_hotels"] = results
    return results


# ─────────────────────────────────────────────────────────────────────────────
# v2 helpers — SearchIntent support
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float_bridge(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int_bridge(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _extract_search_intent(parse_result: dict[str, Any]) -> Any:
    """
    Return a SearchIntent from parse_result["search_intent_v2"], or None.
    Accepts both SearchIntent objects (direct call from new pipeline) and
    serialised dicts (round-tripped through JSON).
    """
    try:
        from .nlu.dto import SearchIntent
    except ImportError:
        return None

    raw = parse_result.get("search_intent_v2")
    if raw is None:
        return None
    if isinstance(raw, SearchIntent):
        return raw
    if isinstance(raw, dict):
        return _reconstruct_intent_from_dict(raw)
    return None


def _reconstruct_intent_from_dict(data: dict[str, Any]) -> Any:
    """Rebuild a SearchIntent from its serialised dict representation."""
    from .nlu.dto import (
        LocationMode,
        LocationStatus,
        ResolvedLocation,
        SearchIntent,
        UserLocationInput,
    )

    loc_data = data.get("location") or {}

    try:
        loc_mode = LocationMode(loc_data.get("mode", "unknown"))
    except ValueError:
        loc_mode = LocationMode.UNKNOWN

    try:
        loc_status = LocationStatus(loc_data.get("status", "none"))
    except ValueError:
        loc_status = LocationStatus.NONE

    loc = ResolvedLocation(
        status=loc_status,
        mode=loc_mode,
        canonical_area=loc_data.get("canonical_area"),
        display_label=loc_data.get("display_label"),
        anchor_name=loc_data.get("anchor_name"),
        anchor_kind=loc_data.get("anchor_kind"),
        latitude=_safe_float_bridge(loc_data.get("latitude")),
        longitude=_safe_float_bridge(loc_data.get("longitude")),
        radius_km=float(loc_data.get("radius_km") or 10.0),
        provider=loc_data.get("provider"),
        nearby_poi_key=loc_data.get("nearby_poi_key"),
        nearby_poi_label=loc_data.get("nearby_poi_label"),
        raw_phrase=loc_data.get("raw_phrase"),
        cache_hit=bool(loc_data.get("cache_hit")),
        debug=loc_data.get("debug") or {},
    )

    ul_data = data.get("user_location")
    user_location = None
    if isinstance(ul_data, dict) and ul_data.get("lat") and ul_data.get("lon"):
        try:
            user_location = UserLocationInput(
                lat=float(ul_data["lat"]),
                lon=float(ul_data["lon"]),
                radius_km=float(ul_data.get("radius_km") or 10.0),
            )
        except (KeyError, TypeError, ValueError):
            pass

    return SearchIntent(
        raw_text=data.get("raw_text") or "",
        locale=data.get("locale") or "vi",
        conversation_intent=data.get("conversation_intent") or "search",
        input_kind=data.get("input_kind") or "unknown",
        location=loc,
        user_location=user_location,
        selected_place=data.get("selected_place"),
        area=data.get("area"),
        hotel_name=data.get("hotel_name"),
        accommodation_types=list(data.get("accommodation_types") or []),
        budget=_safe_int_bridge(data.get("budget")),
        budget_min=_safe_int_bridge(data.get("budget_min")),
        budget_max=_safe_int_bridge(data.get("budget_max")),
        guest_count=_safe_int_bridge(data.get("guest_count")),
        trip_days=_safe_int_bridge(data.get("trip_days")),
        required_amenities=list(data.get("required_amenities") or []),
        priorities=list(data.get("priorities") or []),
        special_requirements=list(data.get("special_requirements") or []),
        rating_min=_safe_float_bridge(data.get("rating_min")),
        confidence=float(data.get("confidence") or 0.0),
        assumptions=data.get("assumptions") or {},
        used_default_slots=data.get("used_default_slots") or {},
        debug=data.get("debug") or {},
    )


def _validate_intent_for_recommendation(intent: Any) -> None:
    """
    Guard equivalent to the validation block in create_preference_from_parse()
    but operating on a typed SearchIntent.
    Raises ValueError with a descriptive message on failure.
    """
    from .nlu.dto import LocationMode, LocationStatus

    loc = intent.location
    mode = loc.mode
    status = loc.status

    usable = usable_filters_from_intent(intent)

    # Must have at least one usable filter
    if not usable:
        raise ValueError("No usable filters for recommendation.")

    # Greeting with no filters is not eligible
    if intent.input_kind == "greeting":
        raise ValueError("Conversation intent is not eligible for recommendation.")

    # Conflict / multiple_choice location blocks creation (legacy parity)
    if status.value in BLOCKED_LOCATION_STATUSES:
        raise ValueError(
            f"Location status '{status.value}' is not eligible for recommendation."
        )

    # near_anchor / city_center requires resolved coordinates
    if mode in {LocationMode.NEAR_ANCHOR, LocationMode.CITY_CENTER}:
        if loc.latitude is None:
            raise ValueError(
                "Location could not be resolved to coordinates."
            )

    # near_user without GPS: only block when there are zero non-location filters
    if mode == LocationMode.NEAR_USER and intent.user_location is None:
        non_location = [
            f for f in usable
            if f not in {"location", "location_anywhere", "nearby_poi"}
        ]
        if not non_location:
            raise ValueError(
                "near_user mode requires GPS coordinates or at least one other filter."
            )


def _build_used_default_slots_v2(intent: Any) -> dict[str, Any]:
    """Mirror the used_default_slots tracking from the legacy path."""
    used: dict[str, Any] = dict(intent.used_default_slots or {})
    if not intent.budget and not intent.budget_max and not intent.budget_min:
        used.setdefault("budget", {
            "value": 0,
            "reason": "user_missing_budget_no_budget_filter",
        })
    if not intent.guest_count:
        used.setdefault("guest_count", {
            "value": 1,
            "reason": "user_missing_guest_count_safe_minimum",
        })
    return used


def _create_preference_from_intent_v2(
    intent: Any,
    parse_result: dict[str, Any],
) -> dict[str, Any]:
    """
    v2 path for create_preference_from_parse().

    Validates intent, delegates to the new adapter for the DB write,
    then returns the same response shape as the legacy path so callers
    don't need to distinguish between paths.
    """
    from django.urls import reverse

    from .adapters.search_intent_to_user_preference import create_user_preference_from_intent
    from .nlu.dto import LocationMode

    _validate_intent_for_recommendation(intent)

    preference = create_user_preference_from_intent(intent)

    # Overpass enrichment — same logic as legacy path
    loc = intent.location
    if loc.mode in {LocationMode.NEAR_ANCHOR, LocationMode.NEAR_USER} and loc.latitude is not None:
        try:
            pseudo = {
                "location_mode": loc.mode.value,
                "anchor_lat": loc.latitude,
                "anchor_lon": loc.longitude,
            }
            enrich_near_anchor_with_overpass(pseudo)
            if "overpass_nearby_hotels" in pseudo:
                parse_result["overpass_nearby_hotels"] = pseudo["overpass_nearby_hotels"]
        except Exception:
            pass

    used_default_slots = _build_used_default_slots_v2(intent)
    search_origin = (preference.filter_tree_json or {}).get("search_origin") or {}
    has_user_location = (
        intent.user_location is not None
        and loc.mode == LocationMode.NEAR_USER
    )

    return {
        "pref_id": preference.id,
        "recommendation_url": reverse(
            "recommendation_result", kwargs={"pref_id": preference.id}
        ),
        "used_default_slots": used_default_slots,
        "user_location_used": has_user_location,
        "search_origin": search_origin,
    }


def _read_search_origin_location(search_origin: dict[str, Any]) -> dict[str, float] | None:
    if search_origin.get("type") not in COORDINATE_ORIGIN_TYPES:
        return None
    try:
        lat = float(search_origin.get("latitude"))
        lon = float(search_origin.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    try:
        radius_km = float(search_origin.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM)
    except (TypeError, ValueError):
        radius_km = DEFAULT_NEARBY_RADIUS_KM
    radius_km = min(max(radius_km, 1.0), 50.0)
    return {"lat": lat, "lon": lon, "radius_km": radius_km}
