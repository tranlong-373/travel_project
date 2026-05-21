"""
FallbackGeocodeStrategy — external geocoder (Nominatim/OSM) as last-resort resolution.

Fires only when NearAnchorFromPlaceReferenceStrategy missed (cache miss).

Design:
  - Rate-limit guard is enforced inside nominatim_geocoder._wait_for_rate_limit().
  - Timeout guard: geocoder call runs in a thread with GEOCODE_TIMEOUT seconds.
    If it hangs, the future is cancelled and None is returned (no crash).
  - specific_address: full query is passed as-is — not shortened to district.
  - landmark_or_poi: location_phrase is passed as-is.
  - On any exception: logs warning, returns None (does not propagate).

Timeout budget:
  Nominatim enforces 1 req/sec and builds up to 4 queries per phrase.
  Worst case: 3s rate-limit sleep + 4 × HTTP latency + 1s outer rate-limit
  guard ≈ 6–10 s on a normal network.  GEOCODE_TIMEOUT defaults to 15 s to
  give comfortable headroom; override with FALLBACK_GEOCODE_TIMEOUT_SECONDS.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)

_HANDLED_KINDS: frozenset[str] = frozenset({
    "landmark_or_poi",
    "specific_address",
})


def _geocode_timeout() -> float:
    try:
        return float(os.getenv("FALLBACK_GEOCODE_TIMEOUT_SECONDS", "15"))
    except (TypeError, ValueError):
        return 15.0


def _geocode(phrase: str) -> tuple[float, float] | None:
    """
    Call the geocoder and return (lat, lon) or None.
    Wrapped for testability — patch this function in tests.
    Rate limit and caching are handled inside geocode_street_address().
    """
    try:
        from ...nominatim_geocoder import geocode_street_address
        return geocode_street_address(phrase)
    except Exception as exc:
        logger.warning("fallback_geocode: geocoder raised for %r: %s", phrase, exc)
        return None


class FallbackGeocodeStrategy(LocationStrategy):
    order = 60
    name = "fallback_geocode"

    def can_handle(self, context: LocationContext) -> bool:
        return (
            context.input_kind in _HANDLED_KINDS
            and bool(context.location_phrase)
        )

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        # specific_address: keep full query — never truncate to district
        # landmark_or_poi:  location_phrase already stripped of near-cue
        # Prefer the accented (raw) phrase so Nominatim can match Vietnamese
        # streets/POIs accurately.  Fall back to normalized form when raw is
        # unavailable (e.g. context built without classifier output).
        query = context.location_phrase_raw or context.location_phrase
        if not query:
            return None

        timeout = _geocode_timeout()
        logger.debug(
            "fallback_geocode: geocoding %r (kind=%s, timeout=%.1fs)",
            query, context.input_kind, timeout,
        )

        # Run geocoder with timeout guard
        coords: tuple[float, float] | None = None
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_geocode, query)
                try:
                    coords = future.result(timeout=timeout)
                except FuturesTimeout:
                    elapsed = time.monotonic() - started
                    logger.warning(
                        "fallback_geocode: timed out after %.1fs for %r — "
                        "increase FALLBACK_GEOCODE_TIMEOUT_SECONDS (current=%.0f)",
                        elapsed, query, timeout,
                    )
                    future.cancel()
        except Exception as exc:
            logger.warning("fallback_geocode: executor error for %r: %s", query, exc)

        if coords is None:
            elapsed = time.monotonic() - started
            logger.info(
                "fallback_geocode: no coordinates for %r (kind=%s, elapsed=%.2fs)",
                query, context.input_kind, elapsed,
            )
            return None

        lat, lon = coords
        return ResolvedLocation(
            status=LocationStatus.GEOCODED,
            mode=LocationMode.NEAR_ANCHOR,
            raw_phrase=query,
            display_label=query,
            anchor_name=query,
            anchor_kind="geocoded",
            latitude=lat,
            longitude=lon,
            radius_km=5.0,
            provider="nominatim",
            cache_hit=False,
            debug={"query": query, "source": "external_geocoder"},
        )
