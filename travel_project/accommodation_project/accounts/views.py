from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .forms import RegisterForm
from .models import Profile, Favorite
from accommodations.models import Accommodation


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )

            Profile.objects.create(user=user)

            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    favorites = Favorite.objects.filter(user=request.user).select_related('accommodation')

    if request.method == 'POST':
        profile.full_name = request.POST.get('full_name', '')
        profile.phone = request.POST.get('phone', '')
        profile.address = request.POST.get('address', '')
        profile.save()
        return redirect('profile')

    return render(request, 'accounts/profile.html', {
        'profile': profile,
        'favorites': favorites
    })


@login_required
def add_favorite(request, accommodation_id):
    if request.method == 'POST':
        accommodation = get_object_or_404(Accommodation, id=accommodation_id)
        Favorite.objects.get_or_create(user=request.user, accommodation=accommodation)
    return redirect('accommodation_detail', pk=accommodation_id)


@login_required
def remove_favorite(request, accommodation_id):
    if request.method == 'POST':
        accommodation = get_object_or_404(Accommodation, id=accommodation_id)
        Favorite.objects.filter(user=request.user, accommodation=accommodation).delete()
    return redirect('accommodation_detail', pk=accommodation_id)