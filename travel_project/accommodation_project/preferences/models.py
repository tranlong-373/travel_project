from django.db import models

class UserPreference(models.Model):
    TYPE_CHOICES = [
        ('hotel', 'Hotel'),
        ('homestay', 'Homestay'),
        ('hostel', 'Hostel'),
        ('apartment', 'Apartment'),
    ]

    area = models.CharField(max_length=100)
    budget = models.IntegerField()
    guest_count = models.IntegerField()
    preferred_type = models.CharField(max_length=20, choices=TYPE_CHOICES, blank=True, null=True)
    required_amenities = models.JSONField(default=list, blank=True)
    user_latitude = models.FloatField(blank=True, null=True)
    user_longitude = models.FloatField(blank=True, null=True)
    search_radius_km = models.FloatField(default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.area} - {self.budget}"
