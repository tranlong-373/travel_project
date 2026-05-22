"""
Tests for SearchIntent → UserPreference adapter.

Run:
    cd travel_project/accommodation_project
    python -m unittest chat_api.adapters.test_search_intent_to_user_preference -v
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, _APP_ROOT)

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "preferences"],
        USE_TZ=True,
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )
    django.setup()

from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)
from chat_api.adapters.search_intent_to_user_preference import (
    build_user_preference_kwargs,
    create_user_preference_from_intent,
    search_intent_to_legacy_slots,
    search_intent_to_location_result,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_intent(
    *,
    mode: LocationMode = LocationMode.UNKNOWN,
    status: LocationStatus = LocationStatus.NONE,
    canonical_area: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float = 10.0,
    anchor_name: str | None = None,
    anchor_kind: str | None = None,
    display_label: str | None = None,
    provider: str | None = None,
    raw_phrase: str | None = None,
    nearby_poi_key: str | None = None,
    nearby_poi_label: str | None = None,
    user_location: UserLocationInput | None = None,
    budget: int | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    guest_count: int | None = None,
    trip_days: int | None = None,
    accommodation_types: list[str] | None = None,
    required_amenities: list[str] | None = None,
    priorities: list[str] | None = None,
    hotel_name: str | None = None,
    area: str | None = None,
    raw_text: str = "test",
    confidence: float = 0.80,
    loc_debug: dict | None = None,
) -> SearchIntent:
    loc = ResolvedLocation(
        status=status,
        mode=mode,
        canonical_area=canonical_area,
        display_label=display_label,
        anchor_name=anchor_name,
        anchor_kind=anchor_kind,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        provider=provider,
        nearby_poi_key=nearby_poi_key,
        nearby_poi_label=nearby_poi_label,
        raw_phrase=raw_phrase,
        debug=loc_debug or {},
    )
    return SearchIntent(
        raw_text=raw_text,
        location=loc,
        user_location=user_location,
        budget=budget,
        budget_min=budget_min,
        budget_max=budget_max,
        guest_count=guest_count,
        trip_days=trip_days,
        accommodation_types=accommodation_types or [],
        required_amenities=required_amenities or [],
        priorities=priorities or [],
        hotel_name=hotel_name,
        area=area or canonical_area,
        confidence=confidence,
    )


# ── search_intent_to_legacy_slots ─────────────────────────────────────────────

class TestLegacySlots(unittest.TestCase):

    def test_area_mode_sets_area_key(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        slots = search_intent_to_legacy_slots(intent)
        self.assertEqual(slots["area"], "quan 3")

    def test_near_user_mode_passes_user_location_dict(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=5.0)
        intent = _make_intent(mode=LocationMode.NEAR_USER, user_location=gps)
        slots = search_intent_to_legacy_slots(intent)
        self.assertIn("user_location", slots)
        self.assertAlmostEqual(slots["user_location"]["lat"], 10.77)

    def test_near_anchor_does_not_set_area(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            canonical_area=None,
            latitude=10.77,
            longitude=106.69,
        )
        slots = search_intent_to_legacy_slots(intent)
        self.assertNotIn("area", slots)

    def test_anywhere_does_not_set_area(self):
        intent = _make_intent(mode=LocationMode.ANYWHERE)
        slots = search_intent_to_legacy_slots(intent)
        self.assertNotIn("area", slots)

    def test_budget_keys_included(self):
        intent = _make_intent(budget=500_000, budget_min=200_000, budget_max=500_000)
        slots = search_intent_to_legacy_slots(intent)
        self.assertEqual(slots["budget"], 500_000)
        self.assertEqual(slots["budget_min"], 200_000)
        self.assertEqual(slots["budget_max"], 500_000)

    def test_guest_count_included(self):
        intent = _make_intent(guest_count=3)
        slots = search_intent_to_legacy_slots(intent)
        self.assertEqual(slots["guest_count"], 3)

    def test_accommodation_types_and_preferred_type(self):
        intent = _make_intent(accommodation_types=["homestay", "hotel"])
        slots = search_intent_to_legacy_slots(intent)
        self.assertEqual(slots["accommodation_types"], ["homestay", "hotel"])
        self.assertEqual(slots["preferred_type"], "homestay")

    def test_amenities_included(self):
        intent = _make_intent(required_amenities=["wifi", "pool"])
        slots = search_intent_to_legacy_slots(intent)
        self.assertEqual(slots["required_amenities"], ["wifi", "pool"])

    def test_no_none_values_in_output(self):
        intent = _make_intent()
        slots = search_intent_to_legacy_slots(intent)
        for v in slots.values():
            self.assertIsNotNone(v)


# ── search_intent_to_location_result ─────────────────────────────────────────

class TestLocationResult(unittest.TestCase):

    def test_area_mode_keys(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 1",
            display_label="Quận 1",
        )
        result = search_intent_to_location_result(intent)
        self.assertEqual(result["location_mode"], "area")
        self.assertEqual(result["canonical_area"], "quan 1")
        self.assertFalse(result.get("unresolved_location"))

    def test_near_anchor_includes_coords(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.OK,
            latitude=10.77,
            longitude=106.69,
            anchor_name="Landmark 81",
            anchor_kind="landmark",
        )
        result = search_intent_to_location_result(intent)
        self.assertAlmostEqual(result["anchor_lat"], 10.77)
        self.assertAlmostEqual(result["anchor_lon"], 106.69)
        self.assertEqual(result["anchor_name"], "Landmark 81")

    def test_near_user_includes_user_location(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=3.0)
        intent = _make_intent(mode=LocationMode.NEAR_USER, user_location=gps)
        result = search_intent_to_location_result(intent)
        self.assertIn("user_location", result)
        self.assertAlmostEqual(result["user_location"]["lat"], 10.77)

    def test_unresolved_flag(self):
        intent = _make_intent(mode=LocationMode.UNKNOWN, status=LocationStatus.UNRESOLVED)
        result = search_intent_to_location_result(intent)
        self.assertTrue(result.get("unresolved_location"))

    def test_ambiguous_flag(self):
        intent = _make_intent(mode=LocationMode.AMBIGUOUS, status=LocationStatus.AMBIGUOUS)
        result = search_intent_to_location_result(intent)
        self.assertTrue(result.get("ambiguous_location"))


# ── build_user_preference_kwargs ──────────────────────────────────────────────

class TestBuildUserPreferenceKwargs(unittest.TestCase):

    # ── area mode ─────────────────────────────────────────────────────────────

    def test_area_mode_sets_area_no_coords(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 5",
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["area"], "quan 5")
        self.assertNotIn("user_latitude", kwargs)
        self.assertNotIn("user_longitude", kwargs)

    def test_area_mode_location_mode_value(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 3")
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["location_mode"], "area")

    # ── near_anchor mode ──────────────────────────────────────────────────────

    def test_near_anchor_stores_coords(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            status=LocationStatus.OK,
            latitude=10.77,
            longitude=106.69,
            radius_km=5.0,
            anchor_name="Landmark 81",
            anchor_kind="landmark",
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertAlmostEqual(kwargs["user_latitude"], 10.77)
        self.assertAlmostEqual(kwargs["user_longitude"], 106.69)
        self.assertAlmostEqual(kwargs["search_radius_km"], 5.0)
        self.assertIsNone(kwargs["area"])

    def test_near_anchor_sets_anchor_kind(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            anchor_kind="landmark",
            latitude=10.77,
            longitude=106.69,
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["anchor_kind"], "landmark")

    def test_near_anchor_filter_tree_location_mode(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_ANCHOR,
            latitude=10.77,
            longitude=106.69,
        )
        kwargs = build_user_preference_kwargs(intent)
        loc_branch = kwargs["filter_tree_json"]["location"]
        self.assertEqual(loc_branch["mode"], "near_anchor")

    # ── near_user mode ────────────────────────────────────────────────────────

    def test_near_user_with_gps_stores_coords(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=3.0)
        intent = _make_intent(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            user_location=gps,
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertAlmostEqual(kwargs["user_latitude"], 10.77)
        self.assertAlmostEqual(kwargs["user_longitude"], 106.69)
        self.assertAlmostEqual(kwargs["search_radius_km"], 3.0)
        self.assertIsNone(kwargs["area"])

    def test_near_user_filter_tree_location_mode(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=5.0)
        intent = _make_intent(mode=LocationMode.NEAR_USER, user_location=gps)
        kwargs = build_user_preference_kwargs(intent)
        loc_branch = kwargs["filter_tree_json"]["location"]
        self.assertEqual(loc_branch["mode"], "near_user")
        self.assertAlmostEqual(loc_branch["anchor_lat"], 10.77)

    def test_near_user_without_gps_no_coords_in_kwargs(self):
        intent = _make_intent(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.UNRESOLVED,
            user_location=None,
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertNotIn("user_latitude", kwargs)
        self.assertNotIn("user_longitude", kwargs)

    # ── anywhere mode ─────────────────────────────────────────────────────────

    def test_anywhere_no_area_no_coords(self):
        intent = _make_intent(mode=LocationMode.ANYWHERE, status=LocationStatus.OK)
        kwargs = build_user_preference_kwargs(intent)
        self.assertIsNone(kwargs["area"])
        self.assertNotIn("user_latitude", kwargs)
        self.assertNotIn("user_longitude", kwargs)

    def test_anywhere_filter_tree_location_mode(self):
        intent = _make_intent(mode=LocationMode.ANYWHERE)
        kwargs = build_user_preference_kwargs(intent)
        loc_branch = kwargs["filter_tree_json"]["location"]
        self.assertEqual(loc_branch["mode"], "anywhere")

    # ── hotel_name mode ───────────────────────────────────────────────────────

    def test_hotel_name_with_coords_uses_near_anchor(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            status=LocationStatus.OK,
            anchor_name="Vincom Hotel",
            anchor_kind="hotel",
            latitude=10.77,
            longitude=106.69,
            hotel_name="Vincom Hotel",
        )
        kwargs = build_user_preference_kwargs(intent)
        # hotel_name with coords: mode in filter_tree should be near_anchor
        loc_branch = kwargs["filter_tree_json"]["location"]
        self.assertEqual(loc_branch["mode"], "near_anchor")
        self.assertEqual(loc_branch["anchor_kind"], "hotel")
        # Must not set area (hotel_name ≠ area)
        self.assertIsNone(kwargs["area"])

    def test_hotel_name_without_coords_is_unknown_not_area(self):
        intent = _make_intent(
            mode=LocationMode.HOTEL_NAME,
            status=LocationStatus.OK,
            hotel_name="Khách Sạn ABC",
            # No lat/lon
        )
        kwargs = build_user_preference_kwargs(intent)
        loc_branch = kwargs["filter_tree_json"]["location"]
        # No fabricated area
        self.assertIsNone(kwargs["area"])
        # mode should be unknown, not area
        self.assertNotEqual(loc_branch["mode"], "area")

    # ── amenity_only: no fabricated location ──────────────────────────────────

    def test_amenity_only_no_area_created(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            required_amenities=["wifi", "pool"],
            loc_debug={"needs_area_clarification": True},
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertIsNone(kwargs["area"])
        self.assertNotIn("user_latitude", kwargs)

    def test_amenity_only_clarification_question_in_location_branch(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            required_amenities=["wifi"],
            loc_debug={"needs_area_clarification": True},
        )
        kwargs = build_user_preference_kwargs(intent)
        branch = kwargs["filter_tree_json"]["location"]
        self.assertTrue(branch.get("needs_area_clarification") or branch.get("ambiguous_location_question"))

    def test_amenity_only_amenities_still_in_kwargs(self):
        intent = _make_intent(
            mode=LocationMode.UNKNOWN,
            status=LocationStatus.UNRESOLVED,
            required_amenities=["wifi", "kitchen"],
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertIn("wifi", kwargs["required_amenities"])
        self.assertIn("kitchen", kwargs["required_amenities"])

    # ── filter nodes ──────────────────────────────────────────────────────────

    def test_budget_stored_as_int(self):
        intent = _make_intent(budget_max=500_000)
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["budget"], 500_000)
        self.assertIsInstance(kwargs["budget"], int)

    def test_budget_zero_default_when_none(self):
        intent = _make_intent()
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["budget"], 0)

    def test_guest_count_minimum_one(self):
        intent = _make_intent(guest_count=None)
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["guest_count"], 1)

    def test_preferred_type_valid_only(self):
        intent = _make_intent(accommodation_types=["resort"])  # not a valid type
        kwargs = build_user_preference_kwargs(intent)
        self.assertIsNone(kwargs["preferred_type"])

    def test_preferred_type_homestay_accepted(self):
        intent = _make_intent(accommodation_types=["homestay"])
        kwargs = build_user_preference_kwargs(intent)
        self.assertEqual(kwargs["preferred_type"], "homestay")

    # ── filter_tree_json structure ────────────────────────────────────────────

    def test_filter_tree_json_has_required_keys(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1")
        kwargs = build_user_preference_kwargs(intent)
        ft = kwargs["filter_tree_json"]
        for key in ("location", "filters", "available_slots", "usable_filter_count"):
            self.assertIn(key, ft, f"filter_tree_json missing key: {key}")

    def test_usable_filter_count_positive_for_area(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 1",
            budget_max=500_000,
            guest_count=2,
        )
        kwargs = build_user_preference_kwargs(intent)
        self.assertGreater(kwargs["filter_tree_json"]["usable_filter_count"], 0)

    def test_search_origin_in_filter_tree(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 7")
        kwargs = build_user_preference_kwargs(intent)
        self.assertIn("search_origin", kwargs["filter_tree_json"])

    def test_soft_filter_summary_is_string(self):
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 1", budget_max=300_000)
        kwargs = build_user_preference_kwargs(intent)
        self.assertIsInstance(kwargs["soft_filter_summary"], str)

    # ── all required model fields present ─────────────────────────────────────

    def test_all_model_fields_present(self):
        required = {
            "area", "budget", "guest_count", "preferred_type",
            "required_amenities", "location_mode", "location_label",
            "anchor_kind", "filter_tree_json", "soft_filter_summary",
            "search_radius_km",
        }
        intent = _make_intent(
            mode=LocationMode.AREA,
            canonical_area="quan 2",
            budget_max=400_000,
            guest_count=2,
        )
        kwargs = build_user_preference_kwargs(intent)
        for field in required:
            self.assertIn(field, kwargs, f"Missing model field: {field}")

    # ── backward-compatible to_preference_kwargs ──────────────────────────────

    def test_to_preference_kwargs_backward_compat(self):
        from chat_api.adapters.search_intent_to_user_preference import to_preference_kwargs
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 4")
        kwargs = to_preference_kwargs(intent)
        self.assertIn("budget", kwargs)
        self.assertIn("guest_count", kwargs)
        self.assertIn("filter_tree_json", kwargs)

    def test_to_preference_kwargs_accepts_override_filter_tree(self):
        from chat_api.adapters.search_intent_to_user_preference import to_preference_kwargs
        intent = _make_intent(mode=LocationMode.AREA, canonical_area="quan 4")
        custom_tree = {"location": {"mode": "area"}, "filters": [], "custom": True}
        kwargs = to_preference_kwargs(intent, filter_tree_json=custom_tree)
        self.assertTrue(kwargs["filter_tree_json"].get("custom"))


# ── create_user_preference_from_intent (DB write) ─────────────────────────────

class TestCreateUserPreference(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from django.db import connection
        with connection.schema_editor() as schema_editor:
            from preferences.models import UserPreference
            try:
                schema_editor.create_model(UserPreference)
            except Exception:
                pass  # table may already exist

    def test_creates_preference_and_returns_instance(self):
        from preferences.models import UserPreference
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 1",
            budget_max=300_000,
            guest_count=2,
            accommodation_types=["hotel"],
        )
        pref = create_user_preference_from_intent(intent)
        self.assertIsInstance(pref, UserPreference)
        self.assertIsNotNone(pref.pk)

    def test_preference_area_matches_intent(self):
        intent = _make_intent(
            mode=LocationMode.AREA,
            status=LocationStatus.OK,
            canonical_area="quan 5",
            budget_max=200_000,
            guest_count=1,
        )
        pref = create_user_preference_from_intent(intent)
        self.assertEqual(pref.area, "quan 5")

    def test_preference_near_user_has_coordinates(self):
        gps = UserLocationInput(lat=10.77, lon=106.69, radius_km=5.0)
        intent = _make_intent(
            mode=LocationMode.NEAR_USER,
            status=LocationStatus.OK,
            user_location=gps,
            budget_max=500_000,
            guest_count=2,
        )
        pref = create_user_preference_from_intent(intent)
        self.assertAlmostEqual(pref.user_latitude, 10.77)
        self.assertAlmostEqual(pref.user_longitude, 106.69)
        self.assertIsNone(pref.area)

    def test_preference_anywhere_no_area_no_coords(self):
        intent = _make_intent(
            mode=LocationMode.ANYWHERE,
            status=LocationStatus.OK,
            budget_max=300_000,
            guest_count=1,
        )
        pref = create_user_preference_from_intent(intent)
        self.assertIsNone(pref.area)
        self.assertIsNone(pref.user_latitude)


if __name__ == "__main__":
    unittest.main(verbosity=2)
