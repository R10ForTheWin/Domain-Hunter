"""Reading/writing the data/*.csv files this package touches.

Schemas are pinned in docs/data-contracts.md — this module is just the
stdlib `csv` plumbing around them, nothing schema-defining lives here.
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
from typing import Dict, Iterable, List, Optional

from .models import BookInput, Verdict

BOOK_CORPUS_COLUMNS = [
    "book_id", "title", "author", "author_death_year",
    "author_death_year_disputed", "publication_year", "source",
    "source_url", "language", "notes",
]

SUPPLEMENTARY_COLUMNS = [
    "book_id", "country_of_first_publication", "simultaneous_us_publication",
    "is_anonymous_pseudonymous_or_corporate", "had_copyright_notice_at_publication",
    "renewal_filed", "creation_year", "source", "notes",
]

VERIFICATION_COLUMNS = ["book_id", "pd_status", "reasoning", "rule_applied", "flags", "verified_date"]


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    return int(value)


def _parse_optional_bool(value: Optional[str]) -> Optional[bool]:
    """Blank => None (unknown). Never treat a blank as False — an unknown
    fact is not the same as a confirmed "no", and the rule engine needs to
    tell the two apart.
    """
    if value is None:
        return None
    value = value.strip().lower()
    if value == "":
        return None
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Not a recognized boolean value: {value!r}")


def _bool_to_csv(value: Optional[bool]) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def read_book_corpus(path: str) -> List[Dict[str, str]]:
    """Raw rows from Package 3's data/book_corpus.csv, as plain dicts (still
    strings — combine with a supplementary row via build_book_input to get
    a typed BookInput).
    """
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_supplementary_inputs(path: str) -> Dict[str, Dict[str, str]]:
    """data/pd_verification_inputs.csv (this package's own supplementary
    legal metadata), keyed by book_id. Returns {} if the file doesn't exist
    yet — that's expected the first time this package runs.
    """
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["book_id"]: row for row in csv.DictReader(f)}


def find_corpus_row_by_gutenberg_id(corpus_rows: List[Dict[str, str]], gutenberg_id: str) -> Optional[Dict[str, str]]:
    """Best-effort match: does the team's already-researched book_corpus.csv
    already have a row for this Gutenberg ebook? Matches on `source_url`'s
    final path segment being exactly the ebook ID. Used so the public
    validator bot can reuse real publication-year/death-year research
    instead of falling back to Gutenberg's own catalog, which doesn't carry
    a first-publication year at all.

    Exact, not substring: a plain `needle in source_url` check (the
    original approach here) matches ID "10" against ".../ebooks/103",
    ".../ebooks/1000", ".../ebooks/2910", etc. -- found live when looking
    up ebook 10 (the King James Bible) returned Jules Verne's "Around the
    World in Eighty Days" (ebook 103) instead, silently, with a confident
    wrong verdict. Comparing only the URL's last path segment closes this
    for every ID, not just the one that happened to be tested.
    """
    target = str(gutenberg_id).strip()
    for row in corpus_rows:
        url = (row.get("source_url") or "").rstrip("/")
        if url.rsplit("/", 1)[-1] == target:
            return row
    return None


def find_corpus_row_by_title_author(
    corpus_rows: List[Dict[str, str]], title: str, author: str
) -> Optional[Dict[str, str]]:
    """Best-effort fallback match by normalized title (loose match) --
    used for non-Gutenberg lookups (ISBN/OCLC/title search results) where
    there's no ebook ID to match on. Author isn't compared strictly since
    name formatting ("Last, First" vs "First Last") varies across sources;
    title match alone is treated as sufficient signal, same conservative
    "corroborate, don't invent" spirit as everywhere else in this package.
    """
    target = title.strip().lower()
    if not target:
        return None
    for row in corpus_rows:
        if (row.get("title") or "").strip().lower() == target:
            return row
    return None


def build_book_input(corpus_row: Dict[str, str], supplementary_row: Optional[Dict[str, str]]) -> BookInput:
    supplementary_row = supplementary_row or {}
    return BookInput(
        book_id=corpus_row["book_id"],
        title=corpus_row["title"],
        author=corpus_row["author"],
        publication_year=_parse_optional_int(corpus_row.get("publication_year")),
        author_death_year=_parse_optional_int(corpus_row.get("author_death_year")),
        author_death_year_disputed=(
            (corpus_row.get("author_death_year_disputed") or "").strip().lower() == "true"
        ),
        is_anonymous_pseudonymous_or_corporate=_parse_optional_bool(
            supplementary_row.get("is_anonymous_pseudonymous_or_corporate")
        ),
        country_of_first_publication=(supplementary_row.get("country_of_first_publication") or None) or None,
        simultaneous_us_publication=_parse_optional_bool(supplementary_row.get("simultaneous_us_publication")),
        had_copyright_notice_at_publication=_parse_optional_bool(
            supplementary_row.get("had_copyright_notice_at_publication")
        ),
        renewal_filed=_parse_optional_bool(supplementary_row.get("renewal_filed")),
        creation_year=_parse_optional_int(supplementary_row.get("creation_year")),
    )


def write_verification_csv(path: str, rows: Iterable[tuple], *, as_of_date: Optional[_dt.date] = None) -> None:
    """rows: iterable of (book_id, Verdict). Overwrites `path`."""
    as_of_date = as_of_date or _dt.date.today()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=VERIFICATION_COLUMNS)
        writer.writeheader()
        for book_id, verdict in rows:
            writer.writerow(
                {
                    "book_id": book_id,
                    "pd_status": verdict.pd_status,
                    "reasoning": verdict.reasoning,
                    "rule_applied": verdict.rule_applied,
                    "flags": verdict.flags_str(),
                    "verified_date": as_of_date.isoformat(),
                }
            )


def upsert_supplementary_row(path: str, book_id: str, fields: Dict[str, object]) -> None:
    """Write (or overwrite) one book's row in data/pd_verification_inputs.csv,
    preserving every other book's existing row.
    """
    rows = read_supplementary_inputs(path)
    row = {col: "" for col in SUPPLEMENTARY_COLUMNS}
    row.update(rows.get(book_id, {}))
    row["book_id"] = book_id
    for key, value in fields.items():
        if isinstance(value, bool):
            row[key] = _bool_to_csv(value)
        elif value is None:
            row[key] = ""
        else:
            row[key] = str(value)
    rows[book_id] = row

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUPPLEMENTARY_COLUMNS)
        writer.writeheader()
        for r in rows.values():
            writer.writerow({col: r.get(col, "") for col in SUPPLEMENTARY_COLUMNS})
