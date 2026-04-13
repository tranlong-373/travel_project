from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Accommodation, AccommodationReview

def accommodation_list(request):
    qs = Accommodation.objects.all()

    # Filter loại
    acc_type = request.GET.get('type', '')
    if acc_type:
        qs = qs.filter(accommodation_type=acc_type)

    # Filter giá
    price_range = request.GET.get('price', '')
    if price_range == '0-500k':
        qs = qs.filter(price_per_night__lte=500000)
    elif price_range == '500k-1tr':
        qs = qs.filter(price_per_night__gt=500000, price_per_night__lte=1000000)
    elif price_range == '1tr-2tr':
        qs = qs.filter(price_per_night__gt=1000000, price_per_night__lte=2000000)
    elif price_range == '2tr+':
        qs = qs.filter(price_per_night__gt=2000000)

    # Filter tiện nghi
    amenities = request.GET.getlist('amenity')
    if amenities:
        qs = [r for r in qs if all(a in (r.amenities or []) for a in amenities)]

    # Sort
    sort = request.GET.get('sort', '')
    if isinstance(qs, list):
        if sort == 'price_asc':
            qs.sort(key=lambda x: x.price_per_night)
        elif sort == 'price_desc':
            qs.sort(key=lambda x: x.price_per_night, reverse=True)
        elif sort == 'rating':
            qs.sort(key=lambda x: x.rating, reverse=True)
    else:
        if sort == 'price_asc':
            qs = qs.order_by('price_per_night')
        elif sort == 'price_desc':
            qs = qs.order_by('-price_per_night')
        elif sort == 'rating':
            qs = qs.order_by('-rating')

    paginator = Paginator(qs, 5)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'accommodations/accommodation_list.html', {
        'accommodations': page_obj,
        'page_obj': page_obj,
        'current_type': acc_type,
        'current_price': price_range,
        'current_sort': sort,
        'current_amenities': amenities,  # ← đổi thành list
    })


def accommodation_detail(request, pk):
    accommodation = get_object_or_404(Accommodation, pk=pk)
    approved_reviews = AccommodationReview.objects.filter(
        accommodation=accommodation,
        is_approved=True
    ).order_by('-created_at')

    return render(request, 'accommodations/accommodation_detail.html', {
        'accommodation': accommodation
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

def home_view(request):
    accommodations = Accommodation.objects.all()[:8]
    return render(request, 'home.html', {'accommodations': accommodations})