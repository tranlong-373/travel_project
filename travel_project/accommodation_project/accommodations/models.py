from django.db import models
from django.contrib.auth.models import User


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
    image_url = models.URLField(blank=True, null=True)  # ← thêm dòng này
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.name


class AccommodationReview(models.Model):
    SCORE_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    accommodation = models.ForeignKey(Accommodation, on_delete=models.CASCADE)
    score = models.IntegerField(choices=SCORE_CHOICES)
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.accommodation.name} - {self.score}"

    def save(self, *args, **kwargs):
        old_is_approved = False

        if self.pk:
            old_review = AccommodationReview.objects.get(pk=self.pk)
            old_is_approved = old_review.is_approved

        super().save(*args, **kwargs)

        if self.is_approved and not old_is_approved:
            acc = self.accommodation
            old_total_score = acc.rating * acc.review_count
            new_total_score = old_total_score + self.score

            acc.review_count += 1
            acc.rating = new_total_score / acc.review_count
            acc.save()