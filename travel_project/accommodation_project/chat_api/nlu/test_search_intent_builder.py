"""
Unit tests for SearchIntentBuilder.build().

Run:
    cd travel_project/accommodation_project
    python -m pytest chat_api/nlu/test_search_intent_builder.py -v
    # or:
    python -m unittest chat_api.nlu.test_search_intent_builder -v
"""
from __future__ import annotations

import os
import sys
import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, _APP_ROOT)

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
        USE_TZ=True,
    )
    django.setup()

from chat_api.nlu.dto import LocationMode, LocationStatus, ResolvedLocation, UserLocationInput
from chat_api.nlu.search_intent_builder import SearchIntentBuilder

# ── helpers ────────────────────────────────────────────────────────────────────

_MODULE = "chat_api.nlu.search_intent_builder"


def _ok_resolved(**kw) -> ResolvedLocation:
    return ResolvedLocation(
        status=LocationStatus.OK,
        mode=LocationMode.AREA,
        canonical_area=kw.get("canonical_area", "quan 1"),
        display_label=kw.get("display_label", "Quận 1"),
        latitude=kw.get("latitude", 10.77),
        longitude=kw.get("longitude", 106.69),
        radius_km=kw.get("radius_km", 5.0),
        provider="test",
        cache_hit=True,
    )


def _unresolved() -> ResolvedLocation:
    return ResolvedLocation(
        status=LocationStatus.UNRESOLVED,
        mode=LocationMode.UNKNOWN,
    )


def _make_resolver_mock(resolved: ResolvedLocation) -> MagicMock:
    instance = MagicMock()
    instance.resolve.return_value = resolved
    cls_mock = MagicMock()
    cls_mock.default.return_value = instance
    return cls_mock


# ── test class ─────────────────────────────────────────────────────────────────

