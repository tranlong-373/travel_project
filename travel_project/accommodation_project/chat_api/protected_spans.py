from __future__ import annotations

from typing import Any


def public_protected_spans(slot_parse_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    spans = (slot_parse_context or {}).get("protected_spans") or []
    output: list[dict[str, Any]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        output.append(
            {
                "text": span.get("text"),
                "type": span.get("type"),
                "value": span.get("value"),
            }
        )
    return output

