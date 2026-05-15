from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .stt_model_selector import (
    BALANCED,
    STT_MODEL_DEFAULTS,
    STRONG,
    WEAK,
    get_stronger_model,
    normalize_model_level,
    select_stt_model,
    should_retry_with_stronger_model,
)

logger = logging.getLogger(__name__)

ASR_MODEL_PROFILES = {
    WEAK: STT_MODEL_DEFAULTS[WEAK],
    BALANCED: STT_MODEL_DEFAULTS[BALANCED],
    STRONG: STT_MODEL_DEFAULTS[STRONG],
    "fast": STT_MODEL_DEFAULTS[WEAK],
    "accurate": STT_MODEL_DEFAULTS[STRONG],
}
DEFAULT_ASR_PROFILE = BALANCED
FAST_ASR_MODEL = ASR_MODEL_PROFILES[WEAK]
DEFAULT_ASR_MODEL = ASR_MODEL_PROFILES[DEFAULT_ASR_PROFILE]


class SpeechToTextError(RuntimeError):
    pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or default


def _default_model_name() -> str:
    explicit_model = os.getenv("VOICE_ASR_MODEL", "").strip()
    if explicit_model:
        return explicit_model

    profile = _env_str("VOICE_ASR_PROFILE", DEFAULT_ASR_PROFILE).lower()
    return ASR_MODEL_PROFILES.get(profile, DEFAULT_ASR_MODEL)


def _default_balanced_model_name() -> str:
    explicit_model = os.getenv("VOICE_ASR_BALANCED_MODEL", "").strip()
    if explicit_model:
        return explicit_model
    return _default_model_name()


@dataclass(frozen=True)
class SpeechToTextConfig:
    model_name: str = field(default_factory=_default_balanced_model_name)
    weak_model_name: str = field(
        default_factory=lambda: _env_str("VOICE_ASR_WEAK_MODEL", STT_MODEL_DEFAULTS[WEAK])
    )
    strong_model_name: str = field(
        default_factory=lambda: _env_str("VOICE_ASR_STRONG_MODEL", STT_MODEL_DEFAULTS[STRONG])
    )
    fallback_model_name: str | None = field(
        default_factory=lambda: os.getenv("VOICE_ASR_FALLBACK_MODEL", FAST_ASR_MODEL) or None
    )
    device: str = field(default_factory=lambda: _env_str("VOICE_DEVICE", "auto"))
    language: str = field(default_factory=lambda: _env_str("VOICE_ASR_LANGUAGE", "vi"))
    task: str = field(default_factory=lambda: _env_str("VOICE_ASR_TASK", "transcribe"))
    max_new_tokens: int = field(default_factory=lambda: _env_int("VOICE_MAX_NEW_TOKENS", 96))
    num_beams: int = field(default_factory=lambda: _env_int("VOICE_NUM_BEAMS", 1))
    chunk_length_s: int = field(default_factory=lambda: _env_int("VOICE_CHUNK_LENGTH_S", 0))
    batch_size: int = field(default_factory=lambda: _env_int("VOICE_ASR_BATCH_SIZE", 1))


@dataclass(frozen=True)
class SpeechToTextAttempt:
    transcript: str
    confidence: float | None
    model_level: str
    model_name: str


@dataclass(frozen=True)
class SpeechToTextResult:
    transcript: str
    confidence: float | None
    selected_model: str
    final_model: str
    selected_model_name: str
    final_model_name: str
    retried: bool
    retry_model: str | None = None
    retry_model_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "confidence": self.confidence,
            "selected_model": self.selected_model,
            "final_model": self.final_model,
            "selected_model_name": self.selected_model_name,
            "final_model_name": self.final_model_name,
            "retried": self.retried,
            "retry_model": self.retry_model,
            "retry_model_name": self.retry_model_name,
        }