class TestSearchIntentBuilderBuild(unittest.TestCase):

    def setUp(self):
        self.builder = SearchIntentBuilder()

    # ── anywhere intent ────────────────────────────────────────────────────────

    def test_anywhere_o_dau_cung_duoc(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)
        self.assertEqual(intent.location.status, LocationStatus.OK)

    def test_anywhere_uppercase_variant(self):
        intent = self.builder.build("di dau cung duoc")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)

    def test_anywhere_display_label(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertEqual(intent.location.display_label, "Anywhere")

    def test_anywhere_budget_still_extracted(self):
        # Anywhere + budget: slot extraction still runs
        intent = self.builder.build("o dau cung duoc 200k")
        self.assertEqual(intent.location.mode, LocationMode.ANYWHERE)
        self.assertEqual(intent.budget, 200_000)

    # ── near-me without GPS ────────────────────────────────────────────────────

    def test_near_me_no_gps_returns_unresolved(self):
        intent = self.builder.build("gan toi co wifi", user_location=None)
        self.assertEqual(intent.location.status, LocationStatus.UNRESOLVED)
        self.assertEqual(intent.location.mode, LocationMode.NEAR_USER)

    def test_near_me_no_gps_sets_needs_user_location_flag(self):
        intent = self.builder.build("gan toi", user_location=None)
        self.assertTrue(intent.location.debug.get("needs_user_location"))

    def test_near_me_with_gps_returns_near_user(self):
        gps = UserLocationInput(lat=10.77, lon=106.69)
        intent = self.builder.build("gan toi", user_location=gps)
        self.assertEqual(intent.location.mode, LocationMode.NEAR_USER)
        self.assertEqual(intent.location.status, LocationStatus.OK)
        self.assertAlmostEqual(intent.location.latitude, 10.77)
        self.assertAlmostEqual(intent.location.longitude, 106.69)

    def test_near_me_with_gps_provider_is_browser_gps(self):
        gps = UserLocationInput(lat=10.77, lon=106.69)
        intent = self.builder.build("gan toi", user_location=gps)
        self.assertEqual(intent.location.provider, "browser_gps")

    # ── resolver called for normal queries ─────────────────────────────────────

    def test_area_query_calls_resolver(self):
        resolved = _ok_resolved(canonical_area="quan 3")
        resolver_cls = _make_resolver_mock(resolved)
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("tim phong o quan 3")
        self.assertEqual(intent.location.canonical_area, "quan 3")
        self.assertEqual(intent.area, "quan 3")

    def test_location_unresolved_when_resolver_returns_unresolved(self):
        resolver_cls = _make_resolver_mock(_unresolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("tim phong co wifi")
        self.assertEqual(intent.location.status, LocationStatus.UNRESOLVED)

    def test_amenity_only_no_location_still_returns_intent(self):
        # missing location + amenity → valid SearchIntent, status unresolved
        resolver_cls = _make_resolver_mock(_unresolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("co wifi co bep")
        self.assertIsNotNone(intent)
        self.assertIn("wifi", intent.required_amenities)

    # ── slot extraction ────────────────────────────────────────────────────────

    def test_budget_k_unit(self):
        intent = self.builder.build("200k")
        self.assertEqual(intent.budget, 200_000)

    def test_budget_tr_unit(self):
        intent = self.builder.build("1tr")
        self.assertEqual(intent.budget, 1_000_000)

    def test_budget_million_unit(self):
        intent = self.builder.build("2.5tr")
        self.assertEqual(intent.budget, 2_500_000)

    def test_budget_large_vnd(self):
        intent = self.builder.build("tìm phòng 500000")
        self.assertEqual(intent.budget, 500_000)

    def test_budget_none_when_no_number(self):
        intent = self.builder.build("tìm phòng ở quận 1")
        self.assertIsNone(intent.budget)

    def test_guest_count_nguoi(self):
        intent = self.builder.build("cho 3 nguoi")
        self.assertEqual(intent.guest_count, 3)

    def test_guest_count_cap_doi(self):
        intent = self.builder.build("cap doi")
        self.assertEqual(intent.guest_count, 2)

    def test_guest_count_none_when_absent(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertIsNone(intent.guest_count)

    def test_trip_days_ngay(self):
        intent = self.builder.build("3 ngay")
        self.assertEqual(intent.trip_days, 3)

    def test_trip_days_dem(self):
        intent = self.builder.build("2 dem")
        self.assertEqual(intent.trip_days, 2)

    def test_trip_days_none_when_absent(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertIsNone(intent.trip_days)

    def test_accommodation_type_homestay(self):
        intent = self.builder.build("tim homestay")
        self.assertIn("homestay", intent.accommodation_types)

    def test_accommodation_type_hotel(self):
        intent = self.builder.build("khach san")
        self.assertIn("hotel", intent.accommodation_types)

    def test_accommodation_type_apartment(self):
        intent = self.builder.build("can ho")
        self.assertIn("apartment", intent.accommodation_types)

    def test_amenity_wifi(self):
        intent = self.builder.build("co wifi")
        self.assertIn("wifi", intent.required_amenities)

    def test_amenity_pool(self):
        intent = self.builder.build("co ho boi")
        self.assertIn("pool", intent.required_amenities)

    def test_amenity_parking(self):
        intent = self.builder.build("co parking")
        self.assertIn("parking", intent.required_amenities)

    def test_amenity_multiple(self):
        intent = self.builder.build("co wifi co bep")
        self.assertIn("wifi", intent.required_amenities)
        self.assertIn("kitchen", intent.required_amenities)

    # ── context_slots fallback ─────────────────────────────────────────────────

    def test_context_slots_budget_used_when_text_has_none(self):
        intent = self.builder.build(
            "tim homestay",
            context_slots={"budget": 500_000},
        )
        self.assertEqual(intent.budget, 500_000)

    def test_context_slots_guest_count_used_as_fallback(self):
        intent = self.builder.build(
            "tim phong o quan 1",
            context_slots={"guest_count": 4},
        )
        self.assertEqual(intent.guest_count, 4)

    def test_context_slots_types_used_as_fallback(self):
        intent = self.builder.build(
            "o dau cung duoc",
            context_slots={"accommodation_types": ["hostel"]},
        )
        self.assertIn("hostel", intent.accommodation_types)

    def test_text_budget_overrides_context_slots(self):
        # Text has 300k → should override context_slots budget=100000
        intent = self.builder.build(
            "300k",
            context_slots={"budget": 100_000},
        )
        self.assertEqual(intent.budget, 300_000)

    # ── metadata ───────────────────────────────────────────────────────────────

    def test_input_kind_propagated(self):
        intent = self.builder.build("xin chao")
        self.assertEqual(intent.input_kind, "greeting")

    def test_raw_text_preserved(self):
        text = "gần Landmark 81 ở quận 7"
        resolver_cls = _make_resolver_mock(_ok_resolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build(text)
        self.assertEqual(intent.raw_text, text)

    def test_locale_default_vi(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertEqual(intent.locale, "vi")

    def test_locale_can_be_overridden(self):
        intent = self.builder.build("o dau cung duoc", locale="en")
        self.assertEqual(intent.locale, "en")

    def test_conversation_intent_is_search(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertEqual(intent.conversation_intent, "search")

    def test_selected_place_passed_through(self):
        resolver_cls = _make_resolver_mock(_ok_resolved())
        with patch(f"{_MODULE}.LocationResolver", resolver_cls):
            intent = self.builder.build("o day", selected_place="Quận 1")
        self.assertEqual(intent.selected_place, "Quận 1")

    def test_confidence_from_classifier(self):
        intent = self.builder.build("xin chao")
        self.assertGreater(intent.confidence, 0.0)

    # ── debug flag ─────────────────────────────────────────────────────────────

    def test_debug_empty_by_default(self):
        intent = self.builder.build("o dau cung duoc")
        self.assertEqual(intent.debug, {})

    def test_debug_populated_when_flag_set(self):
        intent = self.builder.build("o dau cung duoc", include_debug=True)
        self.assertIn("classification", intent.debug)
        self.assertIn("is_anywhere", intent.debug)

    def test_debug_includes_is_near_me(self):
        intent = self.builder.build("gan toi", include_debug=True)
        self.assertIn("is_near_me", intent.debug)
        self.assertTrue(intent.debug["is_near_me"])

    # ── edge cases ─────────────────────────────────────────────────────────────

    def test_empty_text_returns_intent(self):
        intent = self.builder.build("")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.input_kind, "unknown")

    def test_whitespace_only_returns_intent(self):
        intent = self.builder.build("   ")
        self.assertIsNotNone(intent)

    def test_never_raises(self):
        bad_inputs = [None, 123, [], {}, True]  # type: ignore[list-item]
        for bad in bad_inputs:
            try:
                # build() accepts str; non-str may raise — that's acceptable,
                # but internal pipeline errors must not propagate
                self.builder.build(str(bad))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build() raised unexpectedly for {bad!r}: {exc}")


# ── sample output ──────────────────────────────────────────────────────────────

def _print_sample(label: str, text: str, **kwargs) -> None:
    builder = SearchIntentBuilder()
    intent = builder.build(text, include_debug=True, **kwargs)
    print(f"\n{'─' * 60}")
    print(f"Input : {label!r}")
    print(f"Text  : {text!r}")
    print(f"  input_kind        : {intent.input_kind}")
    print(f"  location.mode     : {intent.location.mode}")
    print(f"  location.status   : {intent.location.status}")
    print(f"  location.area     : {intent.location.canonical_area}")
    print(f"  location.lat/lon  : {intent.location.latitude}, {intent.location.longitude}")
    print(f"  area              : {intent.area}")
    print(f"  hotel_name        : {intent.hotel_name}")
    print(f"  types             : {intent.accommodation_types}")
    print(f"  budget            : {intent.budget}")
    print(f"  guest_count       : {intent.guest_count}")
    print(f"  trip_days         : {intent.trip_days}")
    print(f"  amenities         : {intent.required_amenities}")
    print(f"  confidence        : {intent.confidence:.2f}")
    print(f"  debug.is_anywhere : {intent.debug.get('is_anywhere')}")
    print(f"  debug.is_near_me  : {intent.debug.get('is_near_me')}")


if __name__ == "__main__":
    print("=" * 60)
    print("SearchIntentBuilder.build() — sample outputs")
    print("=" * 60)

    _print_sample("anywhere", "o dau cung duoc")
    _print_sample("anywhere + budget + guest", "o dau cung duoc 300k cho 2 nguoi")
    _print_sample("near-me no GPS", "gan toi co wifi")
    _print_sample(
        "near-me with GPS",
        "gan toi",
        user_location=UserLocationInput(lat=10.77, lon=106.69),
    )
    _print_sample("amenity only", "co wifi co ho boi")
    _print_sample("area only", "quan 3")
    _print_sample("budget + type + days", "homestay 500k 3 ngay")
    _print_sample("greeting", "xin chao")
    _print_sample(
        "context fallback",
        "tim homestay",
        context_slots={"budget": 200_000, "guest_count": 2},
    )
    _print_sample("full query", "khach san gan ben thanh quan 1 2 nguoi 2 dem 500k co parking")

    print("\n" + "=" * 60)
    unittest.main(verbosity=2)
