from __future__ import annotations

from typing import Any


def build_clarification_payload(result: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    needed = bool(
        result.get("ambiguous_location")
        or result.get("unresolved_location")
        or policy.get("needs_confirmation")
        or policy.get("needs_user_action")
    )
    question = (
        result.get("ambiguous_location_question")
        or policy.get("next_best_question")
        or result.get("follow_up_question")
    )
    return {
        "needed": needed,
        "type": policy.get("confirmation_type") or result.get("confirmation_type") or "none",
        "question": question,
        "candidates": result.get("location_candidates") or [],
    }

