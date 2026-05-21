from __future__ import annotations

from typing import Any, Callable

from .response_templates import (
    build_address_search_message,
    build_conflict_message,
    build_explicit_confirmation_message,
    build_full_message,
    build_goodbye_message,
    build_greeting_message,
    build_help_message,
    build_hotel_name_message,
    build_implicit_confirmation_message,
    build_landmark_search_message,
    build_multiple_choice_message,
    build_off_topic_message,
    build_partial_message,
    build_thanks_message,
    build_unknown_message,
    build_unresolved_location_message,
    build_unresolved_place_message,
    build_unresolved_place_with_filters_message,
    build_unsupported_message,
)


class ResponseGenerator:
    def __init__(
        self,
        *,
        terminal_intents: set[str],
        message_slots_with_location: Callable[[dict[str, Any]], dict[str, Any]],
        format_vnd: Callable[[Any], str],
    ):
        self.terminal_intents = terminal_intents
        self.message_slots_with_location = message_slots_with_location
        self.format_vnd = format_vnd

    def generate(
        self,
        result: dict[str, Any],
        policy: dict[str, Any],
        *,
        input_classification: dict[str, Any] | None = None,
    ) -> str:
        intent = result.get("conversation_intent") or result.get("intent")
        status = result.get("location_status")

        if intent == "off_topic":
            return build_off_topic_message()
        if intent == "greeting":
            return build_greeting_message()
        if intent == "thanks":
            return build_thanks_message()
        if intent == "goodbye":
            return build_goodbye_message()
        if intent == "help":
            return build_help_message()
        if status == "multiple_choice":
            return build_multiple_choice_message(result.get("location_candidates") or [])
        if status == "conflict":
            return build_conflict_message(result)
        if result.get("ambiguous_location") and not result.get("can_show_recommendations"):
            return (
                policy.get("next_best_question")
                or result.get("ambiguous_location_question")
                or build_explicit_confirmation_message(result.get("location_candidates") or [])
            )
        if policy.get("confirmation_type") == "implicit" and policy.get("assumptions"):
            return build_implicit_confirmation_message(policy["assumptions"][0])
        if result.get("location_mode") == "city_center" and policy.get("recommendation_level") in {"full", "partial"}:
            return self._city_center_message(result, policy)
        if (
            result.get("location_mode") == "near_anchor"
            and result.get("can_show_recommendations")
            and result.get("unresolved_location")
        ):
            return build_unresolved_place_with_filters_message(
                result.get("slots") or {},
                result.get("location_phrase") or result.get("matched_text"),
            )
        if (
            result.get("location_mode") == "near_anchor"
            and result.get("can_show_recommendations")
            and not result.get("unresolved_location")
            and result.get("anchor_name")
        ):
            # Dùng input-type-aware message nếu có
            if input_classification:
                itype = input_classification.get("type")
                if itype == "address":
                    return build_address_search_message(input_classification.get("address_phrase"))
                if itype == "landmark":
                    return build_landmark_search_message(result["anchor_name"], resolved=True)
            return f"Được nhé, mình sẽ gợi ý chỗ ở gần {result['anchor_name']}."

        # Khi user tìm theo tên khách sạn cụ thể và đã match được
        if (
            input_classification
            and input_classification.get("type") == "hotel_name"
            and input_classification.get("hotel_match")
            and result.get("can_show_recommendations")
        ):
            match = input_classification["hotel_match"]
            return build_hotel_name_message(match.get("name"), match.get("area"))

        if result.get("ambiguous_location") and result.get("can_show_recommendations"):
            base_message = build_partial_message(
                self.message_slots_with_location(result),
                assumptions=policy.get("assumptions"),
            )
            question = policy.get("next_best_question") or result.get("ambiguous_location_question")
            return f"{base_message} {question}" if question else base_message
        if policy.get("recommendation_level") == "full":
            return build_full_message(self.message_slots_with_location(result))
        if policy.get("recommendation_level") == "partial":
            return build_partial_message(
                self.message_slots_with_location(result),
                assumptions=policy.get("assumptions"),
                next_best_question=policy.get("next_best_question"),
            )
        if status == "ambiguous":
            return build_explicit_confirmation_message(result.get("location_candidates") or [])
        if status == "unsupported":
            return build_unsupported_message()
        if result.get("unresolved_location"):
            return build_unresolved_place_message()
        if status == "unresolved":
            return build_unresolved_location_message()
        if intent == "unknown":
            return build_unknown_message()
        return build_unknown_message()

    def _city_center_message(self, result: dict[str, Any], policy: dict[str, Any]) -> str:
        slots = result.get("slots") or {}
        label = result.get("location_display_label") or result.get("anchor_name") or "trung tâm thành phố"
        parts = [f"Được nhé, mình sẽ tìm các chỗ ở gần {label}"]
        guest_count = slots.get("guest_count")
        budget_max = slots.get("budget_max") or slots.get("budget")
        if guest_count:
            parts.append(f"cho {guest_count} người")
        if budget_max:
            parts.append(f"ngân sách dưới {self.format_vnd(budget_max)}/đêm")
        message = ", ".join(parts) + "."
        if policy.get("recommendation_level") == "partial" and policy.get("next_best_question"):
            message = f"{message} {policy['next_best_question']}"
        return message
