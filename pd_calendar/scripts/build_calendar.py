#!/usr/bin/env python3
"""
Builds the Forward-Looking PD Calendar (Package 1) from the book corpus.

Reads data/book_corpus.csv (Package 3), applies the term rules in pd_rules.py to
every row, and writes:

  - data/pd_calendar.csv  — the contract file, schema in docs/data-contracts.md
  - data/pd_calendar.md   — the readable report the brief asks for
                            (Year -> Authors entering PD -> Notable works)

Usage from the repo root:

    python3 pd_calendar/scripts/build_calendar.py
    python3 pd_calendar/scripts/build_calendar.py --as-of-year 2026 --horizon 5
    python3 pd_calendar/scripts/build_calendar.py --all      # every book, not just the window

WHAT GOES IN THE CSV
--------------------
By default, only works crossing one of the next `--horizon` January 1st cliffs --
that is what makes this a calendar rather than a dump of the corpus. `--all`
writes every row instead, including works whose term expired long ago and works
with no determinable date, which is the mode to use when auditing the rules
against the whole corpus.

Either way the funnel is printed to stderr: how many rows were read, how many
were already public domain, how many could not be dated and why. Nothing is
dropped silently -- a calendar that quietly discards half its input looks
identical to one that found nothing.

WHY as_of_year IS EXPLICIT
--------------------------
It defaults to the current year but can be pinned, so a report can be
regenerated exactly as it was produced on a given date. pd_rules never reads
the clock itself; see its module docstring.

A NOTE ON WHAT THIS FILE CANNOT TELL YOU
----------------------------------------
The corpus this reads is sourced from Project Gutenberg and Open Library, both
of which hold works that are already public domain. So the forward window is
sparse by construction, and what little lands in it is mostly non-English --
exactly the category where URAA restoration is most likely and where the corpus
has no country-of-first-publication column to settle it. Expect a short list of
`uncertain` rows. That is the corpus's shape showing through, not a bug here.
See docs/branch-audit-2026-08-12.md.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pd_rules import Term, next_cliffs, public_domain_term  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

CORPUS_PATH = DATA_DIR / "book_corpus.csv"
CSV_OUT_PATH = DATA_DIR / "pd_calendar.csv"
REPORT_OUT_PATH = DATA_DIR / "pd_calendar.md"

# Exactly the columns in docs/data-contracts.md, in that order.
FIELDNAMES = [
    "pd_date",
    "book_id",
    "title",
    "author",
    "author_death_year",
    "publication_year",
    "rule_applied",
    "confidence",
    "flags",
    "source",
    "notes",
]

DEFAULT_HORIZON = 5


def parse_year(value: str | None) -> int | None:
    """Blank, whitespace, or non-numeric all mean "not on file"."""
    text = (value or "").strip()
    return int(text) if text.lstrip("-").isdigit() else None


def parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def read_corpus(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate_corpus(rows: list[dict], as_of_year: int) -> list[tuple[dict, Term]]:
    return [
        (
            row,
            public_domain_term(
                parse_year(row.get("publication_year")),
                parse_year(row.get("author_death_year")),
                as_of_year=as_of_year,
                language=row.get("language") or "en",
                death_year_disputed=parse_bool(row.get("author_death_year_disputed")),
            ),
        )
        for row in rows
    ]


def to_csv_row(row: dict, term: Term) -> dict:
    return {
        "pd_date": term.pd_date,
        "book_id": row.get("book_id", ""),
        "title": row.get("title", ""),
        "author": row.get("author", ""),
        "author_death_year": row.get("author_death_year", ""),
        "publication_year": row.get("publication_year", ""),
        "rule_applied": term.rule_applied,
        "confidence": term.confidence,
        "flags": term.flags_field(),
        # Provenance is the corpus row this was derived from; the term itself is
        # computed here, not sourced.
        "source": row.get("source", ""),
        "notes": term.reasoning,
    }


def write_csv(path: Path, entries: list[tuple[dict, Term]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row, term in entries:
            writer.writerow(to_csv_row(row, term))


def write_report(
    path: Path,
    entries: list[tuple[dict, Term]],
    cliffs: list[int],
    as_of_year: int,
    funnel: dict,
) -> None:
    """The Year -> Authors -> Notable works report from pd_calendar/README.md."""
    by_year: dict[int, list[tuple[dict, Term]]] = defaultdict(list)
    for row, term in entries:
        if term.pd_year in cliffs:
            by_year[term.pd_year].append((row, term))

    lines: list[str] = [
        "# Forward-Looking Public Domain Calendar",
        "",
        f"Works entering the U.S. public domain on each of the next {len(cliffs)} January 1sts, "
        f"as of {as_of_year}.",
        "",
        "Copyright runs through December 31 of its final year, so works do not trickle into the "
        "public domain through the year — they all arrive on January 1. See "
        "`docs/project-plan.md` §1.",
        "",
        f"Generated from `data/book_corpus.csv` ({funnel['read']} rows) by "
        "`pd_calendar/scripts/build_calendar.py`.",
        "",
        "## Summary",
        "",
        "| | count |",
        "|---|---|",
        f"| Books read | {funnel['read']} |",
        f"| Already public domain as of {as_of_year} | {funnel['already_pd']} |",
        f"| No determinable date | {funnel['undetermined']} |",
        f"| Entering in {cliffs[0]}–{cliffs[-1]} | {funnel['in_window']} |",
        f"| Entering after {cliffs[-1]} | {funnel['beyond_window']} |",
        "",
    ]

    if not funnel["in_window"]:
        lines += [
            "## No works in this window",
            "",
            "Nothing in the corpus crosses one of these cliffs. That is a fact about the corpus, "
            "not a failure of the calculation — see the note at the top of "
            "`build_calendar.py`.",
            "",
        ]

    for year in cliffs:
        hits = sorted(by_year.get(year, []), key=lambda rt: (rt[0].get("author", ""), rt[0].get("title", "")))
        lines += [f"## January 1, {year}", ""]
        if not hits:
            lines += ["_No works from this corpus enter the public domain on this date._", ""]
            continue

        lines += [f"{len(hits)} work(s), by author:", ""]
        by_author: dict[str, list[tuple[dict, Term]]] = defaultdict(list)
        for row, term in hits:
            by_author[row.get("author") or "(unknown author)"].append((row, term))

        for author in sorted(by_author):
            lines.append(f"**{author}**")
            lines.append("")
            for row, term in by_author[author]:
                pub = row.get("publication_year") or "?"
                bits = [f"published {pub}", f"rule `{term.rule_applied}`", term.confidence]
                if term.flags:
                    bits.append(f"flags: {term.flags_field()}")
                lines.append(f"- *{row.get('title', '(untitled)')}* — {', '.join(bits)}")
            lines.append("")

    uncertain = sum(1 for _, t in entries if t.pd_year in cliffs and t.confidence == "uncertain")
    if funnel["in_window"]:
        lines += [
            "## Reading the confidence column",
            "",
            f"{uncertain} of the {funnel['in_window']} works above are marked `uncertain`. That is "
            "a required answer under `docs/project-plan.md` §5, not a hedge: a renewal-era work "
            "may already be public domain if its copyright was never renewed, and a foreign work "
            "may have been restored by the URAA. Neither can be settled from the columns "
            "`book_corpus.csv` currently carries.",
            "",
            "Do not treat any date here as cleared for use. Package 2 "
            "(`pd_verification/`) is the agent that confirms a specific book's public-domain "
            "claim; this file only says when a term is scheduled to end.",
            "",
        ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_funnel(entries: list[tuple[dict, Term]], cliffs: list[int], as_of_year: int) -> dict:
    return {
        "read": len(entries),
        "already_pd": sum(1 for _, t in entries if t.already_public_domain(as_of_year)),
        "undetermined": sum(1 for _, t in entries if t.pd_year is None),
        "in_window": sum(1 for _, t in entries if t.pd_year in cliffs),
        "beyond_window": sum(
            1 for _, t in entries if t.pd_year is not None and t.pd_year > cliffs[-1]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--input", type=Path, default=CORPUS_PATH)
    parser.add_argument("--output", type=Path, default=CSV_OUT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_OUT_PATH)
    parser.add_argument(
        "--as-of-year",
        type=int,
        default=_dt.date.today().year,
        help="pin the year the calendar is computed against (default: this year)",
    )
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON,
                        help=f"how many January 1st cliffs to cover (default: {DEFAULT_HORIZON})")
    parser.add_argument("--all", action="store_true",
                        help="write every book to the CSV, not just the ones in the window")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(
            f"error: {args.input} not found.\n"
            "  data/book_corpus.csv is Package 3's output and is not on every branch yet — see\n"
            "  docs/data-contracts.md. Pass --input to point at a copy.",
            file=sys.stderr,
        )
        return 1

    rows = read_corpus(args.input)
    entries = evaluate_corpus(rows, args.as_of_year)
    cliffs = next_cliffs(args.as_of_year, args.horizon)
    funnel = build_funnel(entries, cliffs, args.as_of_year)

    written = entries if args.all else [(r, t) for r, t in entries if t.pd_year in cliffs]
    write_csv(args.output, written)
    write_report(args.report, entries, cliffs, args.as_of_year, funnel)

    # Full funnel to stderr so nothing is dropped silently.
    print(f"Read {funnel['read']} books from {args.input}", file=sys.stderr)
    print(f"  already public domain as of {args.as_of_year}: {funnel['already_pd']}", file=sys.stderr)
    print(f"  no determinable date:                    {funnel['undetermined']}", file=sys.stderr)
    print(f"  entering {cliffs[0]}-{cliffs[-1]}:                        {funnel['in_window']}", file=sys.stderr)
    print(f"  entering after {cliffs[-1]}:                   {funnel['beyond_window']}", file=sys.stderr)
    for rule, n in Counter(t.rule_applied for _, t in entries).most_common():
        print(f"    rule {rule}: {n}", file=sys.stderr)
    print(f"Wrote {len(written)} row(s) to {args.output}", file=sys.stderr)
    print(f"Wrote report to {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
