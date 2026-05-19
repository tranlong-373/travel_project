import json
import logging
import os

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .filter_tree import build_filter_tree, soft_filter_summary
from .recommendation_bridge import attach_recommendation_action, create_preference_from_parse
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .search_origin import build_search_origin
from .services import _finalize_convenience_response, has_recommendation_signal, parse_user_text
from .smart_suggestions import (
    attach_ambiguous_suggestions,
    best_submit_resolution,
    poi_category_clarification_result,
    selected_accommodation_result,
    suggestion_from_payload,
    suggest_places,
)
from .slot_validator import core_missing_slots, validate_slots
from .text_normalizer import normalize_user_text

logger = logging.getLogger(__name__)


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "chat_api",
            "parser_mode": "hybrid_hf_transformers",
            "light_model": os.getenv("CHAT_API_LIGHT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"),
            "model": os.getenv("CHAT_LLM_MODEL") or os.getenv("CHAT_API_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"),
            "fallback_model": os.getenv("CHAT_LLM_FALLBACK_MODEL") or os.getenv("CHAT_API_FALLBACK_MODEL") or os.getenv("CHAT_API_LIGHT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"),
            "strong_model": os.getenv("CHAT_API_STRONG_MODEL", ""),
            "llm_strategy": os.getenv("CHAT_API_LLM_STRATEGY", "auto"),
            "prompt_example_count": os.getenv("CHAT_API_PROMPT_EXAMPLE_COUNT", "5"),
            "use_ner_fallback": os.getenv("CHAT_API_USE_NER", "0") == "1",
        }
    )


@require_GET
def suggestions(request):
    return _suggestion_response(request)


@require_GET
def search_suggest(request):
    response = _suggestion_response(request, include_legacy_fields=True)
    return response


def _suggestion_response(request, *, include_legacy_fields: bool = False):
    query = request.GET.get("q", "")
    context = request.GET.get("context") or "chat"
    try:
        suggestions = suggest_places(query, context=context)
        payload = {
            "ok": True,
            "query": query,
            "suggestions": suggestions,
        }
        if include_legacy_fields:
            payload["external_called"] = False
        return JsonResponse(payload)
    except Exception as exc:
        logger.exception("suggestion endpoint failed")
        payload = {
            "ok": False,
            "query": query,
            "suggestions": [],
            "error": str(exc),
        }
        if include_legacy_fields:
            payload["external_called"] = False
        return JsonResponse(payload, status=200)


@csrf_exempt
def parse_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    body, error = _read_json_body(request)
    if error:
        return error

    text = (body.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "Field 'text' is required"}, status=400)

    locale = _normalize_locale(body.get("locale"))
    context_slots = _read_context_slots(body)
    include_debug = _debug_requested(request, body)
    try:
        result = parse_user_text(text, locale=locale, context_slots=context_slots, include_debug=include_debug)
    except Exception:
        logger.exception("chat_api parse endpoint failed")
        return JsonResponse({"error": "Parser temporarily unavailable"}, status=503)
    attach_recommendation_action(result, reason="parse_only_no_preference")
    return JsonResponse(result, status=200)


