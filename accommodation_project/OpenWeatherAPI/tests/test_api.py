import json
import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from OpenWeatherAPI.services.openweather_service import get_weather
from OpenWeatherAPI.utils.formatter import format_weather


class OpenWeatherFormatterTests(SimpleTestCase):
    def test_format_weather_maps_expected_fields(self):
        sample = {
            "name": "Hanoi",
            "main": {"temp": 28.5, "humidity": 72},
            "weather": [{"description": "few clouds"}],
        }
        formatted = format_weather(sample)
        self.assertEqual(formatted["city"], "Hanoi")
        self.assertEqual(formatted["temperature"], 28.5)
        self.assertEqual(formatted["description"], "few clouds")
        self.assertEqual(formatted["humidity"], 72)


@override_settings(ROOT_URLCONF="OpenWeatherAPI.tests.urls_for_tests")
class OpenWeatherHTTPTests(SimpleTestCase):
    @patch.dict(os.environ, {"OPENWEATHER_API_KEY": "test-key"}, clear=False)
    @patch("OpenWeatherAPI.services.openweather_service.requests.Session.get")
    def test_get_weather_contains_city_and_temperature(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Ho Chi Minh City",
            "main": {"temp": 30.0, "humidity": 65},
            "weather": [{"description": "clear sky"}],
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        data = get_weather("Ho Chi Minh")
        print("get_weather sample output:", json.dumps(data, ensure_ascii=False))

        self.assertIn("city", data)
        self.assertIn("temperature", data)
        self.assertEqual(data["city"], "Ho Chi Minh City")
        self.assertIsNotNone(data["temperature"])

    @patch.dict(os.environ, {"OPENWEATHER_API_KEY": "test-key"}, clear=False)
    @patch("OpenWeatherAPI.services.openweather_service.requests.Session.get")
    def test_weather_endpoint_returns_json(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Hanoi",
            "main": {"temp": 22.0, "humidity": 80},
            "weather": [{"description": "light rain"}],
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        response = self.client.get("/api/weather/", {"city": "Hanoi"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        print("API /api/weather/ sample output:", json.dumps(body, ensure_ascii=False))
        self.assertIn("temperature", body)
        self.assertIn("city", body)
