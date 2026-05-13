"""
Views (API endpoints) for OpenStreetMap_API.

All endpoints return JSON and are stateless.
They call services.py - never access DB models directly
(except to look up Accommodation by PK).
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404

from accommodations.models import Accommodation
from .constants import POI_TYPES, RADIUS_CHOICES, DEFAULT_RADIUS
from . import services


# -- 1. Accommodation coordinates --------------------------------------------

@require_GET
def accommodation_coordinates(request, pk):
    """
    GET /api/map/accommodation/<pk>/coordinates/

    Returns lat/lon and basic info for the given accommodation.
    """
    accommodation = get_object_or_404(Accommodation, pk=pk)
    data = services.get_accommodation_coordinates(accommodation)
    status = 200 if data.get("success") else 404
    return JsonResponse(data, status=status)


# -- 2. Map data (coordinates + POI type list) --------------------------------

@require_GET
def accommodation_map_data(request, pk):
    """
    GET /api/map/accommodation/<pk>/map-data/

    Returns full map initialisation payload:
    - Accommodation marker data
    - Available POI types for filter panel
    - Valid radius choices
    """
    accommodation = get_object_or_404(Accommodation, pk=pk)
    coord_data = services.get_accommodation_coordinates(accommodation)

    if not coord_data.get("success"):
        return JsonResponse(coord_data, status=404)

    return JsonResponse(
        {
            **coord_data,
            "poi_types": services.get_poi_types_metadata(),
            "radius_choices": RADIUS_CHOICES,
            "default_radius": DEFAULT_RADIUS,
        }
    )


# -- 3. POI search -----------------------------------------------------------

@require_GET
def search_pois(request, pk):
    """
    GET /api/map/accommodation/<pk>/pois/

    Query params:
        radius  - int, metres (default 1000, max 5000)
        types   - comma-separated list of POI type keys
                  e.g. ?types=restaurant,cafe,hospital

    Returns list of POI objects sorted by distance.
    """
    accommodation = get_object_or_404(Accommodation, pk=pk)
    coord_data = services.get_accommodation_coordinates(accommodation)

    if not coord_data.get("success"):
        return JsonResponse({"success": False, "error": coord_data.get("error", "")}, status=404)

    # Parse radius
    try:
        radius = int(request.GET.get("radius", DEFAULT_RADIUS))
    except (TypeError, ValueError):
        radius = DEFAULT_RADIUS

    # Parse types filter
    types_param = request.GET.get("types", "").strip()
    if types_param:
        requested_types = [t.strip() for t in types_param.split(",") if t.strip()]
        poi_types = [t for t in requested_types if t in POI_TYPES]
        if not poi_types:
            poi_types = None
    else:
        poi_types = None

    pois = services.search_pois(
        lat=coord_data["lat"],
        lon=coord_data["lon"],
        radius=radius,
        poi_types=poi_types,
    )

    return JsonResponse(
        {
            "success": True,
            "accommodation_id": pk,
            "center": {"lat": coord_data["lat"], "lon": coord_data["lon"]},
            "radius": radius,
            "count": len(pois),
            "pois": pois,
        }
    )


# -- 4. POI types metadata ---------------------------------------------------

@require_GET
def poi_types_list(request):
    """
    GET /api/map/poi-types/

    Returns the full list of supported POI types with label, icon, color.
    Useful for building filter UIs in other modules.
    """
    return JsonResponse({"poi_types": services.get_poi_types_metadata()})


# -- 5. Geocode (utility, reusable by other modules) -------------------------

@require_GET
def geocode(request):
    """
    GET /api/map/geocode/?q=<address>

    Returns {lat, lon, display_name} or 404.
    """
    address = request.GET.get("q", "").strip()
    if not address:
        return JsonResponse({"error": "Missing parameter: q"}, status=400)

    result = services.geocode_address(address)
    if result:
        return JsonResponse({"success": True, **result})
    return JsonResponse({"success": False, "error": "Address not found."}, status=404)


# -- 6. Reverse geocode ------------------------------------------------------

@require_GET
def reverse_geocode(request):
    """
    GET /api/map/reverse-geocode/?lat=<lat>&lon=<lon>

    Returns address info for the given coordinates.
    """
    try:
        lat = float(request.GET.get("lat"))
        lon = float(request.GET.get("lon"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid or missing lat/lon parameters."}, status=400)

    result = services.reverse_geocode(lat, lon)
    if result:
        return JsonResponse({"success": True, **result})
    return JsonResponse({"success": False, "error": "Location not found."}, status=404)
