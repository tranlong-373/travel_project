import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .recommendation_bridge import create_preference_from_parse
from .schema import CORE_SLOTS, INTENT_DEFAULT, SCHEMA_VERSION
from .services import has_recommendation_signal, parse_user_text

logger = logging.getLogger(__name__)


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "chat_api",
            "parser_mode": "hybrid_hf_transformers",
            "model": os.getenv("CHAT_API_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
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
    confirmed_slots = body.get("confirmed_slots") or body.get("slots")
    if isinstance(confirmed_slots, dict):
        result = _build_confirmed_result(confirmed_slots)
    else:
        text = (body.get("text") or "").strip()
        if not text:
            return JsonResponse({"error": "Field 'text' is required"}, status=400)

        context_slots = _read_context_slots(body)
        try:
            result = parse_user_text(text, locale=locale, context_slots=context_slots)
        except Exception:
            logger.exception("chat_api submit endpoint failed")
            return JsonResponse({"error": "Parser temporarily unavailable"}, status=503)

    if not result["ready_for_recommendation"]:
        result.update(
            {
                "created_preference": False,
                "pref_id": None,
                "recommendation_url": None,
            }
        )
        return JsonResponse(result, status=200)

    bridge_result = create_preference_from_parse(result)
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


def _build_confirmed_result(slots):
    missing_slots = []
    for key in CORE_SLOTS:
        if key == "budget":
            if not (slots.get("budget") or slots.get("budget_max")):
                missing_slots.append(key)
        elif not slots.get(key):
            missing_slots.append(key)

    return {
        "schema_version": SCHEMA_VERSION,
        "intent": INTENT_DEFAULT,
        "slots": slots,
        "missing_slots": missing_slots,
        "suggested_questions": [],
        "ready_for_recommendation": has_recommendation_signal(slots),
        "awaiting_confirmation": False,
        "confirmation_required": False,
        "should_ask_optional": False,
        "follow_up_question": None,
        "parser_mode": "confirmed_slots",
        "location_status": "ok" if slots.get("area") else "unresolved",
        "location_candidates": [],
        "canonical_area": slots.get("area"),
    }


def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        locale = "vi"
    return locale
