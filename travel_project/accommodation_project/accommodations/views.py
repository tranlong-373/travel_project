from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q

from accounts.models import Favorite
from .models import Accommodation, AccommodationReview


def accommodation_list(request):
    qs = Accommodation.objects.all()

    destination = request.GET.get('destination', '').strip()
    guests = request.GET.get('guests', '').strip()
    check_in = request.GET.get('check_in', '').strip()
    check_out = request.GET.get('check_out', '').strip()

    if destination:
        qs = qs.filter(
            Q(name__icontains=destination)
            | Q(area__icontains=destination)
            | Q(address__icontains=destination)
            | Q(description__icontains=destination)
        )

    guest_count = None
    if guests:
        try:
            guest_count = int(guests)
            if guest_count > 0:
                qs = qs.filter(capacity__gte=guest_count)
        except (TypeError, ValueError):
            guest_count = None

    acc_type = request.GET.get('type', '')
    if acc_type:
        qs = qs.filter(accommodation_type=acc_type)

    price_range = request.GET.get('price', '')
    if price_range == '0-500k':
        qs = qs.filter(price_per_night__lte=500000)
    elif price_range == '500k-1tr':
        qs = qs.filter(price_per_night__gt=500000, price_per_night__lte=1000000)
    elif price_range == '1tr-2tr':
        qs = qs.filter(price_per_night__gt=1000000, price_per_night__lte=2000000)
    elif price_range == '2tr+':
        qs = qs.filter(price_per_night__gt=2000000)

    amenities = request.GET.getlist('amenity')
    if amenities:
        qs = [room for room in qs if all(a in (room.amenities or []) for a in amenities)]

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

    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(request, 'accommodations/accommodation_list.html', {
        'accommodations': page_obj,
        'page_obj': page_obj,
        'current_type': acc_type,
        'current_price': price_range,
        'current_sort': sort,
        'current_amenities': amenities,
        'current_destination': destination,
        'current_guests': guests,
        'current_check_in': check_in,
        'current_check_out': check_out,
        'query_string': query_params.urlencode(),
        'guest_count': guest_count,
    })



def accommodation_detail(request, pk):
    accommodation = get_object_or_404(Accommodation, pk=pk)
    approved_reviews = AccommodationReview.objects.filter(
        accommodation=accommodation,
        is_approved=True,
    ).select_related('user').order_by('-created_at')

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(
            user=request.user,
            accommodation=accommodation,
        ).exists()

    return render(request, 'accommodations/accommodation_detail.html', {
        'accommodation': accommodation,
        'approved_reviews': approved_reviews,
        'is_favorited': is_favorited,
    })


@login_required
def add_review(request, accommodation_id):
    accommodation = get_object_or_404(Accommodation, id=accommodation_id)

    if request.method == 'POST':
        score = int(request.POST.get('score'))
        comment = request.POST.get('comment', '').strip()

        AccommodationReview.objects.create(
            user=request.user,
            accommodation=accommodation,
            score=score,
            comment=comment,
            is_approved=False,
        )

    return redirect('accommodation_detail', pk=accommodation.id)


def home_view(request):
    accommodations = Accommodation.objects.all()[:8]
    latest_reviews = AccommodationReview.objects.filter(
        is_approved=True
    ).select_related('user', 'accommodation').order_by('-created_at')[:6]

    return render(request, 'home.html', {
        'accommodations': accommodations,
        'latest_reviews': latest_reviews,
    })
