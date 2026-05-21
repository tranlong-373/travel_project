"""
ChatPipeline — end-to-end chat NLU pipeline (v2).

run() is the primary entry point:
  1. SearchIntentBuilder.build()
  2. to_parse_result() → legacy dict
  3. Attach search_intent_v2 for recommendation_bridge
  4. Return dict (raises on error so parser_service can fallback to v1)

Wire via CHAT_PIPELINE_V2_ENABLED=True in settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..nlu.dto import SearchIntent
from ..nlu.search_intent_builder import SearchIntentBuilder


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Output of ChatPipeline.run(). Carries the typed intent alongside
    the raw parse_result dict so callers can access either form
    during the transition period.
    """
    intent: SearchIntent
    parse_result: dict[str, Any] = field(default_factory=dict)
    preference_id: int | None = None
    recommendation_url: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ChatPipeline:
    """
    Orchestrates the chat → parse → intent → preference → recommendation flow.

    Phase 1 (current): skeleton only, not wired to runtime.
    Phase 2: run() will call parser_service + recommendation_bridge internally.
    Phase 3: run() will bypass recommendation_bridge entirely and use
             adapters.search_intent_to_user_preference directly.

    Usage in tests / sandbox (already works):
        pipeline = ChatPipeline()
        intent = pipeline.build_intent_from_parse_result(parse_result, raw_text="...")

    Usage in production (Phase 2+):
        result = pipeline.run(text="khách sạn quận 1", locale="vi")
    """

    def __init__(self) -> None:
        self._builder = SearchIntentBuilder()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(
        self,
        text: str,
        *,
        locale: str = "vi",
        context_slots: dict[str, Any] | None = None,
        selected_place: str | None = None,
        user_location: dict[str, Any] | None = None,
        include_debug: bool = False,
        create_preference: bool = False,  # kept for signature compat; not used here
    ) -> dict[str, Any]:
        """
        Full v2 NLU pipeline.

        Steps:
          1. Build SearchIntent via SearchIntentBuilder.build()
          2. Convert to legacy parse_result dict via to_parse_result()
          3. Attach search_intent_v2 for recommendation_bridge
          4. Return the partial parse_result dict

        Raises on any error — callers (e.g. parse_user_text) catch and fallback.
        No DB writes, no UserPreference creation, no recommendation calls.
        """
        from ..nlu.dto import UserLocationInput
        from ..adapters.search_intent_to_parse_result import to_parse_result

        ul: UserLocationInput | None = None
        if isinstance(user_location, dict):
            try:
                ul = UserLocationInput(
                    lat=float(user_location["lat"]),
                    lon=float(user_location["lon"]),
                    accuracy=user_location.get("accuracy"),
                )
            except (KeyError, TypeError, ValueError):
                ul = None

        intent = self._builder.build(
            text,
            locale=locale,
            context_slots=context_slots,
            selected_place=selected_place,
            user_location=ul,
            include_debug=include_debug,
        )

        result = to_parse_result(intent)
        # Keep the typed SearchIntent object so callers can access it directly.
        # The recommendation bridge can use it when present, or fall back to
        # rebuilding from parse_result dict.
        result["search_intent_v2"] = intent
        result["parser_mode"] = "v2_pipeline"
        result["input_kind"] = intent.input_kind
        return result

    def build_intent_from_parse_result(
        self,
        parse_result: dict[str, Any],
        *,
        raw_text: str = "",
        locale: str = "vi",
    ) -> SearchIntent:
        """
        Convert an existing parse_result dict to a typed SearchIntent.
        Fully operational in Phase 1 — no runtime dependency.
        """
        return self._builder.from_parse_result(
            parse_result,
            raw_text=raw_text,
            locale=locale,
        )
