from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg


class Accommodation(models.Model):
    TYPE_CHOICES = [
        ('hotel', 'Hotel'),
        ('homestay', 'Homestay'),
        ('hostel', 'Hostel'),
        ('apartment', 'Apartment'),
    ]

    accommodation_code = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=200)
    accommodation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    area = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    price_per_night = models.IntegerField()
    capacity = models.IntegerField()

    rating = models.FloatField(default=0)
    review_count = models.IntegerField(default=0)

    amenities = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # ✅ thêm hotline
    hotline = models.CharField(max_length=20, blank=True)
    # Sau này sẽ update model room để hiển thị rõ hơn thông tin chi tiết 
    # Hiện tại bộ nhớ chưa cho phép :333
    def __str__(self):
        return self.name


def update_accommodation_rating(accommodation):
    approved_reviews = AccommodationReview.objects.filter(
        accommodation=accommodation,
        is_approved=True
    )

    review_count = approved_reviews.count()
    avg_rating = approved_reviews.aggregate(avg=Avg('score'))['avg'] or 0

    accommodation.review_count = review_count
    accommodation.rating = round(avg_rating, 2)

    accommodation.save(update_fields=['review_count', 'rating'])

class AccommodationReview(models.Model):
    SCORE_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    accommodation = models.ForeignKey(
        Accommodation,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    score = models.IntegerField(choices=SCORE_CHOICES)
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.accommodation.name} - {self.score}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        update_accommodation_rating(self.accommodation)

    def delete(self, *args, **kwargs):
        accommodation = self.accommodation
        super().delete(*args, **kwargs)
        update_accommodation_rating(accommodation)