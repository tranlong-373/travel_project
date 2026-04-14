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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.area} - {self.budget}"
