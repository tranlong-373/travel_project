from django.shortcuts import render, redirect
from .forms import PreferenceForm
from .models import UserPreference

def preference_form_view(request):
    if request.method == 'POST':
        form = PreferenceForm(request.POST)
        if form.is_valid():
            preference = UserPreference.objects.create(
                area=form.cleaned_data['area'],
                budget=form.cleaned_data['budget'],
                guest_count=form.cleaned_data['guest_count'],
                preferred_type=form.cleaned_data['preferred_type'],
                required_amenities=form.cleaned_data['required_amenities'],
            )
            return redirect('recommendation_result', pref_id=preference.id)
    else:
        form = PreferenceForm()

    return render(request, 'preferences/preference_form.html', {'form': form})