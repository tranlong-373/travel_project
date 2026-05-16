import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase

from .services.speech_to_text import (
    ASR_MODEL_PROFILES,
    FAST_ASR_MODEL,
    HF_API_BACKEND,
    LOCAL_BACKEND,
    SpeechToTextConfig,
    SpeechToTextError,
    SpeechToTextResult,
    SpeechToTextService,
    _default_model_name,
)
from .services.stt_model_selector import (
    BALANCED,
    STRONG,
    WEAK,
    get_stronger_model,
    get_stt_model_defaults,
    select_stt_model,
    should_retry_with_stronger_model,
)
from .services.transcript_cleanup import cleanup_transcript


class FakeUpload:
    name = "voice.webm"

    def chunks(self):
        yield b"fake-audio"


class FakePipeline:
    def __init__(self, response=None):
        self.response = response or {"text": "khách sạn ở Đà Lạt"}
        self.calls = []

    def __call__(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return self.response


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text

    def json(self):
        return self.payload


class STTModelSelectorTests(SimpleTestCase):
    def test_recommendation_search_and_chat_never_use_weak_model(self):
        self.assertEqual(select_stt_model(feature_mode="chat", audio_duration=2.0), BALANCED)
        self.assertEqual(select_stt_model(feature_mode="search", audio_duration=2.0), BALANCED)
        self.assertEqual(select_stt_model(feature_mode="recommendation", audio_duration=2.0), BALANCED)

    def test_accuracy_required_uses_strong_model(self):
        self.assertEqual(select_stt_model(feature_mode="chat", accuracy_required="true"), STRONG)
        self.assertEqual(select_stt_model(feature_mode="chat", accuracy_required="high"), STRONG)

    def test_noisy_audio_uses_strong_model(self):
        self.assertEqual(select_stt_model(feature_mode="chat", audio_quality="noisy"), STRONG)

    def test_realtime_preview_uses_weak_model(self):
        self.assertEqual(select_stt_model(feature_mode="realtime_preview", is_realtime=True), WEAK)

    def test_translation_uses_strong_model(self):
        self.assertEqual(select_stt_model(feature_mode="translation", audio_duration=4.0), STRONG)

    def test_long_audio_uses_strong_model(self):
        self.assertEqual(select_stt_model(feature_mode="chat", audio_duration=18.0), STRONG)

    def test_bad_transcript_retries_with_stronger_model(self):
        self.assertTrue(
            should_retry_with_stronger_model(
                transcript="@@@###",
                confidence=None,
                audio_duration=3.0,
                current_model=WEAK,
            )
        )
        self.assertEqual(get_stronger_model(WEAK), BALANCED)
        self.assertEqual(get_stronger_model(BALANCED), STRONG)
        self.assertEqual(get_stronger_model(STRONG), STRONG)


class SpeechToTextConfigTests(SimpleTestCase):
    def test_balanced_profile_uses_base_model_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_default_model_name(), ASR_MODEL_PROFILES["balanced"])
            self.assertEqual(SpeechToTextConfig().model_name, ASR_MODEL_PROFILES["balanced"])
            self.assertEqual(SpeechToTextConfig().backend, LOCAL_BACKEND)

    def test_profiles_and_explicit_model_are_supported(self):
        with patch.dict("os.environ", {"VOICE_ASR_PROFILE": "fast"}, clear=True):
            self.assertEqual(SpeechToTextConfig().model_name, FAST_ASR_MODEL)

        with patch.dict("os.environ", {"VOICE_ASR_PROFILE": "accurate"}, clear=True):
            self.assertEqual(SpeechToTextConfig().model_name, ASR_MODEL_PROFILES["accurate"])

        with patch.dict("os.environ", {"VOICE_ASR_MODEL": "custom/model"}, clear=True):
            self.assertEqual(SpeechToTextConfig().model_name, "custom/model")

    def test_level_model_env_overrides_are_supported(self):
        with patch.dict(
            "os.environ",
            {
                "VOICE_WEAK_MODEL": "custom/weak",
                "VOICE_BALANCED_MODEL": "custom/balanced",
                "VOICE_STRONG_MODEL": "custom/strong",
            },
            clear=True,
        ):
            config = SpeechToTextConfig()
            self.assertEqual(config.weak_model_name, "custom/weak")
            self.assertEqual(config.model_name, "custom/balanced")
            self.assertEqual(config.strong_model_name, "custom/strong")
            self.assertEqual(get_stt_model_defaults()[BALANCED], "custom/balanced")


