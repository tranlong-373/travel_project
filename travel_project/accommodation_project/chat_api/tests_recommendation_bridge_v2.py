
"""
Tests for recommendation_bridge v2 path (SearchIntent support).

Run:
    cd travel_project/accommodation_project
    python -m unittest chat_api.tests_recommendation_bridge_v2 -v
"""
from __future__ import annotations

import dataclasses
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "preferences"],
        USE_TZ=True,
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        ROOT_URLCONF="chat_api.urls_test_stub",
    )
    django.setup()

# Create tables for tests
from django.test.utils import setup_test_environment
setup_test_environment()

from django.db import connection

with connection.schema_editor() as _se:
    from preferences.models import UserPreference
    try:
        _se.create_model(UserPreference)
    except Exception:
        pass

# ── stubs ─────────────────────────────────────────────────────────────────────

# Minimal URL conf so reverse() works
import types
_url_module = types.ModuleType("chat_api.urls_test_stub")
_url_module.urlpatterns = []

from django.urls import path as _url_path

def _fake_recommendation_result(request, pref_id):  # noqa: ANN
    pass  # pragma: no cover

_url_module.urlpatterns = [
    _url_path("recommendations/<int:pref_id>/", _fake_recommendation_result, name="recommendation_result"),
]
sys.modules["chat_api.urls_test_stub"] = _url_module

