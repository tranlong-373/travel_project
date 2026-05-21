from __future__ import annotations

import os
import re
from enum import Enum


class STTModelLevel(str, Enum):
    WEAK = "weak"
    BALANCED = "balanced"
    STRONG = "strong"


WEAK = STTModelLevel.WEAK.value
BALANCED = STTModelLevel.BALANCED.value
STRONG = STTModelLevel.STRONG.value

STT_MODEL_DEFAULTS = {
    WEAK: "vinai/PhoWhisper-base",
    BALANCED: "vinai/PhoWhisper-medium",
    STRONG: "vinai/PhoWhisper-large",
}

MODEL_ENV_VARS = {
    WEAK: "VOICE_WEAK_MODEL",
    BALANCED: "VOICE_BALANCED_MODEL",
    STRONG: "VOICE_STRONG_MODEL",
}

LEGACY_MODEL_ENV_VARS = {
    WEAK: "VOICE_ASR_WEAK_MODEL",
    BALANCED: "VOICE_ASR_BALANCED_MODEL",
    STRONG: "VOICE_ASR_STRONG_MODEL",
}

MODEL_ALIASES = {
    "fast": WEAK,
    "tiny": WEAK,
    "base": BALANCED,
    "default": BALANCED,
    "accurate": STRONG,
    "small": STRONG,
}

STT_SELECTION_RULES = {
    WEAK: {
        "feature_modes": {"wake_word", "command", "realtime_preview"},
        "accuracy_required": {"speed", "fast", "low"},
        "max_duration_s": 5.0,
    },
    BALANCED: {
        "feature_modes": {"chat", "casual_voice", "recommendation", "search"},
    },
    STRONG: {
        "feature_modes": {
            "dictation",
            "translation",
            "meeting_summary",
            "study_note",
            "code_input",
        },
        "accuracy_required": {"true", "1", "yes", "high", "strict", "accurate"},
        "audio_quality": {"poor", "noisy", "bad"},
        "min_duration_s": 15.0,
    },
}

RETRY_RULES = {
    "confidence_min": 0.75,
    "long_audio_s": 8.0,
    "min_words_for_long_audio": 3,
    "invalid_char_ratio": 0.2,
    "invalid_char_min_count": 3,
}


def get_model_name_for_level(model_level: str | STTModelLevel | None) -> str:
    normalized = normalize_model_level(model_level)
    env_name = MODEL_ENV_VARS[normalized]
    legacy_env_name = LEGACY_MODEL_ENV_VARS[normalized]
    return (os.getenv(env_name) or os.getenv(legacy_env_name) or STT_MODEL_DEFAULTS[normalized]).strip()


def get_stt_model_defaults() -> dict[str, str]:
    return {
        WEAK: get_model_name_for_level(WEAK),
        BALANCED: get_model_name_for_level(BALANCED),
        STRONG: get_model_name_for_level(STRONG),
    }


def normalize_model_level(model_level: str | STTModelLevel | None) -> str:
    if isinstance(model_level, STTModelLevel):
        return model_level.value

    normalized = (model_level or BALANCED).strip().lower()
    normalized = MODEL_ALIASES.get(normalized, normalized)
    if normalized not in STT_MODEL_DEFAULTS:
        return BALANCED
    return normalized


def select_stt_model(
    feature_mode: str,
    audio_duration: float | None = None,
    audio_quality: str | None = None,
    accuracy_required: str | None = None,
    is_realtime: bool = False,
) -> str:
    feature = _normalize(feature_mode) or "chat"
    quality = _normalize(audio_quality)
    accuracy = _normalize(accuracy_required)
    duration = _safe_float(audio_duration)

    strong_rules = STT_SELECTION_RULES[STRONG]
    if (
        feature in strong_rules["feature_modes"]
        or quality in strong_rules["audio_quality"]
        or accuracy in strong_rules["accuracy_required"]
        or (duration is not None and duration >= strong_rules["min_duration_s"])
    ):
        return STRONG

    if feature in STT_SELECTION_RULES[BALANCED]["feature_modes"]:
        return BALANCED

    weak_rules = STT_SELECTION_RULES[WEAK]
    if (
        feature in weak_rules["feature_modes"]
        or (is_realtime and feature in {"wake_word", "realtime_preview"})
        or accuracy in weak_rules["accuracy_required"]
        or (
            duration is not None
            and duration < weak_rules["max_duration_s"]
            and feature not in STT_SELECTION_RULES[BALANCED]["feature_modes"]
        )
    ):
        return WEAK

    return BALANCED


def get_stronger_model(current_model: str) -> str:
    model = normalize_model_level(current_model)
    if model == WEAK:
        return BALANCED
    if model == BALANCED:
        return STRONG
    return STRONG


def retry_reason_for_transcript(
    transcript: str,
    confidence: float | None,
    audio_duration: float | None,
    current_model: str,
) -> str | None:
    if normalize_model_level(current_model) == STRONG:
        return None

    text = (transcript or "").strip()
    if not text:
        return "empty_transcript"

    word_count = _word_count(text)
    if word_count < 2:
        return "transcript_too_short"

    if confidence is not None and confidence < RETRY_RULES["confidence_min"]:
        return "low_confidence"

    duration = _safe_float(audio_duration)
    if duration is not None and duration > RETRY_RULES["long_audio_s"]:
        if word_count < RETRY_RULES["min_words_for_long_audio"]:
            return "too_few_words_for_duration"

    if _has_too_many_invalid_chars(text):
        return "invalid_characters"

    return None


def should_retry_with_stronger_model(
    transcript: str,
    confidence: float | None,
    audio_duration: float | None,
    current_model: str,
) -> bool:
    return retry_reason_for_transcript(
        transcript,
        confidence,
        audio_duration,
        current_model,
    ) is not None


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _safe_float(value: float | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _has_too_many_invalid_chars(text: str) -> bool:
    if not text:
        return False

    invalid_chars = re.findall(r"[^0-9A-Za-zÀ-ỹà-ỹ\s.,!?;:'\"/()\-_%]", text)
    if len(invalid_chars) < RETRY_RULES["invalid_char_min_count"]:
        return False
    return (len(invalid_chars) / max(len(text), 1)) > RETRY_RULES["invalid_char_ratio"]