@csrf_exempt
def submit_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    body, error = _read_json_body(request)
    if error:
        return error

    locale = _normalize_locale(body.get("locale"))
    include_debug = _debug_requested(request, body)
    quick_reply_payload = _read_quick_reply_payload(body)
    context_slots = _read_context_slots(body)
    user_location = _read_user_location(body)
    if quick_reply_payload:
        smart_suggestion = suggestion_from_payload(quick_reply_payload)
        if smart_suggestion and smart_suggestion.get("kind") == "accommodation":
            selected_result = selected_accommodation_result(smart_suggestion)
            selected_result["slots"] = _merge_payload(context_slots, selected_result.get("slots") or {})
            return JsonResponse(selected_result, status=200)
        if smart_suggestion and smart_suggestion.get("kind") == "poi_category":
            return JsonResponse(poi_category_clarification_result("", smart_suggestion), status=200)
        context_slots = _merge_payload(context_slots, quick_reply_payload)

    confirmed_slots = body.get("confirmed_slots") or body.get("slots")
    if isinstance(confirmed_slots, dict):
        result = _build_confirmed_result(confirmed_slots)
    elif quick_reply_payload and not (body.get("text") or "").strip():
        result = _build_confirmed_result(context_slots or {})
    else:
        text = (body.get("text") or "").strip()
        if not text:
            return JsonResponse({"error": "Field 'text' is required"}, status=400)

        smart_resolution = best_submit_resolution(text)
        if smart_resolution and smart_resolution["type"] == "accommodation":
            return JsonResponse(selected_accommodation_result(smart_resolution["suggestion"]), status=200)
        if smart_resolution and smart_resolution["type"] == "poi_category_clarification":
            return JsonResponse(
                poi_category_clarification_result(text, smart_resolution["suggestion"]),
                status=200,
            )

        try:
            result = parse_user_text(text, locale=locale, context_slots=context_slots, include_debug=include_debug)
        except Exception:
            logger.exception("chat_api submit endpoint failed")
            return JsonResponse({"error": "Parser temporarily unavailable"}, status=503)
        attach_ambiguous_suggestions(result, text)

    _attach_user_location(result, user_location)

    if not result.get("can_show_recommendations", result.get("ready_for_recommendation")):
        result.update(
            {
                "created_preference": False,
                "pref_id": None,
                "recommendation_url": None,
            }
        )
        attach_recommendation_action(result)
        return JsonResponse(result, status=200)

    try:
        bridge_result = create_preference_from_parse(result)
    except ValueError:
        result.update(
            {
                "created_preference": False,
                "pref_id": None,
                "recommendation_url": None,
            }
        )
        attach_recommendation_action(result, reason="preference_not_created")
        return JsonResponse(result, status=200)

    result.update({"created_preference": True, **bridge_result})
    attach_recommendation_action(result, bridge_result)
    return JsonResponse(result, status=201)


def _read_json_body(request):
    try:
        raw_body = request.body.decode("utf-8")
    except UnicodeDecodeError:
        raw_body = request.body.decode("utf-8", errors="replace")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(body, dict):
        return None, JsonResponse({"error": "JSON body must be an object"}, status=400)

    return body, None


def _read_context_slots(body):
    context_slots = body.get("context_slots")
    if context_slots is None:
        context_slots = body.get("current_slots")
    return context_slots if isinstance(context_slots, dict) else None


def _read_quick_reply_payload(body):
    payload = body.get("quick_reply_payload")
    if payload is None:
        payload = body.get("payload")
    return payload if isinstance(payload, dict) else None


def _merge_payload(context_slots, payload):
    merged = dict(context_slots or {})
    for key, value in payload.items():
        if key in {"required_amenities", "priorities", "special_requirements"}:
            base = merged.get(key) or []
            add = value if isinstance(value, list) else [value]
            merged[key] = list(dict.fromkeys([*base, *add]))
        else:
            merged[key] = value
    if "budget_max" in payload and "budget" not in payload:
        merged["budget"] = payload["budget_max"]
    return merged


def _read_user_location(body):
    raw_location = body.get("user_location")
    if not isinstance(raw_location, dict):
        return None

    try:
        lat = float(raw_location.get("lat"))
        lon = float(raw_location.get("lon"))
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    location = {"lat": lat, "lon": lon}
    accuracy = raw_location.get("accuracy")
    try:
        if accuracy is not None:
            location["accuracy"] = float(accuracy)
    except (TypeError, ValueError):
        pass
    return location


