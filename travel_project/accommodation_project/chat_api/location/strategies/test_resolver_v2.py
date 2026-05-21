"""
Unit tests for LocationResolver v2 and all strategies.

Run:
    cd travel_project/accommodation_project
    python -m pytest chat_api/location/strategies/test_resolver_v2.py -v
    python -m unittest chat_api.location.strategies.test_resolver_v2 -v
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Make the module importable from any working directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.join(_HERE, "..", "..", "..", "..")  # accommodation_project/
sys.path.insert(0, _APP_ROOT)

from chat_api.nlu.dto import LocationMode, LocationStatus, UserLocationInput
from chat_api.location.context import LocationContext
from chat_api.location.resolver import LocationResolver
from chat_api.location.strategies.base import LocationStrategy
from chat_api.location.strategies.current_location import CurrentLocationStrategy
from chat_api.location.strategies.selected_place import SelectedPlaceStrategy
from chat_api.location.strategies.hotel_name import HotelNameStrategy
from chat_api.location.strategies.direct_area import DirectAreaStrategy
from chat_api.location.strategies.near_anchor import NearAnchorFromPlaceReferenceStrategy
from chat_api.location.strategies.fallback_geocode import FallbackGeocodeStrategy
from chat_api.location.strategies.poi_centroid import PoiCentroidStrategy
from chat_api.location.strategies.ambiguous_or_unsupported import AmbiguousOrUnsupportedStrategy


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ctx(**kw) -> LocationContext:
    return LocationContext(raw_text=kw.pop("raw_text", "test"), **kw)


def _place_ref(
    *,
    name: str = "Test Place",
    lat: float = 10.77,
    lon: float = 106.70,
    kind: str = "landmark",
    radius_km: float = 5.0,
) -> dict:
    return {
        "canonical_name": name,
        "display_name": name,
        "latitude": lat,
        "longitude": lon,
        "kind": kind,
        "default_radius_km": radius_km,
        "provider": "osm",
    }


def _acc_row(
    *,
    name: str = "Test Hotel",
    area: str = "Quận 1",
    lat: float = 10.77,
    lon: float = 106.70,
) -> dict:
    return {"id": 1, "name": name, "area": area, "latitude": lat, "longitude": lon, "accommodation_type": "hotel"}


# ============================================================================
# CurrentLocationStrategy
# ============================================================================

class TestCurrentLocationStrategy(unittest.TestCase):
    strategy = CurrentLocationStrategy()

    def _gps_ctx(self, input_kind: str) -> LocationContext:
        return _ctx(
            input_kind=input_kind,
            user_location=UserLocationInput(lat=10.77, lon=106.70, radius_km=5.0),
        )

    def test_amenity_only_with_gps_can_handle(self):
        self.assertTrue(self.strategy.can_handle(self._gps_ctx("amenity_only")))

    def test_unknown_with_gps_can_handle(self):
        self.assertTrue(self.strategy.can_handle(self._gps_ctx("unknown")))

    def test_landmark_with_gps_not_handled(self):
        # landmark_or_poi → near_anchor strategy should resolve, not GPS
        self.assertFalse(self.strategy.can_handle(self._gps_ctx("landmark_or_poi")))

    def test_area_with_gps_not_handled(self):
        self.assertFalse(self.strategy.can_handle(self._gps_ctx("area")))

    def test_hotel_name_with_gps_not_handled(self):
        self.assertFalse(self.strategy.can_handle(self._gps_ctx("hotel_name")))

    def test_amenity_without_gps_not_handled(self):
        ctx = _ctx(input_kind="amenity_only")  # no user_location
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_resolve_returns_near_user(self):
        r = self.strategy.resolve(self._gps_ctx("amenity_only"))
        self.assertIsNotNone(r)
        self.assertEqual(r.mode, LocationMode.NEAR_USER)
        self.assertEqual(r.status, LocationStatus.OK)

    def test_resolve_correct_coordinates(self):
        r = self.strategy.resolve(self._gps_ctx("amenity_only"))
        self.assertAlmostEqual(r.latitude, 10.77)
        self.assertAlmostEqual(r.longitude, 106.70)
        self.assertAlmostEqual(r.radius_km, 5.0)

    def test_resolve_provider_browser_gps(self):
        r = self.strategy.resolve(self._gps_ctx("unknown"))
        self.assertEqual(r.provider, "browser_gps")


# ============================================================================
# DirectAreaStrategy
# ============================================================================

class TestDirectAreaStrategy(unittest.TestCase):
    strategy = DirectAreaStrategy()

    def test_can_handle_area_with_hint(self):
        ctx = _ctx(input_kind="area", area_hint="quan 3")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_no_hint(self):
        ctx = _ctx(input_kind="area", area_hint=None)
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_cannot_handle_wrong_kind(self):
        ctx = _ctx(input_kind="landmark_or_poi", area_hint="quan 3")
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_resolve_mode_area(self):
        ctx = _ctx(input_kind="area", area_hint="quan 3")
        r = self.strategy.resolve(ctx)
        self.assertIsNotNone(r)
        self.assertEqual(r.mode, LocationMode.AREA)

    def test_resolve_no_lat_lon(self):
        # area mode doesn't need coordinates
        ctx = _ctx(input_kind="area", area_hint="phu nhuan")
        r = self.strategy.resolve(ctx)
        self.assertIsNone(r.latitude)
        self.assertIsNone(r.longitude)

    def test_resolve_canonical_area(self):
        ctx = _ctx(input_kind="area", area_hint="binh thanh")
        r = self.strategy.resolve(ctx)
        self.assertEqual(r.canonical_area, "binh thanh")

    def test_resolve_status_ok(self):
        ctx = _ctx(input_kind="area", area_hint="da nang")
        r = self.strategy.resolve(ctx)
        self.assertEqual(r.status, LocationStatus.OK)


# ============================================================================
# NearAnchorFromPlaceReferenceStrategy — cache hit
# ============================================================================

class TestNearAnchorStrategy(unittest.TestCase):
    strategy = NearAnchorFromPlaceReferenceStrategy()

    def test_can_handle_landmark(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="landmark 81")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_can_handle_specific_address(self):
        ctx = _ctx(input_kind="specific_address", location_phrase="1 su van hanh phuong 9 quan 5")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_no_phrase(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase=None, area_hint=None)
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_cannot_handle_area_kind(self):
        ctx = _ctx(input_kind="area", location_phrase="quan 3")
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_cache_hit_does_not_call_geocoder(self):
        """CRITICAL: cache hit must NOT invoke the external geocoder."""
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="landmark 81")
        cached = _place_ref(name="Landmark 81", lat=10.7950, lon=106.7220)

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=cached) as mock_cache:
            with patch("chat_api.location.strategies.fallback_geocode._geocode") as mock_geocode:
                result = self.strategy.resolve(ctx)

        mock_cache.assert_called_once_with("landmark 81")
        mock_geocode.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.NEAR_ANCHOR)
        self.assertTrue(result.cache_hit)

    def test_cache_hit_correct_coordinates(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="dinh doc lap")
        cached = _place_ref(name="Dinh Độc Lập", lat=10.7769, lon=106.6952)

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=cached):
            result = self.strategy.resolve(ctx)

        self.assertAlmostEqual(result.latitude, 10.7769)
        self.assertAlmostEqual(result.longitude, 106.6952)

    def test_cache_miss_returns_none(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="nha may dien luc")

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=None):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)

    def test_specific_address_full_query_preserved(self):
        """Full address must not be truncated when looking up cache."""
        full_addr = "1 su van hanh phuong 9 quan 5 tp hcm"
        ctx = _ctx(input_kind="specific_address", location_phrase=full_addr)

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=None) as mock_cache:
            self.strategy.resolve(ctx)

        # The strategy must look up the FULL phrase, not a truncated version
        mock_cache.assert_called_with(full_addr)


# ============================================================================
# FallbackGeocodeStrategy
# ============================================================================

class TestFallbackGeocodeStrategy(unittest.TestCase):
    strategy = FallbackGeocodeStrategy()

    def test_can_handle_landmark(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="ben thanh market")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_can_handle_address(self):
        ctx = _ctx(input_kind="specific_address", location_phrase="1 su van hanh phuong 9")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_area(self):
        ctx = _ctx(input_kind="area", location_phrase="quan 3")
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_geocoder_success_returns_near_anchor(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="bitexco tower")

        with patch("chat_api.location.strategies.fallback_geocode._geocode", return_value=(10.7713, 106.7042)):
            result = self.strategy.resolve(ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.NEAR_ANCHOR)
        self.assertEqual(result.status, LocationStatus.GEOCODED)
        self.assertAlmostEqual(result.latitude, 10.7713)
        self.assertAlmostEqual(result.longitude, 106.7042)

    def test_geocoder_fail_does_not_crash(self):
        """Geocoder failure must return None, never raise."""
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="noi bat san tren mat trang")

        with patch("chat_api.location.strategies.fallback_geocode._geocode", side_effect=Exception("network error")):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)

    def test_geocoder_returns_none_passes_through(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="xyzxyz unknown place")

        with patch("chat_api.location.strategies.fallback_geocode._geocode", return_value=None):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)

    def test_specific_address_full_query(self):
        """Full address must be passed to geocoder without truncation."""
        full_addr = "120 nguyen hue, quan 1, tp hcm"
        ctx = _ctx(input_kind="specific_address", location_phrase=full_addr)

        with patch("chat_api.location.strategies.fallback_geocode._geocode", return_value=(10.77, 106.70)) as mock_geocode:
            self.strategy.resolve(ctx)

        mock_geocode.assert_called_with(full_addr)

    def test_geocoder_timeout_does_not_crash(self):
        """Timeout should return None, not raise."""
        from concurrent.futures import TimeoutError as FuturesTimeout

        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="slow place")

        def slow_geocode(phrase):
            import time
            time.sleep(10)  # will timeout

        # Patch with a real slow function but set a short timeout
        import chat_api.location.strategies.fallback_geocode as fg_module
        original_timeout = fg_module.GEOCODE_TIMEOUT
        fg_module.GEOCODE_TIMEOUT = 0.01  # 10ms — will timeout
        try:
            with patch("chat_api.location.strategies.fallback_geocode._geocode", side_effect=slow_geocode):
                result = self.strategy.resolve(ctx)
        finally:
            fg_module.GEOCODE_TIMEOUT = original_timeout

        # Must return None, not crash
        self.assertIsNone(result)


# ============================================================================
# HotelNameStrategy
# ============================================================================

class TestHotelNameStrategy(unittest.TestCase):
    strategy = HotelNameStrategy()

    def test_can_handle_hotel_name(self):
        ctx = _ctx(input_kind="hotel_name", hotel_name="Rex Hotel")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_no_hotel_name(self):
        ctx = _ctx(input_kind="hotel_name", hotel_name=None)
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_cannot_handle_wrong_kind(self):
        ctx = _ctx(input_kind="area", hotel_name="Rex Hotel")
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_db_hit_returns_hotel_name_mode(self):
        ctx = _ctx(input_kind="hotel_name", hotel_name="Rex Hotel")
        acc = _acc_row(name="Rex Hotel", area="Quận 1", lat=10.7769, lon=106.7009)

        with patch("chat_api.location.strategies.hotel_name._find_accommodation_by_name", return_value=acc):
            result = self.strategy.resolve(ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.HOTEL_NAME)
        self.assertEqual(result.canonical_area, "Quận 1")
        self.assertTrue(result.cache_hit)

    def test_db_miss_returns_none(self):
        ctx = _ctx(input_kind="hotel_name", hotel_name="Unknown Hotel XYZ")

        with patch("chat_api.location.strategies.hotel_name._find_accommodation_by_name", return_value=None):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)

    def test_db_error_returns_none(self):
        ctx = _ctx(input_kind="hotel_name", hotel_name="Rex Hotel")

        with patch("chat_api.location.strategies.hotel_name._find_accommodation_by_name", side_effect=Exception("DB error")):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)


# ============================================================================
# PoiCentroidStrategy
# ============================================================================

class TestPoiCentroidStrategy(unittest.TestCase):
    strategy = PoiCentroidStrategy()

    def test_can_handle_generic_poi(self):
        ctx = _ctx(input_kind="generic_poi_in_area", area_hint="quan 5", poi_category="cafe")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_no_area(self):
        ctx = _ctx(input_kind="generic_poi_in_area", area_hint=None)
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_centroid_found_returns_area_mode(self):
        ctx = _ctx(
            input_kind="generic_poi_in_area",
            area_hint="quan 5",
            poi_category="cafe",
            location_phrase="gan quan cafe o quan 5",
        )
        ref = _place_ref(name="Quận 5", lat=10.7518, lon=106.6641, radius_km=10.0)

        with patch("chat_api.location.strategies.poi_centroid._lookup_area_centroid", return_value=ref):
            result = self.strategy.resolve(ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.AREA)
        self.assertAlmostEqual(result.latitude, 10.7518)
        self.assertEqual(result.canonical_area, "quan 5")
        self.assertEqual(result.nearby_poi_key, "cafe")
        self.assertTrue(result.cache_hit)

    def test_no_centroid_still_returns_area(self):
        ctx = _ctx(input_kind="generic_poi_in_area", area_hint="phu nhuan", poi_category="hospital")

        with patch("chat_api.location.strategies.poi_centroid._lookup_area_centroid", return_value=None):
            result = self.strategy.resolve(ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.AREA)
        self.assertIsNone(result.latitude)  # no centroid
        self.assertEqual(result.canonical_area, "phu nhuan")


# ============================================================================
# AmbiguousOrUnsupportedStrategy
# ============================================================================

class TestAmbiguousOrUnsupportedStrategy(unittest.TestCase):
    strategy = AmbiguousOrUnsupportedStrategy()

    def test_always_can_handle(self):
        for kind in ["unknown", "amenity_only", "area", "landmark_or_poi", "greeting"]:
            with self.subTest(kind=kind):
                ctx = _ctx(input_kind=kind)
                self.assertTrue(self.strategy.can_handle(ctx))

    def test_amenity_only_no_gps_unresolved(self):
        ctx = _ctx(input_kind="amenity_only", amenity_terms=["wifi"])
        result = self.strategy.resolve(ctx)
        self.assertEqual(result.status, LocationStatus.UNRESOLVED)
        self.assertTrue(result.debug.get("needs_area_clarification"))

    def test_unknown_kind_unresolved(self):
        ctx = _ctx(input_kind="unknown")
        result = self.strategy.resolve(ctx)
        self.assertEqual(result.status, LocationStatus.UNRESOLVED)

    def test_landmark_exhausted_ambiguous(self):
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="some unresolved place")
        result = self.strategy.resolve(ctx)
        self.assertEqual(result.status, LocationStatus.AMBIGUOUS)
        self.assertEqual(result.mode, LocationMode.AMBIGUOUS)

    def test_always_returns_resolved_location_not_none(self):
        ctx = _ctx(input_kind="mixed_search", location_phrase="somewhere")
        result = self.strategy.resolve(ctx)
        self.assertIsNotNone(result)


# ============================================================================
# LocationResolver — integration
# ============================================================================

class TestLocationResolver(unittest.TestCase):

    def _resolver(self, *strategies) -> LocationResolver:
        return LocationResolver(list(strategies))

    def test_strategy_order_is_respected(self):
        """Strategies must run in ascending order, not insertion order."""
        log = []

        class S1(DirectAreaStrategy):
            order = 50
            def resolve(self, ctx):
                log.append(50)
                return None
            def can_handle(self, ctx): return True

        class S2(DirectAreaStrategy):
            order = 10
            def resolve(self, ctx):
                log.append(10)
                return super().resolve(ctx)  # returns a result
            def can_handle(self, ctx): return True

        resolver = self._resolver(S1(), S2())  # S1 registered first but has higher order
        resolver.resolve(_ctx(input_kind="area", area_hint="quan 1"))

        self.assertEqual(log[0], 10)  # S2 (order=10) ran first

    def test_first_successful_strategy_wins(self):
        """Chain stops at first non-None result."""
        class EarlyWinner(CurrentLocationStrategy):
            order = 5
            def can_handle(self, ctx): return True
            def resolve(self, ctx):
                from chat_api.nlu.dto import ResolvedLocation, LocationStatus, LocationMode
                return ResolvedLocation(status=LocationStatus.OK, mode=LocationMode.AREA)

        class ShouldNotRun(DirectAreaStrategy):
            order = 10
            def resolve(self, ctx):
                raise AssertionError("This strategy should not have run")

        resolver = self._resolver(ShouldNotRun(), EarlyWinner())
        result = resolver.resolve(_ctx(input_kind="area", area_hint="quan 1"))
        self.assertEqual(result.status, LocationStatus.OK)

    def test_amenity_only_no_gps_returns_unresolved(self):
        """amenity_only without GPS must end in UNRESOLVED, not crash."""
        resolver = LocationResolver([
            CurrentLocationStrategy(),
            AmbiguousOrUnsupportedStrategy(),
        ])
        ctx = _ctx(input_kind="amenity_only", amenity_terms=["wifi"])
        result = resolver.resolve(ctx)
        self.assertEqual(result.status, LocationStatus.UNRESOLVED)
        self.assertTrue(result.debug.get("needs_area_clarification"))

    def test_landmark_cache_hit_is_near_anchor(self):
        """Landmark with cache hit → near_anchor, geocoder not called."""
        resolver = LocationResolver([
            NearAnchorFromPlaceReferenceStrategy(),
            FallbackGeocodeStrategy(),
            AmbiguousOrUnsupportedStrategy(),
        ])
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="ben thanh")
        cached = _place_ref(name="Chợ Bến Thành", lat=10.7722, lon=106.6980)

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=cached):
            with patch("chat_api.location.strategies.fallback_geocode._geocode") as mock_geo:
                result = resolver.resolve(ctx)

        mock_geo.assert_not_called()
        self.assertEqual(result.mode, LocationMode.NEAR_ANCHOR)
        self.assertTrue(result.cache_hit)

    def test_area_resolves_without_geocoder(self):
        """area input kind must never call geocoder."""
        resolver = LocationResolver([
            DirectAreaStrategy(),
            FallbackGeocodeStrategy(),
        ])
        ctx = _ctx(input_kind="area", area_hint="quan 3")

        with patch("chat_api.location.strategies.fallback_geocode._geocode") as mock_geo:
            result = resolver.resolve(ctx)

        mock_geo.assert_not_called()
        self.assertEqual(result.mode, LocationMode.AREA)

    def test_geocoder_fail_falls_back_to_ambiguous(self):
        """Geocoder failure must not crash — resolver returns ambiguous."""
        resolver = LocationResolver([
            NearAnchorFromPlaceReferenceStrategy(),
            FallbackGeocodeStrategy(),
            AmbiguousOrUnsupportedStrategy(),
        ])
        ctx = _ctx(input_kind="landmark_or_poi", location_phrase="xyzxyz unknown")

        with patch("chat_api.location.strategies.near_anchor._lookup_place_reference", return_value=None):
            with patch("chat_api.location.strategies.fallback_geocode._geocode", side_effect=Exception("boom")):
                result = resolver.resolve(ctx)

        self.assertIn(result.status, {LocationStatus.AMBIGUOUS, LocationStatus.UNRESOLVED})

    def test_resolver_never_raises(self):
        """Resolver must always return a ResolvedLocation, even if all strategies raise."""
        class BrokenStrategy(LocationStrategy):
            order = 1
            name = "broken"
            def can_handle(self, ctx): return True
            def resolve(self, ctx): raise RuntimeError("broken")

        resolver = LocationResolver([BrokenStrategy(), AmbiguousOrUnsupportedStrategy()])
        result = resolver.resolve(_ctx(input_kind="unknown"))
        self.assertIsNotNone(result)

    def test_empty_resolver_returns_unresolved(self):
        resolver = LocationResolver([])
        result = resolver.resolve(_ctx())
        self.assertEqual(result.status, LocationStatus.UNRESOLVED)

    def test_debug_mode_adds_metadata(self):
        resolver = LocationResolver([DirectAreaStrategy()])
        ctx = _ctx(input_kind="area", area_hint="quan 1", debug=True)
        result = resolver.resolve(ctx)
        self.assertIn("resolved_by", result.debug)
        self.assertIn("attempted", result.debug)


# ============================================================================
# SelectedPlaceStrategy
# ============================================================================

class TestSelectedPlaceStrategy(unittest.TestCase):
    strategy = SelectedPlaceStrategy()

    def test_can_handle_with_selected(self):
        ctx = _ctx(selected_place="Nhà Thờ Đức Bà")
        self.assertTrue(self.strategy.can_handle(ctx))

    def test_cannot_handle_no_selected(self):
        ctx = _ctx(selected_place=None)
        self.assertFalse(self.strategy.can_handle(ctx))

    def test_resolve_returns_near_anchor_on_hit(self):
        ctx = _ctx(selected_place="Landmark 81")
        ref = _place_ref(name="Landmark 81", lat=10.7950, lon=106.7222)

        with patch("chat_api.location.strategies.selected_place._lookup_place_reference", return_value=ref):
            result = self.strategy.resolve(ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result.mode, LocationMode.NEAR_ANCHOR)

    def test_resolve_returns_none_on_miss(self):
        ctx = _ctx(selected_place="Unknown Place XYZ")

        with patch("chat_api.location.strategies.selected_place._lookup_place_reference", return_value=None):
            result = self.strategy.resolve(ctx)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
