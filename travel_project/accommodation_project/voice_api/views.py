import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from chat_api.recommendation_bridge import create_preference_from_parse
from chat_api.services import parse_user_text

from .services.speech_to_text import SpeechToTextError, transcribe_audio_with_metadata
from .services.transcript_cleanup import build_confirmation, cleanup_transcript

logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE = int(os.getenv("VOICE_MAX_AUDIO_MB", "5")) * 1024 * 1024


@csrf_exempt
def parse_voice(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Only POST allowed"}, status=405)

    audio = request.FILES.get("audio") or request.FILES.get("file")
    if audio is None:
        return JsonResponse({"success": False, "error": "Audio file is required"}, status=400)

    if audio.size and audio.size > MAX_AUDIO_SIZE:
        return JsonResponse({"success": False, "error": "Audio file is too large"}, status=413)

    locale = _normalize_locale(request.POST.get("locale"))
    context_slots = _read_context_slots(request.POST.get("context_slots"))
    feature_mode = _normalize_optional(request.POST.get("feature_mode")) or "chat"
    audio_duration = _read_float(request.POST.get("audio_duration") or request.POST.get("duration"))
    audio_quality = _normalize_optional(request.POST.get("audio_quality"))
    accuracy_required = _normalize_optional(request.POST.get("accuracy_required"))
    is_realtime = _read_bool(request.POST.get("is_realtime"))

    try:
        stt_result = transcribe_audio_with_metadata(
            audio,
            feature_mode=feature_mode,
            audio_duration=audio_duration,
            audio_quality=audio_quality,
            accuracy_required=accuracy_required,
            is_realtime=is_realtime,
        )
        transcript = stt_result.transcript
    except SpeechToTextError as exc:
        return JsonResponse(
            {"success": False, "error": str(exc), "error_code": exc.code},
            status=503,
        )
    except Exception:
        logger.exception("voice_api unexpected speech-to-text error")
        return JsonResponse({"success": False, "error": "Speech-to-text unavailable"}, status=503)

    if not transcript:
        return JsonResponse({"success": False, "error": "Transcript is empty"}, status=422)

    cleanup = cleanup_transcript(transcript)

    try:
        parsed_result = parse_user_text(cleanup.cleaned_text, locale=locale, context_slots=context_slots)
    except Exception:
        logger.exception("voice_api chat parser failed")
        return JsonResponse({"success": False, "transcript": transcript, "error": "Parser unavailable"}, status=503)

    confirmation = build_confirmation(cleanup, parsed_result)
    preference_payload = _build_preference_payload(parsed_result)

    return JsonResponse(
        {
            "success": True,
            "transcript": transcript,
            "cleaned_transcript": cleanup.cleaned_text,
            "transcript_cleanup": cleanup.as_dict(),
            "stt_router": stt_result.as_dict(),
            "confirmation": confirmation,
            **preference_payload,
            "ready_for_recommendation": parsed_result.get("ready_for_recommendation", False),
            "awaiting_confirmation": parsed_result.get("awaiting_confirmation", False),
            "confirmation_required": parsed_result.get("confirmation_required", False),
            "confirm_table": parsed_result.get("confirm_table"),
            "confirmation_options": parsed_result.get("confirmation_options"),
            "follow_up_question": parsed_result.get("follow_up_question"),
            "slots": parsed_result.get("slots") or {},
            "parsed_result": parsed_result,
        },
        status=200,
    )


def _normalize_locale(locale):
    locale = (locale or "vi").strip().lower()
    if locale not in ["vi", "en"]:
        locale = "vi"
    return locale


def _read_context_slots(raw_context):
    if not raw_context:
        return None
    try:
        context_slots = json.loads(raw_context)
    except (TypeError, json.JSONDecodeError):
        return None
    return context_slots if isinstance(context_slots, dict) else None


def _normalize_optional(value):
    value = (value or "").strip()
    return value or None


def _read_float(value):
    if value in [None, ""]:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_bool(value):
    if isinstance(value, bool):
        return value
    return (value or "").strip().lower() in ["1", "true", "yes", "on"]


def _build_preference_payload(parsed_result):
    if not parsed_result.get("ready_for_recommendation"):
        return {
            "created_preference": False,
            "pref_id": None,
            "recommendation_url": None,
        }

    try:
        bridge_result = create_preference_from_parse(parsed_result)
    except Exception:
        logger.exception("voice_api could not create preference")
        return {
            "created_preference": False,
            "pref_id": None,
            "recommendation_url": None,
            "save_error": "Could not save recommendation request.",
        }

    return {"created_preference": True, **bridge_result}
