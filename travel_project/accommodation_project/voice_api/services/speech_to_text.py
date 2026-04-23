from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ASR_MODEL = "vinai/PhoWhisper-tiny"


class SpeechToTextError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechToTextConfig:
    model_name: str = os.getenv("VOICE_ASR_MODEL", DEFAULT_ASR_MODEL)
    device: str = os.getenv("VOICE_DEVICE", "auto")
    max_new_tokens: int = int(os.getenv("VOICE_MAX_NEW_TOKENS", "96"))
    chunk_length_s: int = int(os.getenv("VOICE_CHUNK_LENGTH_S", "15"))


class SpeechToTextService:
    def __init__(self, config: SpeechToTextConfig | None = None):
        self.config = config or SpeechToTextConfig()
        self._pipeline = None
        self._lock = Lock()

    def transcribe(self, uploaded_file) -> str:
        if uploaded_file is None:
            raise SpeechToTextError("Audio file is required.")

        with tempfile.NamedTemporaryFile(suffix=self._suffix(uploaded_file.name), delete=False) as tmp:
            tmp_path = tmp.name
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)

        try:
            pipe = self._ensure_pipeline()
            try:
                result = pipe(
                    tmp_path,
                    chunk_length_s=self.config.chunk_length_s,
                    generate_kwargs={"language": "vi", "max_new_tokens": self.config.max_new_tokens},
                )
            except TypeError:
                result = pipe(tmp_path, chunk_length_s=self.config.chunk_length_s)
            transcript = self._extract_text(result)
            if not transcript:
                raise SpeechToTextError("Transcript is empty.")
            return transcript
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

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        with self._lock:
            if self._pipeline is not None:
                return self._pipeline

            try:
                from transformers import pipeline
            except Exception as exc:
                raise SpeechToTextError("transformers is required for speech-to-text.") from exc

            kwargs: dict[str, Any] = {}
            if self.config.device == "auto":
                try:
                    import torch

                    kwargs["device"] = 0 if torch.cuda.is_available() else -1
                except Exception:
                    kwargs["device"] = -1
            elif self.config.device == "cpu":
                kwargs["device"] = -1
            elif self.config.device.startswith("cuda"):
                kwargs["device"] = 0

            self._pipeline = pipeline(
                "automatic-speech-recognition",
                model=self.config.model_name,
                **kwargs,
            )
            return self._pipeline

    @staticmethod
    def _extract_text(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("text") or "").strip()
        if isinstance(result, str):
            return result.strip()
        return ""

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


def transcribe_audio(uploaded_file) -> str:
    return get_speech_to_text_service().transcribe(uploaded_file)
