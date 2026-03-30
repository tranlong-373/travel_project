from __future__ import annotations

from pydantic import BaseModel, Field


class LocationBias(BaseModel):
    latitude: float
    longitude: float
    radius_meters: float = Field(default=5000, gt=0, le=50000)


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class PlaceAutocompleteRequest(BaseModel):
    input: str = Field(min_length=2, max_length=200)
    session_token: str | None = None
    language_code: str = Field(default="vi", min_length=2, max_length=10)
    region_code: str | None = Field(default=None, min_length=2, max_length=2)
    include_query_predictions: bool = False
    location_bias: LocationBias | None = None


class PlaceTextSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    language_code: str = Field(default="vi", min_length=2, max_length=10)
    region_code: str | None = Field(default=None, min_length=2, max_length=2)
    page_size: int = Field(default=10, ge=1, le=20)
    location_bias: LocationBias | None = None


class PlaceSuggestion(BaseModel):
    place_id: str | None = None
    resource_name: str | None = None
    text: str
    main_text: str | None = None
    secondary_text: str | None = None
    types: list[str] = Field(default_factory=list)
    distance_meters: int | None = None
    is_query_prediction: bool = False


class PlaceAutocompleteResponse(BaseModel):
    suggestions: list[PlaceSuggestion] = Field(default_factory=list)


class PlaceSearchResult(BaseModel):
    place_id: str
    resource_name: str | None = None
    name: str | None = None
    formatted_address: str | None = None
    location: Coordinates | None = None
    types: list[str] = Field(default_factory=list)


class PlaceSearchResponse(BaseModel):
    results: list[PlaceSearchResult] = Field(default_factory=list)


class PlaceDetailsResponse(BaseModel):
    place_id: str | None = None
    resource_name: str | None = None
    name: str | None = None
    formatted_address: str | None = None
    location: Coordinates | None = None
    google_maps_uri: str | None = None
    types: list[str] = Field(default_factory=list)
