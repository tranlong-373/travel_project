from __future__ import annotations

from typing import Any

import httpx

from app.core.settings import get_settings

AUTOCOMPLETE_FIELD_MASK = ",".join(
    [
        "suggestions.placePrediction.place",
        "suggestions.placePrediction.placeId",
        "suggestions.placePrediction.text.text",
        "suggestions.placePrediction.structuredFormat.mainText.text",
        "suggestions.placePrediction.structuredFormat.secondaryText.text",
        "suggestions.placePrediction.types",
        "suggestions.placePrediction.distanceMeters",
        "suggestions.queryPrediction.text.text",
    ]
)

TEXT_SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.name",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
    ]
)

PLACE_DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "name",
        "displayName",
        "formattedAddress",
        "location",
        "googleMapsUri",
        "types",
    ]
)


class GooglePlacesError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GooglePlacesClient:
    base_url = "https://places.googleapis.com/v1"

    async def autocomplete(
        self,
        *,
        input_text: str,
        session_token: str | None,
        language_code: str,
        region_code: str | None,
        location_bias: dict[str, Any] | None,
        include_query_predictions: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input": input_text,
            "languageCode": language_code,
            "includeQueryPredictions": include_query_predictions,
        }

        if session_token:
            payload["sessionToken"] = session_token

        if region_code:
            payload["regionCode"] = region_code

        if location_bias:
            payload["locationBias"] = location_bias

        return await self._post(
            path="/places:autocomplete",
            payload=payload,
            field_mask=AUTOCOMPLETE_FIELD_MASK,
        )

    async def search_text(
        self,
        *,
        query: str,
        page_size: int,
        language_code: str,
        region_code: str | None,
        location_bias: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "textQuery": query,
            "pageSize": page_size,
            "languageCode": language_code,
        }

        if region_code:
            payload["regionCode"] = region_code

        if location_bias:
            payload["locationBias"] = location_bias

        return await self._post(
            path="/places:searchText",
            payload=payload,
            field_mask=TEXT_SEARCH_FIELD_MASK,
        )

    async def get_place_details(
        self,
        *,
        place_id: str,
        session_token: str | None,
        language_code: str,
        region_code: str | None,
    ) -> dict[str, Any]:
        normalized_place_id = place_id.removeprefix("places/")
        params: dict[str, Any] = {"languageCode": language_code}

        if session_token:
            params["sessionToken"] = session_token

        if region_code:
            params["regionCode"] = region_code

        return await self._get(
            path=f"/places/{normalized_place_id}",
            params=params,
            field_mask=PLACE_DETAILS_FIELD_MASK,
        )

    async def _post(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        field_mask: str,
    ) -> dict[str, Any]:
        settings = get_settings()
        api_key = self._require_api_key(settings.google_places_api_key)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.google_places_timeout_seconds,
        ) as client:
            try:
                response = await client.post(path, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GooglePlacesError(
                    exc.response.status_code,
                    self._extract_error_message(exc.response),
                ) from exc
            except httpx.HTTPError as exc:
                raise GooglePlacesError(502, f"Google Places request failed: {exc}") from exc

        return response.json()

    async def _get(
        self,
        *,
        path: str,
        params: dict[str, Any],
        field_mask: str,
    ) -> dict[str, Any]:
        settings = get_settings()
        api_key = self._require_api_key(settings.google_places_api_key)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.google_places_timeout_seconds,
        ) as client:
            try:
                response = await client.get(path, params=params, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GooglePlacesError(
                    exc.response.status_code,
                    self._extract_error_message(exc.response),
                ) from exc
            except httpx.HTTPError as exc:
                raise GooglePlacesError(502, f"Google Places request failed: {exc}") from exc

        return response.json()

    @staticmethod
    def _require_api_key(api_key: str | None) -> str:
        if not api_key:
            raise GooglePlacesError(
                500,
                "Missing GOOGLE_PLACES_API_KEY in environment variables.",
            )

        return api_key

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text

        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])

        return response.text
