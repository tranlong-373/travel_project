import json
from django.core.management.base import BaseCommand
from chat_api.schema import SCHEMA_VERSION, SLOTS, empty_slots

class Command(BaseCommand):
    help = "Export chat_api schema to JSON."

    def add_arguments(self, parser):
        parser.add_argument("--out", type=str, default="chat_api_schema.json")

    def handle(self, *args, **options):
        out = {
            "schema_version": SCHEMA_VERSION,
            "slots_shape": empty_slots(),
            "slots": {
                k: {
                    "level": spec.level,
                    "value_type": spec.value_type,
                    "description": spec.description,
                    "allowed": sorted(list(spec.allowed)) if spec.allowed else None,
                    "question_vi": spec.question_vi,
                    "question_en": spec.question_en,
                }
                for k, spec in SLOTS.items()
            },
        }
        path = options["out"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f"Exported schema to {path}"))
