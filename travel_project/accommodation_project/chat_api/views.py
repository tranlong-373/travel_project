import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .filter_tree import build_filter_tree, soft_filter_summary
from .recommendation_bridge import create_preference_from_parse
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .services import _finalize_convenience_response, has_recommendation_signal, parse_user_text
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
    try:
        result = parse_user_text(text, locale=locale, context_slots=context_slots)
    except Exception:
        logger.exception("chat_api parse endpoint failed")
        return JsonResponse({"error": "Parser temporarily unavailable"}, status=503)
    return JsonResponse(result, status=200)


@csrf_exempt
def submit_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    body, error = _read_json_body(request)
    if error:
        return error

    locale = _normalize_locale(body.get("locale"))
    quick_reply_payload = _read_quick_reply_payload(body)
    context_slots = _read_context_slots(body)
    user_location = _read_user_location(body)
    if quick_reply_payload:
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

        try:
            result = parse_user_text(text, locale=locale, context_slots=context_slots)
        except Exception:
            logger.exception("chat_api submit endpoint failed")
            return JsonResponse({"error": "Parser temporarily unavailable"}, status=503)

    _attach_user_location(result, user_location)

    if not result.get("can_show_recommendations", result.get("ready_for_recommendation")):
        result.update(
            {
                "created_preference": False,
                "pref_id": None,
                "recommendation_url": None,
            }
        )
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
        return JsonResponse(result, status=200)

    result.update({"created_preference": True, **bridge_result})
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


def _build_confirmed_result(slots):
    slots = validate_slots(slots)
    missing_slots = core_missing_slots(slots)
    canonical_area = slots.get("area")

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
        "location_status": "ok" if canonical_area else "unresolved",
        "location_candidates": [],
        "canonical_area": canonical_area,
        "location_confidence": 1.0 if canonical_area else 0.0,
        "location_source": "confirmed_slots" if canonical_area else "none",
        "matched_text": canonical_area,
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
