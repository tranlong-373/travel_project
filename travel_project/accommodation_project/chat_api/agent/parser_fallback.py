from __future__ import annotations

from typing import Any

from .schema_normalizer import normalize_parsed_result


def normalize_rule_result(
    text: str,
    *,
    locale: str = "vi",
    context_slots: dict[str, Any] | None = None,
    fallback_result: dict[str, Any] | None = None,
    parser_mode: str = "hybrid_rule_fallback",
) -> dict[str, Any]:
    if fallback_result is None:
        from ..services import parse_user_text_rule_based

        fallback_result = parse_user_text_rule_based(text, locale=locale, context_slots=context_slots)

    return normalize_parsed_result(
        fallback_result,
        raw_text=text,
        locale=locale,
        context_slots=context_slots,
        fallback_result=fallback_result,
        parser_mode=parser_mode,
    )
