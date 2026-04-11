from django.shortcuts import render, get_object_or_404
from preferences.models import UserPreference

from .services import calculate_matching_score, get_candidate_accommodations
from .services import calculate_matching_score


def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)


    accommodations = get_candidate_accommodations(preference)

    scored_results = []

    # Lọc nhẹ để tải dữ liệu cơ bản
    accommodations = Accommodation.objects.filter(capacity__gte=preference.guest_count)


    # Gộp tên để tránh trùng lặp dữ liệu từ giả lập seed.py
    unique_items = {}
    for item in accommodations:

        scored_results.append((item, calculate_matching_score(item, preference)))

        if item.name not in unique_items:
            unique_items[item.name] = item
            
    valid_items = list(unique_items.values())
    
    scored_results = []

    for item in valid_items:
        # Gọi thuật toán Matching Score. Rating mặc định của DB nằm sẵn trong item.rating
        score = calculate_matching_score(item, preference)
        scored_results.append((item, round(score, 2)))


    # Sắp xếp từ cao xuống thấp theo Score
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # Nếu n < 5, biến count sẽ lấy chính n đó. Còn n >= 5 thì count bằng 5.
    count = min(len(scored_results), 5)
    final_output = scored_results[:count]

    return render(request, 'recommendations/recommendation_result.html', 
    {
        'preference': preference,

        'results': scored_results[:5]
    })

        'results': final_output
    })
