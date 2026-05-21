"""
Circuit breaker for the PlaceReference / cache database.

The geocoder calls DB-backed cache lookups (place_reference, place_cache,
fuzzy/semantic search) before reaching the external geocoder.  When the
configured DB is unreachable (e.g. MSSQL server not running), each lookup
takes the full driver login-timeout (~15 s) before raising, multiplied
across 3-4 lookups per request — geocode_place ends up taking 45-60 s
just to discover the DB is down.

This module probes the connection once, caches the result for a TTL, and
exposes `is_geocoder_db_available()` so DB-dependent paths can fail fast
when the server is offline.  The probe itself runs in a thread with a
short timeout so it never blocks longer than DB_HEALTH_PROBE_TIMEOUT_SECONDS.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_AVAILABLE: bool | None = None
_EXPIRES_AT: float = 0.0


def _probe_timeout() -> float:
    try:
        return float(os.getenv("DB_HEALTH_PROBE_TIMEOUT_SECONDS", "1.5"))
    except (TypeError, ValueError):
        return 1.5


def _probe_ttl() -> float:
    try:
        return float(os.getenv("DB_HEALTH_PROBE_TTL_SECONDS", "60"))
    except (TypeError, ValueError):
        return 60.0


def _do_probe() -> bool:
    from django.db import connection

    try:
        connection.close()  # drop any half-broken connection
        connection.ensure_connection()
        return True
    except Exception as exc:
        logger.warning("db_health: DB unavailable — %s", exc)
        return False


def is_geocoder_db_available() -> bool:
    """Return True if the geocoder's DB is reachable, False otherwise.

    Result is cached for DB_HEALTH_PROBE_TTL_SECONDS so we don't probe on
    every call.  The probe itself runs in a worker thread with a short
    DB_HEALTH_PROBE_TIMEOUT_SECONDS guard so it never stalls the caller.
    """
    global _AVAILABLE, _EXPIRES_AT
    now = time.monotonic()
    if _AVAILABLE is not None and now < _EXPIRES_AT:
        return _AVAILABLE
    with _LOCK:
        now = time.monotonic()
        if _AVAILABLE is not None and now < _EXPIRES_AT:
            return _AVAILABLE
        timeout = _probe_timeout()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_do_probe)
        try:
            _AVAILABLE = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("db_health: probe timed out after %.1fs — assuming DB down", timeout)
            _AVAILABLE = False
        finally:
            executor.shutdown(wait=False)
        _EXPIRES_AT = now + _probe_ttl()
        return _AVAILABLE


def reset_health_cache() -> None:
    """Force the next call to re-probe.  Useful in tests."""
    global _AVAILABLE, _EXPIRES_AT
    with _LOCK:
        _AVAILABLE = None
        _EXPIRES_AT = 0.0
