from __future__ import annotations

from typing import Any

from .suggestion_catalog import catalog_search_stopwords, detect_nearby_poi, normalize_text, tokens
from .suggestion_service import (
    SuggestionService,
    accommodation_search_url,
    clear_suggestion_service_cache,
)


MAX_SUGGESTIONS = 8
ACCOMMODATION_CONFIDENCE = 84
ACCOMMODATION_MARGIN = 6


def clear_suggestion_cache() -> None:
    clear_suggestion_service_cache()


def suggest_places(
    query: str | None,
    *,
    limit: int = MAX_SUGGESTIONS,
    context: str = "chat",
) -> list[dict[str, Any]]:
    return SuggestionService.suggest(query, context=context, limit=limit)


def best_submit_resolution(text: str | None) -> dict[str, Any] | None:
    suggestions = suggest_places(text, limit=5)
    if not suggestions:
        return None

    for suggestion in suggestions:
        if _is_poi_category_clarification(text, suggestion, suggestions):
            return {"type": "poi_category_clarification", "suggestion": suggestion, "suggestions": suggestions}

    top = suggestions[0]
    top_score = _score_percent(top)
    second_score = _score_percent(suggestions[1]) if len(suggestions) > 1 else 0
    if (
        top.get("kind") == "accommodation"
        and top_score >= ACCOMMODATION_CONFIDENCE
        and _is_clear_accommodation_selection(text, top)
        and (
            top_score - second_score >= ACCOMMODATION_MARGIN
            or not _has_strong_place_competitor(top, suggestions[1:])
        )
    ):
        return {"type": "accommodation", "suggestion": top, "suggestions": suggestions}
    return None


def selected_accommodation_result(suggestion: dict[str, Any]) -> dict[str, Any]:
    payload = suggestion.get("payload") or {}
    accommodation_type = payload.get("accommodation_type")
    area = payload.get("area")
    destination = payload.get("destination") or suggestion.get("title") or suggestion.get("label")
    url = accommodation_search_url(str(destination or ""))
    slots = {
        "area": area,
        "budget": None,
        "guest_count": None,
        "preferred_type": accommodation_type,
        "accommodation_type": accommodation_type,
        "accommodation_types": [accommodation_type] if accommodation_type else [],
        "required_amenities": [],
        "priorities": [],
        "special_requirements": [],
        "trip_days": None,
        "room_count": None,
        "rating": None,
        "check_in": None,
        "check_out": None,
        "location_phrase": destination,
        "location_mode": "area" if area else "unknown",
    }
    return {
        "schema_version": "2.0",
        "intent": "recommend_accommodation",
        "conversation_intent": "recommend_accommodation",
        "slots": slots,
        "raw_text": destination,
        "parser_mode": "smart_suggestion_accommodation",
        "location_status": "ok" if area else "unresolved",
        "location_candidates": [],
        "canonical_area": area,
        "location_confidence": 1.0,
        "location_source": "smart_suggestion_accommodation",
        "location_mode": slots["location_mode"],
        "location_phrase": destination,
        "matched_text": destination,
        "accommodation_type": accommodation_type,
        "accommodation_types": slots["accommodation_types"],
        "ready_for_recommendation": True,
        "can_show_recommendations": True,
        "recommendation_level": "partial",
        "missing_slots": [],
        "suggested_questions": [],
        "follow_up_question": None,
        "awaiting_confirmation": False,
        "confirmation_required": False,
        "confirmation_heading": "Tìm thấy chỗ ở",
        "polite_bot_message": f"Mình tìm thấy {destination}. Bạn có thể mở danh sách đang lọc theo tên này.",
        "bot_message": f"Mình tìm thấy {destination}. Bạn có thể mở danh sách đang lọc theo tên này.",
        "confirm_table": [
            {
                "key": "selected_accommodation",
                "label": "Chỗ ở",
                "value": destination,
                "display_value": suggestion.get("subtitle") or destination,
            }
        ],
        "recommendation_url": url,
        "recommendation_action": {
            "visible": True,
            "enabled": True,
            "eligible": True,
            "requires_submit": False,
            "pref_id": None,
            "url": url,
            "reason": "selected_accommodation",
        },
        "smart_suggestion": suggestion,
        "usable_filters": ["accommodation_name"],
    }


