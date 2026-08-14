"""Identifier-based book lookup for the public validator bot.

The bot offers exactly four ways to identify a book -- Book Name, ISBN,
Project Gutenberg number, or OCLC number -- and this module is the single
dispatch point for all four. It never guesses which book someone meant: a
title search that turns up more than one plausible match comes back
"ambiguous" and asks for one of the three unique identifiers instead of
silently picking one.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import gutenberg, io_csv, openlibrary

IDENTIFIER_TYPES = ("book_name", "isbn", "gutenberg_id", "oclc")

# Absolute, not a bare relative "data/book_corpus.csv": this module gets
# bundled into site/pd_verification/ for a CLI Railway deploy (a sibling of
# site/data/), so __file__'s parent.parent lands on the right data/ in both
# a normal repo checkout (pd_verification/ and data/ as siblings of repo
# root) and the bundled deploy shape -- unlike a CWD-relative path, which
# happened to work in production (gunicorn's CWD is site/) but silently
# fell through to the network on any other CWD, defeating the point of
# checking locally first.
_LOCAL_CORPUS_PATH = str(Path(__file__).resolve().parent.parent / "data" / "book_corpus.csv")


def _local_corpus_match(query: str) -> Optional[Dict[str, Any]]:
    """Exact-title match against the team's own, already-vetted
    book_corpus.csv, checked before ever touching the network. A well-known
    classic that's already in our corpus (the common case in a demo) then
    resolves instantly and doesn't depend on Gutendex/Open Library being up
    or fast -- both have been observed flaky live. Falls through to the live
    lookups on any miss (partial title, not yet in the corpus), so nothing
    is lost, just the common case gets faster and more reliable.
    """
    try:
        rows = io_csv.read_book_corpus(_LOCAL_CORPUS_PATH)
    except OSError:
        return None
    target = query.strip().lower()
    if not target:
        return None
    for row in rows:
        if (row.get("title") or "").strip().lower() == target:
            death_year = row.get("author_death_year")
            pub_year = row.get("publication_year")
            return {
                "source": "local_corpus",
                "source_id": row.get("book_id"),
                "title": row.get("title"),
                "authors": [{
                    "name": row.get("author"),
                    "birth_year": None,
                    "death_year": int(death_year) if death_year else None,
                }],
                "publication_year": int(pub_year) if pub_year else None,
            }
    return None


@dataclass
class LookupResult:
    status: str  # "found" | "not_found" | "ambiguous" | "error"
    book: Optional[Dict[str, Any]] = None
    message: Optional[str] = None  # set on not_found / ambiguous / error


def resolve_author_death_year(authors: List[Dict[str, Any]]) -> Tuple[Optional[int], bool]:
    """For a (possibly joint) work, figure out the single death year that
    controls the life+70 rule -- the LAST surviving author's death, per the
    joint-work rule -- without ever guessing at a missing one.

    Returns (death_year, is_joint_work_with_gap). `death_year` is None
    unless every listed author has a known death year on file (any single
    unknown author poisons the joint-work determination, since the term
    doesn't run out until the last one dies). `is_joint_work_with_gap` is
    true whenever there's more than one author and at least one is
    missing/unknown, purely so a caller can explain why author_death_year
    came back empty even though *some* death years were on file.
    """
    if not authors:
        return None, False
    death_years = [a.get("death_year") for a in authors]
    known = [d for d in death_years if d is not None]
    if len(known) == len(authors):
        return max(known), False
    return None, len(authors) > 1 and len(known) > 0


def _dedupe_source_ids(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for r in results:
        key = (r.get("source"), r.get("source_id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def locate_book(identifier_type: str, query: str) -> LookupResult:
    if identifier_type not in IDENTIFIER_TYPES:
        return LookupResult("error", message=f"Unknown identifier type: {identifier_type!r}")

    query = (query or "").strip()
    if not query:
        return LookupResult("not_found", message="No search value was entered.")

    try:
        if identifier_type == "gutenberg_id":
            try:
                gid = int(query)
            except ValueError:
                return LookupResult("not_found", message=f"'{query}' isn't a valid Project Gutenberg number.")
            found = gutenberg.fetch_by_id(gid)
            if found is None:
                return LookupResult("not_found", message=f"No Project Gutenberg book found with ID {gid}.")
            return LookupResult("found", book=found)

        if identifier_type == "isbn":
            found = openlibrary.fetch_by_isbn(query)
            if found is None:
                return LookupResult("not_found", message=f"No book found for ISBN {query}.")
            return LookupResult("found", book=found)

        if identifier_type == "oclc":
            found = openlibrary.fetch_by_oclc(query)
            if found is None:
                return LookupResult("not_found", message=f"No book found for OCLC number {query}.")
            return LookupResult("found", book=found)

        # identifier_type == "book_name"
        local_match = _local_corpus_match(query)
        if local_match is not None:
            return LookupResult("found", book=local_match)

        gutenberg_matches = gutenberg.search(query, limit=5)
        if len(gutenberg_matches) == 1:
            return LookupResult("found", book=gutenberg_matches[0])
        if len(gutenberg_matches) > 1:
            return LookupResult(
                "ambiguous",
                message=(
                    f"Found {len(gutenberg_matches)} possible matches for '{query}' on Project "
                    f"Gutenberg. Please provide the ISBN, OCLC number, or Project Gutenberg ID "
                    f"to identify the exact edition."
                ),
            )
        # nothing on Gutenberg -- try Open Library before giving up
        ol_matches = _dedupe_source_ids(openlibrary.search_by_title(query, limit=5))
        if len(ol_matches) == 1:
            return LookupResult("found", book=ol_matches[0])
        if len(ol_matches) > 1:
            return LookupResult(
                "ambiguous",
                message=(
                    f"Found {len(ol_matches)} possible matches for '{query}'. Please provide the "
                    f"ISBN, OCLC number, or Project Gutenberg ID to identify the exact edition."
                ),
            )
        return LookupResult("not_found", message=f"No book found matching '{query}'.")

    except (gutenberg.GutenbergLookupError, openlibrary.OpenLibraryLookupError) as exc:
        return LookupResult("error", message=f"Couldn't reach the lookup service: {exc}")
