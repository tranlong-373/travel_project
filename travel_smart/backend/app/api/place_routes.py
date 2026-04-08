from __future__ import annotations

from fastapi import APIRouter, Query

from app.integrations.google_places import GooglePlacesClient
from app.schemas.place import (
    PlaceAutocompleteRequest,
    PlaceAutocompleteResponse,
    PlaceDetailsResponse,
    PlaceSearchResponse,
    PlaceTextSearchRequest,
)
from app.services.place_service import PlaceService

router = APIRouter(prefix="/api/v1/places", tags=["places"])
place_service = PlaceService(GooglePlacesClient())


@router.post("/autocomplete", response_model=PlaceAutocompleteResponse)
async def autocomplete_places(
    request: PlaceAutocompleteRequest,
) -> PlaceAutocompleteResponse:
    return await place_service.autocomplete(request)


@router.post("/search", response_model=PlaceSearchResponse)
async def search_places(
    request: PlaceTextSearchRequest,
) -> PlaceSearchResponse:
    return await place_service.search_text(request)


@router.get("/{place_id}", response_model=PlaceDetailsResponse)
async def get_place_details(
    place_id: str,
    session_token: str | None = Query(default=None),
    language_code: str = Query(default="vi"),
    region_code: str | None = Query(default=None),
) -> PlaceDetailsResponse:
    return await place_service.get_place_details(
        place_id=place_id,
        session_token=session_token,
        language_code=language_code,
        region_code=region_code,
    )
