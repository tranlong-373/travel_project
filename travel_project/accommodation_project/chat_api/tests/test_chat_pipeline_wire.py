"""
Phase B / C / D wire tests.

Tests:
  1. ChatPipeline.run() returns dict with required keys
  2. ChatPipeline.run() attaches search_intent_v2
  3. ChatPipeline.run() raises on builder failure
  4. parse_user_text CHAT_PIPELINE_V2_ENABLED=False → v1 called
  5. parse_user_text CHAT_PIPELINE_V2_ENABLED=True  → v2 called
  6. parse_user_text CHAT_PIPELINE_V2_ENABLED=True, v2 fails → fallback v1
  7. parse_user_text v2 result has bot_message (fully finalised)
  8. recommendation_bridge uses search_intent_v2 when present
  9. recommendation_bridge falls back to legacy when no search_intent_v2

Run:
  python manage.py test chat_api.tests.test_chat_pipeline_wire --settings=accommodation_project.test_settings
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings


class TestChatPipelineRun(SimpleTestCase):
    """PHASE B — ChatPipeline.run() returns dict + search_intent_v2."""

    def test_run_returns_dict(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("khách sạn quận 1")
        self.assertIsInstance(result, dict)

    def test_run_has_location_keys(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("khách sạn quận 1")
        self.assertIn("location_status", result)
        self.assertIn("location_mode", result)

    def test_run_attaches_search_intent_v2(self):
        from chat_api.application.chat_pipeline import ChatPipeline
        from chat_api.nlu.dto import SearchIntent

        result = ChatPipeline().run("khách sạn quận 1")
        self.assertIn("search_intent_v2", result)
        self.assertIsInstance(result["search_intent_v2"], SearchIntent)

    def test_run_has_parser_mode_v2(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("khách sạn quận 1")
        self.assertEqual(result.get("parser_mode"), "v2_pipeline")

    def test_run_has_slots(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("homestay quận 3 dưới 800k")
        self.assertIn("slots", result)
        slots = result["slots"]
        self.assertIsInstance(slots, dict)

    def test_run_raises_on_builder_error(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        pipeline = ChatPipeline()
        with patch.object(pipeline._builder, "build", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                pipeline.run("test")

    def test_run_with_user_location_dict(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run(
            "gần đây có hồ bơi",
            user_location={"lat": 10.77, "lon": 106.69},
        )
        self.assertIsInstance(result, dict)

    def test_run_area_query_has_canonical_area(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("Quận 3")
        self.assertIsNotNone(result.get("canonical_area") or result.get("slots", {}).get("area"))

    def test_run_hotel_name_has_hotel_name_mode(self):
        from chat_api.application.chat_pipeline import ChatPipeline

        result = ChatPipeline().run("Rex Hotel")
        self.assertIn(result.get("location_mode"), {"hotel_name", "unknown", "unresolved"})
        intent = result.get("search_intent_v2")
        self.assertEqual(intent.input_kind, "hotel_name")


class TestParseUserTextFeatureFlag(SimpleTestCase):
    """PHASE C — parse_user_text() v2 flag behaviour."""

    @override_settings(CHAT_PIPELINE_V2_ENABLED=False)
    def test_flag_false_uses_v1(self):
        with patch("chat_api.parser_service.parse_user_text_rule_based") as mock_v1:
            mock_v1.return_value = {
                "location_status": "unresolved",
                "location_mode": "unknown",
                "slots": {},
                "conversation_intent": "unknown",
                "filter_tree": {"location": {}, "filters": [], "usable_filter_count": 0,
                                "available_slots": [], "missing_slots": []},
            }
            with patch("chat_api.parser_service._try_enrich_with_groq", side_effect=lambda r, t, **kw: r):
                with patch("chat_api.parser_service._finalize_convenience_response", side_effect=lambda r, t, **kw: r):
                    from chat_api.parser_service import parse_user_text
                    parse_user_text("test query")

        mock_v1.assert_called_once()

    @override_settings(CHAT_PIPELINE_V2_ENABLED=True)
    def test_flag_true_calls_v2_pipeline(self):
        fake_intent = MagicMock()
        fake_intent.input_kind = "area"
        fake_intent.conversation_intent = "recommend_accommodation"
        fake_intent.location.status.value = "ok"
        fake_intent.location.mode.value = "area"
        fake_intent.location.canonical_area = "Quận 3"
        fake_intent.location.latitude = None
        fake_intent.location.longitude = None
        fake_intent.location.anchor_name = None
        fake_intent.location.anchor_kind = None
        fake_intent.location.radius_km = 10.0
        fake_intent.location.nearby_poi_key = None
        fake_intent.location.nearby_poi_label = None
        fake_intent.location.display_label = None
        fake_intent.location.raw_phrase = None
        fake_intent.area = "Quận 3"
        fake_intent.hotel_name = None
        fake_intent.accommodation_types = []
        fake_intent.budget = None
        fake_intent.budget_min = None
        fake_intent.budget_max = None
        fake_intent.guest_count = None
        fake_intent.trip_days = None
        fake_intent.required_amenities = []
        fake_intent.priorities = []
        fake_intent.special_requirements = []
        fake_intent.rating_min = None
        fake_intent.confidence = 0.9
        fake_intent.used_default_slots = {}
        fake_intent.selected_place = None
        fake_intent.user_location = None

        with patch("chat_api.application.chat_pipeline.ChatPipeline.run") as mock_run:
            mock_run.return_value = {
                "location_status": "ok",
                "location_mode": "area",
                "canonical_area": "Quận 3",
                "slots": {"area": "Quận 3"},
                "conversation_intent": "recommend_accommodation",
                "filter_tree": {"location": {"mode": "area", "canonical_area": "Quận 3"},
                                "filters": [], "usable_filter_count": 1,
                                "available_slots": [], "missing_slots": []},
                "search_intent_v2": fake_intent,
                "parser_mode": "v2_pipeline",
                "input_kind": "area",
            }
            with patch("chat_api.parser_service._finalize_v2_result") as mock_fin:
                mock_fin.return_value = mock_run.return_value
                from chat_api.parser_service import parse_user_text
                result = parse_user_text("Quận 3")

        mock_run.assert_called_once()
        mock_fin.assert_called_once()

    @override_settings(CHAT_PIPELINE_V2_ENABLED=True)
    def test_v2_exception_falls_back_to_v1(self):
        with patch("chat_api.application.chat_pipeline.ChatPipeline.run",
                   side_effect=RuntimeError("v2 boom")):
            with patch("chat_api.parser_service.parse_user_text_rule_based") as mock_v1:
                mock_v1.return_value = {
                    "location_status": "unresolved",
                    "location_mode": "unknown",
                    "slots": {},
                    "conversation_intent": "unknown",
                    "filter_tree": {"location": {}, "filters": [], "usable_filter_count": 0,
                                    "available_slots": [], "missing_slots": []},
                }
                with patch("chat_api.parser_service._try_enrich_with_groq", side_effect=lambda r, t, **kw: r):
                    with patch("chat_api.parser_service._finalize_convenience_response", side_effect=lambda r, t, **kw: r):
                        from chat_api.parser_service import parse_user_text
                        result = parse_user_text("Quận 3")

            mock_v1.assert_called_once()

    @override_settings(CHAT_PIPELINE_V2_ENABLED=True)
    def test_v2_result_is_fully_finalized(self):
        """When v2 enabled, result should have bot_message from finalization."""
        from chat_api.parser_service import parse_user_text

        result = parse_user_text("Quận 3")
        self.assertIn("bot_message", result)
        self.assertIn("location_status", result)

    @override_settings(CHAT_PIPELINE_V2_ENABLED=False)
    def test_v1_result_has_bot_message(self):
        from chat_api.parser_service import parse_user_text

        result = parse_user_text("Quận 3")
        self.assertIn("bot_message", result)


class TestRecommendationBridgeIntegration(SimpleTestCase):
    """PHASE D — recommendation_bridge picks up search_intent_v2."""

    def test_bridge_uses_search_intent_v2_when_present(self):
        from chat_api.recommendation_bridge import usable_filters_from_parse
        from chat_api.nlu.dto import (
            LocationMode, LocationStatus, ResolvedLocation, SearchIntent,
        )

        intent = SearchIntent(
            raw_text="homestay quận 3 dưới 800k",
            conversation_intent="recommend_accommodation",
            input_kind="mixed_search",
            location=ResolvedLocation(
                status=LocationStatus.OK,
                mode=LocationMode.AREA,
                canonical_area="Quận 3",
            ),
            area="Quận 3",
            budget_max=800000,
        )
        parse_result = {"search_intent_v2": intent}
        filters = usable_filters_from_parse(parse_result)
        self.assertIn("location", filters)
        self.assertIn("budget", filters)

    def test_bridge_falls_back_legacy_without_search_intent_v2(self):
        from chat_api.recommendation_bridge import usable_filters_from_parse

        parse_result = {
            "slots": {
                "area": "Quận 3",
                "budget_max": 800000,
                "required_amenities": ["wifi"],
            }
        }
        filters = usable_filters_from_parse(parse_result)
        self.assertIsInstance(filters, list)
