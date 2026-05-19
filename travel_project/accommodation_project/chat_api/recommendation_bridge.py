from __future__ import annotations

from typing import Any

from django.urls import reverse

from preferences.models import UserPreference

from .search_origin import COORDINATE_ORIGIN_TYPES, build_search_origin


DOWNSTREAM_TYPES = {"hotel", "homestay", "hostel", "apartment"}
BLOCKED_INTENTS = {"off_topic", "greeting", "thanks", "help", "goodbye"}
BLOCKED_LOCATION_STATUSES = {"conflict", "multiple_choice"}
DEFAULT_NEARBY_RADIUS_KM = 10.0


def usable_filters_from_parse(parse_result: dict[str, Any]) -> list[str]:
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
