from django.contrib import admin
from django.utils.html import format_html
from .models import Accommodation, AccommodationReview

@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = ('name', 'accommodation_code', 'area', 'price_per_night', 'rating', 'review_count')
    search_fields = ('name', 'accommodation_code', 'area')


@admin.register(AccommodationReview)
class AccommodationReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'accommodation', 'score', 'approved_icon', 'created_at')
    list_filter = ('is_approved',)
    ordering = ('is_approved', '-created_at')
    actions = ['approve_reviews']

    # 🔥 hiển thị dấu tích
    def approved_icon(self, obj):
        if obj.is_approved:
            return format_html('<span style="color:green;">✔</span>')
        return format_html('<span style="color:red;">✘</span>')
    
    approved_icon.short_description = "Duyệt"

    # 🔥 action duyệt hàng loạt
    def approve_reviews(self, request, queryset):
        for review in queryset:
            if not review.is_approved:
                review.is_approved = True
                review.save()

    approve_reviews.short_description = "Duyệt các đánh giá đã chọn"