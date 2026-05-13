from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.utils.html import format_html, format_html_join

from .models import Favorite, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('avatar_preview', 'user', 'full_name', 'phone', 'address', 'favorite_count', 'firebase_uid')
    search_fields = ('user__username', 'user__email', 'full_name', 'phone', 'firebase_uid')
    list_select_related = ('user',)
    readonly_fields = ('avatar_preview_large', 'favorite_hotels')
    fieldsets = (
        ('User', {
            'fields': ('user', 'firebase_uid')
        }),
        ('Profile', {
            'fields': ('avatar_preview_large', 'avatar', 'avatar_url', 'full_name', 'phone', 'address')
        }),
        ('Favorites', {
            'fields': ('favorite_hotels',)
        }),
    )

    def avatar_preview(self, obj):
        image_url = obj.avatar.url if obj.avatar else obj.avatar_url
        if image_url:
            return format_html(
                '<img src="{}" style="width:42px;height:42px;object-fit:cover;border-radius:50%;" />',
                image_url,
            )
        return format_html(
            '<span style="display:inline-flex;width:42px;height:42px;border-radius:50%;background:#dbeafe;'
            'align-items:center;justify-content:center;color:#1565c0;font-weight:700;">{}</span>',
            obj.user.username[:1].upper(),
        )

    avatar_preview.short_description = 'Avatar'

    def avatar_preview_large(self, obj):
        if not obj:
            return 'Save first to preview avatar'
        image_url = obj.avatar.url if obj.avatar else obj.avatar_url
        if image_url:
            return format_html(
                '<img src="{}" style="width:120px;height:120px;object-fit:cover;border-radius:50%;" />',
                image_url,
            )
        return 'No avatar'

    avatar_preview_large.short_description = 'Avatar preview'

    def favorite_count(self, obj):
        return Favorite.objects.filter(user=obj.user).count()

    favorite_count.short_description = 'Favorites'

    def favorite_hotels(self, obj):
        favorites = Favorite.objects.filter(user=obj.user).select_related('accommodation').order_by('-created_at')
        if not favorites:
            return 'No favorite hotels'
        items = format_html_join(
            '',
            '<li>{} <span style="color:#64748b;">({})</span></li>',
            (
                (favorite.accommodation.name, favorite.created_at.strftime('%d/%m/%Y'))
                for favorite in favorites
            ),
        )
        return format_html('<ul style="margin:0;padding-left:18px;">{}</ul>', items)

    favorite_hotels.short_description = 'Favorite hotels'


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'accommodation', 'created_at')
    search_fields = ('user__username', 'accommodation__name')
    list_filter = ('created_at',)


# ─── Audit Logs: Lịch sử hoạt động Admin (Read-only) ─────────────────────────
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message')
    list_filter = ('action_time', 'user', 'content_type')
    search_fields = ('object_repr', 'change_message')
    date_hierarchy = 'action_time'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
