"""URL configuration for OpenStreetMap_API app."""

from django.urls import path
from . import views

app_name = "osm"

urlpatterns = [
    # Accommodation map data endpoints
    path(
        "accommodation/<int:pk>/coordinates/",
        views.accommodation_coordinates,
        name="accommodation_coordinates",
    ),
    path(
        "accommodation/<int:pk>/map-data/",
        views.accommodation_map_data,
        name="accommodation_map_data",
    ),
    path(
        "accommodation/<int:pk>/pois/",
        views.search_pois,
        name="search_pois",
    ),
    # Generic utilities
    path("poi-types/", views.poi_types_list, name="poi_types_list"),
    path("geocode/", views.geocode, name="geocode"),
    path("reverse-geocode/", views.reverse_geocode, name="reverse_geocode"),
]
