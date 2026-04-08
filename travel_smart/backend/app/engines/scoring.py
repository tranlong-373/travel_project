from typing import List, Dict, Any
import random

def score_accommodations(
    filtered_data: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Mock AI tính điểm cho chỗ ở dựa trên mô tả, đánh giá, giá cả và sở thích người dùng."""
    scored_list: List[Dict[str, Any]] = []

    base_preferences = [str(p).strip().lower() for p in user_profile.get("preferences", []) if p]
    price_sensitivity = float(user_profile.get("price_sensitivity", 1.0))

    for item in filtered_data:
        score = 0.0

        description = str(item.get("description", "")).lower()
        amen_text = " ".join([str(a).lower() for a in item.get("amenities", [])])
        combined = f"{description} {amen_text}"

        if base_preferences:
            matches = sum(1 for pref in base_preferences if pref in combined)
            score += matches / max(1, len(base_preferences))

        if item.get("rating") is not None:
            rating = float(item.get("rating", 0.0)) / 5.0
            score += 0.5 * rating

        if item.get("price") is not None and price_sensitivity > 0:
            price = float(item.get("price", 0.0))
            budget_max = float(user_profile.get("budget_max", 0) or 0)
            if budget_max > 0:
                price_score = max(0.0, min(1.0, 1 - (price / budget_max)))
                score += 0.5 * price_score * (1 / price_sensitivity)

        # Thêm random noise siêu nhỏ để tránh bị trùng lặp cứng khi điểm bằng nhau
        score += random.uniform(0.0, 0.05)

        score = max(0.0, min(1.0, score))
        item_with_score = item.copy()
        item_with_score["score"] = round(score, 4)
        scored_list.append(item_with_score)

    return scored_list


def generate_reason_for_score(accommodation: Dict[str, Any]) -> str:
    """Tạo lý do giải thích cho điểm số của chỗ ở dựa trên các yếu tố như đánh giá và giá cả."""
    score = float(accommodation.get("score", 0.0))
    raw_price = accommodation.get("price")
    price = float(raw_price) if raw_price is not None else 0.0

    reasons = []
    if score >= 0.85:
        reasons.append("Đánh giá cực cao")
    elif score >= 0.65:
        reasons.append("Lựa chọn ổn")
    else:
        reasons.append("Phù hợp với yêu cầu cơ bản")

    if price <= 300000:
        reasons.append("Giá phù hợp nhất")
    elif price <= 700000:
        reasons.append("Giá hợp lý")
    else:
        reasons.append("Giá cao nhưng xứng đáng")

    return "; ".join(reasons)


def score_with_ai(user_profile: Dict[str, Any], item: Dict[str, Any]) -> float:
    """Hàm mock thay thế cho logic tính điểm bằng AI chuyên biệt."""
    # Hiện tại gọi lại hàm chấm cơ bản nhưng có thể mở rộng gọi model NLP, LLM ở đây
    return score_accommodations([item], user_profile)[0]["score"]


def generate_reasoning_with_ai(user_profile: Dict[str, Any], item: Dict[str, Any]) -> str:
    """Hàm mock thay thế cho logic giải thích lý do bằng AI chuyên biệt."""
    scored_item = score_accommodations([item], user_profile)[0]
    return generate_reason_for_score(scored_item)
