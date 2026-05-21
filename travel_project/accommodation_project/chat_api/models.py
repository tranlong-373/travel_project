from django.db import models


class PlaceReference(models.Model):
    query_text = models.CharField(max_length=300, blank=True)
    normalized_query = models.CharField(max_length=300, blank=True, db_index=True)
    canonical_name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=220, unique=True, db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    kind = models.CharField(max_length=50, default="geocoded")
    latitude = models.FloatField()
    longitude = models.FloatField()
    default_radius_km = models.FloatField(default=5.0)
    district = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    provider = models.CharField(max_length=50, default="osm")
    source = models.CharField(max_length=50, default="cache")
    confidence = models.FloatField(default=0.0)
    provider_place_id = models.CharField(max_length=120, blank=True)
    query = models.CharField(max_length=300, blank=True)
    display_name = models.CharField(max_length=500, blank=True)
    address = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("canonical_name",)

    def __str__(self):
        return self.canonical_name
