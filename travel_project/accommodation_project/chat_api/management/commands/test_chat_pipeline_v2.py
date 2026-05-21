"""
Management command: test_chat_pipeline_v2

Runs queries through the v2 pipeline only.
No v1 pipeline. No DB writes. No UserPreference created.

Usage:
  python manage.py test_chat_pipeline_v2 --input-file docs/claude/sample_queries.txt
  python manage.py test_chat_pipeline_v2 --input-file docs/claude/sample_queries_200.txt --limit 50 --verbose
  python manage.py test_chat_pipeline_v2 --input-file queries.txt --fail-on-core-error
"""
from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand


CORE_GROUPS = [
    "specific_address",
    "landmark_or_poi",
    "generic_poi_in_area",
    "hotel_name",
    "amenity_only",
    "near_user",
    "area",
    "anywhere",
    "mixed_search",
    "unknown",
]

_SEP = "─" * 70
_SEP_THICK = "═" * 70


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "  0"
    return f"{round(100 * n / total):3d}"


def _load_queries(path: str, limit: int | None) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            queries = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    except FileNotFoundError:
        raise SystemExit(f"ERROR: Input file not found: {path}")
    if limit:
        queries = queries[:limit]
    return queries


_NO_LOCATION_KINDS = frozenset({"amenity_only", "anywhere"})


def _cat(loc_status: str, loc_mode: str, needs_gps: bool, input_kind: str) -> str:
    if needs_gps:
        return "needs_user_location"
    if loc_status == "ok":
        return "ok"
    if loc_mode == "anywhere":
        return "ok"
    if loc_status in {"ambiguous", "unsupported"}:
        return "ambiguous"
    # amenity_only / anywhere with unresolved location is expected — no location needed
    if input_kind in _NO_LOCATION_KINDS:
        return "ok"
    # hotel_name:unresolved is expected when DB is empty — count as ok
    if input_kind == "hotel_name" and loc_mode == "hotel_name":
        return "ok"
    return "unresolved"


class Command(BaseCommand):
    help = "Test v2 chat pipeline (no v1, no DB writes)"

    def add_arguments(self, parser):
        parser.add_argument("--input-file", required=True, help="Path to query file (one query per line)")
        parser.add_argument("--limit", type=int, default=None, help="Max queries to run")
        parser.add_argument("--verbose", action="store_true", help="Print each query result")
        parser.add_argument("--fail-on-core-error", action="store_true", help="Exit 1 if any query raises an exception")

    def handle(self, *args, **options):
        from chat_api.nlu.search_intent_builder import SearchIntentBuilder

        queries = _load_queries(options["input_file"], options["limit"])
        builder = SearchIntentBuilder()
        verbose = options["verbose"]

        stats: dict[str, int] = {
            "total": 0,
            "ok": 0,
            "ambiguous": 0,
            "unresolved": 0,
            "needs_user_location": 0,
            "error": 0,
        }
        _empty_gs = lambda: {k: 0 for k in stats}
        group_stats: dict[str, dict[str, int]] = {g: _empty_gs() for g in CORE_GROUPS}
        group_stats["other"] = _empty_gs()

        risky: list[tuple[str, str, dict[str, Any]]] = []

        self.stdout.write(_SEP_THICK)
        self.stdout.write(f"  V2 pipeline test — {len(queries)} queries")
        self.stdout.write(_SEP_THICK)

        for q in queries:
            stats["total"] += 1
            t0 = time.perf_counter()

            try:
                intent = builder.build(q)
                elapsed_ms = (time.perf_counter() - t0) * 1000

                loc = intent.location
                loc_status = loc.status.value
                loc_mode = loc.mode.value
                needs_gps = bool(loc.debug.get("needs_user_location"))

                outcome = _cat(loc_status, loc_mode, needs_gps, intent.input_kind)
                stats[outcome] += 1

                group = intent.input_kind if intent.input_kind in CORE_GROUPS else "other"
                group_stats[group]["total"] += 1
                group_stats[group][outcome] += 1

                is_risky = outcome in {"ambiguous"} or (
                    outcome == "unresolved" and intent.input_kind not in {"hotel_name", "specific_address", "near_user"}
                )
                if is_risky:
                    risky.append((
                        q,
                        outcome,
                        {
                            "input_kind": intent.input_kind,
                            "loc_mode": loc_mode,
                            "loc_status": loc_status,
                            "area": intent.area,
                            "amenities": intent.required_amenities,
                        },
                    ))

                if verbose:
                    flag = "⚠" if is_risky else " "
                    self.stdout.write(
                        f"[{stats['total']:3d}]{flag} {outcome.upper():20s} {q!r}"
                    )
                    self.stdout.write(
                        f"       kind={intent.input_kind}, mode={loc_mode}, status={loc_status}"
                        f", area={intent.area!r}, amen={intent.required_amenities}"
                        f", budget={intent.budget_max or intent.budget}, gc={intent.guest_count}"
                        f"  ({elapsed_ms:.1f}ms)"
                    )

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                stats["error"] += 1
                group_stats["other"]["total"] += 1
                group_stats["other"]["error"] += 1
                risky.append((q, "error", {"exc": str(exc)}))
                self.stdout.write(f"[{stats['total']:3d}]✗ ERROR               {q!r}")
                self.stdout.write(f"       {exc}  ({elapsed_ms:.1f}ms)")

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(_SEP_THICK)
        self.stdout.write("  SUMMARY")
        self.stdout.write(_SEP_THICK)
        t = stats["total"]
        self.stdout.write(f"  Total              : {t}")
        self.stdout.write(f"  ok                 : {stats['ok']:3d}  ({_pct(stats['ok'], t)}%)")
        self.stdout.write(f"  unresolved         : {stats['unresolved']:3d}  ({_pct(stats['unresolved'], t)}%)")
        self.stdout.write(f"  ambiguous          : {stats['ambiguous']:3d}  ({_pct(stats['ambiguous'], t)}%)")
        self.stdout.write(f"  needs_user_location: {stats['needs_user_location']:3d}  ({_pct(stats['needs_user_location'], t)}%)")
        self.stdout.write(f"  error              : {stats['error']:3d}  ({_pct(stats['error'], t)}%)")

        self.stdout.write("")
        self.stdout.write(_SEP)
        self.stdout.write("  Per input_kind:")
        self.stdout.write(_SEP)
        for g in CORE_GROUPS + ["other"]:
            gs = group_stats[g]
            if gs["total"] == 0:
                continue
            self.stdout.write(
                f"  {g:25s}: {gs['total']:3d} total"
                f" | ok={gs['ok']:3d}({_pct(gs['ok'], gs['total'])}%)"
                f" | ambig={gs['ambiguous']:2d}"
                f" | unres={gs['unresolved']:2d}"
                f" | needs_gps={gs['needs_user_location']:2d}"
                f" | err={gs['error']:2d}"
            )

        if risky:
            self.stdout.write("")
            self.stdout.write(_SEP)
            self.stdout.write("  Risky / error queries:")
            self.stdout.write(_SEP)
            for q, outcome, details in risky:
                self.stdout.write(f"  [{outcome.upper():<20}] {q!r}")
                if verbose:
                    self.stdout.write(f"    {details}")

        self.stdout.write(_SEP_THICK)

        if options["fail_on_core_error"] and stats["error"] > 0:
            raise SystemExit(1)
