from django.shortcuts import render, get_object_or_404
from accommodations.models import Accommodation
from preferences.models import UserPreference

def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)

    accommodations = Accommodation.objects.filter(
        area__icontains=preference.area,
        price_per_night__lte=preference.budget,
        capacity__gte=preference.guest_count
    )

    scored_results = []

    for item in accommodations:
        score = 0

        if item.accommodation_type == preference.preferred_type:
            score += 3

        for amenity in preference.required_amenities:
            if amenity in item.amenities:
                score += 2

        if item.rating >= 4.5:
            score += 3
        elif item.rating >= 4.0:
            score += 2
        elif item.rating >= 3.5:
            score += 1

        scored_results.append((item, score))

    scored_results.sort(key=lambda x: x[1], reverse=True)

    return render(request, 'recommendations/recommendation_result.html', {
        'preference': preference,
        'results': scored_results[:5]
    })