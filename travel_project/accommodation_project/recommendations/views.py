from django.shortcuts import render, get_object_or_404
from preferences.models import UserPreference
from .services import calculate_matching_score, get_candidate_accommodations

SORT_OPTIONS = (
    ("recommended", "Phù hợp nhất"),
    ("price_asc", "Giá thấp nhất"),
    ("price_desc", "Giá cao nhất"),
    ("rating_desc", "Đánh giá cao nhất"),
    ("rating_asc", "Đánh giá thấp nhất"),
)
VALID_SORT_KEYS = {key for key, _ in SORT_OPTIONS}


def normalize_sort_key(sort_key):
    return sort_key if sort_key in VALID_SORT_KEYS else "recommended"


def sort_scored_results(scored_results, sort_key):
    sort_key = normalize_sort_key(sort_key)

    if sort_key == "price_asc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].price_per_night or float("inf"), -result[1]),
        )
    if sort_key == "price_desc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].price_per_night or 0, result[1]),
            reverse=True,
        )
    if sort_key == "rating_desc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].rating or 0, result[1]),
            reverse=True,
        )
    if sort_key == "rating_asc":
        return sorted(
            scored_results,
            key=lambda result: (
                result[0].rating if result[0].rating is not None else float("inf"),
                -result[1],
            ),
        )

    return sorted(scored_results, key=lambda result: result[1], reverse=True)


def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)
    selected_sort = normalize_sort_key(request.GET.get("sort", "recommended"))

    accommodations = get_candidate_accommodations(preference)

    scored_results = []

    for item in accommodations:
        # Gọi thuật toán Matching Score. Rating mặc định của DB nằm sẵn trong item.rating
        scored_results.append((item, calculate_matching_score(item, preference)))

    scored_results = sort_scored_results(scored_results, selected_sort)

    # Nếu n < 5, biến count sẽ lấy chính n đó. Còn n >= 5 thì count bằng 5.
    count = min(len(scored_results), 5)
    final_output = scored_results[:count]

    return render(
        request,
        'recommendations/recommendation_result.html',
        {
            'preference': preference,
            'results': final_output,
            'selected_sort': selected_sort,
            'sort_options': SORT_OPTIONS,
        },
    )


def chat_recommendation_page(request):
    return render(request, 'recommendations/chat_recommendation.html')
