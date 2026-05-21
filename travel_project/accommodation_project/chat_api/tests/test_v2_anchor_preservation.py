"""
Regression tests for the post-merge fixes in parser_service.

Covers:
  1. _attach_filter_tree_payload no longer wipes v2-resolved anchor coords
     for landmarks / POIs / city_center (only anchor_kind == "geocoded"
     was preserved before).
  2. _finalize_v2_result no longer forces ambiguous_location when v2 has
     already resolved a specific anchor.
  3. Bare follow-up replies ("2") still fill the first missing core slot
     when arriving through the v2 pipeline.

Run:
  python manage.py test chat_api.tests.test_v2_anchor_preservation \
      --settings=accommodation_project.test_settings
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings


@override_settings(CHAT_PIPELINE_V2_ENABLED=True)
class TestV2AnchorPreserved(SimpleTestCase):
    """v2-resolved anchors must survive filter_tree (v1) rebuild."""

    def _assert_anchor_resolved(self, text: str):
        from chat_api.parser_service import parse_user_text

        result = parse_user_text(text)
        self.assertEqual(
            result.get("location_status"),
            "ok",
            msg=f"{text!r} expected location_status=ok, got {result.get('location_status')!r}",
        )
        self.assertEqual(
            result.get("location_mode"),
            "near_anchor",
            msg=f"{text!r} expected location_mode=near_anchor, got {result.get('location_mode')!r}",
        )
        self.assertIsNotNone(
            result.get("anchor_lat"),
            msg=f"{text!r} dropped anchor_lat (v2 coords overwritten)",
        )
        self.assertIsNotNone(
            result.get("anchor_lon"),
            msg=f"{text!r} dropped anchor_lon (v2 coords overwritten)",
        )
        self.assertIsNotNone(
            result.get("anchor_kind"),
            msg=f"{text!r} dropped anchor_kind",
        )
        self.assertFalse(
            result.get("ambiguous_location"),
            msg=f"{text!r} unexpectedly flagged ambiguous after v2 resolved",
        )
        return result

    def test_landmark_81_preserved(self):
        """`gần Landmark 81` resolves through v2; coords must survive."""
        self._assert_anchor_resolved("Tìm khách sạn gần Landmark 81")

    def test_cho_ben_thanh_preserved(self):
        """v2 resolves Chợ Bến Thành as a POI; filter_tree must not wipe it."""
        self._assert_anchor_resolved("Tìm chỗ ở gần Chợ Bến Thành")

    def test_san_bay_tan_son_nhat_preserved(self):
        """`gần sân bay Tân Sơn Nhất` must not be downgraded to ambiguous."""
        result = self._assert_anchor_resolved("Tìm khách sạn gần sân bay Tân Sơn Nhất")
        # Sanity: the resolved anchor should mention the airport / district.
        anchor_name = (result.get("anchor_name") or "").lower()
        self.assertTrue(
            "tân sơn nhất" in anchor_name
            or "tan son nhat" in anchor_name
            or "tân bình" in anchor_name
            or "tan binh" in anchor_name,
            msg=f"unexpected anchor_name for TSN airport: {result.get('anchor_name')!r}",
        )


@override_settings(CHAT_PIPELINE_V2_ENABLED=True)
class TestV2AmbiguousFallback(SimpleTestCase):
    """Generic POI categories without a specific name stay ambiguous."""

    def test_generic_sanbay_is_ambiguous(self):
        from chat_api.parser_service import parse_user_text

        result = parse_user_text("Tìm khách sạn gần sân bay")
        self.assertEqual(result.get("location_status"), "ambiguous")
        self.assertTrue(result.get("ambiguous_location"))
        self.assertIsNone(result.get("anchor_lat"))
        self.assertIsNone(result.get("anchor_lon"))


@override_settings(CHAT_PIPELINE_V2_ENABLED=True)
class TestV2BareCountFollowUp(SimpleTestCase):
    """Bare numeric follow-up should fill the first missing core slot."""

    def test_bare_two_fills_guest_count(self):
        from chat_api.parser_service import parse_user_text

        context = {"area": "Quận 1", "budget": 500000, "trip_days": 2}
        result = parse_user_text("2", context_slots=context)
        slots = result.get("slots") or {}
        self.assertEqual(slots.get("guest_count"), 2)

    def test_bare_three_fills_guest_count_via_normalized_text(self):
        """Verifies _apply_bare_count_follow_up sees the normalized form."""
        from chat_api.parser_service import parse_user_text

        # "ba" (vi) → normalized → key 'ba' → NUMBER_WORDS["ba"] == 3
        context = {"area": "Quận 1", "budget": 500000, "trip_days": 1}
        result = parse_user_text("ba", context_slots=context)
        slots = result.get("slots") or {}
        self.assertEqual(slots.get("guest_count"), 3)
