# chat_api/nlu_ner.py
from __future__ import annotations
from .hf_cache import get_ner_pipeline

def extract_area_by_ner(text: str) -> str | None:
    nlp = get_ner_pipeline()
    ents = nlp(text) or []
    locs = [e for e in ents if e.get("entity_group") in ("LOC", "LOCATION") or e.get("entity") in ("LOC", "LOCATION")]
    if not locs:
        return None
    locs.sort(key=lambda e: (len(e.get("word", "")), float(e.get("score", 0.0))), reverse=True)
    area = (locs[0].get("word") or "").strip()
    return area if area else None