class SpeechToTextServiceTests(SimpleTestCase):
    def test_transcribe_uses_vietnamese_transcription_kwargs_without_chunking_by_default(self):
        pipeline = FakePipeline()
        service = SpeechToTextService(
            SpeechToTextConfig(
                model_name="test/model",
                fallback_model_name=None,
                max_new_tokens=64,
                chunk_length_s=0,
            )
        )
        service._pipeline = pipeline

        with patch.object(service, "_prepare_audio_file", return_value=("voice.wav", [])):
            transcript = service.transcribe(FakeUpload())

        self.assertEqual(transcript, "khách sạn ở Đà Lạt")
        _, kwargs = pipeline.calls[0]
        self.assertNotIn("chunk_length_s", kwargs)
        self.assertEqual(
            kwargs["generate_kwargs"],
            {"language": "vi", "task": "transcribe", "max_new_tokens": 64},
        )

    def test_chunking_and_beam_search_remain_configurable(self):
        service = SpeechToTextService(
            SpeechToTextConfig(
                model_name="test/model",
                fallback_model_name=None,
                num_beams=2,
                chunk_length_s=15,
                batch_size=2,
            )
        )

        self.assertEqual(
            service._call_kwargs(),
            {
                "generate_kwargs": {
                    "language": "vi",
                    "task": "transcribe",
                    "max_new_tokens": 96,
                    "num_beams": 2,
                },
                "chunk_length_s": 15,
                "batch_size": 2,
            },
        )

    def test_transcribe_retries_from_balanced_to_strong_when_transcript_is_empty(self):
        balanced_pipeline = FakePipeline({"text": ""})
        strong_pipeline = FakePipeline({"text": "khách sạn gần biển"})
        service = SpeechToTextService(
            SpeechToTextConfig(
                model_name="balanced/model",
                strong_model_name="strong/model",
                fallback_model_name=None,
            )
        )
        service._pipelines[BALANCED] = balanced_pipeline
        service._pipelines[STRONG] = strong_pipeline

        with patch.object(service, "_prepare_audio_file", return_value=("voice.wav", [])):
            result = service.transcribe_with_metadata(
                FakeUpload(),
                feature_mode="chat",
                audio_duration=9.0,
            )

        self.assertEqual(result.transcript, "khách sạn gần biển")
        self.assertEqual(result.selected_profile, BALANCED)
        self.assertEqual(result.final_profile, STRONG)
        self.assertTrue(result.retried)
        self.assertEqual(result.retry_profile, STRONG)
        self.assertEqual(result.retry_reason, "empty_transcript")
        self.assertEqual(len(balanced_pipeline.calls), 1)
        self.assertEqual(len(strong_pipeline.calls), 1)

    def test_hf_api_missing_token_returns_clear_error(self):
        service = SpeechToTextService(
            SpeechToTextConfig(backend=HF_API_BACKEND, hf_token="", fallback_model_name=None)
        )

        with self.assertRaises(SpeechToTextError) as ctx:
            service._transcribe_path_hf_api("voice.wav", BALANCED)

        self.assertEqual(ctx.exception.code, "hf_token_missing")
        self.assertIn("HF_TOKEN", str(ctx.exception))

    @patch("voice_api.services.speech_to_text.requests.post")
    def test_hf_api_transcribe_success(self, mock_post):
        mock_post.return_value = FakeResponse(
            payload={"text": "khách sạn Đà Lạt", "confidence": 0.91}
        )
        service = SpeechToTextService(
            SpeechToTextConfig(
                backend=HF_API_BACKEND,
                hf_token="test-token",
                hf_api_model="openai/whisper-large-v3",
                fallback_model_name=None,
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"fake-audio")
            tmp.flush()
            attempt = service._transcribe_path_hf_api(tmp.name, BALANCED)

        self.assertEqual(attempt.transcript, "khách sạn Đà Lạt")
        self.assertEqual(attempt.confidence, 0.91)
        self.assertEqual(attempt.model_name, "openai/whisper-large-v3")
        mock_post.assert_called_once()

    @patch("voice_api.services.speech_to_text.requests.post")
    def test_hf_api_503_returns_asr_failed(self, mock_post):
        mock_post.return_value = FakeResponse(status_code=503, payload={"error": "loading"})
        service = SpeechToTextService(
            SpeechToTextConfig(
                backend=HF_API_BACKEND,
                hf_token="test-token",
                hf_api_model="openai/whisper-large-v3",
                fallback_model_name=None,
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"fake-audio")
            tmp.flush()
            with self.assertRaises(SpeechToTextError) as ctx:
                service._transcribe_path_hf_api(tmp.name, BALANCED)

        self.assertEqual(ctx.exception.code, "asr_failed")


class VoiceParseEndpointTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("voice_api.views.parse_user_text")
    @patch("voice_api.views.transcribe_audio_with_metadata")
    def test_parse_voice_passes_router_context_and_returns_stt_router(self, mock_transcribe, mock_parse):
        mock_transcribe.return_value = SpeechToTextResult(
            transcript="khách sạn Đà Lạt",
            confidence=None,
            selected_profile=WEAK,
            final_profile=WEAK,
            selected_model="weak/model",
            final_model="weak/model",
            backend=LOCAL_BACKEND,
            retried=False,
            latency_ms=12,
        )
        mock_parse.return_value = {"ready_for_recommendation": False, "slots": {"area": "Đà Lạt"}}

        response = self.client.post(
            "/api/voice/parse/",
            {
                "audio": SimpleUploadedFile("voice.webm", b"fake-audio", content_type="audio/webm"),
                "feature_mode": "command",
                "audio_duration": "2.4",
                "audio_quality": "normal",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["stt_router"]["selected_profile"], WEAK)
        self.assertEqual(data["stt_router"]["selected_model"], "weak/model")
        self.assertEqual(data["stt_router"]["backend"], LOCAL_BACKEND)
        self.assertEqual(data["stt_router"]["latency_ms"], 12)
        mock_transcribe.assert_called_once()
        call_kwargs = mock_transcribe.call_args.kwargs
        self.assertEqual(call_kwargs["feature_mode"], "command")
        self.assertEqual(call_kwargs["audio_duration"], 2.4)
        self.assertEqual(call_kwargs["audio_quality"], "normal")


class TranscriptCleanupTravelTests(SimpleTestCase):
    def test_travel_phrases_are_restored_without_overcorrecting(self):
        cleanup = cleanup_transcript("ks da lac gan bien co ho boi mot trieu ruoi")

        self.assertIn("khách sạn", cleanup.cleaned_text)
        self.assertIn("Đà Lạt", cleanup.cleaned_text)
        self.assertIn("gần biển", cleanup.cleaned_text)
        self.assertIn("hồ bơi", cleanup.cleaned_text)
        self.assertIn("1500000", cleanup.cleaned_text)

    def test_common_location_noise_is_corrected(self):
        cleanup = cleanup_transcript("tim khach san ha loi hoac sai gon")

        self.assertIn("Hà Nội", cleanup.cleaned_text)
        self.assertIn("Sài Gòn", cleanup.cleaned_text)