def poi_category_clarification_result(text: str | None, suggestion: dict[str, Any]) -> dict[str, Any]:
    payload = suggestion.get("payload") or {}
    title = payload.get("nearby_place") or payload.get("name") or suggestion.get("label") or suggestion.get("title") or "địa điểm"
    question = f"Bạn muốn gần {title} ở khu vực nào?"
    return {
        "schema_version": "2.0",
        "intent": "recommend_accommodation",
        "conversation_intent": "recommend_accommodation",
        "slots": {
            "area": None,
            "budget": None,
            "guest_count": None,
            "preferred_type": payload.get("accommodation_type"),
            "accommodation_type": payload.get("accommodation_type"),
            "accommodation_types": [payload["accommodation_type"]] if payload.get("accommodation_type") else [],
            "required_amenities": [],
            "priorities": [],
            "special_requirements": [],
            "trip_days": None,
            "room_count": None,
            "rating": None,
            "check_in": None,
            "check_out": None,
            "location_phrase": title,
            "location_mode": "nearby_place",
            "nearby_place": title,
        },
        "raw_text": text or "",
        "parser_mode": "smart_suggestion_poi_category",
        "location_status": "ambiguous",
        "location_candidates": [],
        "canonical_area": None,
        "location_confidence": 0.72,
        "location_source": "catalog_poi",
        "matched_text": title,
        "location_mode": "nearby_place",
        "location_phrase": title,
        "nearby_place": title,
        "geocoder_called": False,
        "geocoder_reason": "poi_category_needs_area",
        "ambiguous_location": True,
        "ambiguous_location_question": question,
        "unresolved_location": False,
        "ready_for_recommendation": False,
        "can_show_recommendations": False,
        "recommendation_level": "none",
        "missing_slots": ["location"],
        "suggested_questions": [question],
        "follow_up_question": question,
        "awaiting_confirmation": True,
        "confirmation_required": True,
        "polite_bot_message": f"Mình hiểu bạn muốn gần {title}. {question}",
        "bot_message": f"Mình hiểu bạn muốn gần {title}. {question}",
        "recommendation_action": {
            "visible": True,
            "enabled": False,
            "eligible": False,
            "requires_submit": False,
            "pref_id": None,
            "url": None,
            "reason": "poi_category_needs_anchor",
        },
        "smart_suggestion": suggestion,
        "usable_filters": [],
    }


def suggestion_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = payload or {}
    selected = payload.get("smart_suggestion") if isinstance(payload.get("smart_suggestion"), dict) else None
    if selected:
        selected = dict(selected)
        merged_payload = {key: value for key, value in payload.items() if key != "smart_suggestion"}
        selected["payload"] = {**(selected.get("payload") or {}), **merged_payload}
        selected.setdefault("label", selected.get("title"))
        selected.setdefault("title", selected.get("label"))
        selected.setdefault("kind", selected["payload"].get("smart_kind") or selected.get("type"))
        return selected
    if payload.get("selected_accommodation_id"):
        return SuggestionService.accommodation_by_id(payload["selected_accommodation_id"])
    return None


def attach_ambiguous_suggestions(
    result: dict[str, Any],
    text: str | None,
    *,
    limit: int = 5,
) -> bool:
    # When a spatial anchor is already resolved to coordinates, the user's
    # intent is clear — show results near that point.  Do not override with
    # hotel-name suggestions regardless of can_show_recommendations, because
    # geocoded coordinates supersede any prior "multiple_choice" ambiguity.
    if (
        result.get("location_mode") in {"near_anchor", "city_center"}
        and result.get("anchor_lat") is not None
    ):
        return False

    # For specific street addresses, never show hotel-name/amenity disambiguation.
    # If geocoding succeeded we proceed above; if it failed, the parser will
    # ask the user to clarify the area separately.
    if result.get("input_type") == "address" and result.get("location_mode") == "near_anchor":
        return False

    search_text = _ambiguous_search_text(result, text)
    suggestions = _clarification_candidates(result, text, suggest_places(search_text, limit=limit))
    if not suggestions:
        return False

    force_prompt = _has_high_value_candidate(suggestions)
    needs_prompt = force_prompt or not result.get("can_show_recommendations", result.get("ready_for_recommendation"))
    if not needs_prompt:
        return False

    question = "Mình thấy vài khả năng trong câu của bạn. Bạn muốn dùng gợi ý nào?"
    result["smart_suggestions"] = suggestions
    result["smart_suggestion_candidates"] = suggestions
    result["smart_suggestion_question"] = question
    result["needs_user_action"] = True
    result["awaiting_confirmation"] = True
    result["confirmation_required"] = True
    result["confirmation_type"] = "explicit"
    result["can_show_recommendations"] = False
    result["ready_for_recommendation"] = False
    result["created_preference"] = False
    result["pref_id"] = None
    result["recommendation_url"] = None
    result["follow_up_question"] = question
    result["suggested_questions"] = [question]
    result["polite_bot_message"] = question
    result["bot_message"] = question
    result["recommendation_action"] = {
        "visible": True,
        "enabled": False,
        "eligible": False,
        "requires_submit": False,
        "pref_id": None,
        "url": None,
        "reason": "smart_suggestion_needs_choice",
    }
    return True


def _ambiguous_search_text(result: dict[str, Any], text: str | None) -> str | None:
    """Return the most specific fragment to search for suggestions.

    When the parser already resolved accommodation type and only the location
    is ambiguous (near_anchor / city_center mode), search on the raw location
    phrase instead of the full sentence.  This prevents spurious token matches
    between accommodation keywords (e.g. "ho" from "căn hộ") and unrelated
    catalog items (e.g. "Hồ bơi").
    """
    location_mode = result.get("location_mode")
    if location_mode in {"near_anchor", "city_center"}:
        phrase = (
            result.get("location_phrase")
            or result.get("anchor_name")
            or result.get("matched_text")
        )
        if phrase:
            return str(phrase)
    return text


