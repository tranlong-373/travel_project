from __future__ import annotations

import time
from typing import Any

import requests
from django.core.management.base import BaseCommand

from chat_api.services.place_cache import save_place_cache
from chat_api.services.place_reference import generate_place_aliases, normalize_place_text


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "travel-project-hcm-poi-import/1.0"
# Overpass is used only by this offline import/cache command, never during chat requests.
OVERPASS_QUERY = """
[out:json][timeout:30];
area["name"~"Thành phố Hồ Chí Minh|Ho Chi Minh", i]["admin_level"~"4|6"]->.hcm;
(
  nwr(area.hcm)["tourism"="attraction"];
  nwr(area.hcm)["tourism"="museum"];
  nwr(area.hcm)["tourism"="theme_park"];
  nwr(area.hcm)["tourism"="artwork"];
  nwr(area.hcm)["historic"];
  nwr(area.hcm)["leisure"="park"];
  nwr(area.hcm)["leisure"="water_park"];
  nwr(area.hcm)["amenity"="marketplace"];
  nwr(area.hcm)["amenity"="theatre"];
  nwr(area.hcm)["amenity"="arts_centre"];
  nwr(area.hcm)["shop"="mall"];
);
out center tags;
""".strip()


class Command(BaseCommand):
    help = "Import Ho Chi Minh City POIs from OpenStreetMap Overpass into PlaceReference."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=OVERPASS_URL)
        parser.add_argument("--timeout", type=int, default=45)
        parser.add_argument("--retries", type=int, default=2)

    def handle(self, *args, **options):
        try:
            payload = self._fetch(options["url"], timeout=options["timeout"], retries=options["retries"])
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"Overpass import skipped: {exc}")
            return

        imported = 0
        skipped = 0
        for element in payload.get("elements") or []:
            candidate = self._candidate_from_element(element)
            if not candidate:
                skipped += 1
                continue
            saved = save_place_cache(candidate["name"], candidate)
            if saved:
                imported += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} HCM POIs; skipped {skipped}."))

    def _fetch(self, url: str, *, timeout: int, retries: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(max(retries, 0) + 1):
            try:
                response = requests.post(
                    url,
                    data={"data": OVERPASS_QUERY},
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < retries:
                    time.sleep(1 + attempt)
        raise last_error or RuntimeError("unknown Overpass error")

    def _candidate_from_element(self, element: dict[str, Any]) -> dict[str, Any] | None:
        tags = element.get("tags") or {}
        name = tags.get("name") or tags.get("name:vi") or tags.get("name:en")
        if not name:
            return None
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if lat is None or lon is None:
            return None
        kind = _kind_from_tags(tags)
        aliases = generate_place_aliases(name)
        aliases.extend(generate_place_aliases(normalize_place_text(name)))
        return {
            "name": name,
            "canonical_name": name,
            "display_name": tags.get("addr:full") or name,
            "aliases": sorted({alias for alias in aliases if alias}),
            "lat": lat,
            "lon": lon,
            "address": {
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
                **{key: value for key, value in tags.items() if key.startswith("addr:")},
            },
            "district": tags.get("addr:district") or tags.get("addr:suburb") or "",
            "city": "Thành phố Hồ Chí Minh",
            "country": "Việt Nam",
            "kind": kind,
            "provider": "osm_overpass",
            "provider_place_id": f"{element.get('type', 'nwr')}:{element.get('id', '')}",
            "confidence": 0.9,
            "source": "osm_overpass",
            "raw_payload": element,
        }


def _kind_from_tags(tags: dict[str, Any]) -> str:
    for key in ("tourism", "historic", "leisure", "amenity", "shop"):
        value = tags.get(key)
        if value:
            return str(value)
    return "poi"
