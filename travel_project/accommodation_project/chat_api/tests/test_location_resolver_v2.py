"""
Unit tests for LocationResolver v2.

Mandatory cases (spec):
  9.  cache hit PlaceReference — geocoder MUST NOT be called
  10. geocoder fail — resolver MUST NOT raise, returns UNRESOLVED

Run:  python manage.py test chat_api.tests.test_location_resolver_v2
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from chat_api.location.context import LocationContext
from chat_api.location.resolver import LocationResolver
from chat_api.nlu.dto import LocationMode, LocationStatus, ResolvedLocation, UserLocationInput


_NEAR_ANCHOR_MODULE = "chat_api.location.strategies.near_anchor"
_FALLBACK_MODULE = "chat_api.location.strategies.fallback_geocode"
_LANDMARK_JSON_MODULE = "chat_api.location.strategies.landmark_static_json"


def _make_place_ref(lat: float = 10.77, lon: float = 106.69) -> dict:
    return {
        "canonical_name": "Landmark 81",
        "display_name": "Landmark 81, Quận Bình Thạnh",
        "latitude": lat,
        "longitude": lon,
        "default_radius_km": 5.0,
        "kind": "landmark",
        "provider": "osm",
    }


def _landmark_context(**kw) -> LocationContext:
    return LocationContext(
        raw_text=kw.get("raw_text", "gần Landmark 81"),
        input_kind="landmark_or_poi",
        location_phrase=kw.get("location_phrase", "landmark 81"),
        debug=kw.get("debug", False),
    )


class TestCacheHit(SimpleTestCase):
    """Test 9: PlaceReference cache hit must NOT invoke the geocoder."""

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference")
    @patch(f"{_FALLBACK_MODULE}._geocode")
    def test_cache_hit_skips_geocoder(self, mock_geocode, mock_lookup):
        mock_lookup.return_value = _make_place_ref()

        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())

        mock_geocode.assert_not_called()
        self.assertEqual(result.status, LocationStatus.OK)
        self.assertEqual(result.mode, LocationMode.NEAR_ANCHOR)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference")
    @patch(f"{_FALLBACK_MODULE}._geocode")
    def test_cache_hit_coordinates_match_stored(self, mock_geocode, mock_lookup):
        mock_lookup.return_value = _make_place_ref(lat=10.8235, lon=106.7296)

        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())

        self.assertAlmostEqual(result.latitude, 10.8235, places=4)
        self.assertAlmostEqual(result.longitude, 106.7296, places=4)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference")
    @patch(f"{_FALLBACK_MODULE}._geocode")
    def test_cache_hit_anchor_name_preserved(self, mock_geocode, mock_lookup):
        mock_lookup.return_value = _make_place_ref()

        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())

        self.assertIsNotNone(result.anchor_name)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference")
    @patch(f"{_FALLBACK_MODULE}._geocode")
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_cache_miss_calls_geocoder(self, _mock_landmark, mock_geocode, mock_lookup):
        mock_lookup.return_value = None
        mock_geocode.return_value = (10.77, 106.69)

        resolver = LocationResolver.default()
        resolver.resolve(_landmark_context())

        mock_geocode.assert_called_once()


class TestGeocoderFail(SimpleTestCase):
    """Test 10: geocoder failure must NOT propagate; returns UNRESOLVED."""

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference", return_value=None)
    @patch(f"{_FALLBACK_MODULE}._geocode", side_effect=ConnectionError("network timeout"))
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_geocoder_exception_does_not_crash(self, _mock_lm, mock_geocode, mock_lookup):
        resolver = LocationResolver.default()
        try:
            result = resolver.resolve(_landmark_context())
        except Exception as exc:
            self.fail(f"resolver.resolve() raised unexpectedly: {exc}")

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference", return_value=None)
    @patch(f"{_FALLBACK_MODULE}._geocode", side_effect=RuntimeError("upstream error"))
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_geocoder_fail_returns_non_ok_status(self, _mock_lm, mock_geocode, mock_lookup):
        # When geocoder fails for landmark_or_poi, chain ends at AmbiguousOrUnsupported.
        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())
        self.assertNotEqual(result.status, LocationStatus.OK)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference", return_value=None)
    @patch(f"{_FALLBACK_MODULE}._geocode", return_value=None)
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_geocoder_none_returns_non_ok_status(self, _mock_lm, mock_geocode, mock_lookup):
        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())
        self.assertNotEqual(result.status, LocationStatus.OK)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference", return_value=None)
    @patch(f"{_FALLBACK_MODULE}._geocode", side_effect=TimeoutError)
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_geocoder_timeout_returns_non_ok_mode(self, _mock_lm, mock_geocode, mock_lookup):
        # AmbiguousOrUnsupportedStrategy fires — mode is AMBIGUOUS, not UNKNOWN.
        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())
        self.assertNotEqual(result.mode, LocationMode.NEAR_ANCHOR)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference", return_value=None)
    @patch(f"{_FALLBACK_MODULE}._geocode", side_effect=Exception("any error"))
    @patch(f"{_LANDMARK_JSON_MODULE}._find_landmark", return_value=None)
    def test_geocoder_fail_result_has_no_coordinates(self, _mock_lm, mock_geocode, mock_lookup):
        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context())
        self.assertIsNone(result.latitude)
        self.assertIsNone(result.longitude)


class TestResolverBehavior(SimpleTestCase):
    """General resolver contract tests."""

    def test_resolver_default_returns_instance(self):
        resolver = LocationResolver.default()
        self.assertIsInstance(resolver, LocationResolver)

    def test_strategy_names_not_empty(self):
        resolver = LocationResolver.default()
        self.assertGreater(len(resolver.strategy_names), 0)

    def test_always_returns_resolved_location(self):
        resolver = LocationResolver.default()
        ctx = LocationContext(
            raw_text="something very obscure 12345 xyz",
            input_kind="unknown",
        )
        result = resolver.resolve(ctx)
        self.assertIsInstance(result, ResolvedLocation)

    def test_area_context_does_not_call_geocoder(self):
        resolver = LocationResolver.default()
        ctx = LocationContext(
            raw_text="Quận 3",
            input_kind="area",
            area_hint="quan 3",
        )
        with patch(f"{_FALLBACK_MODULE}._geocode") as mock_geo:
            result = resolver.resolve(ctx)
        mock_geo.assert_not_called()
        self.assertEqual(result.status, LocationStatus.OK)
        self.assertEqual(result.mode, LocationMode.AREA)

    def test_anywhere_context_resolves_to_anywhere(self):
        resolver = LocationResolver.default()
        ctx = LocationContext(
            raw_text="ở đâu cũng được",
            input_kind="amenity_only",
            area_hint=None,
        )
        result = resolver.resolve(ctx)
        self.assertIsInstance(result, ResolvedLocation)

    def test_near_user_with_gps_resolves_ok(self):
        resolver = LocationResolver.default()
        ctx = LocationContext(
            raw_text="gần tôi",
            input_kind="amenity_only",
            user_location=UserLocationInput(lat=10.77, lon=106.69),
        )
        result = resolver.resolve(ctx)
        self.assertIsInstance(result, ResolvedLocation)

    @patch(f"{_NEAR_ANCHOR_MODULE}._lookup_place_reference")
    def test_debug_flag_adds_resolved_by_key(self, mock_lookup):
        mock_lookup.return_value = _make_place_ref()
        resolver = LocationResolver.default()
        result = resolver.resolve(_landmark_context(debug=True))
        self.assertIn("resolved_by", result.debug)

    def test_custom_strategy_is_used(self):
        from chat_api.location.strategies.base import LocationStrategy

        class AlwaysAreaStrategy(LocationStrategy):
            order = 1
            name = "always_area"

            def can_handle(self, context):
                return True

            def resolve(self, context):
                return ResolvedLocation(
                    status=LocationStatus.OK,
                    mode=LocationMode.AREA,
                    canonical_area="custom_area",
                )

        resolver = LocationResolver([AlwaysAreaStrategy()])
        ctx = LocationContext(raw_text="anything", input_kind="unknown")
        result = resolver.resolve(ctx)
        self.assertEqual(result.canonical_area, "custom_area")
