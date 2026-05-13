from django.contrib import admin

from .models import UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('area', 'budget', 'guest_count', 'preferred_type', 'amenities_text', 'created_at')
    list_filter = ('preferred_type', 'area', 'created_at')
    search_fields = ('area', 'preferred_type')
    readonly_fields = ('created_at',)

    def amenities_text(self, obj):
        return ', '.join(obj.required_amenities or []) or 'None'

    amenities_text.short_description = 'Amenities'
