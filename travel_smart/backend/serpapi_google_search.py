from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import urlopen
from typing import Any


def search_osaka_cafes() -> dict[str, Any]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise SystemExit("Missing SERPAPI_KEY environment variable.")

    params = {
        "engine": "google",
        "q": "quán cà phê ở Osaka",
        "location": "Osaka, Japan",
        "hl": "vi",
        "gl": "jp",
        "google_domain": "google.co.jp",
        "api_key": api_key,
    }
    search_url = f"https://serpapi.com/search.json?{urlencode(params)}"

    with urlopen(search_url) as response:
        return json.load(response)


def print_results(results: dict[str, Any]) -> None:
    print(results)

    organic_results = results.get("organic_results", [])
    for item in organic_results[:5]:
        print("-" * 50)
        print("Title:", item.get("title"))
        print("Link :", item.get("link"))
        print("Snippet:", item.get("snippet"))


def main() -> int:
    results = search_osaka_cafes()
    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
