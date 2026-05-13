from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.models import User
from django import forms

from .models import Accommodation, AccommodationReview, Room


# ─── Form tùy chỉnh: nhập Khuyến mãi trực tiếp (không cần gõ JSON thô) ───────
class AccommodationForm(forms.ModelForm):
    discount_percent = forms.IntegerField(
        label="Giảm giá (%)", required=False, min_value=0, max_value=100,
        help_text="Nhập % giảm giá (vd: 8)"
    )
    discount_amount = forms.IntegerField(
        label="Giảm giá (VND)", required=False, min_value=0,
        help_text="Nhập số tiền giảm cố định (vd: 300000). Ưu tiên hơn % nếu cả hai được nhập."
    )

    class Meta:
        model = Accommodation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.amenities:
            amenities = self.instance.amenities
            if isinstance(amenities, dict):
                self.fields['discount_percent'].initial = amenities.get('discount_percent')
                self.fields['discount_amount'].initial = amenities.get('discount_amount')

    def save(self, commit=True):
        instance = super().save(commit=False)
        amenities = instance.amenities

        if isinstance(amenities, list):
            amenities_dict = {"tien_ich": amenities}
        elif isinstance(amenities, dict):
            amenities_dict = amenities
        else:
            amenities_dict = {"tien_ich": []}

        percent = self.cleaned_data.get('discount_percent')
        amount = self.cleaned_data.get('discount_amount')

        if percent is not None:
            amenities_dict['discount_percent'] = percent
        else:
            amenities_dict.pop('discount_percent', None)

        if amount is not None:
            amenities_dict['discount_amount'] = amount
        else:
            amenities_dict.pop('discount_amount', None)

        instance.amenities = amenities_dict
        if commit:
            instance.save()
        return instance


# ─── Inlines ──────────────────────────────────────────────────────────────────
class ReviewInline(admin.TabularInline):
    model = AccommodationReview
    extra = 0
    fields = ('user', 'score', 'comment', 'is_approved', 'created_at')
    readonly_fields = ('created_at',)


# ─── Accommodation Admin ───────────────────────────────────────────────────────
@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    form = AccommodationForm
    list_display = (
        'image_preview', 'name', 'accommodation_code', 'accommodation_type',
        'area', 'price_per_night', 'capacity', 'rating', 'review_count',
        'get_amenities_tags',
    )
    list_filter = ('accommodation_type', 'area', 'rating')
    search_fields = ('name', 'accommodation_code', 'area', 'address')
    list_display_links = ('image_preview', 'name')
    readonly_fields = ('image_preview_large', 'rating', 'review_count')
    inlines = [ReviewInline]
    fieldsets = (
        ('Thông tin chính', {
            'fields': (
                'image_preview_large', 'image_url',
                'accommodation_code', 'name', 'accommodation_type',
                'area', 'address', 'hotline',
            )
        }),
        ('Giá & Khuyến mãi', {
            'fields': ('price_per_night', 'capacity', 'discount_percent', 'discount_amount')
        }),
        ('Đánh giá', {
            'fields': ('rating', 'review_count')
        }),
        ('Mô tả & Tiện ích', {
            'fields': ('description', 'amenities')
        }),
        ('Tọa độ bản đồ', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',),
        }),
    )

    # ── Cột Tags / Khuyến mãi ──
    def get_amenities_tags(self, obj):
        if not obj.amenities:
            return "-"
        tags_str = ""
        sales = []
        if isinstance(obj.amenities, list):
            tags_str = ", ".join([str(i) for i in obj.amenities if str(i).startswith("#")])
        elif isinstance(obj.amenities, dict):
            tien_ich = obj.amenities.get('tien_ich', [])
            if isinstance(tien_ich, list):
                tags_str = ", ".join([str(i) for i in tien_ich if str(i).startswith("#")])
            if 'discount_percent' in obj.amenities:
                sales.append(f"-{obj.amenities['discount_percent']}%")
            if 'discount_amount' in obj.amenities:
                sales.append(f"-{obj.amenities['discount_amount']}đ")
        sale_str = format_html(
            '<br><span style="color:red;font-weight:bold;">Sale: {}</span>', " | ".join(sales)
        ) if sales else ""
        return format_html('{}{}', tags_str, sale_str)

    get_amenities_tags.short_description = "Tags / Khuyến mãi"

    # ── Image preview nhỏ trong danh sách ──
    def image_preview(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="width:64px;height:44px;object-fit:cover;border-radius:6px;" />',
                obj.image_url,
            )
        return format_html('<span style="color:#94a3b8;">No image</span>')

    image_preview.short_description = 'Ảnh'

    # ── Image preview lớn trong form ──
    def image_preview_large(self, obj):
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width:320px;max-height:180px;object-fit:cover;border-radius:8px;" />',
                obj.image_url,
            )
        return 'No image'

    image_preview_large.short_description = 'Xem trước ảnh'

    def room_count(self, obj):
        return obj.rooms.count()

    room_count.short_description = 'Phòng'


