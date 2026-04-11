from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Accommodation, AccommodationReview

def accommodation_list(request):
    accommodations = Accommodation.objects.all()
    return render(request, 'accommodations/accommodation_list.html', {
        'accommodations': accommodations
    })


def accommodation_detail(request, pk):
    accommodation = get_object_or_404(Accommodation, pk=pk)
    approved_reviews = AccommodationReview.objects.filter(
        accommodation=accommodation,
        is_approved=True
    ).order_by('-created_at')

    return render(request, 'accommodations/accommodation_detail.html', {
        'accommodation': accommodation,
        'approved_reviews': approved_reviews
    })
@login_required
def add_review(request, accommodation_id):
    accommodation = get_object_or_404(Accommodation, id=accommodation_id)

    if request.method == 'POST':
        score = int(request.POST.get('score'))
        comment = request.POST.get('comment')

        AccommodationReview.objects.create(
            user=request.user,
            accommodation=accommodation,
            score=score,
            comment=comment,
            is_approved=False
        )

    return redirect('accommodation_detail', pk=accommodation.id)