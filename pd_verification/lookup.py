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
from typing import Any, Dict, List, Optional, Tuple

from . import gutenberg, openlibrary

IDENTIFIER_TYPES = ("book_name", "isbn", "gutenberg_id", "oclc")


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