def _attach_user_location(result, user_location):
    if not user_location:
        return

    slots = dict(result.get("slots") or {})
    slots["user_location"] = user_location
    slots["use_current_location"] = True
    slots["area"] = "Vị trí hiện tại"

    result["slots"] = slots
    result["user_location"] = user_location
    result["canonical_area"] = slots.get("area")
    result["location_status"] = "ok"
    result["location_source"] = "browser_geolocation"
    result["ready_for_recommendation"] = True
    result["can_show_recommendations"] = True
    result["location_mode"] = "near_user"
    result["anchor_name"] = "Vị trí hiện tại"
    result["anchor_kind"] = "user_location"
    result["anchor_lat"] = user_location["lat"]
    result["anchor_lon"] = user_location["lon"]
    result["anchor_radius_km"] = 10.0
    result["location_display_label"] = "Gần vị trí hiện tại"

    tree = build_filter_tree(text="", slots=slots, location_result=result).to_dict()
    result["filter_tree"] = tree
    result["available_slots"] = tree["available_slots"]
    result["missing_filter_slots"] = tree["missing_slots"]
    result["partial_intent"] = tree["partial_intent"]
    result["soft_filter_summary"] = soft_filter_summary(tree)
    result["search_origin"] = build_search_origin(result)
    result["location_meta"] = {
        "status": result.get("location_status"),
        "mode": result.get("location_mode"),
        "origin_type": result["search_origin"]["type"],
        "search_origin": result["search_origin"],
        "source": result.get("location_source"),
        "phrase": None,
        "confidence": 1.0,
        "geocoder_called": False,
        "geocoder_reason": "browser_geolocation",
        "canonical_area": result.get("canonical_area"),
        "display_label": result.get("location_display_label"),
        "anchor": {
            "name": result.get("anchor_name"),
            "kind": result.get("anchor_kind"),
            "lat": result.get("anchor_lat"),
            "lon": result.get("anchor_lon"),
            "radius_km": result.get("anchor_radius_km"),
        },
        "map": {"area": None, "display_name": None, "address": {}},
        "rejected_geocoder_results": [],
    }


def _build_confirmed_result(slots):
    raw_slots = dict(slots or {})
    selected_place = raw_slots.get("selected_place") if isinstance(raw_slots.get("selected_place"), dict) else None
    slots = validate_slots(raw_slots)
    if selected_place:
        slots["area"] = None
        slots["location_mode"] = "near_anchor"
        slots["location_phrase"] = selected_place.get("name") or selected_place.get("display_name")
    missing_slots = core_missing_slots(slots)
    canonical_area = slots.get("area")
    has_selected_place = bool(selected_place and selected_place.get("lat") is not None and selected_place.get("lon") is not None)

    result = {
        "schema_version": SCHEMA_VERSION,
        "intent": INTENT_DEFAULT,
        "conversation_intent": INTENT_DEFAULT,
        "slots": slots,
        "missing_slots": missing_slots,
        "suggested_questions": [],
        "ready_for_recommendation": has_recommendation_signal(slots),
        "awaiting_confirmation": False,
        "confirmation_required": False,
        "should_ask_optional": False,
        "follow_up_question": None,
        "parser_mode": "confirmed_slots",
        "location_status": "ok" if canonical_area or has_selected_place else "unresolved",
        "location_candidates": [],
        "canonical_area": canonical_area,
        "location_confidence": 1.0 if canonical_area or has_selected_place else 0.0,
        "location_source": "selected_map_candidate" if has_selected_place else ("confirmed_slots" if canonical_area else "none"),
        "matched_text": canonical_area or (selected_place.get("name") if selected_place else None),
        "selected_place": selected_place,
        "assumptions": [],
        "used_default_slots": {},
    }
    return _finalize_convenience_response(
        result,
        "",
        router={"intent": INTENT_DEFAULT, "confidence": 1.0, "reason": "confirmed_slots"},
        normalized=normalize_user_text(""),
    )


def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        locale = "vi"
    return locale


def _debug_requested(request, body):
    value = request.GET.get("debug") if request is not None else None
    if value is None and isinstance(body, dict):
        value = body.get("debug")
    if value is None:
        return bool(getattr(settings, "DEBUG", False))
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
