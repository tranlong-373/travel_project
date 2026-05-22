"""
Regression tests for 6 verified location-parsing/display bugs.

Run:
  python manage.py test chat_api.tests.test_bug_fixes
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from chat_api.nlu.input_classifier_v2 import classify_v2
from chat_api.nlu.dto import (
    LocationMode,
    LocationStatus,
    ResolvedLocation,
    SearchIntent,
    UserLocationInput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intent(
    *,
    mode: LocationMode = LocationMode.AREA,
    status: LocationStatus = LocationStatus.OK,
    canonical_area: str | None = "quan 1",
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 5.0,
    display_label: str | None = None,
    nearby_poi_key: str | None = None,
) -> SearchIntent:
    loc = ResolvedLocation(
        status=status,
        mode=mode,
        canonical_area=canonical_area,
        display_label=display_label or canonical_area,
        latitude=lat,
        longitude=lon,
        radius_km=radius_km,
        nearby_poi_key=nearby_poi_key,
    )
    return SearchIntent(
        raw_text="test",
        input_kind="area",
        location=loc,
        area=canonical_area if mode == LocationMode.AREA else None,
        budget=None,
        budget_max=None,
        guest_count=None,
        trip_days=None,
        required_amenities=[],
        accommodation_types=[],
        user_location=None,
        conversation_intent="search",
    )


# ---------------------------------------------------------------------------
# Fix 1: Bến Thành landmark priority
# ---------------------------------------------------------------------------

class TestBenThanhLandmarkPriority(SimpleTestCase):

    def test_gan_cho_ben_thanh_is_landmark_or_poi(self):
        result = classify_v2("gần chợ Bến Thành")
        self.assertEqual(result.input_kind, "landmark_or_poi",
                         f"Expected landmark_or_poi, got {result.input_kind}: {result.debug}")

    def test_gan_ben_thanh_is_landmark_or_poi(self):
        result = classify_v2("gần Bến Thành")
        self.assertEqual(result.input_kind, "landmark_or_poi",
                         f"Expected landmark_or_poi, got {result.input_kind}: {result.debug}")

    def test_gan_cho_ben_thanh_reason(self):
        result = classify_v2("gần chợ Bến Thành")
        self.assertEqual(result.debug.get("reason"), "near_cue+known_landmark")

    def test_gan_ben_thanh_location_phrase_set(self):
        result = classify_v2("gần Bến Thành")
        self.assertIsNotNone(result.location_phrase)

    # Regression: "gần quán cafe ở Quận 5" must still be generic_poi_in_area
    def test_near_cafe_district5_unchanged(self):
        result = classify_v2("gần quán cafe ở Quận 5")
        self.assertEqual(result.input_kind, "generic_poi_in_area")

    # Regression: "gần Quận 3" must remain area
    def test_near_district3_is_area(self):
        result = classify_v2("gần Quận 3")
        self.assertEqual(result.input_kind, "area")

    # Regression: Landmark 81 still landmark_or_poi
    def test_landmark81_unchanged(self):
        result = classify_v2("gần Landmark 81")
        self.assertEqual(result.input_kind, "landmark_or_poi")

    # Regression: Nhà thờ Đức Bà still landmark_or_poi
    def test_nha_tho_duc_ba_unchanged(self):
        result = classify_v2("gần Nhà thờ Đức Bà")
        self.assertEqual(result.input_kind, "landmark_or_poi")

    # Regression: Dinh Độc Lập still landmark_or_poi
    def test_dinh_doc_lap_unchanged(self):
        result = classify_v2("gần Dinh Độc Lập")
        self.assertEqual(result.input_kind, "landmark_or_poi")


# ---------------------------------------------------------------------------
# Fix 2: AREA mode with resolved coordinates → near_anchor in adapter
# ---------------------------------------------------------------------------

class TestAreaWithCoordsProducesAnchor(SimpleTestCase):

    def _kwargs(self, **kw):
        from chat_api.adapters.search_intent_to_user_preference import build_user_preference_kwargs
        return build_user_preference_kwargs(_intent(**kw))

    def test_area_with_coords_sets_user_lat_lon(self):
        kw = self._kwargs(
            mode=LocationMode.AREA,
            canonical_area="quan 5",
            lat=10.757, lon=106.667,
        )
        self.assertIsNotNone(kw.get("user_latitude"))
        self.assertAlmostEqual(kw["user_latitude"], 10.757)
        self.assertAlmostEqual(kw["user_longitude"], 106.667)

    def test_area_with_coords_location_mode_is_near_anchor(self):
        kw = self._kwargs(
            mode=LocationMode.AREA,
            canonical_area="quan 5",
            lat=10.757, lon=106.667,
        )
        self.assertEqual(kw.get("location_mode"), "near_anchor")

    def test_area_with_coords_filter_tree_branch_mode_is_near_anchor(self):
        kw = self._kwargs(
            mode=LocationMode.AREA,
            canonical_area="quan 5",
            lat=10.757, lon=106.667,
        )
        loc_branch = kw["filter_tree_json"]["location"]
        self.assertEqual(loc_branch.get("mode"), "near_anchor")
        self.assertIsNotNone(loc_branch.get("anchor_lat"))

    def test_area_without_coords_remains_area_text(self):
        """Pure area query — no lat/lon — must keep text-area filtering."""
        kw = self._kwargs(
            mode=LocationMode.AREA,
            canonical_area="quan 3",
            lat=None, lon=None,
        )
        self.assertEqual(kw.get("area"), "quan 3")
        self.assertEqual(kw.get("location_mode"), "area")
        self.assertIsNone(kw.get("user_latitude"))

    def test_area_without_coords_filter_tree_mode_is_area(self):
        kw = self._kwargs(
            mode=LocationMode.AREA,
            canonical_area="quan 3",
            lat=None, lon=None,
        )
        loc_branch = kw["filter_tree_json"]["location"]
        self.assertEqual(loc_branch.get("mode"), "area")


# ---------------------------------------------------------------------------
# Fix 3: Specific address with postal code / Vietnam suffix
# ---------------------------------------------------------------------------

class TestSpecificAddressWithPostalCode(SimpleTestCase):

    def test_vo_van_tan_address_is_specific_address(self):
        result = classify_v2("14 Võ Văn Tần, Xuân Hòa, Hồ Chí Minh 70000, Vietnam, Quận 3")
        self.assertEqual(result.input_kind, "specific_address",
                         f"Expected specific_address, got {result.input_kind}: {result.debug}")

    def test_vo_van_tan_location_phrase_raw_preserved(self):
        result = classify_v2("14 Võ Văn Tần, Xuân Hòa, Hồ Chí Minh 70000, Vietnam, Quận 3")
        self.assertIsNotNone(result.location_phrase_raw)
        # accented form should be preserved for geocoder
        self.assertIn("Võ Văn Tần", result.location_phrase_raw)

    def test_vo_van_tan_area_hint_is_quan_3(self):
        result = classify_v2("14 Võ Văn Tần, Xuân Hòa, Hồ Chí Minh 70000, Vietnam, Quận 3")
        self.assertIsNotNone(result.area_hint)
        self.assertIn("3", result.area_hint or "")


# ---------------------------------------------------------------------------
# Fix 4: Nguyễn Huệ display label must not contain "Thành phố Thủ Đức"
# ---------------------------------------------------------------------------

class TestNguyenHueDisplayLabel(SimpleTestCase):

    def _ref_to_resolved(self, **overrides):
        from chat_api.location.strategies.near_anchor import _ref_to_resolved
        ref = {
            "canonical_name": "Đường đi bộ Nguyễn Huệ",
            "name": "Đường đi bộ Nguyễn Huệ",
            "display_name": (
                "Đường đi bộ Nguyễn Huệ, Khu phố 8, Phường Sài Gòn, "
                "Thành phố Thủ Đức, Thành phố Hồ Chí Minh, 71006, Việt Nam"
            ),
            "latitude": 10.7737196,
            "longitude": 106.7040457,
            "default_radius_km": 2.5,
            "kind": "pedestrian",
            "provider": "osm",
        }
        ref.update(overrides)
        return _ref_to_resolved(ref)

    def test_display_label_does_not_contain_thu_duc(self):
        resolved = self._ref_to_resolved()
        label = resolved.display_label or ""
        self.assertNotIn("Thành phố Thủ Đức", label,
                         f"display_label should not expose OSM admin area: {label}")

    def test_display_label_uses_canonical_name(self):
        resolved = self._ref_to_resolved()
        self.assertIn("Nguyễn Huệ", resolved.display_label or "")

    def test_adapter_location_label_does_not_contain_thu_duc(self):
        from chat_api.adapters.search_intent_to_user_preference import build_user_preference_kwargs
        kw = build_user_preference_kwargs(_intent(
            mode=LocationMode.NEAR_ANCHOR,
            canonical_area="Đường đi bộ Nguyễn Huệ",
            lat=10.7737196, lon=106.7040457,
            display_label="Đường đi bộ Nguyễn Huệ",
        ))
        label = kw.get("location_label") or ""
        self.assertNotIn("Thành phố Thủ Đức", label)


# ---------------------------------------------------------------------------
# Fix 5: Suggestion selection state hygiene
# ---------------------------------------------------------------------------

class TestSuggestionStateHygiene(SimpleTestCase):

    def test_stale_key_name_parent_cleared_on_new_area(self):
        """Selecting a new area must wipe stale key/name/parent from prior selection."""
        from chat_api.views import _merge_payload

        stale_context = {
            "area": "Quận 2",
            "key": "quan_2",
            "name": "Quận 2",
            "parent": "Thành phố Hồ Chí Minh",
            "location_type": "district",
            "budget": 500_000,
        }
        new_payload = {
            "area": "Quận 1",
            "key": "quan_1",
            "name": "Quận 1",
        }
        merged = _merge_payload(stale_context, new_payload)

        self.assertEqual(merged.get("area"), "Quận 1")
        self.assertEqual(merged.get("key"), "quan_1")
        self.assertEqual(merged.get("name"), "Quận 1")
        # parent from old selection must be gone (not overridden by new payload)
        self.assertIsNone(merged.get("parent"))
        self.assertIsNone(merged.get("location_type"))
        # budget must survive — it's not a location key
        self.assertEqual(merged.get("budget"), 500_000)

    def test_non_location_payload_does_not_wipe_area(self):
        """A budget update must not wipe the area."""
        from chat_api.views import _merge_payload

        stale_context = {"area": "Quận 1", "budget": 300_000}
        new_payload = {"budget": 500_000}
        merged = _merge_payload(stale_context, new_payload)
        self.assertEqual(merged.get("area"), "Quận 1")

    def test_key_name_parent_not_in_confirm_table(self):
        """Internal suggestion keys must not appear in confirm_table."""
        from chat_api.parser_service import build_confirm_table

        slots = {
            "area": "Quận 1",
            "key": "quan_1",
            "name": "Quận 1",
            "parent": "Thành phố Hồ Chí Minh",
            "location_type": "district",
            "smart_suggestion": {"id": "location:quan-1"},
        }
        table = build_confirm_table(slots)
        table_keys = {item["key"] for item in table}
        for banned in ("key", "name", "parent", "location_type", "smart_suggestion"):
            self.assertNotIn(banned, table_keys,
                             f"'{banned}' must not appear in confirm_table")

    def test_build_confirmed_result_sets_anchor_coords_from_selected_place(self):
        """selected_place with lat/lon must populate anchor_lat/lon in result."""
        from chat_api.views import _build_confirmed_result

        slots = {
            "selected_place": {
                "name": "Quận 5",
                "lat": 10.7558,
                "lon": 106.6683,
                "radius_km": 2.5,
                "kind": "historic",
            }
        }
        result = _build_confirmed_result(slots)
        self.assertIsNotNone(result.get("anchor_lat"))
        self.assertAlmostEqual(result["anchor_lat"], 10.7558, places=3)
        self.assertEqual(result.get("location_mode"), "near_anchor")


# ---------------------------------------------------------------------------
# Fix 6: Gas station POI category
# ---------------------------------------------------------------------------

class TestGasStationPOICategory(SimpleTestCase):

    def test_tram_xang_quan3_is_generic_poi_in_area(self):
        result = classify_v2("trạm xăng ở Quận 3")
        self.assertEqual(result.input_kind, "generic_poi_in_area",
                         f"Expected generic_poi_in_area, got {result.input_kind}: {result.debug}")

    def test_tram_xang_quan3_area_hint_set(self):
        result = classify_v2("trạm xăng ở Quận 3")
        self.assertIsNotNone(result.area_hint)
        self.assertIn("3", result.area_hint or "")

    def test_cay_xang_quan1_is_generic_poi_in_area(self):
        result = classify_v2("cây xăng Quận 1")
        self.assertEqual(result.input_kind, "generic_poi_in_area")

    def test_gas_station_near_cue_is_generic_poi_in_area(self):
        result = classify_v2("gần trạm xăng ở Quận 7")
        self.assertEqual(result.input_kind, "generic_poi_in_area")
