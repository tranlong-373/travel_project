from django.shortcuts import render, get_object_or_404
from preferences.models import UserPreference
from .services import calculate_matching_score, get_candidate_accommodations

def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)

    accommodations = get_candidate_accommodations(preference)

    scored_results = []

    for item in accommodations:
        scored_results.append((item, calculate_matching_score(item, preference)))

    scored_results.sort(key=lambda x: x[1], reverse=True)

    return render(request, 'recommendations/recommendation_result.html', {
        'preference': preference,
        'results': scored_results[:5]
    })
