#!/usr/bin/env python3
"""
Package 5 - Shortlist & Output Formatting  (Domain Huntress)
Owner: Luis R.

Takes the scored, PD-confirmed books and produces the final top-10 shortlist.

Reads (all plain CSV, per docs/data-contracts.md):
  data/pd_verification.csv  - Package 2 (which books are public-domain confirmed)
  data/studio_scores.csv    - Package 4 (how each book scored against the mandate)
  data/book_corpus.csv      - Package 3 (title + author lookup; pd_verification and
                              studio_scores only carry book_id, so we join titles here)

Writes:
  data/shortlist.csv        - the contract output (see data-contracts.md)
  data/shortlist.md         - human-readable report for review

The one iron rule (project-plan.md sec 5): only rows whose joined pd_status == "confirmed"
are eligible for the top 10. No exceptions, even for a high-scoring book. If fewer than 10
books are confirmed, the shortlist is shorter than 10 - it is never padded.

Standard library only (csv, argparse, pathlib) so it runs in any Claude session with no install.
"""

import argparse
import csv
import sys
from pathlib import Path

# Exact column order for data/shortlist.csv - this is the data contract. Do not reorder
# or rename without editing docs/data-contracts.md and telling the group.
SHORTLIST_COLUMNS = [
    "rank",
    "book_id",
    "title",
    "author",
    "total_score",
    "score_reasoning",
    "pd_status",
    "pd_reasoning",
]

TOP_N = 10
CONFIRMED = "confirmed"


def read_csv(path):
    """Read a CSV into a list of dict rows. Errors clearly if the file is missing."""
    if not path.exists():
        sys.exit(
            f"ERROR: expected input file not found: {path}\n"
            f"       (Packages 2/3/4 write this. If they haven't yet, run with sample data.)"
        )
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value):
    """Parse a score to float; return None if blank or unparseable (row gets skipped + warned)."""
    try:
        return float(str(value).strip())
    except (ValueError, AttributeError):
        return None


def build_shortlist(data_dir):
    corpus_rows = read_csv(data_dir / "book_corpus.csv")
    verify_rows = read_csv(data_dir / "pd_verification.csv")
    score_rows = read_csv(data_dir / "studio_scores.csv")

    # Lookups keyed by book_id (the shared primary key across all packages).
    corpus = {r["book_id"]: r for r in corpus_rows}
    verify = {r["book_id"]: r for r in verify_rows}

    warnings = []
    eligible = []

    for s in score_rows:
        book_id = s.get("book_id", "").strip()
        if not book_id:
            warnings.append("studio_scores row with blank book_id - skipped")
            continue

        v = verify.get(book_id)
        if v is None:
            # Scored but Package 2 never ruled on it -> cannot confirm -> not eligible.
            warnings.append(f"{book_id}: scored but missing from pd_verification.csv - skipped")
            continue

        # THE PD GATE. Anything not explicitly "confirmed" (not_confirmed / uncertain) is out.
        if v.get("pd_status", "").strip().lower() != CONFIRMED:
            continue

        score = to_float(s.get("total_score"))
        if score is None:
            warnings.append(f"{book_id}: confirmed but total_score is blank/invalid - skipped")
            continue

        c = corpus.get(book_id, {})
        if not c:
            warnings.append(f"{book_id}: not in book_corpus.csv - title/author will be blank")

        eligible.append(
            {
                "book_id": book_id,
                "title": c.get("title", ""),
                "author": c.get("author", ""),
                "total_score": score,
                "score_reasoning": s.get("reasoning", ""),
                "pd_status": CONFIRMED,
                "pd_reasoning": v.get("reasoning", ""),
            }
        )

    # Highest score first; tie-break on title so the ordering is deterministic run-to-run.
    eligible.sort(key=lambda r: (-r["total_score"], r["title"].lower()))

    shortlist = eligible[:TOP_N]
    for i, row in enumerate(shortlist, start=1):
        row["rank"] = i

    return shortlist, warnings, len(eligible)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHORTLIST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in SHORTLIST_COLUMNS})


def write_markdown(path, rows, total_confirmed):
    lines = []
    lines.append("# Domain Huntress - Final Shortlist")
    lines.append("")
    lines.append("Top public-domain-confirmed books, ranked by studio-mandate score.")
    lines.append("")
    if not rows:
        lines.append("_No books passed public-domain verification, so the shortlist is empty._")
    else:
        note = "" if total_confirmed >= TOP_N else (
            f" _(only {total_confirmed} book(s) passed PD verification, so the list is shorter than 10 - not padded.)_"
        )
        lines.append(f"**{len(rows)} book(s) shown.**{note}")
        lines.append("")
        for r in rows:
            lines.append(f"## {r['rank']}. {r['title']} - {r['author']}")
            lines.append("")
            lines.append(f"- **Score:** {r['total_score']:g}")
            lines.append(f"- **Why it scored this way:** {r['score_reasoning']}")
            lines.append(f"- **Public-domain basis:** {r['pd_reasoning']}")
            lines.append(f"- `book_id: {r['book_id']}`")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build the Domain Huntress top-10 shortlist.")
    # Default: the data/ folder that sits next to this package folder (repo-root/data).
    default_data = Path(__file__).resolve().parent.parent / "data"
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data,
        help=f"Folder holding the input/output CSVs (default: {default_data})",
    )
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    shortlist, warnings, total_confirmed = build_shortlist(data_dir)

    write_csv(data_dir / "shortlist.csv", shortlist)
    write_markdown(data_dir / "shortlist.md", shortlist, total_confirmed)

    print(f"Read inputs from: {data_dir}")
    print(f"PD-confirmed & scored books: {total_confirmed}")
    print(f"Shortlist written: {len(shortlist)} book(s) (cap {TOP_N})")
    print(f"  -> {data_dir / 'shortlist.csv'}")
    print(f"  -> {data_dir / 'shortlist.md'}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
