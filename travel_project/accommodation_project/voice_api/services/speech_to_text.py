from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import requests

from .stt_model_selector import (
    BALANCED,
    STT_MODEL_DEFAULTS,
    STRONG,
    WEAK,
    get_model_name_for_level,
    get_stronger_model,
    normalize_model_level,
    retry_reason_for_transcript,
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
LOCAL_BACKEND = "local"
HF_API_BACKEND = "hf_api"
DEFAULT_STT_BACKEND = LOCAL_BACKEND
# PhoWhisper-large is the local accuracy profile. The HF Inference Provider
# default stays on OpenAI Whisper because PhoWhisper-large is not guaranteed
# to be deployed by Hugging Face providers.
DEFAULT_HF_API_MODEL = "openai/whisper-large-v3"


class SpeechToTextError(RuntimeError):
    def __init__(self, message: str, *, code: str = "asr_failed"):
        super().__init__(message)
        self.code = code


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


def _normalize_backend(value: str | None) -> str:
    backend = (value or DEFAULT_STT_BACKEND).strip().lower()
    if backend not in {LOCAL_BACKEND, HF_API_BACKEND}:
        return DEFAULT_STT_BACKEND
    return backend


def _default_model_name() -> str:
    explicit_model = os.getenv("VOICE_ASR_MODEL", "").strip()
    if explicit_model:
        return explicit_model

    profile = _env_str("VOICE_ASR_PROFILE", DEFAULT_ASR_PROFILE).lower()
    return get_model_name_for_level(profile)


def _default_balanced_model_name() -> str:
    explicit_model = (
        os.getenv("VOICE_BALANCED_MODEL", "").strip()
        or os.getenv("VOICE_ASR_BALANCED_MODEL", "").strip()
    )
    if explicit_model:
        return explicit_model
    return _default_model_name()


def _default_weak_model_name() -> str:
    return get_model_name_for_level(WEAK)


def _default_strong_model_name() -> str:
    return get_model_name_for_level(STRONG)


@dataclass(frozen=True)
class SpeechToTextConfig:
    backend: str = field(default_factory=lambda: _normalize_backend(os.getenv("STT_BACKEND")))
    model_name: str = field(default_factory=_default_balanced_model_name)
    weak_model_name: str = field(default_factory=_default_weak_model_name)
    strong_model_name: str = field(default_factory=_default_strong_model_name)
    hf_api_model: str = field(default_factory=lambda: _env_str("HF_API_MODEL", DEFAULT_HF_API_MODEL))
    hf_token: str = field(default_factory=lambda: os.getenv("HF_TOKEN", "").strip())
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
    min_audio_seconds: int = field(default_factory=lambda: _env_int("VOICE_MIN_AUDIO_SECONDS", 1))
    max_audio_seconds: int = field(default_factory=lambda: _env_int("VOICE_MAX_AUDIO_SECONDS", 30))


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
    selected_profile: str
    final_profile: str
    selected_model: str
    final_model: str
    backend: str
    retried: bool
    latency_ms: int
    retry_reason: str | None = None
    retry_profile: str | None = None
    retry_model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "confidence": self.confidence,
            "backend": self.backend,
            "selected_profile": self.selected_profile,
            "final_profile": self.final_profile,
            "selected_model": self.selected_model,
            "final_model": self.final_model,
            "selected_model_name": self.selected_model,
            "final_model_name": self.final_model,
            "retried": self.retried,
            "retry_reason": self.retry_reason,
            "retry_profile": self.retry_profile,
            "retry_model": self.retry_model,
            "retry_model_name": self.retry_model,
            "latency_ms": self.latency_ms,
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
            raise SpeechToTextError("Audio file is required.", code="audio_required")

        start_time = time.monotonic()
        self._validate_audio_duration(audio_duration)
        cleanup_paths: list[str] = []
        tmp_path, cleanup_paths = self._prepare_audio_file(uploaded_file)
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
            retry_profile = None
            retry_model = None
            retry_reason = retry_reason_for_transcript(
                first_attempt.transcript,
                first_attempt.confidence,
                audio_duration,
                selected_model,
            )
            retried = False

            if should_retry_with_stronger_model(
                first_attempt.transcript,
                first_attempt.confidence,
                audio_duration,
                selected_model,
            ):
                retry_profile = get_stronger_model(selected_model)
                if retry_profile != selected_model:
                    retried = True
                    final_attempt = self._transcribe_path(tmp_path, retry_profile)
                    retry_model = final_attempt.model_name

            self._raise_if_final_attempt_failed(final_attempt, audio_duration)

            self._log_router_decision(
                feature=feature,
                audio_duration=audio_duration,
                audio_quality=audio_quality,
                selected_model=selected_model,
                retried=retried,
                retry_model=retry_profile if retried else None,
            )

            if not final_attempt.transcript:
                raise SpeechToTextError("no_speech_detected", code="no_speech_detected")

            return SpeechToTextResult(
                transcript=final_attempt.transcript,
                confidence=final_attempt.confidence,
                selected_profile=selected_model,
                final_profile=final_attempt.model_level,
                selected_model=first_attempt.model_name,
                final_model=final_attempt.model_name,
                backend=self.config.backend,
                retried=retried,
                retry_reason=retry_reason,
                retry_profile=retry_profile if retried else None,
                retry_model=retry_model,
                latency_ms=int((time.monotonic() - start_time) * 1000),
            )
        except SpeechToTextError:
            raise
        except Exception as exc:
            logger.exception("voice_api speech-to-text failed")
            raise SpeechToTextError("Speech-to-text failed.") from exc
        finally:
            for path in cleanup_paths:
                try:
                    os.unlink(path)
                except OSError:
                    logger.debug("Could not remove temporary audio file: %s", path, exc_info=True)

    def _transcribe_path(self, tmp_path: str, model_level: str) -> SpeechToTextAttempt:
        if self.config.backend == HF_API_BACKEND:
            return self._transcribe_path_hf_api(tmp_path, model_level)
        return self._transcribe_path_local(tmp_path, model_level)

    def _transcribe_path_local(self, tmp_path: str, model_level: str) -> SpeechToTextAttempt:
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

    def _transcribe_path_hf_api(self, tmp_path: str, model_level: str) -> SpeechToTextAttempt:
        if not self.config.hf_token:
            raise SpeechToTextError(
                "HF_TOKEN is required when STT_BACKEND=hf_api.",
                code="hf_token_missing",
            )

        normalized_model = normalize_model_level(model_level)
        model_name = self._model_name_for_level(normalized_model)
        url = f"https://api-inference.huggingface.co/models/{model_name}"
        headers = {
            "Authorization": f"Bearer {self.config.hf_token}",
            "Content-Type": "audio/wav",
        }
        with open(tmp_path, "rb") as audio_file:
            response = requests.post(
                url,
                headers=headers,
                data=audio_file.read(),
                params={"language": self.config.language, "task": self.config.task},
                timeout=90,
            )

        if response.status_code == 503:
            raise SpeechToTextError(
                "Hugging Face Inference API unavailable.",
                code="asr_failed",
            )
        if response.status_code >= 400:
            raise SpeechToTextError(
                f"Hugging Face Inference API failed with status {response.status_code}.",
                code="asr_failed",
            )

        try:
            result: Any = response.json()
        except ValueError:
            result = {"text": response.text}

        return SpeechToTextAttempt(
            transcript=self._extract_text(result),
            confidence=self._extract_confidence(result),
            model_level=normalized_model,
            model_name=model_name,
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

            raise SpeechToTextError(
                "; ".join(load_errors) or "No speech-to-text model configured.",
                code="asr_failed",
            )

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
        if self.config.backend == HF_API_BACKEND:
            return self.config.hf_api_model

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

    def _prepare_audio_file(self, uploaded_file) -> tuple[str, list[str]]:
        original_path = self._write_temp_file(uploaded_file)
        wav_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = wav_file.name
        wav_file.close()
        cleanup_paths = [original_path, wav_path]

        try:
            self._convert_to_wav_16k_mono(original_path, wav_path)
        except Exception:
            for path in cleanup_paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            raise

        return wav_path, cleanup_paths

    @staticmethod
    def _convert_to_wav_16k_mono(input_path: str, output_path: str) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            output_path,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise SpeechToTextError(
                "Bạn cần cài ffmpeg để xử lý file ghi âm.",
                code="ffmpeg_missing",
            ) from exc

        if result.returncode != 0:
            logger.warning("ffmpeg audio conversion failed: %s", result.stderr.strip())
            raise SpeechToTextError(
                "Không xử lý được file ghi âm.",
                code="audio_processing_failed",
            )

    def _validate_audio_duration(self, audio_duration: float | None) -> None:
        duration = self._to_float(audio_duration)
        if duration is None:
            return
        if duration < self.config.min_audio_seconds:
            raise SpeechToTextError("no_speech_detected", code="no_speech_detected")
        if duration > self.config.max_audio_seconds:
            raise SpeechToTextError("Audio file is too long.", code="audio_too_long")

    def _raise_if_final_attempt_failed(
        self,
        attempt: SpeechToTextAttempt,
        audio_duration: float | None,
    ) -> None:
        reason = retry_reason_for_transcript(
            attempt.transcript,
            attempt.confidence,
            audio_duration,
            WEAK,
        )
        if not reason:
            return

        if reason == "empty_transcript":
            raise SpeechToTextError("no_speech_detected", code="no_speech_detected")
        if normalize_model_level(attempt.model_level) == STRONG:
            raise SpeechToTextError("asr_failed", code="asr_failed")

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
