"""
Basic tests for OpenStreetMap_API app.

These tests verify API endpoint routing and response structure
without making real external HTTP calls (services are mocked).
"""

from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse


class OSMAPIRoutingTest(TestCase):
    """Verify that all API URLs resolve correctly."""

    def setUp(self):
        self.client = Client()

    def test_poi_types_list_url(self):
        url = reverse('osm:poi_types_list')
        self.assertEqual(url, '/api/map/poi-types/')

    def test_geocode_url(self):
        url = reverse('osm:geocode')
        self.assertEqual(url, '/api/map/geocode/')

    def test_reverse_geocode_url(self):
        url = reverse('osm:reverse_geocode')
        self.assertEqual(url, '/api/map/reverse-geocode/')

    def test_accommodation_coordinates_url(self):
        url = reverse('osm:accommodation_coordinates', kwargs={'pk': 1})
        self.assertEqual(url, '/api/map/accommodation/1/coordinates/')

    def test_accommodation_map_data_url(self):
        url = reverse('osm:accommodation_map_data', kwargs={'pk': 1})
        self.assertEqual(url, '/api/map/accommodation/1/map-data/')

    def test_search_pois_url(self):
        url = reverse('osm:search_pois', kwargs={'pk': 1})
        self.assertEqual(url, '/api/map/accommodation/1/pois/')


class POITypesEndpointTest(TestCase):
    """Test the /api/map/poi-types/ endpoint."""

    def test_returns_json(self):
        resp = self.client.get('/api/map/poi-types/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('poi_types', data)
        self.assertIsInstance(data['poi_types'], list)
        # Must have at least one type
        self.assertGreater(len(data['poi_types']), 0)

    def test_poi_type_structure(self):
        resp = self.client.get('/api/map/poi-types/')
        data = resp.json()
        for pt in data['poi_types']:
            self.assertIn('key', pt)
            self.assertIn('label', pt)
            self.assertIn('icon', pt)
            self.assertIn('color', pt)


class GeocodeEndpointTest(TestCase):
    """Test the geocode utility endpoint."""

    def test_missing_q_param(self):
        resp = self.client.get('/api/map/geocode/')
        self.assertEqual(resp.status_code, 400)

    @patch('OpenStreetMap_API.services.geocode_address')
    def test_address_found(self, mock_geo):
        mock_geo.return_value = {
            'lat': 21.0285,
            'lon': 105.8542,
            'display_name': 'Hà Nội, Việt Nam',
        }
        resp = self.client.get('/api/map/geocode/?q=Ha+Noi')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('lat', data)
        self.assertIn('lon', data)

    @patch('OpenStreetMap_API.services.geocode_address')
    def test_address_not_found(self, mock_geo):
        mock_geo.return_value = None
        resp = self.client.get('/api/map/geocode/?q=XYZNOTEXIST')
        self.assertEqual(resp.status_code, 404)


class ReverseGeocodeEndpointTest(TestCase):
    """Test the reverse-geocode utility endpoint."""

    def test_missing_params(self):
        resp = self.client.get('/api/map/reverse-geocode/')
        self.assertEqual(resp.status_code, 400)

    def test_invalid_params(self):
        resp = self.client.get('/api/map/reverse-geocode/?lat=abc&lon=xyz')
        self.assertEqual(resp.status_code, 400)

    @patch('OpenStreetMap_API.services.reverse_geocode')
    def test_valid_coords(self, mock_rev):
        mock_rev.return_value = {
            'display_name': 'Hoàn Kiếm, Hà Nội',
            'address': {'city': 'Hà Nội'},
        }
        resp = self.client.get('/api/map/reverse-geocode/?lat=21.0285&lon=105.8542')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('display_name', data)
