from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..normalizers import normalize_key


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PLACE_ALIASES_PATH = DATA_DIR / "place_aliases.json"
SEMANTIC_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_ACCEPT_THRESHOLD = 0.78

ALIAS_PREFIXES = (
    "khu du lich",
    "cong vien van hoa",
    "cong vien",
    "bao tang",
    "lang du lich",
    "khu di tich",
)


def normalize_place_text(text: str | None) -> str:
    value = normalize_key(text or "")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


@lru_cache(maxsize=1)
def load_place_aliases() -> dict[str, list[str]]:
    try:
        data = json.loads(PLACE_ALIASES_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    output: dict[str, list[str]] = {}
    for key, values in data.items():
        alias_key = normalize_place_text(key)
        aliases = [normalize_place_text(value) for value in values or []]
        aliases = [value for value in aliases if value]
        if alias_key:
            output[alias_key] = sorted({alias_key, *aliases})
    return output


def alias_expansions(query: str | None) -> list[str]:
    family = known_alias_family(query)
    if not family:
        return []
    return sorted(family, key=len, reverse=True)


def known_alias_family(query: str | None) -> set[str]:
    key = normalize_place_text(query)
    if not key:
        return set()
    for alias_key, aliases in load_place_aliases().items():
        if key == alias_key or key in aliases or any(alias in key for alias in aliases):
            return {alias_key, *aliases}
    return set()


def candidate_matches_known_alias(query: str | None, candidate: dict[str, Any] | None) -> bool:
    family = known_alias_family(query)
    if not family:
        return True
    candidate = candidate or {}
    parts = [
        candidate.get("name") or "",
        candidate.get("canonical_name") or "",
        candidate.get("display_name") or "",
    ]
    aliases = candidate.get("aliases") or []
    if isinstance(aliases, (list, tuple, set)):
        parts.extend(str(alias) for alias in aliases)
    address = candidate.get("address") or {}
    if isinstance(address, dict):
        parts.extend(str(value) for value in address.values() if value)
    haystack = normalize_place_text(" ".join(parts))
    return any(alias and alias in haystack for alias in family)


def generate_place_aliases(name: str | None) -> list[str]:
    normalized = normalize_place_text(name)
    if not normalized:
        return []
    aliases = {normalized, normalized.replace(" ", "")}
    for prefix in ALIAS_PREFIXES:
        if normalized.startswith(f"{prefix} "):
            stripped = normalized[len(prefix) :].strip()
            if stripped:
                aliases.add(stripped)
                aliases.add(stripped.replace(" ", ""))
    return sorted(aliases)


def find_place_reference(query: str | None) -> dict[str, Any] | None:
    key = normalize_place_text(query)
    if not key:
        return None
    try:
        from ..models import PlaceReference

        reference = (
            PlaceReference.objects.filter(normalized_name=key).first()
            or PlaceReference.objects.filter(normalized_query=key).first()
        )
        if reference is None:
            try:
                reference = PlaceReference.objects.filter(aliases__contains=[key]).first()
            except Exception:
                reference = None
        if reference is None:
            reference = next(
                (
                    item
                    for item in PlaceReference.objects.all()
                    if key in {normalize_place_text(alias) for alias in (item.aliases or [])}
                ),
                None,
            )
        if reference is None:
            return None
        return reference_to_payload(reference, source="place_reference")
    except Exception:
        return None


def semantic_search_place_reference(query: str | None) -> dict[str, Any] | None:
    key = normalize_place_text(query)
    if not key:
        return None
    try:
        model, references, texts = _semantic_index()
    except Exception:
        return None
    if not references or not texts:
        return None
    try:
        import numpy as np

        query_embedding = model.encode([key], normalize_embeddings=True)[0]
        embeddings = model.encode(texts, normalize_embeddings=True)
        scores = np.matmul(embeddings, query_embedding)
        best_index = int(np.argmax(scores))
        similarity = float(scores[best_index])
    except Exception:
        return None
    if similarity < SEMANTIC_ACCEPT_THRESHOLD:
        return None
    payload = reference_to_payload(references[best_index], source="semantic")
    payload["semantic_similarity"] = similarity
    payload["confidence"] = max(float(payload.get("confidence") or 0.0), similarity)
    return payload


@lru_cache(maxsize=1)
def _semantic_index():
    from sentence_transformers import SentenceTransformer

    from ..models import PlaceReference

    references = list(PlaceReference.objects.all()[:1000])
    texts: list[str] = []
    expanded_references = []
    for reference in references:
        values = [reference.canonical_name, *(reference.aliases or [])]
        for value in values:
            normalized = normalize_place_text(value)
            if normalized:
                texts.append(normalized)
                expanded_references.append(reference)
    return SentenceTransformer(SEMANTIC_MODEL_NAME), expanded_references, texts


def reference_to_payload(reference, *, source: str | None = None) -> dict[str, Any]:
    address = reference.address or {}
    return {
        "name": reference.canonical_name,
        "canonical_name": reference.canonical_name,
        "normalized_name": reference.normalized_name,
        "aliases": list(reference.aliases or []),
        "kind": reference.kind,
        "place_type": reference.kind,
        "lat": reference.latitude,
        "lon": reference.longitude,
        "latitude": reference.latitude,
        "longitude": reference.longitude,
        "default_radius_km": reference.default_radius_km,
        "provider": reference.provider,
        "provider_place_id": reference.provider_place_id,
        "query": reference.query or reference.query_text,
        "query_used": reference.query or reference.query_text,
        "query_text": reference.query_text,
        "normalized_query": reference.normalized_query,
        "display_name": reference.display_name or reference.canonical_name,
        "address": address,
        "district": reference.district or _address_value(address, "city_district", "district", "suburb"),
        "city": reference.city or _address_value(address, "city", "municipality", "state"),
        "country": reference.country or _address_value(address, "country"),
        "raw_payload": reference.raw_payload or {},
        "confidence": reference.confidence,
        "source": source or reference.source or "place_reference",
    }


def _address_value(address: dict[str, Any], *keys: str) -> str:
    if not isinstance(address, dict):
        return ""
    for key in keys:
        value = address.get(key)
        if value:
            return str(value)
    return ""
