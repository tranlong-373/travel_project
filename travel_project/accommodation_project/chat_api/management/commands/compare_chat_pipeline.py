"""
Management command: compare_chat_pipeline

Runs each query from an input file through both the v1 (parse_user_text) and
v2 (SearchIntentBuilder) pipelines, then prints a comparison report.

Usage:
  python manage.py compare_chat_pipeline --input-file docs/claude/sample_queries.txt
  python manage.py compare_chat_pipeline --input-file queries.txt --limit 20 --verbose
"""
from __future__ import annotations

import sys
import time
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand


# ── Severity helpers ──────────────────────────────────────────────────────────

_CRITICAL_KEYS = {"location_mode", "location_status", "budget", "guest_count", "area"}
_ACCEPTABLE_KEYS = {"confidence", "display_label", "provider", "parser_mode", "input_kind"}


def _v1_summary(parse_result: dict[str, Any]) -> dict[str, Any]:
    slots = parse_result.get("slots", {})
    return {
        "location_status": parse_result.get("location_status"),
        "location_mode":   parse_result.get("location_mode"),
        "input_kind":      parse_result.get("input_type"),
        "area":            parse_result.get("canonical_area") or slots.get("area"),
        "budget":          slots.get("budget_max") or slots.get("budget"),
        "guest_count":     slots.get("guest_count"),
        "trip_days":       slots.get("trip_days"),
        "amenities":       sorted(slots.get("required_amenities") or []),
        "acc_types":       sorted(slots.get("accommodation_types") or []),
        "ready":           parse_result.get("ready_for_recommendation"),
    }


def _v2_summary(intent: Any) -> dict[str, Any]:
    loc = intent.location
    return {
        "location_status": loc.status.value if loc.status else None,
        "location_mode":   loc.mode.value if loc.mode else None,
        "input_kind":      intent.input_kind,
        "area":            intent.area or loc.canonical_area,
        "budget":          intent.budget_max or intent.budget,
        "guest_count":     intent.guest_count,
        "trip_days":       intent.trip_days,
        "amenities":       sorted(intent.required_amenities or []),
        "acc_types":       sorted(intent.accommodation_types or []),
        "ready":           None,  # v2 doesn't expose this directly
    }


def _diff_keys(v1: dict, v2: dict) -> dict[str, tuple]:
    """Return keys where values differ."""
    all_keys = set(v1) | set(v2)
    return {k: (v1.get(k), v2.get(k)) for k in all_keys if v1.get(k) != v2.get(k)}


def _severity(diff: dict[str, tuple]) -> str:
    """Classify divergence as same / acceptable / risky."""
    if not diff:
        return "same"
    diff_keys = set(diff)
    if diff_keys & _CRITICAL_KEYS:
        return "risky"
    if diff_keys <= _ACCEPTABLE_KEYS:
        return "acceptable"
    return "acceptable"


_SEVERITY_COLOR = {
    "same":       "\033[32m",   # green
    "acceptable": "\033[33m",   # yellow
    "risky":      "\033[31m",   # red
}
_RESET = "\033[0m"


