from django import forms

TYPE_CHOICES = [
    ('', 'No preference'),
    ('hotel', 'Hotel'),
    ('homestay', 'Homestay'),
    ('hostel', 'Hostel'),
    ('apartment', 'Apartment'),
]

AMENITY_CHOICES = [
    ('wifi', 'Wifi'),
    ('air_conditioner', 'Air Conditioner'),
    ('kitchen', 'Kitchen'),
    ('parking', 'Parking'),
    ('pool', 'Pool'),
    ('washing_machine', 'Washing Machine'),
]

class PreferenceForm(forms.Form):
    area = forms.CharField(max_length=100)
    budget = forms.IntegerField()
    guest_count = forms.IntegerField()
    preferred_type = forms.ChoiceField(choices=TYPE_CHOICES, required=False)
    required_amenities = forms.MultipleChoiceField(
        choices=AMENITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