# ─── Room Admin ───────────────────────────────────────────────────────────────
class RoomForm(forms.ModelForm):
    discount_percent = forms.IntegerField(
        label="Giảm giá phòng này (%)", required=False, min_value=0, max_value=100,
        help_text="Chỉ áp dụng riêng cho loại phòng này (vd: 20 → giảm 20%). Bỏ trống = dùng giảm giá chung của nơi lưu trú."
    )
    discount_amount = forms.IntegerField(
        label="Giảm giá phòng này (VND)", required=False, min_value=0,
        help_text="Giảm số tiền cố định riêng cho phòng này (vd: 200000). Ưu tiên hơn % nếu cả hai được nhập."
    )

    class Meta:
        model = Room
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and isinstance(self.instance.amenities, dict):
            self.fields['discount_percent'].initial = self.instance.amenities.get('discount_percent')
            self.fields['discount_amount'].initial = self.instance.amenities.get('discount_amount')

    def save(self, commit=True):
        instance = super().save(commit=False)
        amenities = instance.amenities

        if isinstance(amenities, list):
            amenities_dict = {"tien_ich": amenities}
        elif isinstance(amenities, dict):
            amenities_dict = amenities
        else:
            amenities_dict = {}

        percent = self.cleaned_data.get('discount_percent')
        amount = self.cleaned_data.get('discount_amount')

        if percent is not None:
            amenities_dict['discount_percent'] = percent
        else:
            amenities_dict.pop('discount_percent', None)

        if amount is not None:
            amenities_dict['discount_amount'] = amount
        else:
            amenities_dict.pop('discount_amount', None)

        instance.amenities = amenities_dict
        if commit:
            instance.save()
        return instance


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    form = RoomForm
    list_display = (
        'name', 'accommodation', 'room_code', 'room_type',
        'price_per_night', 'get_discount_tag', 'capacity',
        'available_rooms', 'total_rooms', 'is_active',
    )
    list_filter = ('room_type', 'is_active', 'accommodation__area')
    search_fields = ('name', 'room_code', 'accommodation__name')
    autocomplete_fields = ('accommodation',)
    fieldsets = (
        ('Thông tin phòng', {
            'fields': ('accommodation', 'room_code', 'name', 'room_type', 'capacity', 'description')
        }),
        ('Giá & Khuyến mãi riêng phòng này', {
            'fields': ('price_per_night', 'discount_percent', 'discount_amount'),
            'description': '💡 Để trống nếu muốn dùng khuyến mãi chung của nơi lưu trú. Nhập vào đây để ghi đè riêng cho loại phòng này.',
        }),
        ('Số lượng & Trạng thái', {
            'fields': ('total_rooms', 'available_rooms', 'is_active')
        }),
        ('Tiện ích phòng', {
            'fields': ('amenities',),
            'classes': ('collapse',),
        }),
    )

    def get_discount_tag(self, obj):
        if not obj.has_discount:
            return "-"
        label = obj.discount_label
        source = "phòng" if (isinstance(obj.amenities, dict) and (
            'discount_percent' in obj.amenities or 'discount_amount' in obj.amenities
        )) else "chung"
        return format_html(
            '<span style="color:red;font-weight:bold;">{}</span> '
            '<span style="color:#94a3b8;font-size:11px;">({})</span>',
            label, source
        )

    get_discount_tag.short_description = "Khuyến mãi"


# ─── AccommodationReview Admin ────────────────────────────────────────────────
@admin.register(AccommodationReview)
class AccommodationReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'accommodation', 'score', 'short_comment', 'approved_icon', 'created_at')
    list_filter = ('is_approved', 'score', 'created_at')
    search_fields = ('user__username', 'accommodation__name', 'comment')
    ordering = ('is_approved', '-created_at')
    actions = ['approve_reviews', 'unapprove_reviews']

    def approved_icon(self, obj):
        if obj.is_approved:
            return format_html('<span style="color:green;font-weight:700;">✔ Đã duyệt</span>')
        return format_html('<span style="color:#dc2626;font-weight:700;">✘ Chờ duyệt</span>')

    approved_icon.short_description = "Trạng thái"

    def short_comment(self, obj):
        return obj.comment[:80] + ('...' if len(obj.comment) > 80 else '')

    short_comment.short_description = 'Bình luận'

    def approve_reviews(self, request, queryset):
        for review in queryset:
            if not review.is_approved:
                review.is_approved = True
                review.save()

    approve_reviews.short_description = "Duyệt các đánh giá đã chọn"

    def unapprove_reviews(self, request, queryset):
        for review in queryset:
            if review.is_approved:
                review.is_approved = False
                review.save()

    unapprove_reviews.short_description = "Hủy duyệt các đánh giá đã chọn"


# ─── Dashboard: bơm biến thống kê vào trang chủ Admin ───────────────────────
original_index = admin.site.index


def custom_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context['total_accommodations'] = Accommodation.objects.count()
    extra_context['total_users'] = User.objects.count()
    extra_context['total_reviews'] = AccommodationReview.objects.count()
    return original_index(request, extra_context=extra_context)


admin.site.index = custom_index
