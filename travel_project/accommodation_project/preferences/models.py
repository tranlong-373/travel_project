from django.db import models

class UserPreference(models.Model):
    TYPE_CHOICES = [
        ('hotel', 'Hotel'),
        ('homestay', 'Homestay'),
        ('hostel', 'Hostel'),
        ('apartment', 'Apartment'),
    ]

    area = models.CharField(max_length=100, blank=True, null=True)
    budget = models.IntegerField()
    guest_count = models.IntegerField()
    preferred_type = models.CharField(max_length=20, choices=TYPE_CHOICES, blank=True, null=True)
    required_amenities = models.JSONField(default=list, blank=True)
    location_mode = models.CharField(max_length=32, blank=True, default='unknown')
    location_label = models.CharField(max_length=150, blank=True, null=True)
    anchor_kind = models.CharField(max_length=32, blank=True, null=True)
    filter_tree_json = models.JSONField(default=dict, blank=True)
    soft_filter_summary = models.TextField(blank=True)
    user_latitude = models.FloatField(blank=True, null=True)
    user_longitude = models.FloatField(blank=True, null=True)
    search_radius_km = models.FloatField(default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        area = self.area or self.location_label or 'Không giới hạn khu vực'
        return f"{area} - {self.budget}"
