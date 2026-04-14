import json
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .recommendation_bridge import create_preference_from_parse
from .services import parse_user_text


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "chat_api",
            "parser_mode": "deterministic_fast",
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
    context_slots = body.get("context_slots")
    result = parse_user_text(text, locale=locale, context_slots=context_slots)
    return JsonResponse(result, status=200)


@csrf_exempt
def submit_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    body, error = _read_json_body(request)
    if error:
        return error

    text = (body.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "Field 'text' is required"}, status=400)

    locale = _normalize_locale(body.get("locale"))
    context_slots = body.get("context_slots")
    result = parse_user_text(text, locale=locale, context_slots=context_slots)

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


def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        locale = "vi"
    return locale
