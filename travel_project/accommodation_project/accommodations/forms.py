from django import forms
from .models import PartnerAccommodationRequest


class PartnerAccommodationRequestForm(forms.ModelForm):
    amenities = forms.MultipleChoiceField(
        choices=PartnerAccommodationRequest.AMENITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Tiện ích'
    )

    class Meta:
        model = PartnerAccommodationRequest
        fields = [
            'representative_name',
            'phone',
            'email',

            'hotel_name',
            'accommodation_type',
            'area',
            'address',
            'price_per_night',
            'capacity',
            'hotline',
            'amenities',
            'description',
            'image_url',
            'google_maps_link',

            'room_name',
            'room_type',
            'room_price_per_night',
            'room_capacity',
            'total_rooms',
            'available_rooms',
            'room_description',
        ]

        widgets = {
            'representative_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tên người đại diện'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Số điện thoại'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email liên hệ'
            }),
            'hotel_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tên khách sạn / homestay / căn hộ'
            }),
            'accommodation_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'area': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Khu vực, ví dụ: Đà Nẵng, Nha Trang, Đà Lạt'
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Địa chỉ cụ thể'
            }),
            'price_per_night': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Giá trung bình mỗi đêm'
            }),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Sức chứa tổng'
            }),
            'hotline': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Hotline'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Mô tả chỗ ở'
            }),
            'image_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Link ảnh đại diện'
            }),
            'google_maps_link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Link Google Maps'
            }),

            'room_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ví dụ: Standard Room, Deluxe Room'
            }),
            'room_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'room_price_per_night': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Giá phòng mỗi đêm'
            }),
            'room_capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Sức chứa phòng'
            }),
            'total_rooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tổng số phòng loại này'
            }),
            'available_rooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Số phòng còn trống'
            }),
            'room_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Mô tả phòng'
            }),
        }

    def clean_available_rooms(self):
        available_rooms = self.cleaned_data.get('available_rooms')
        total_rooms = self.cleaned_data.get('total_rooms')

        if available_rooms is not None and total_rooms is not None:
            if available_rooms > total_rooms:
                raise forms.ValidationError('Số phòng còn trống không được lớn hơn tổng số phòng.')

        return available_rooms