from django.shortcuts import render, get_object_or_404
from .models import Accommodation

def accommodation_list(request):
    accommodations = Accommodation.objects.all()
    return render(request, 'accommodations/accommodation_list.html', {
        'accommodations': accommodations
    })

def accommodation_detail(request, pk):
    accommodation = get_object_or_404(Accommodation, pk=pk)
    return render(request, 'accommodations/accommodation_detail.html', {
        'accommodation': accommodation
    })

def home_view(request):
    accommodations = Accommodation.objects.all()[:8]
    return render(request, 'home.html', {'accommodations': accommodations})