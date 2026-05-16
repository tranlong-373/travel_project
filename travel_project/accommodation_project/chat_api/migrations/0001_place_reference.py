from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PlaceReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("canonical_name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(db_index=True, max_length=220, unique=True)),
                ("aliases", models.JSONField(blank=True, default=list)),
                ("kind", models.CharField(default="geocoded", max_length=50)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("default_radius_km", models.FloatField(default=5.0)),
                ("provider", models.CharField(default="osm", max_length=50)),
                ("source", models.CharField(default="cache", max_length=50)),
                ("confidence", models.FloatField(default=0.0)),
                ("provider_place_id", models.CharField(blank=True, max_length=120)),
                ("query", models.CharField(blank=True, max_length=300)),
                ("display_name", models.CharField(blank=True, max_length=500)),
                ("address", models.JSONField(blank=True, default=dict)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("canonical_name",),
            },
        ),
    ]