class SpeechToTextService:
    def __init__(self, config: SpeechToTextConfig | None = None):
        self.config = config or SpeechToTextConfig()
        self._pipelines: dict[str, Any] = {}
        self._pipeline_model_names: dict[str, str] = {}
        self._pipeline = None
        self._lock = Lock()

    def transcribe(
        self,
        uploaded_file,
        *,
        feature_mode: str | None = None,
        audio_duration: float | None = None,
        audio_quality: str | None = None,
        accuracy_required: str | None = None,
        is_realtime: bool = False,
        model_level: str | None = None,
    ) -> str:
        return self.transcribe_with_metadata(
            uploaded_file,
            feature_mode=feature_mode,
            audio_duration=audio_duration,
            audio_quality=audio_quality,
            accuracy_required=accuracy_required,
            is_realtime=is_realtime,
            model_level=model_level,
        ).transcript

    def transcribe_with_metadata(
        self,
        uploaded_file,
        *,
        feature_mode: str | None = None,
        audio_duration: float | None = None,
        audio_quality: str | None = None,
        accuracy_required: str | None = None,
        is_realtime: bool = False,
        model_level: str | None = None,
    ) -> SpeechToTextResult:
        if uploaded_file is None:
            raise SpeechToTextError("Audio file is required.")

        tmp_path = self._write_temp_file(uploaded_file)
        feature = (feature_mode or "chat").strip() or "chat"
        selected_model = (
            normalize_model_level(model_level)
            if model_level
            else select_stt_model(
                feature_mode=feature,
                audio_duration=audio_duration,
                audio_quality=audio_quality,
                accuracy_required=accuracy_required,
                is_realtime=is_realtime,
            )
        )

        try:
            first_attempt = self._transcribe_path(tmp_path, selected_model)
            final_attempt = first_attempt
            retry_model = None
            retry_model_name = None
            retried = False

            if should_retry_with_stronger_model(
                first_attempt.transcript,
                first_attempt.confidence,
                audio_duration,
                selected_model,
            ):
                retry_model = get_stronger_model(selected_model)
                if retry_model != selected_model:
                    retried = True
                    final_attempt = self._transcribe_path(tmp_path, retry_model)
                    retry_model_name = final_attempt.model_name

            self._log_router_decision(
                feature=feature,
                audio_duration=audio_duration,
                audio_quality=audio_quality,
                selected_model=selected_model,
                retried=retried,
                retry_model=retry_model if retried else None,
            )

            if not final_attempt.transcript:
                raise SpeechToTextError("Transcript is empty.")

            return SpeechToTextResult(
                transcript=final_attempt.transcript,
                confidence=final_attempt.confidence,
                selected_model=selected_model,
                final_model=final_attempt.model_level,
                selected_model_name=first_attempt.model_name,
                final_model_name=final_attempt.model_name,
                retried=retried,
                retry_model=retry_model if retried else None,
                retry_model_name=retry_model_name,
            )
        except SpeechToTextError:
            raise
        except Exception as exc:
            logger.exception("voice_api speech-to-text failed")
            raise SpeechToTextError("Speech-to-text failed.") from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug("Could not remove temporary audio file: %s", tmp_path, exc_info=True)

    def _transcribe_path(self, tmp_path: str, model_level: str) -> SpeechToTextAttempt:
        normalized_model = normalize_model_level(model_level)
        pipe = self._ensure_pipeline(normalized_model)
        call_kwargs = self._call_kwargs()
        try:
            result = pipe(tmp_path, **call_kwargs)
        except TypeError:
            result = pipe(tmp_path)
        return SpeechToTextAttempt(
            transcript=self._extract_text(result),
            confidence=self._extract_confidence(result),
            model_level=normalized_model,
            model_name=self._pipeline_model_names.get(
                normalized_model,
                self._model_name_for_level(normalized_model),
            ),
        )

    def _ensure_pipeline(self, model_level: str = BALANCED):
        normalized_model = normalize_model_level(model_level)
        if normalized_model == BALANCED and self._pipeline is not None:
            self._pipelines.setdefault(BALANCED, self._pipeline)
            self._pipeline_model_names.setdefault(BALANCED, self._model_name_for_level(BALANCED))

        if normalized_model in self._pipelines:
            return self._pipelines[normalized_model]

        with self._lock:
            if normalized_model in self._pipelines:
                return self._pipelines[normalized_model]

            try:
                from transformers import pipeline
            except Exception as exc:
                raise SpeechToTextError("transformers is required for speech-to-text.") from exc

            kwargs = self._pipeline_kwargs()
            load_errors: list[str] = []
            for model_name in self._candidate_model_names(normalized_model):
                try:
                    logger.info("voice_api loading ASR model (%s): %s", normalized_model, model_name)
                    loaded_pipeline = pipeline(
                        "automatic-speech-recognition",
                        model=model_name,
                        **kwargs,
                    )
                    self._pipelines[normalized_model] = loaded_pipeline
                    self._pipeline_model_names[normalized_model] = model_name
                    if normalized_model == BALANCED:
                        self._pipeline = loaded_pipeline
                    return loaded_pipeline
                except Exception as exc:
                    load_errors.append(f"{model_name}: {exc}")
                    logger.warning("voice_api ASR model load failed for %s", model_name, exc_info=True)

            raise SpeechToTextError("; ".join(load_errors) or "No speech-to-text model configured.")

    def _pipeline_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        torch_module = None

        if self.config.device == "auto":
            try:
                import torch

                torch_module = torch
                kwargs["device"] = 0 if torch.cuda.is_available() else -1
            except Exception:
                kwargs["device"] = -1
        elif self.config.device == "cpu":
            kwargs["device"] = -1
        elif self.config.device.startswith("cuda"):
            kwargs["device"] = 0

        if kwargs.get("device") == 0:
            try:
                torch_module = torch_module or __import__("torch")
                kwargs["torch_dtype"] = torch_module.float16
            except Exception:
                logger.debug("Could not enable fp16 for voice ASR.", exc_info=True)

        return kwargs

    def _candidate_model_names(self, model_level: str = BALANCED) -> list[str]:
        names = [self._model_name_for_level(model_level), self.config.fallback_model_name]
        return list(dict.fromkeys(name for name in names if name))

    def _model_name_for_level(self, model_level: str) -> str:
        normalized_model = normalize_model_level(model_level)
        if normalized_model == WEAK:
            return self.config.weak_model_name
        if normalized_model == STRONG:
            return self.config.strong_model_name
        return self.config.model_name

    def _call_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "generate_kwargs": {
                "language": self.config.language,
                "task": self.config.task,
                "max_new_tokens": self.config.max_new_tokens,
            }
        }
        if self.config.num_beams > 1:
            kwargs["generate_kwargs"]["num_beams"] = self.config.num_beams
        if self.config.chunk_length_s > 0:
            kwargs["chunk_length_s"] = self.config.chunk_length_s
            if self.config.batch_size > 1:
                kwargs["batch_size"] = self.config.batch_size
        return kwargs

    @staticmethod
    def _extract_text(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("text") or "").strip()
        if isinstance(result, str):
            return result.strip()
        return ""

    @classmethod
    def _extract_confidence(cls, result: Any) -> float | None:
        if not isinstance(result, dict):
            return None

        for key in ["confidence", "score"]:
            confidence = cls._to_float(result.get(key))
            if confidence is not None:
                return confidence

        chunks = result.get("chunks")
        if not isinstance(chunks, list):
            return None

        scores: list[float] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            for key in ["confidence", "score"]:
                score = cls._to_float(chunk.get(key))
                if score is not None:
                    scores.append(score)
                    break
        if not scores:
            return None
        return sum(scores) / len(scores)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _write_temp_file(self, uploaded_file) -> str:
        with tempfile.NamedTemporaryFile(suffix=self._suffix(getattr(uploaded_file, "name", None)), delete=False) as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            return tmp.name

    @staticmethod
    def _log_router_decision(
        *,
        feature: str,
        audio_duration: float | None,
        audio_quality: str | None,
        selected_model: str,
        retried: bool,
        retry_model: str | None,
    ) -> None:
        logger.info(
            "[STT Router] feature=%s duration=%s quality=%s selected=%s retry=%s retry_model=%s",
            feature,
            "-" if audio_duration is None else audio_duration,
            audio_quality or "unknown",
            selected_model,
            str(retried).lower(),
            retry_model or "-",
        )

    @staticmethod
    def _suffix(file_name: str | None) -> str:
        if not file_name or "." not in file_name:
            return ".wav"
        suffix = "." + file_name.rsplit(".", 1)[-1].lower()
        return suffix if len(suffix) <= 8 else ".wav"