def _color(text: str, severity: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{_SEVERITY_COLOR.get(severity, '')}{text}{_RESET}"


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Compare v1 (parse_user_text) vs v2 (SearchIntentBuilder) pipeline output"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--input-file",
            required=True,
            metavar="PATH",
            help="Path to a text file with one query per line",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            help="Process only the first N queries",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Print full v1/v2 summaries for every query",
        )

    def handle(self, *args, **options) -> None:
        input_file: str = options["input_file"]
        limit: int | None = options["limit"]
        verbose: bool = options["verbose"]
        use_color: bool = sys.stdout.isatty()

        try:
            with open(input_file, encoding="utf-8") as fh:
                lines = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {input_file}"))
            return

        if limit is not None:
            lines = lines[:limit]

        if not lines:
            self.stdout.write("No queries found.")
            return

        # Import here so Django is fully initialised
        from chat_api.parser_service import parse_user_text
        from chat_api.nlu.search_intent_builder import SearchIntentBuilder

        builder = SearchIntentBuilder()

        stats = {"same": 0, "acceptable": 0, "risky": 0, "error": 0}
        risky_queries: list[str] = []

        self.stdout.write(f"\n{'═' * 70}")
        self.stdout.write(f"  Pipeline comparison — {len(lines)} queries")
        self.stdout.write(f"{'═' * 70}\n")

        for i, query in enumerate(lines, start=1):
            # ── v1 ──────────────────────────────────────────────────────────
            v1_result: dict = {}
            v1_err: str | None = None
            try:
                t0 = time.perf_counter()
                v1_result = parse_user_text(query)
                v1_ms = round((time.perf_counter() - t0) * 1000, 1)
                v1_sum = _v1_summary(v1_result)
            except Exception as exc:
                v1_err = str(exc)
                v1_sum = {}
                v1_ms = 0.0

            # ── v2 ──────────────────────────────────────────────────────────
            v2_intent = None
            v2_err: str | None = None
            try:
                t0 = time.perf_counter()
                v2_intent = builder.build(query, include_debug=False)
                v2_ms = round((time.perf_counter() - t0) * 1000, 1)
                v2_sum = _v2_summary(v2_intent)
            except Exception as exc:
                v2_err = str(exc)
                v2_sum = {}
                v2_ms = 0.0

            if v1_err or v2_err:
                stats["error"] += 1
                severity = "risky"
            else:
                diff = _diff_keys(v1_sum, v2_sum)
                severity = _severity(diff)
                stats[severity] += 1
                if severity == "risky":
                    risky_queries.append(query)

            severity_label = _color(severity.upper(), severity, use_color)

            self.stdout.write(f"[{i:3d}] {severity_label}  {query!r}")

            if v1_err:
                self.stdout.write(f"       v1 ERROR: {v1_err}")
            if v2_err:
                self.stdout.write(f"       v2 ERROR: {v2_err}")

            if verbose and not v1_err and not v2_err:
                self.stdout.write(f"       v1 ({v1_ms}ms): {v1_sum}")
                self.stdout.write(f"       v2 ({v2_ms}ms): {v2_sum}")

                diff = _diff_keys(v1_sum, v2_sum)
                if diff:
                    self.stdout.write(f"       diff keys:")
                    for key, (old, new) in diff.items():
                        self.stdout.write(f"         {key}: {old!r} → {new!r}")
            elif not v1_err and not v2_err and severity != "same":
                diff = _diff_keys(v1_sum, v2_sum)
                if diff:
                    diff_keys_str = ", ".join(sorted(diff))
                    self.stdout.write(f"       diff: [{diff_keys_str}]")

        # ── Summary ──────────────────────────────────────────────────────────
        self.stdout.write(f"\n{'─' * 70}")
        self.stdout.write("  Summary")
        self.stdout.write(f"{'─' * 70}")
        total = len(lines)
        self.stdout.write(
            f"  Total  : {total}\n"
            f"  {_color('Same      ', 'same', use_color)}: {stats['same']} "
            f"({100 * stats['same'] // total}%)\n"
            f"  {_color('Acceptable', 'acceptable', use_color)}: {stats['acceptable']} "
            f"({100 * stats['acceptable'] // total}%)\n"
            f"  {_color('Risky     ', 'risky', use_color)}: {stats['risky']} "
            f"({100 * stats['risky'] // total}%)\n"
            f"  Error   : {stats['error']}"
        )

        if risky_queries:
            self.stdout.write(f"\n{'─' * 70}")
            self.stdout.write("  Risky queries (manual review recommended):")
            for q in risky_queries:
                self.stdout.write(f"    • {q!r}")

        self.stdout.write(f"{'═' * 70}\n")
