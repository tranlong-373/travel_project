from django.shortcuts import render, get_object_or_404
from preferences.models import UserPreference
from .services import calculate_matching_score, get_candidate_accommodations

def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)

    accommodations = get_candidate_accommodations(preference)

    scored_results = []

    for item in accommodations:
        # Gọi thuật toán Matching Score. Rating mặc định của DB nằm sẵn trong item.rating
        scored_results.append((item, calculate_matching_score(item, preference)))

    # Sắp xếp từ cao xuống thấp theo Score
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # Nếu n < 5, biến count sẽ lấy chính n đó. Còn n >= 5 thì count bằng 5.
    count = min(len(scored_results), 5)
    final_output = scored_results[:count]

    return render(request, 'recommendations/recommendation_result.html', 
    {
        'preference': preference,
        'results': final_output
    })
def chat_recommendation_page(request):
    return render(request, 'recommendations/chat_recommendation.html')