from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accommodations.models import Accommodation
from chat_api.recommendation_bridge import create_preference_from_parse
from chat_api.services import parse_user_text
from preferences.models import UserPreference
from .services import calculate_matching_score, get_candidate_accommodations


class SoftFilterRecommendationTests(TestCase):
    def _accommodation(
        self,
        name: str,
        *,
        price: int,
        capacity: int = 2,
        amenities: list[str] | None = None,
        area: str = "Quận 1",
        accommodation_type: str = "hotel",
        lat: float = 10.7798,
        lon: float = 106.6990,
        rating: float = 4.2,
    ) -> Accommodation:
        return Accommodation.objects.create(
            name=name,
            accommodation_type=accommodation_type,
            area=area,
            address=f"{name} address",
            price_per_night=price,
            capacity=capacity,
            rating=rating,
            review_count=10,
            amenities=amenities or [],
            latitude=lat,
            longitude=lon,
        )

    def _preference_from_text(self, text: str):
        parsed = parse_user_text(text)
        bridge_result = create_preference_from_parse(parsed)
        return parsed, bridge_result["pref_id"]

    def test_budget_only_recommendation_runs_without_area(self):
        cheap = self._accommodation("Budget stay", price=900_000, capacity=1)
        self._accommodation("Premium stay", price=1_600_000, capacity=1)

        parsed, pref_id = self._preference_from_text("dưới 1 triệu")
        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertTrue(parsed["can_show_recommendations"])
        self.assertIsNone(preference.area)
        self.assertIn(cheap, candidates)
        self.assertTrue(all(item.price_per_night <= 1_000_000 for item in candidates))

    def test_guest_count_only_recommendation_filters_capacity(self):
        small = self._accommodation("Small room", price=700_000, capacity=1)
        large = self._accommodation("Large room", price=900_000, capacity=2)

        _, pref_id = self._preference_from_text("cho 2 người")

        candidates = get_candidate_accommodations(UserPreference.objects.get(pk=pref_id))

        self.assertIn(large, candidates)
        self.assertNotIn(small, candidates)

    def test_amenity_only_recommendation_prioritizes_matching_amenity(self):
        pool = self._accommodation("Pool hotel", price=1_200_000, amenities=["pool", "wifi"])
        no_pool = self._accommodation("Plain hotel", price=800_000, amenities=["wifi"])

        _, pref_id = self._preference_from_text("có hồ bơi")

        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)
        scores = {item.name: calculate_matching_score(item, preference) for item in [pool, no_pool]}

        self.assertEqual(candidates, [pool])
        self.assertGreater(scores["Pool hotel"], scores["Plain hotel"])

    def test_near_landmark_recommendation_uses_distance(self):
        near = self._accommodation("Near Notre Dame", price=900_000, lat=10.7799, lon=106.6992)
        far = self._accommodation("Far stay", price=800_000, lat=10.9000, lon=106.9000)

        _, pref_id = self._preference_from_text("gần nhà thờ Đức Bà")

        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertEqual(preference.location_mode, "near_anchor")
        self.assertIn(near, candidates)
        self.assertNotIn(far, candidates)
        matched_near = next(item for item in candidates if item.pk == near.pk)
        self.assertLess(matched_near.distance_km, 1)

    def test_unseeded_tourist_anchor_recommendation_uses_distance(self):
        near = self._accommodation("Cu Chi nearby stay", price=900_000, lat=11.1450, lon=106.4640)
        far = self._accommodation("Central stay", price=800_000, lat=10.7799, lon=106.6992)
        preference = UserPreference.objects.create(
            area="gần Địa đạo Củ Chi",
            budget=0,
            guest_count=1,
            location_mode="near_anchor",
            location_label="gần Địa đạo Củ Chi",
            user_latitude=11.1419,
            user_longitude=106.4625,
            search_radius_km=8.0,
        )

        candidates = get_candidate_accommodations(preference)

        self.assertEqual(candidates[0], near)
        self.assertIn(near, candidates)
        self.assertNotIn(far, candidates)
        self.assertLess(candidates[0].distance_km, 1)

    def test_near_anchor_without_coordinates_returns_no_candidates(self):
        self._accommodation("Any stay", price=900_000, lat=10.7799, lon=106.6992)
        preference = UserPreference.objects.create(
            area="gần địa điểm mơ hồ",
            budget=0,
            guest_count=1,
            location_mode="near_anchor",
            location_label="gần địa điểm mơ hồ",
            search_radius_km=5.0,
        )

        candidates = get_candidate_accommodations(preference)

        self.assertEqual(candidates, [])

    def test_near_anchor_does_not_relax_radius_when_near_result_exists(self):
        near = self._accommodation(
            "Inside radius",
            price=900_000,
            lat=10.7799,
            lon=106.6992,
        )
        outside_original_radius = self._accommodation(
            "Outside radius",
            price=900_000,
            lat=10.8200,
            lon=106.6990,
        )

        _, pref_id = self._preference_from_text("gần nhà thờ Đức Bà")

        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertIn(near, candidates)
        self.assertNotIn(outside_original_radius, candidates)
        self.assertFalse(preference.relaxed)
        self.assertNotIn("radius", preference.relaxed_filters)

    def test_near_anchor_relaxes_radius_only_when_strict_radius_empty(self):
        fallback = self._accommodation(
            "Fallback radius stay",
            price=900_000,
            lat=10.8200,
            lon=106.6990,
        )

        _, pref_id = self._preference_from_text("gần nhà thờ Đức Bà")

        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertIn(fallback, candidates)
        self.assertTrue(preference.relaxed)
        self.assertIn("radius", preference.relaxed_filters)
        self.assertGreater(preference.used_radius_km, 2.5)
        self.assertIn("km", preference.relaxation_message)

    @patch("chat_api.services.geocoder.geocode_place")
    def test_geocode_accommodations_command_saves_missing_coordinates(self, mock_geocode_place):
        accommodation = Accommodation.objects.create(
            name="Uncached stay",
            accommodation_type="hotel",
            area="Quận 1",
            address="1 Nguyễn Huệ",
            price_per_night=900_000,
            capacity=2,
            rating=4.2,
            review_count=10,
            amenities=[],
        )
        mock_geocode_place.return_value = SimpleNamespace(
            success=True,
            latitude=10.7732,
            longitude=106.7032,
            source="osm",
            display_name="1 Nguyễn Huệ, Quận 1, Thành phố Hồ Chí Minh",
        )

        call_command("geocode_accommodations", limit=1, sleep=0)

        accommodation.refresh_from_db()

        self.assertEqual(accommodation.latitude, 10.7732)
        self.assertEqual(accommodation.longitude, 106.7032)
        mock_geocode_place.assert_called_once()

    @patch("chat_api.services.geocoder.geocode_place")
    def test_missing_accommodation_coordinates_are_skipped_at_request_time(self, mock_geocode_place):
        accommodation = Accommodation.objects.create(
            name="Uncached stay",
            accommodation_type="hotel",
            area="Quận 1",
            address="1 Nguyễn Huệ",
            price_per_night=900_000,
            capacity=2,
            rating=4.2,
            review_count=10,
            amenities=[],
        )

        preference = UserPreference.objects.create(
            area="gần Phố đi bộ Nguyễn Huệ",
            budget=0,
            guest_count=1,
            location_mode="near_anchor",
            location_label="gần Phố đi bộ Nguyễn Huệ",
            user_latitude=10.7731,
            user_longitude=106.7031,
            search_radius_km=3.0,
        )

        candidates = get_candidate_accommodations(preference)
        accommodation.refresh_from_db()

        self.assertNotIn(accommodation, candidates)
        self.assertIsNone(accommodation.latitude)
        self.assertIsNone(accommodation.longitude)
        mock_geocode_place.assert_not_called()

    def test_no_result_relaxation_marks_relaxed_filters(self):
        fallback = self._accommodation(
            "Almost matching stay",
            price=220_000,
            capacity=2,
            amenities=["wifi"],
            lat=10.7799,
            lon=106.6991,
        )

        _, pref_id = self._preference_from_text("villa có hồ bơi riêng dưới 200 nghìn gần nhà thờ Đức Bà")

        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertIn(fallback, candidates)
        self.assertTrue(preference.relaxed)
        self.assertIn("amenities", preference.relaxed_filters)
        self.assertIn("budget", preference.relaxed_filters)

    def test_multi_type_preference_filters_with_or(self):
        homestay = self._accommodation("Local homestay", price=900_000, accommodation_type="homestay")
        hostel = self._accommodation("Friendly hostel", price=700_000, accommodation_type="hostel")
        hotel = self._accommodation("Business hotel", price=900_000, accommodation_type="hotel")

        _, pref_id = self._preference_from_text("Homestay, trọ")
        preference = UserPreference.objects.get(pk=pref_id)
        candidates = get_candidate_accommodations(preference)

        self.assertIn(homestay, candidates)
        self.assertIn(hostel, candidates)
        self.assertNotIn(hotel, candidates)

    def test_recommendation_result_page_paginates_and_prefills_chatbot_filters(self):
        for index in range(12):
            self._accommodation(
                f"Hotel {index}",
                price=2_500_000 + index,
                accommodation_type="hotel",
                amenities=["wifi"],
            )

        _, pref_id = self._preference_from_text("khách sạn ở đâu cũng được giá tầm 2 đến 5 triệu")
        response = self.client.get(reverse("recommendation_result", kwargs={"pref_id": pref_id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_results"], 12)
        self.assertEqual(response.context["page_size"], 10)
        self.assertEqual(len(response.context["results"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertIn("hotel", response.context["current_types"])
        self.assertEqual(response.context["current_budget_min"], 2_000_000)
        self.assertEqual(response.context["current_budget_max"], 5_000_000)

    def test_recommendation_result_page_can_apply_multi_type_filter(self):
        hotel = self._accommodation("Hotel stay", price=900_000, accommodation_type="hotel")
        homestay = self._accommodation("Homestay stay", price=900_000, accommodation_type="homestay")
        hostel = self._accommodation("Hostel stay", price=900_000, accommodation_type="hostel")

        _, pref_id = self._preference_from_text("ở đâu cũng được dưới 5 triệu")
        response = self.client.get(
            reverse("recommendation_result", kwargs={"pref_id": pref_id}),
            {"filters": "1", "type": ["homestay", "hostel"]},
        )
        names = [item.name for item, _score in response.context["results"]]

        self.assertNotIn(hotel.name, names)
        self.assertIn(homestay.name, names)
        self.assertIn(hostel.name, names)
        self.assertEqual(response.context["current_types"], ["homestay", "hostel"])
