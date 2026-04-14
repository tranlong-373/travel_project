from __future__ import annotations

import os
from functools import lru_cache

DEFAULT_CHAT_API_NER_MODEL = os.getenv("CHAT_API_NER_MODEL", "")


@lru_cache(maxsize=1)
def get_ner_pipeline():
    if not DEFAULT_CHAT_API_NER_MODEL:
        raise RuntimeError(
            "CHAT_API_NER_MODEL is not set. Keep CHAT_API_USE_NER=0 or configure a small local NER model."
        )

    from transformers import pipeline

    return pipeline(
        task="ner",
        model=DEFAULT_CHAT_API_NER_MODEL,
        tokenizer=DEFAULT_CHAT_API_NER_MODEL,
        aggregation_strategy="simple",
    )
