#!/usr/bin/env python3
"""
Agent 3: the mandate-aware public-domain forecast (Package 1).

The calendar answers "what enters the public domain, and when". This answers the
question a producer actually has: **"what is worth waiting for?"**

It joins `data/pd_calendar.csv` against Package 4's `data/studio_scores.csv`,
keeps the books that score well against the current mandate, and reports the best
of them in date order — capped at 10 titles across a 10-year horizon.

    python3 pd_calendar/scripts/build_forecast.py
    python3 pd_calendar/scripts/build_forecast.py --limit 10 --horizon 10

Outputs `data/pd_forecast.csv` (schema in docs/data-contracts.md) and
`data/pd_forecast.md`.

WHY THIS IS A SEPARATE FILE FROM pd_calendar.csv
------------------------------------------------
Different grain and different question. The calendar is every work crossing a
cliff, one row per work, no opinion about quality. The forecast is a ranked
top-N with an opinion, and it exists only when Package 4 has scored the corpus.
Keeping them apart means the calendar never breaks when scores are missing, and
nothing that already reads the calendar has to change.

DEGRADES, DOES NOT FAIL
-----------------------
`studio_scores.csv` is Package 4's output and is not present on every branch. If
it is missing the script says so and exits 0 without writing a forecast, because
"no scores yet" is a normal state, not an error.

A NOTE ON WHAT A DATE HERE MEANS
--------------------------------
A row is a scheduled term expiry, not cleared rights. `confidence` carries
through from the calendar: `confirmed` means a renewal record was found and the
full 95-year term is running, so the date is solid. `uncertain` means it is the
latest possible date and the work may already be free, or may be a foreign work
the URAA restored. Package 2 is what confirms a specific claim; this only says
when a term is scheduled to end.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pd_rules import next_cliffs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

CALENDAR_PATH = DATA_DIR / "pd_calendar.csv"
# Package 4 scores the main corpus; the renewal-era batch is a separate corpus
# file and can be scored into its own output rather than appended to Chantell's.
# Same pattern as the calendar's renewal sources: read whatever exists, never
# require one file to be rewritten to accommodate another.
SCORES_PATHS = [
    DATA_DIR / "studio_scores.csv",
    DATA_DIR / "studio_scores_renewal.csv",
]
CSV_OUT_PATH = DATA_DIR / "pd_forecast.csv"
REPORT_OUT_PATH = DATA_DIR / "pd_forecast.md"

DEFAULT_LIMIT = 10
DEFAULT_HORIZON = 10

FIELDNAMES = [
    "rank",
    "pd_date",
    "book_id",
    "title",
    "author",
    "publication_year",
    "total_score",
    "score_reasoning",
    "confidence",
    "rule_applied",
    "flags",
    "years_away",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value: str | None) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def build_rows(calendar: list[dict], scores: dict, cliffs: list[int], limit: int,
               as_of_year: int) -> tuple[list[dict], dict]:
    """Rank scored calendar entries inside the horizon. Returns (rows, funnel)."""
    years = {str(y) for y in cliffs}
    in_window = [r for r in calendar if (r.get("pd_date") or "")[:4] in years]

    scored, unscored = [], 0
    for r in in_window:
        s = scores.get(r.get("book_id"))
        value = to_float(s.get("total_score")) if s else None
        if value is None:
            unscored += 1
            continue
        scored.append((value, s, r))

    # Highest score first; ties broken by the sooner date, since a producer can
    # act on a nearer one.
    scored.sort(key=lambda t: (-t[0], t[2]["pd_date"]))
    kept = scored[:limit]

    rows = []
    for i, (value, s, r) in enumerate(kept, start=1):
        year = int(r["pd_date"][:4])
        rows.append({
            "rank": i,
            "pd_date": r["pd_date"],
            "book_id": r["book_id"],
            "title": r.get("title", ""),
            "author": r.get("author", ""),
            "publication_year": r.get("publication_year", ""),
            "total_score": f"{value:g}",
            "score_reasoning": s.get("reasoning", ""),
            "confidence": r.get("confidence", ""),
            "rule_applied": r.get("rule_applied", ""),
            "flags": r.get("flags", ""),
            "years_away": year - as_of_year,
        })

    funnel = {
        "calendar": len(calendar),
        "in_window": len(in_window),
        "scored": len(scored),
        "unscored": unscored,
        "reported": len(rows),
        "dropped": max(0, len(scored) - len(rows)),
    }
    return rows, funnel


def write_report(path: Path, rows: list[dict], funnel: dict, cliffs: list[int],
                 as_of_year: int) -> None:
    lines = [
        "# Public Domain Forecast",
        "",
        f"The highest-scoring books against the current studio mandate that are **not yet** in the "
        f"public domain, but will be between {cliffs[0]} and {cliffs[-1]}.",
        "",
        "A producer who wants one of these can start developing now and be ready to shoot the "
        "January they become free.",
        "",
        "| | count |",
        "|---|---|",
        f"| Works crossing a cliff in the window | {funnel['in_window']} |",
        f"| ...that Package 4 has scored | {funnel['scored']} |",
        f"| ...not yet scored | {funnel['unscored']} |",
        f"| Reported below | {funnel['reported']} |",
        f"| Scored but ranked out | {funnel['dropped']} |",
        "",
    ]

    if not rows:
        lines += [
            "## Nothing to report",
            "",
            "No scored work crosses a cliff inside the horizon. That is a real answer: it means "
            "everything worth adapting in this corpus is already available, and waiting buys "
            "nothing.",
            "",
        ]
    else:
        by_year: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_year[r["pd_date"][:4]].append(r)
        for year in sorted(by_year):
            lines += [f"## January 1, {year}", ""]
            for r in by_year[year]:
                wait = r["years_away"]
                mark = "confirmed date" if r["confidence"] == "confirmed" else "date not yet certain"
                lines.append(
                    f"**{r['rank']}. {r['title']}** — {r['author']}  \n"
                    f"score {r['total_score']} · published {r['publication_year']} · "
                    f"{wait} year{'s' if wait != 1 else ''} away · {mark}"
                )
                if r["score_reasoning"]:
                    lines.append(f"> {r['score_reasoning']}")
                lines.append("")

        lines += [
            "## Reading the dates",
            "",
            "**A date here is a scheduled term expiry, not cleared rights.** `confirmed` means a "
            "copyright renewal is on record, so the full 95-year term is running and the date is "
            "solid. Anything else is the *latest possible* date — the work may already be free if "
            "its copyright was never renewed, or may be a foreign work whose US copyright the URAA "
            "restored. Package 2 confirms a specific claim; this only says when a term is "
            "scheduled to end.",
            "",
        ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rank forthcoming public-domain books by mandate fit")
    p.add_argument("--calendar", type=Path, default=CALENDAR_PATH)
    p.add_argument("--scores", type=Path, nargs="*", default=SCORES_PATHS,
                   help="score files keyed by book_id; all present files are merged")
    p.add_argument("--output", type=Path, default=CSV_OUT_PATH)
    p.add_argument("--report", type=Path, default=REPORT_OUT_PATH)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    p.add_argument("--as-of-year", type=int, default=None)
    args = p.parse_args(argv)

    if not args.calendar.exists():
        print(f"error: {args.calendar} not found — run build_calendar.py first", file=sys.stderr)
        return 1

    present = [p for p in args.scores if p.exists()]
    if not present:
        names = ", ".join(str(p) for p in args.scores)
        print(
            f"No forecast written: none of {names} found.\n"
            "  Package 4 has not scored this corpus on this branch. The forecast needs scores to\n"
            "  rank by; the calendar itself is unaffected.",
            file=sys.stderr,
        )
        return 0

    calendar = read_csv(args.calendar)
    scores: dict = {}
    for path in present:
        for r in read_csv(path):
            if r.get("book_id"):
                scores.setdefault(r["book_id"], r)

    as_of = args.as_of_year
    if as_of is None:
        import datetime as _dt
        as_of = _dt.date.today().year
    cliffs = next_cliffs(as_of, args.horizon)

    rows, funnel = build_rows(calendar, scores, cliffs, args.limit, as_of)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    write_report(args.report, rows, funnel, cliffs, as_of)

    print(f"Score sources: {', '.join(p.name for p in present)}", file=sys.stderr)
    print(f"Calendar entries in {cliffs[0]}-{cliffs[-1]}: {funnel['in_window']}", file=sys.stderr)
    print(f"  scored by Package 4: {funnel['scored']}   unscored: {funnel['unscored']}", file=sys.stderr)
    print(f"  reported: {funnel['reported']}   ranked out: {funnel['dropped']}", file=sys.stderr)
    print(f"Wrote {args.output}", file=sys.stderr)
    print(f"Wrote {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
