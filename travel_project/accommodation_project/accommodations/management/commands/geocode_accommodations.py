from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from accommodations.models import Accommodation
from OpenStreetMap_API.services import build_accommodation_geocode_query, geocode_accommodation_address


class Command(BaseCommand):
    help = "Geocode accommodations missing latitude/longitude using the default free geocoder."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--force", action="store_true", help="Geocode every accommodation, even if coordinates exist.")
        parser.add_argument("--dry-run", action="store_true", help="Show queries without saving coordinates.")
        parser.add_argument("--sleep", type=float, default=1.0, help="Delay between geocoder calls for Nominatim friendliness.")

    def handle(self, *args, **options):
        queryset = Accommodation.objects.all().order_by("id")
        if not options["force"]:
            queryset = queryset.filter(latitude__isnull=True) | queryset.filter(longitude__isnull=True)
            queryset = queryset.order_by("id")
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        total = queryset.count() if hasattr(queryset, "count") else len(queryset)
        geocoded = 0
        skipped = 0
        failed = 0

        for accommodation in queryset:
            query = build_accommodation_geocode_query(accommodation)
            if options["dry_run"]:
                self.stdout.write(f"[dry-run] {accommodation.id}: {query}")
                skipped += 1
                continue

            result = geocode_accommodation_address(accommodation, save=True)
            if result:
                geocoded += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[ok] {accommodation.id}: {accommodation.name} -> {result['lat']:.6f}, {result['lon']:.6f}"
                    )
                )
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"[miss] {accommodation.id}: {query}"))

            if options["sleep"] > 0:
                time.sleep(options["sleep"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. scanned={total}, geocoded={geocoded}, skipped={skipped}, failed={failed}"
            )
        )
