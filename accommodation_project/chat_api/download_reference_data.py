from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"

WIKIDATA_TERMS = [
    "Ho Chi Minh City",
    "Hanoi",
    "Thanh Hóa",
    "Đồng Nai",
    "An Giang",
    "Bình Định",
    "Landmark 81",
    "Bến Thành Market",
    "Old Quarter Hanoi",
    "Hoàn Kiếm Lake",
    "Nội Bài International Airport",
    "Tân Sơn Nhất International Airport",
]

GEONAMES_ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """
[out:json][timeout:25];
area["ISO3166-1"="VN"][admin_level=2]->.vn;
(
  nwr(area.vn)["name"~"Landmark 81|Bến Thành|Ben Thanh|Old Quarter|Hoàn Kiếm|Hoan Kiem|Nội Bài|Noi Bai|Tân Sơn Nhất|Tan Son Nhat|Sầm Sơn|Sam Son|Bửu Long|Buu Long|Núi Cấm|Nui Cam|Eo Gió|Eo Gio", i];
);
out center tags 50;
""".strip()


def _download_text(url: str, *, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "chat-api-location-builder/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _download_wikidata_search(term: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": "5",
            "search": term,
        }
    )
    return json.loads(_download_text(f"{WIKIDATA_SEARCH_URL}?{query}"))


def _download_overpass_landmarks() -> dict:
    payload = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=payload,
        headers={
            "User-Agent": "chat-api-location-builder/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    geonames_raw = _download_text(GEONAMES_ADMIN1_URL)
    wanted_names = ("Ho Chi Minh", "Hanoi", "Thanh Hoa", "Dong Nai", "An Giang", "Binh Dinh")
    filtered_lines = [
        line
        for line in geonames_raw.splitlines()
        if line.startswith("VN.") and any(name.lower() in line.lower() for name in wanted_names)
    ]
    (RAW_DIR / "geonames_admin1_vn_supported.txt").write_text("\n".join(filtered_lines), encoding="utf-8")

    wikidata = {term: _download_wikidata_search(term) for term in WIKIDATA_TERMS}
    (RAW_DIR / "wikidata_search.json").write_text(
        json.dumps(wikidata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overpass_status: dict[str, object]
    try:
        overpass = _download_overpass_landmarks()
        (RAW_DIR / "overpass_landmarks.json").write_text(
            json.dumps(overpass, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        overpass_status = {"ok": True, "elements": len(overpass.get("elements", []))}
    except Exception as e:
        overpass_status = {"ok": False, "error": str(e)}

    manifest = {
        "sources": {
            "geonames_admin1": GEONAMES_ADMIN1_URL,
            "wikidata_search": WIKIDATA_SEARCH_URL,
            "overpass": OVERPASS_URL,
        },
        "overpass_status": overpass_status,
        "note": "Raw public reference snippets only. Final runtime JSON is intentionally small and curated for the requested six-area scope. GeoNames admin1 reflects current administrative data and may not include every historical province name separately.",
    }
    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Downloaded raw reference snippets to {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