def _is_poi_category_clarification(
    text: str | None,
    top: dict[str, Any],
    suggestions: list[dict[str, Any]],
) -> bool:
    if top.get("kind") != "poi_category" or _score_percent(top) < 80:
        return False
    if detect_nearby_poi(text):
        return True
    if any(
        item.get("kind") in {"area", "cached_poi", "accommodation"}
        and _score_percent(item) >= max(_score_percent(top), 88)
        for item in suggestions[1:]
    ):
        return False

    payload = top.get("payload") or {}
    category_tokens: set[str] = set()
    for value in [
        payload.get("name"),
        payload.get("nearby_place"),
        top.get("title"),
        top.get("label"),
        top.get("matched_alias"),
    ]:
        category_tokens.update(tokens(value))
    meaningful = tokens(text) - category_tokens - catalog_search_stopwords()
    return not meaningful


def _clarification_candidates(
    result: dict[str, Any],
    text: str | None,
    suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    location_mode = result.get("location_mode")
    location_status = result.get("location_status")
    # When location is already the only unresolved part, only surface location-type
    # candidates — skip amenities and accommodation types to avoid false matches
    # caused by tokens in the accommodation phrase (e.g. "ho" from "căn hộ").
    location_focused = (
        location_mode in {"near_anchor", "city_center"}
        and location_status in {"unresolved", "ambiguous"}
    )
    for item in suggestions:
        if _score_percent(item) < 80:
            continue
        if item.get("kind") == "poi_category" and not detect_nearby_poi(text):
            continue
        # Amenities are never useful for disambiguation — users type them
        # naturally and the parser extracts them directly.
        if item.get("kind") == "amenity":
            continue
        if location_focused and item.get("kind") == "accommodation_type":
            continue
        label = str(item.get("label") or item.get("title") or "").strip()
        if not label or normalize_text(label) == "smart suggestion":
            continue
        if _suggestion_already_in_result(item, result):
            continue
        identity = f"{item.get('kind')}:{item.get('object_id') or (item.get('payload') or {}).get('key') or label}"
        if identity in seen:
            continue
        seen.add(identity)
        output.append(item)
    return output


def _suggestion_already_in_result(item: dict[str, Any], result: dict[str, Any]) -> bool:
    slots = result.get("slots") or {}
    payload = item.get("payload") or {}
    kind = item.get("kind")
    if kind == "amenity":
        amenity = payload.get("amenity_key") or ((payload.get("required_amenities") or [None])[0])
        return bool(amenity and amenity in (slots.get("required_amenities") or []))
    if kind == "accommodation_type":
        accommodation_type = payload.get("accommodation_type")
        if not accommodation_type:
            return False
        # Skip if the accommodation type was already extracted by the parser
        return bool(
            accommodation_type in (slots.get("accommodation_types") or [])
            or accommodation_type == slots.get("accommodation_type")
            or accommodation_type == slots.get("preferred_type")
        )
    if kind == "area":
        area = payload.get("area") or payload.get("name")
        current_area = result.get("canonical_area") or slots.get("area")
        return normalize_text(area) == normalize_text(current_area)
    if kind == "poi_category":
        nearby_place = payload.get("nearby_place") or payload.get("name")
        return normalize_text(nearby_place) == normalize_text(result.get("nearby_place") or slots.get("nearby_place"))
    return False


def _has_high_value_candidate(suggestions: list[dict[str, Any]]) -> bool:
    return any(
        item.get("kind") in {"accommodation", "cached_poi"}
        and _score_percent(item) >= ACCOMMODATION_CONFIDENCE
        for item in suggestions
    )


def _is_clear_accommodation_selection(text: str | None, suggestion: dict[str, Any]) -> bool:
    payload = suggestion.get("payload") or {}
    suggestion_tokens: set[str] = set()
    for value in [
        suggestion.get("label"),
        suggestion.get("title"),
        suggestion.get("matched_alias"),
        payload.get("destination"),
        payload.get("area"),
        payload.get("accommodation_type"),
    ]:
        suggestion_tokens.update(tokens(value))
    remaining = tokens(text) - suggestion_tokens - catalog_search_stopwords()
    return not remaining


def _has_strong_place_competitor(top: dict[str, Any], competitors: list[dict[str, Any]]) -> bool:
    top_score = _score_percent(top)
    return any(
        item.get("kind") in {"accommodation", "area", "cached_poi"}
        and _score_percent(item) >= top_score - ACCOMMODATION_MARGIN
        for item in competitors
    )


def _score_percent(item: dict[str, Any]) -> int:
    if item.get("score_percent") is not None:
        try:
            return int(item.get("score_percent") or 0)
        except (TypeError, ValueError):
            return 0
    try:
        score = float(item.get("score") or 0)
    except (TypeError, ValueError):
        return 0
    return int(round(score * 100)) if 0 <= score <= 1 else int(round(score))
