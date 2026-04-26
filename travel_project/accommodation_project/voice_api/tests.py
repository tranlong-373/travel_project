from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase

from .services.speech_to_text import (
    ASR_MODEL_PROFILES,
    FAST_ASR_MODEL,
    SpeechToTextConfig,
    SpeechToTextResult,
    SpeechToTextService,
    _default_model_name,
)
from .services.stt_model_selector import (
    BALANCED,
    STRONG,
    WEAK,
    get_stronger_model,
    select_stt_model,
    should_retry_with_stronger_model,
)


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


class STTModelSelectorTests(SimpleTestCase):
    def test_short_command_uses_weak_model(self):
        self.assertEqual(
            select_stt_model(feature_mode="command", audio_duration=2.0, accuracy_required="speed"),
            WEAK,
        )

    def test_normal_chat_uses_balanced_model(self):
        self.assertEqual(select_stt_model(feature_mode="chat", audio_duration=7.0), BALANCED)

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
                "VOICE_ASR_WEAK_MODEL": "custom/weak",
                "VOICE_ASR_BALANCED_MODEL": "custom/balanced",
                "VOICE_ASR_STRONG_MODEL": "custom/strong",
            },
            clear=True,
        ):
            config = SpeechToTextConfig()
            self.assertEqual(config.weak_model_name, "custom/weak")
            self.assertEqual(config.model_name, "custom/balanced")
            self.assertEqual(config.strong_model_name, "custom/strong")


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

    def test_transcribe_retries_with_stronger_model_when_result_looks_bad(self):
        weak_pipeline = FakePipeline({"text": "ờ"})
        balanced_pipeline = FakePipeline({"text": "khách sạn gần biển"})
        service = SpeechToTextService(
            SpeechToTextConfig(
                model_name="balanced/model",
                weak_model_name="weak/model",
                fallback_model_name=None,
            )
        )
        service._pipelines[WEAK] = weak_pipeline
        service._pipelines[BALANCED] = balanced_pipeline

        result = service.transcribe_with_metadata(
            FakeUpload(),
            feature_mode="command",
            audio_duration=9.0,
        )

        self.assertEqual(result.transcript, "khách sạn gần biển")
        self.assertEqual(result.selected_model, WEAK)
        self.assertEqual(result.final_model, BALANCED)
        self.assertTrue(result.retried)
        self.assertEqual(result.retry_model, BALANCED)
        self.assertEqual(len(weak_pipeline.calls), 1)
        self.assertEqual(len(balanced_pipeline.calls), 1)


class VoiceParseEndpointTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("voice_api.views.parse_user_text")
    @patch("voice_api.views.transcribe_audio_with_metadata")
    def test_parse_voice_passes_router_context_and_returns_stt_router(self, mock_transcribe, mock_parse):
        mock_transcribe.return_value = SpeechToTextResult(
            transcript="khách sạn Đà Lạt",
            confidence=None,
            selected_model=WEAK,
            final_model=WEAK,
            selected_model_name="weak/model",
            final_model_name="weak/model",
            retried=False,
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
        self.assertEqual(data["stt_router"]["selected_model"], WEAK)
        mock_transcribe.assert_called_once()
        call_kwargs = mock_transcribe.call_args.kwargs
        self.assertEqual(call_kwargs["feature_mode"], "command")
        self.assertEqual(call_kwargs["audio_duration"], 2.4)
        self.assertEqual(call_kwargs["audio_quality"], "normal")
