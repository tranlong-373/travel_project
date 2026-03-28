from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.integrations.google_places import GooglePlacesClient, GooglePlacesError
from app.schemas.place import (
    Coordinates,
    LocationBias,
    PlaceAutocompleteRequest,
    PlaceAutocompleteResponse,
    PlaceDetailsResponse,
    PlaceSearchResponse,
    PlaceSearchResult,
    PlaceSuggestion,
    PlaceTextSearchRequest,
)


class PlaceService:
    def __init__(self, client: GooglePlacesClient) -> None:
        self.client = client

    async def autocomplete(
        self,
        request: PlaceAutocompleteRequest,
    ) -> PlaceAutocompleteResponse:
        response = await self._handle_client_error(
            self.client.autocomplete(
                input_text=request.input,
                session_token=request.session_token,
                language_code=request.language_code,
                region_code=request.region_code,
                location_bias=self._build_location_bias(request.location_bias),
                include_query_predictions=request.include_query_predictions,
            )
        )

        suggestions: list[PlaceSuggestion] = []
        for item in response.get("suggestions", []):
            place_prediction = item.get("placePrediction")
            if place_prediction:
                suggestions.append(
                    PlaceSuggestion(
                        place_id=place_prediction.get("placeId"),
                        resource_name=place_prediction.get("place"),
                        text=place_prediction.get("text", {}).get("text", ""),
                        main_text=place_prediction.get("structuredFormat", {})
                        .get("mainText", {})
                        .get("text"),
                        secondary_text=place_prediction.get("structuredFormat", {})
                        .get("secondaryText", {})
                        .get("text"),
                        types=place_prediction.get("types", []),
                        distance_meters=place_prediction.get("distanceMeters"),
                    )
                )
                continue

            query_prediction = item.get("queryPrediction")
            if query_prediction:
                suggestions.append(
                    PlaceSuggestion(
                        text=query_prediction.get("text", {}).get("text", ""),
                        is_query_prediction=True,
                    )
                )

        return PlaceAutocompleteResponse(suggestions=suggestions)

    async def search_text(
        self,
        request: PlaceTextSearchRequest,
    ) -> PlaceSearchResponse:
        response = await self._handle_client_error(
            self.client.search_text(
                query=request.query,
                page_size=request.page_size,
                language_code=request.language_code,
                region_code=request.region_code,
                location_bias=self._build_location_bias(request.location_bias),
            )
        )

        results = [
            PlaceSearchResult(
                place_id=place["id"],
                resource_name=place.get("name"),
                name=place.get("displayName", {}).get("text"),
                formatted_address=place.get("formattedAddress"),
                location=self._to_coordinates(place.get("location")),
                types=place.get("types", []),
            )
            for place in response.get("places", [])
            if place.get("id")
        ]

        return PlaceSearchResponse(results=results)

    async def get_place_details(
        self,
        *,
        place_id: str,
        session_token: str | None,
        language_code: str,
        region_code: str | None,
    ) -> PlaceDetailsResponse:
        place = await self._handle_client_error(
            self.client.get_place_details(
                place_id=place_id,
                session_token=session_token,
                language_code=language_code,
                region_code=region_code,
            )
        )

        return PlaceDetailsResponse(
            place_id=place.get("id"),
            resource_name=place.get("name"),
            name=place.get("displayName", {}).get("text"),
            formatted_address=place.get("formattedAddress"),
            location=self._to_coordinates(place.get("location")),
            google_maps_uri=place.get("googleMapsUri"),
            types=place.get("types", []),
        )

    @staticmethod
    def _build_location_bias(
        location_bias: LocationBias | None,
    ) -> dict[str, Any] | None:
        if location_bias is None:
            return None

        return {
            "circle": {
                "center": {
                    "latitude": location_bias.latitude,
                    "longitude": location_bias.longitude,
                },
                "radius": location_bias.radius_meters,
            }
        }

    @staticmethod
    def _to_coordinates(location: dict[str, Any] | None) -> Coordinates | None:
        if not location:
            return None

        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            return None

        return Coordinates(latitude=latitude, longitude=longitude)

    @staticmethod
    async def _handle_client_error(coroutine: Any) -> dict[str, Any]:
        try:
            return await coroutine
        except GooglePlacesError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
