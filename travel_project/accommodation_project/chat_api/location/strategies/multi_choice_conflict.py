"""
MultiChoiceConflictStrategy — detect multi-area / conflict scenarios via v1.

Wraps the legacy `chat_api.location_resolver.resolve_location()` so v2 can
honour cases like:
  - "Hà Nội hoặc TP HCM"     → status=MULTIPLE_CHOICE
  - "Landmark 81 ở Đồng Nai" → status=CONFLICT
  - "Tôi muốn ở gần Bến Thành ở Hà Nội" → status=CONFLICT

The strategy only fires when v1 confidently sees 2+ candidates and returns
multiple_choice/conflict.  Single-area resolutions are passed through so
later strategies (DirectArea, NearAnchor, …) keep their behaviour.
"""
from __future__ import annotations

import logging

from ...nlu.dto import LocationMode, LocationStatus, ResolvedLocation
from ..context import LocationContext
from .base import LocationStrategy

logger = logging.getLogger(__name__)


class MultiChoiceConflictStrategy(LocationStrategy):
    # Run before DirectArea (40) so a multi-area choice isn't collapsed to one.
    order = 35
    name = "multi_choice_conflict"

    def can_handle(self, context: LocationContext) -> bool:
        # Need raw_text — v1's mention extractor reads the full sentence.
        return bool(context.raw_text)

    def resolve(self, context: LocationContext) -> ResolvedLocation | None:
        try:
            from ...location_resolver import resolve_location
        except Exception as exc:
            logger.debug("multi_choice_conflict: v1 resolver unavailable: %s", exc)
            return None

        try:
            legacy = resolve_location(context.raw_text, locale=context.locale or "vi")
        except Exception as exc:
            logger.debug("multi_choice_conflict: legacy resolve raised: %s", exc)
            return None

        status = legacy.get("location_status")
        if status not in {"multiple_choice", "conflict"}:
            return None  # let other strategies handle

        candidates = legacy.get("location_candidates") or []
        choice_labels = [c.get("canonical_area") or c.get("label") or "" for c in candidates]
        choice_labels = [c for c in choice_labels if c]

        if status == "multiple_choice":
            return ResolvedLocation(
                status=LocationStatus.MULTIPLE_CHOICE,
                mode=LocationMode.MULTIPLE_CHOICE,
                raw_phrase=context.raw_text,
                canonical_area=None,
                display_label=" / ".join(choice_labels) or None,
                provider="multi_choice_v1",
                cache_hit=False,
                debug={
                    "candidates": choice_labels,
                    "follow_up_question": legacy.get("follow_up_question"),
                    "source": "v1_resolve_location",
                },
            )

        # conflict
        return ResolvedLocation(
            status=LocationStatus.CONFLICT,
            mode=LocationMode.AMBIGUOUS,
            raw_phrase=context.raw_text,
            canonical_area=None,
            display_label=" / ".join(choice_labels) or None,
            provider="conflict_v1",
            cache_hit=False,
            debug={
                "candidates": choice_labels,
                "follow_up_question": legacy.get("follow_up_question"),
                "source": "v1_resolve_location",
            },
        )
