from django.db import models

class Accommodation(models.Model):
    TYPE_CHOICES = [
        ('hotel', 'Hotel'),
        ('homestay', 'Homestay'),
        ('hostel', 'Hostel'),
        ('apartment', 'Apartment'),
    ]

    name = models.CharField(max_length=200)
    accommodation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    area = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    price_per_night = models.IntegerField()
    capacity = models.IntegerField()

    rating = models.FloatField(default=0)
    rate_count = models.IntegerField(default=0)

    amenities = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    def __str__(self):
        return self.name
    def update_rating(self, new_rating):
        self.rating = (self.rating * self.rate_count)/(self.rate_count+1) + new_rating/(self.rate_count+1)
        self.rate_count = self.rate_count + 1
        self.save()