_service: SpeechToTextService | None = None
_service_lock = Lock()


def get_speech_to_text_service() -> SpeechToTextService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = SpeechToTextService()
    return _service


def transcribe_audio(
    uploaded_file,
    *,
    feature_mode: str | None = None,
    audio_duration: float | None = None,
    audio_quality: str | None = None,
    accuracy_required: str | None = None,
    is_realtime: bool = False,
    model_level: str | None = None,
) -> str:
    return get_speech_to_text_service().transcribe(
        uploaded_file,
        feature_mode=feature_mode,
        audio_duration=audio_duration,
        audio_quality=audio_quality,
        accuracy_required=accuracy_required,
        is_realtime=is_realtime,
        model_level=model_level,
    )


def transcribe_audio_with_metadata(
    uploaded_file,
    *,
    feature_mode: str | None = None,
    audio_duration: float | None = None,
    audio_quality: str | None = None,
    accuracy_required: str | None = None,
    is_realtime: bool = False,
    model_level: str | None = None,
) -> SpeechToTextResult:
    return get_speech_to_text_service().transcribe_with_metadata(
        uploaded_file,
        feature_mode=feature_mode,
        audio_duration=audio_duration,
        audio_quality=audio_quality,
        accuracy_required=accuracy_required,
        is_realtime=is_realtime,
        model_level=model_level,
    )
