from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from accounts.models import Favorite
from blog.models import BlogPost
from .models import Accommodation, AccommodationReview, Room


def accommodation_list(request):

    qs = Accommodation.objects.all()

    def positive_int(value):
        try:
            parsed = int(str(value or '').strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    # =========================
    # SEARCH
    # =========================
    destination = request.GET.get('destination', '').strip()
    guests = request.GET.get('guests', '').strip()
    adults = request.GET.get('adults', '').strip()
    children = request.GET.get('children', '').strip()
    rooms = request.GET.get('rooms', '').strip()
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
        guest_count = positive_int(guests)
    elif adults or children:
        adult_count = positive_int(adults) or 0
        child_count = positive_int(children) or 0
        guest_count = adult_count + child_count or None

    if guest_count:
        qs = qs.filter(capacity__gte=guest_count)

    room_count = positive_int(rooms)
    if room_count:
        qs = qs.annotate(
            total_available_room_count=Sum(
                'rooms__available_rooms',
                filter=Q(rooms__is_active=True),
            )
        ).filter(total_available_room_count__gte=room_count)

    # =========================
    # TYPE
    # =========================
    acc_type = request.GET.get('type', '')

    if acc_type:
        qs = qs.filter(accommodation_type=acc_type)

    # =========================
    # PRICE RADIO
    # =========================
    price_range = request.GET.get('price', '')

    if price_range == '0-500k':
        qs = qs.filter(price_per_night__lte=500000)

    elif price_range == '500k-1tr':
        qs = qs.filter(
            price_per_night__gt=500000,
            price_per_night__lte=1000000
        )

    elif price_range == '1tr-2tr':
        qs = qs.filter(
            price_per_night__gt=1000000,
            price_per_night__lte=2000000
        )

    elif price_range == '2tr+':
        qs = qs.filter(price_per_night__gt=2000000)

    # =========================
    # PRICE SLIDER
    # =========================
    price_min = request.GET.get('price_min', '')
    price_max = request.GET.get('price_max', '')

    try:
        if price_min != '':
            qs = qs.filter(price_per_night__gte=int(price_min))

        if price_max != '':
            qs = qs.filter(price_per_night__lte=int(price_max))

    except ValueError:
        pass

    # =========================
    # AMENITIES
    # =========================
    amenities = request.GET.getlist('amenity')

    if amenities:
        qs = [
            room for room in qs
            if all(a in (room.amenities or []) for a in amenities)
        ]

    # =========================
    # SORT
    # =========================
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

    # =========================
    # PAGINATION
    # =========================
    paginator = Paginator(qs, 5)

    page_number = request.GET.get('page', 1)

    page_obj = paginator.get_page(page_number)

    page_accommodations = list(page_obj.object_list)

    accommodation_ids = [
        accommodation.id
        for accommodation in page_accommodations
    ]

    # =========================
    # REVIEWS
    # =========================
    latest_reviews = (
        AccommodationReview.objects.filter(
            accommodation_id__in=accommodation_ids,
            is_approved=True,
        )
        .select_related('user', 'accommodation')
        .order_by('accommodation_id', '-created_at')
    )

    reviews_by_accommodation = {}

    for review in latest_reviews:

        reviews_by_accommodation.setdefault(
            review.accommodation_id,
            []
        )

        if len(reviews_by_accommodation[review.accommodation_id]) < 2:
            reviews_by_accommodation[
                review.accommodation_id
            ].append(review)

    # =========================
    # POSTS
    # =========================
    latest_posts = (
        BlogPost.objects.filter(
            accommodation_id__in=accommodation_ids
        )
        .select_related('author', 'accommodation')
        .prefetch_related('images', 'comments')
        .order_by('accommodation_id', '-created_at')
    )

    posts_by_accommodation = {}

    for post in latest_posts:

        posts_by_accommodation.setdefault(
            post.accommodation_id,
            []
        )

        if len(posts_by_accommodation[post.accommodation_id]) < 2:
            posts_by_accommodation[
                post.accommodation_id
            ].append(post)

    # =========================
    # ATTACH PREVIEW
    # =========================
    for accommodation in page_accommodations:

        accommodation.preview_reviews = (
            reviews_by_accommodation.get(
                accommodation.id,
                []
            )
        )

        accommodation.preview_posts = (
            posts_by_accommodation.get(
                accommodation.id,
                []
            )
        )

    # =========================
    # QUERY STRING
    # =========================
    query_params = request.GET.copy()

    query_params.pop('page', None)

    # =========================
    # RENDER
    # =========================
    return render(
        request,
        'accommodations/accommodation_list.html',
        {
            'accommodations': page_obj,
            'page_obj': page_obj,

            'current_type': acc_type,
            'current_price': price_range,
            'current_sort': sort,

            'current_amenities': amenities,

            'current_destination': destination,
            'current_guests': guests or (str(guest_count) if guest_count else ''),
            'current_adults': adults,
            'current_children': children,
            'current_rooms': rooms,

            'current_check_in': check_in,
            'current_check_out': check_out,

            'current_price_min': price_min,
            'current_price_max': price_max,

            'query_string': query_params.urlencode(),

            'guest_count': guest_count,
        }
    )


def accommodation_detail(request, pk):
    accommodation = get_object_or_404(Accommodation, pk=pk)
    reviews = accommodation.reviews.filter(is_approved=True)
    rooms = accommodation.rooms.filter(is_active=True).order_by('price_per_night')

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(
            user=request.user,
            accommodation=accommodation
        ).exists()

    current_filters = request.GET.urlencode()

    return render(request, 'accommodations/accommodation_detail.html', {
        'accommodation': accommodation,
        'reviews': reviews,
        'rooms': rooms,
        'is_favorited': is_favorited,
        'current_filters': current_filters,
    })


@login_required
def add_review(request, accommodation_id):
    accommodation = get_object_or_404(Accommodation, id=accommodation_id)

    if request.method == 'POST':
        try:
            score = int(request.POST.get('score', 0))
        except ValueError:
            return redirect('accommodation_detail', pk=accommodation.id)

        comment = request.POST.get('comment', '').strip()

        # validate
        if score not in [1, 2, 3, 4, 5]:
            return redirect('accommodation_detail', pk=accommodation.id)

        if not comment:
            return redirect('accommodation_detail', pk=accommodation.id)

        # tạo review
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
