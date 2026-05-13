from django.contrib import admin
from django.utils.html import format_html

from .models import Accommodation, AccommodationReview, Room


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0
    fields = (
        'room_code',
        'name',
        'room_type',
        'price_per_night',
        'capacity',
        'total_rooms',
        'available_rooms',
        'is_active',
    )


class ReviewInline(admin.TabularInline):
    model = AccommodationReview
    extra = 0
    fields = ('user', 'score', 'comment', 'is_approved', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = (
        'image_preview',
        'name',
        'accommodation_code',
        'accommodation_type',
        'area',
        'price_per_night',
        'capacity',
        'rating',
        'review_count',
        'room_count',
    )
    list_filter = ('accommodation_type', 'area', 'rating')
    search_fields = ('name', 'accommodation_code', 'area', 'address')
    readonly_fields = ('image_preview_large', 'rating', 'review_count')
    inlines = [RoomInline, ReviewInline]
    fieldsets = (
        ('Thong tin chinh', {
            'fields': (
                'image_preview_large',
                'image_url',
                'accommodation_code',
                'name',
                'accommodation_type',
                'area',
                'address',
                'hotline',
            )
        }),
        ('Gia va suc chua', {
            'fields': ('price_per_night', 'capacity')
        }),
        ('Danh gia', {
            'fields': ('rating', 'review_count')
        }),
        ('Mo ta va tien ich', {
            'fields': ('description', 'amenities')
        }),
        ('Toa do ban do', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',),
        }),
    )

    def image_preview(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="width:64px;height:44px;object-fit:cover;border-radius:6px;" />',
                obj.image_url,
            )
        return format_html('<span style="color:#94a3b8;">No image</span>')

    image_preview.short_description = 'Image'

    def image_preview_large(self, obj):
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width:320px;max-height:180px;object-fit:cover;border-radius:8px;" />',
                obj.image_url,
            )
        return 'No image'

    image_preview_large.short_description = 'Image preview'

    def room_count(self, obj):
        return obj.rooms.count()

    room_count.short_description = 'Rooms'


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'accommodation',
        'room_code',
        'room_type',
        'price_per_night',
        'capacity',
        'available_rooms',
        'total_rooms',
        'is_active',
    )
    list_filter = ('room_type', 'is_active', 'accommodation__area')
    search_fields = ('name', 'room_code', 'accommodation__name')
    autocomplete_fields = ('accommodation',)


@admin.register(AccommodationReview)
class AccommodationReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'accommodation', 'score', 'short_comment', 'approved_status', 'created_at')
    list_filter = ('is_approved', 'score', 'created_at')
    search_fields = ('user__username', 'accommodation__name', 'comment')
    autocomplete_fields = ('user', 'accommodation')
    ordering = ('is_approved', '-created_at')
    actions = ['approve_reviews', 'unapprove_reviews']

    def approved_status(self, obj):
        if obj.is_approved:
            return format_html('<span style="color:green;font-weight:700;">Approved</span>')
        return format_html('<span style="color:#dc2626;font-weight:700;">Pending</span>')

    approved_status.short_description = 'Status'

    def short_comment(self, obj):
        return obj.comment[:80] + ('...' if len(obj.comment) > 80 else '')

    short_comment.short_description = 'Comment'

    def approve_reviews(self, request, queryset):
        for review in queryset:
            if not review.is_approved:
                review.is_approved = True
                review.save()

    approve_reviews.short_description = 'Approve selected reviews'

    def unapprove_reviews(self, request, queryset):
        for review in queryset:
            if review.is_approved:
                review.is_approved = False
                review.save()

    unapprove_reviews.short_description = 'Unapprove selected reviews'