# ── imports under test ────────────────────────────────────────────────────────

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)
from chat_api.recommendation_bridge import (
    attach_recommendation_action,
    create_preference_from_parse,
    usable_filters_from_intent,
    usable_filters_from_parse,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_intent(
    *,
    mode: LocationMode = LocationMode.AREA,
    status: LocationStatus = LocationStatus.OK,
    canonical_area: str | None = "quan 1",
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float = 10.0,
    anchor_name: str | None = None,
    anchor_kind: str | None = None,
    display_label: str | None = None,
    provider: str | None = None,
    nearby_poi_key: str | None = None,
    user_location: UserLocationInput | None = None,
    budget: int | None = None,
    budget_max: int | None = None,
    guest_count: int | None = None,
    accommodation_types: list[str] | None = None,
    required_amenities: list[str] | None = None,
    hotel_name: str | None = None,
    input_kind: str = "area",
    confidence: float = 0.80,
    loc_debug: dict | None = None,
) -> SearchIntent:
    loc = ResolvedLocation(
        status=status,
        mode=mode,
        canonical_area=canonical_area,
        display_label=display_label or canonical_area,
        anchor_name=anchor_name,
        anchor_kind=anchor_kind,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        provider=provider,
        nearby_poi_key=nearby_poi_key,
        debug=loc_debug or {},
    )
    return SearchIntent(
        raw_text="test query",
        input_kind=input_kind,
        location=loc,
        user_location=user_location,
        budget=budget,
        budget_max=budget_max,
        guest_count=guest_count,
        accommodation_types=accommodation_types or [],
        required_amenities=required_amenities or [],
        hotel_name=hotel_name,
        area=canonical_area,
        confidence=confidence,
    )


def _make_legacy_parse_result(**kw) -> dict:
    """Minimal legacy parse_result that passes create_preference_from_parse guards."""
    base = {
        "can_show_recommendations": True,
        "conversation_intent": "search",
        "location_mode": "area",
        "location_status": "ok",
        "canonical_area": "quan 1",
        "unresolved_location": False,
        "filter_tree": {
            "location": {"mode": "area", "canonical_area": "quan 1"},
            "filters": [],
            "usable_filter_count": 1,
        },
        "slots": {"area": "quan 1", "budget": 300_000, "guest_count": 2},
        "soft_filter_summary": "khu vực quận 1",
    }
    base.update(kw)
    return base


# ── usable_filters_from_intent ────────────────────────────────────────────────

class TestUsableFiltersFromIntent(unittest.TestCase):

    def test_area_mode_returns_location(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        filters = usable_filters_from_intent(intent)
        self.assertIn("location", filters)

    def test_anywhere_mode_returns_location_anywhere(self):
        intent = _make_intent(mode=LocationMode.ANYWHERE, canonical_area=None)
        filters = usable_filters_from_intent(intent)
        self.assertIn("location_anywhere", filters)

    def test_near_anchor_with_coords_returns_location(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            canonical_area=None,
            latitude=10.77,
            longitude=106.69,
        )
        filters = usable_filters_from_intent(intent)
        self.assertIn("location", filters)

    def test_near_anchor_without_coords_no_location(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            canonical_area=None,
            latitude=None,
        )
        filters = usable_filters_from_intent(intent)
        self.assertNotIn("location", filters)

    def test_hotel_name_mode_returns_location(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            canonical_area=None,
            hotel_name="Vincom Hotel",
        )
        filters = usable_filters_from_intent(intent)
        self.assertIn("location", filters)

    def test_budget_included(self):
        intent = _make_intent(budget_max=500_000)
        filters = usable_filters_from_intent(intent)
        self.assertIn("budget", filters)

    def test_amenities_included(self):
        intent = _make_intent(required_amenities=["wifi"])
        filters = usable_filters_from_intent(intent)
        self.assertIn("amenities", filters)

    def test_nearby_poi_when_key_set(self):
        intent = _make_intent(nearby_poi_key="cafe")
        filters = usable_filters_from_intent(intent)
        self.assertIn("nearby_poi", filters)

    def test_empty_intent_returns_only_location_if_area(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 5")
        filters = usable_filters_from_intent(intent)
        self.assertEqual(filters, ["location"])


# ── usable_filters_from_parse with v2 ────────────────────────────────────────

class TestUsableFiltersFromParseV2(unittest.TestCase):

    def test_delegates_to_intent_when_search_intent_v2_present(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1", budget_max=300_000)
        parse_result = {"search_intent_v2": intent}
        filters = usable_filters_from_parse(parse_result)
        self.assertIn("location", filters)
        self.assertIn("budget", filters)

    def test_legacy_path_used_when_no_search_intent_v2(self):
        parse_result = _make_legacy_parse_result()
        filters = usable_filters_from_parse(parse_result)
        self.assertIn("location", filters)

    def test_v2_dict_round_trip(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 2")
        intent_dict = dataclasses.asdict(intent)
        parse_result = {"search_intent_v2": intent_dict}
        filters = usable_filters_from_parse(parse_result)
        self.assertIn("location", filters)


# ── create_preference_from_parse: legacy path ─────────────────────────────────

class TestLegacyPath(unittest.TestCase):

    def test_legacy_parse_result_creates_preference(self):
        parse_result = _make_legacy_parse_result()
        result = create_preference_from_parse(parse_result)
        self.assertIn("pref_id", result)
        self.assertIn("recommendation_url", result)
        self.assertIsNotNone(result["pref_id"])

    def test_legacy_response_keys(self):
        parse_result = _make_legacy_parse_result()
        result = create_preference_from_parse(parse_result)
        for key in ("pref_id", "recommendation_url", "used_default_slots",
                    "user_location_used", "search_origin"):
            self.assertIn(key, result, f"Missing legacy key: {key}")

    def test_legacy_blocked_intent_raises(self):
        parse_result = _make_legacy_parse_result(conversation_intent="greeting")
        with self.assertRaises(ValueError):
            create_preference_from_parse(parse_result)


# ── create_preference_from_parse: v2 path ─────────────────────────────────────

class TestV2PathWithIntentObject(unittest.TestCase):

    def _run(self, intent: SearchIntent) -> dict:
        parse_result = {"search_intent_v2": intent}
        return create_preference_from_parse(parse_result)

    def test_returns_same_response_keys_as_legacy(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3", budget_max=300_000, guest_count=2)
        result = self._run(intent)
        for key in ("pref_id", "recommendation_url", "used_default_slots",
                    "user_location_used", "search_origin"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_pref_id_is_integer(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1", budget_max=200_000)
        result = self._run(intent)
        self.assertIsInstance(result["pref_id"], int)

    def test_recommendation_url_contains_pref_id(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 2", budget_max=500_000)
        result = self._run(intent)
        self.assertIn(str(result["pref_id"]), result["recommendation_url"])

    def test_area_mode_preference_stored(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 5",
            budget_max=400_000,
            guest_count=2,
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertEqual(pref.area, "quan 5")
        self.assertIsNone(pref.user_latitude)

    def test_near_anchor_stores_coords_downstream(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.GEOCODED,
            canonical_area=None,
            anchor_name="Landmark 81",
            anchor_kind="landmark",
            latitude=10.7950,
            longitude=106.7220,
            radius_km=5.0,
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertAlmostEqual(pref.user_latitude, 10.7950, places=3)
        self.assertAlmostEqual(pref.user_longitude, 106.7220, places=3)
        self.assertIsNone(pref.area)
        self.assertEqual(pref.location_mode, "near_anchor")

    def test_near_user_with_gps_stores_coords(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=3.0)
        intent = _make_intent(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            canonical_area=None,
            latitude=10.77,
            longitude=106.69,
            user_location=gps,
            input_kind="amenity_only",
            budget_max=300_000,
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertAlmostEqual(pref.user_latitude, 10.77, places=3)
        self.assertIsNone(pref.area)
        self.assertTrue(result["user_location_used"])

    def test_anywhere_mode_no_coords(self):
        intent = _make_intent(
            mode=LocationMode.ANYWHERE,
            status=LocationStatus.OK,
            canonical_area=None,
            latitude=None,
            input_kind="unknown",
            budget_max=200_000,
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertIsNone(pref.area)
        self.assertIsNone(pref.user_latitude)
        self.assertEqual(pref.location_mode, "anywhere")

    # ── hotel_name: not lost in filter_tree_json ──────────────────────────────

    def test_hotel_name_not_lost_in_filter_tree_json(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            status=LocationStatus.OK,
            canonical_area=None,
            anchor_name="Khách Sạn ABC",
            anchor_kind="hotel",
            latitude=10.77,
            longitude=106.69,
            hotel_name="Khách Sạn ABC",
            input_kind="hotel_name",
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        ft = pref.filter_tree_json or {}
        loc_branch = ft.get("location") or {}
        # anchor_name or location_phrase must contain the hotel name
        self.assertTrue(
            loc_branch.get("anchor_name") == "Khách Sạn ABC"
            or loc_branch.get("location_phrase") == "Khách Sạn ABC",
            f"Hotel name not in location branch: {loc_branch}",
        )

    def test_hotel_name_anchor_kind_is_hotel(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            status=LocationStatus.OK,
            canonical_area=None,
            anchor_kind="hotel",
            latitude=10.77,
            longitude=106.69,
            hotel_name="Khách Sạn XYZ",
            input_kind="hotel_name",
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        ft = pref.filter_tree_json or {}
        loc_branch = ft.get("location") or {}
        self.assertEqual(loc_branch.get("anchor_kind"), "hotel")

    def test_hotel_name_does_not_become_area(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            status=LocationStatus.OK,
            canonical_area=None,
            hotel_name="Sheraton Saigon",
            input_kind="hotel_name",
        )
        result = self._run(intent)
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertIsNone(pref.area)

    # ── amenity_only: no fabricated location ──────────────────────────────────

    def test_amenity_only_with_amenities_creates_preference(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            canonical_area=None,
            required_amenities=["wifi", "pool"],
            input_kind="amenity_only",
        )
        result = self._run(intent)
        self.assertIsNotNone(result["pref_id"])
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertIsNone(pref.area)
        self.assertIn("wifi", pref.required_amenities)

    def test_amenity_only_no_amenities_raises(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            canonical_area=None,
            required_amenities=[],
            input_kind="amenity_only",
            budget_max=None,
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})

    # ── validation guards ─────────────────────────────────────────────────────

    def test_greeting_without_filters_raises(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.NONE,
            canonical_area=None,
            input_kind="greeting",
        )
        # area=None and no filters → no usable filters → raises
        intent_no_area = dataclasses.replace(intent, area=None, location=dataclasses.replace(intent.location, canonical_area=None))
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent_no_area})

    def test_near_anchor_without_coords_raises(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.UNRESOLVED,
            canonical_area=None,
            latitude=None,
            longitude=None,
            input_kind="landmark_or_poi",
        )
        # no coords + near_anchor → raises
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})

    def test_ambiguous_location_raises(self):
        intent = _make_intent(
            mode=LocationMode.AMBIGUOUS,
            status=LocationStatus.AMBIGUOUS,
            canonical_area=None,
            input_kind="unknown",
            budget_max=300_000,
        )
        with self.assertRaises(ValueError):
            create_preference_from_parse({"search_intent_v2": intent})

    # ── used_default_slots ────────────────────────────────────────────────────

    def test_used_default_slots_budget_when_missing(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            canonical_area="quan 6",
            budget_max=None,
            guest_count=2,
        )
        # Remove budget from intent
        intent = dataclasses.replace(intent, budget=None, budget_min=None, budget_max=None)
        result = self._run(intent)
        self.assertIn("budget", result["used_default_slots"])
        self.assertEqual(result["used_default_slots"]["budget"]["value"], 0)

    def test_used_default_slots_guest_count_when_missing(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            canonical_area="quan 7",
            guest_count=None,
            budget_max=300_000,
        )
        result = self._run(intent)
        self.assertIn("guest_count", result["used_default_slots"])


# ── v2 path: dict round-trip (serialised SearchIntent) ────────────────────────

class TestV2PathWithIntentDict(unittest.TestCase):

    def test_dict_round_trip_creates_preference(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 8", budget_max=200_000)
        intent_dict = dataclasses.asdict(intent)
        parse_result = {"search_intent_v2": intent_dict}
        result = create_preference_from_parse(parse_result)
        self.assertIn("pref_id", result)
        self.assertIsNotNone(result["pref_id"])

    def test_dict_near_anchor_restores_coords(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            canonical_area=None,
            latitude=10.78,
            longitude=106.70,
            radius_km=5.0,
            anchor_name="Ben Thanh",
            anchor_kind="market",
            status=LocationStatus.OK,
        )
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        pref = UserPreference.objects.get(pk=result["pref_id"])
        self.assertAlmostEqual(pref.user_latitude, 10.78, places=2)

    def test_dict_hotel_name_preserved(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            anchor_name="Park Hyatt Saigon",
            anchor_kind="hotel",
            latitude=10.77,
            longitude=106.70,
            hotel_name="Park Hyatt Saigon",
            canonical_area=None,
            status=LocationStatus.OK,
            input_kind="hotel_name",
        )
        intent_dict = dataclasses.asdict(intent)
        result = create_preference_from_parse({"search_intent_v2": intent_dict})
        pref = UserPreference.objects.get(pk=result["pref_id"])
        ft = pref.filter_tree_json or {}
        loc = ft.get("location") or {}
        self.assertEqual(loc.get("anchor_kind"), "hotel")


# ── attach_recommendation_action with v2 ──────────────────────────────────────

class TestAttachRecommendationActionV2(unittest.TestCase):

    def test_recommendation_action_enabled_for_v2_intent(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            canonical_area="quan 9",
            budget_max=300_000,
            guest_count=2,
        )
        parse_result = {
            "search_intent_v2": intent,
            "can_show_recommendations": True,
        }
        bridge_result = {"pref_id": 999, "recommendation_url": "/recommendations/999/"}
        result = attach_recommendation_action(parse_result, bridge_result)
        action = result.get("recommendation_action") or {}
        self.assertTrue(action.get("visible"))
        self.assertIn("location", result.get("usable_filters") or [])

    def test_recommendation_action_disabled_for_greeting_without_filters(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.NONE,
            canonical_area=None,
            input_kind="greeting",
        )
        intent = dataclasses.replace(intent, area=None, location=dataclasses.replace(intent.location, canonical_area=None))
        parse_result = {
            "search_intent_v2": intent,
            "can_show_recommendations": True,
        }
        result = attach_recommendation_action(parse_result)
        action = result.get("recommendation_action") or {}
        self.assertFalse(action.get("enabled"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
