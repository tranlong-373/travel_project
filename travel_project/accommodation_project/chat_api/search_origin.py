from __future__ import annotations

from typing import Any


COORDINATE_ORIGIN_TYPES = {"anchor", "semantic_center", "user_location"}


def build_search_origin(parse_result: dict[str, Any] | None) -> dict[str, Any]:
    parse_result = parse_result or {}
    slots = parse_result.get("slots") or {}
    filter_tree = parse_result.get("filter_tree") or {}
    location = filter_tree.get("location") or {}

    mode = (
        parse_result.get("location_mode")
        or slots.get("location_mode")
        or location.get("mode")
        or "unknown"
    )
    origin_type = _origin_type_for_mode(mode)

    label = (
        parse_result.get("location_display_label")
        or location.get("location_display_label")
        or parse_result.get("canonical_area")
        or slots.get("area")
        or location.get("canonical_area")
    )
    if origin_type == "anchor":
        label = label or parse_result.get("anchor_name") or location.get("anchor_name")
    elif origin_type == "semantic_center":
        label = label or parse_result.get("anchor_name") or location.get("anchor_name") or "Trung tâm TP.HCM"
    elif origin_type == "user_location":
        label = label or "Gần vị trí hiện tại"
    elif origin_type == "none":
        label = None

    latitude = _first_float(
        parse_result.get("anchor_lat"),
        location.get("anchor_lat"),
        (parse_result.get("user_location") or {}).get("lat")
        if isinstance(parse_result.get("user_location"), dict)
        else None,
    )
    longitude = _first_float(
        parse_result.get("anchor_lon"),
        location.get("anchor_lon"),
        (parse_result.get("user_location") or {}).get("lon")
        if isinstance(parse_result.get("user_location"), dict)
        else None,
    )
    radius_km = _first_float(
        parse_result.get("anchor_radius_km"),
        location.get("anchor_radius_km"),
        (parse_result.get("user_location") or {}).get("radius_km")
        if isinstance(parse_result.get("user_location"), dict)
        else None,
        (parse_result.get("user_location") or {}).get("radius")
        if isinstance(parse_result.get("user_location"), dict)
        else None,
    )

    if origin_type not in COORDINATE_ORIGIN_TYPES:
        latitude = None
        longitude = None
        radius_km = None
    elif radius_km is None:
        radius_km = 10.0 if origin_type == "user_location" else 5.0

    return {
        "type": origin_type,
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
    }


def _origin_type_for_mode(mode: str | None) -> str:
    if mode == "area":
        return "area"
    if mode == "city_center":
        return "semantic_center"
    if mode == "near_anchor":
        return "anchor"
    if mode == "near_user":
        return "user_location"
    return "none"


def _first_float(*values: Any) -> float | None:
    for value in values:
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None
