from django.contrib import admin

from .models import UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('area', 'budget', 'guest_count', 'preferred_type', 'location_text', 'amenities_text', 'created_at')
    list_filter = ('preferred_type', 'area', 'created_at')
    search_fields = ('area', 'preferred_type')
    readonly_fields = ('created_at',)

    def amenities_text(self, obj):
        return ', '.join(obj.required_amenities or []) or 'None'

    amenities_text.short_description = 'Amenities'

    def location_text(self, obj):
        if obj.user_latitude is None or obj.user_longitude is None:
            return 'None'
        return f'{obj.user_latitude:.5f}, {obj.user_longitude:.5f}'

    location_text.short_description = 'Current location'
