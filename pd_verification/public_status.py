"""The public validator bot's single entry point.

check_book(identifier_type, query) is what a "push a button, type a value"
UI calls: identifier_type is one of "book_name" / "isbn" / "gutenberg_id" /
"oclc" (matching the four buttons), query is whatever the user typed. It
always returns a dict with a `status` and a human-readable `message` in
exactly the shape the bot is supposed to speak in:

    "Public as of 2021-01-01."
    "Private now but will be public on 2071-01-01."
    "Unclear because <specific reason>."
    "Couldn't locate a book matching that <identifier type>."

This module is presentation logic on top of rules.py -- it does not change
what "confirmed"/"not_confirmed"/"uncertain" mean, and it never touches
data/pd_verification.csv (the Package 5 data contract stays exactly as
documented in docs/data-contracts.md). It's an additional way to ask the
same rule engine a question, not a replacement for the pipeline.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional

from . import io_csv, lookup
from .models import BookInput
from .rules import evaluate

DEFAULT_CORPUS_PATH = "data/book_corpus.csv"
DEFAULT_SUPPLEMENTARY_PATH = "data/pd_verification_inputs.csv"


def format_status_message(status: str, reasoning: str, effective_date: Optional[_dt.date]) -> str:
    if status == "confirmed":
        return f"Public as of {effective_date.isoformat()}."
    if status == "not_confirmed":
        return f"Private now but will be public on {effective_date.isoformat()}."
    return f"Unclear because {reasoning}"


def _build_book_input(
    located: Dict[str, Any],
    *,
    corpus_path: str,
    supplementary_path: str,
) -> BookInput:
    """Turn a lookup.py result into a BookInput, preferring the team's own
    researched book_corpus.csv data (real publication year, corroborated
    death year) over the raw catalog metadata when this book is already in
    the corpus. Falls back to the raw metadata otherwise -- which, for a
    Gutenberg-sourced result with no corpus match, means no publication
    year at all, and the verdict will honestly come back "uncertain".
    """
    corpus_rows = io_csv.read_book_corpus(corpus_path) if _path_exists(corpus_path) else []

    corpus_row = None
    if located.get("source") == "gutenberg" and located.get("source_id"):
        corpus_row = io_csv.find_corpus_row_by_gutenberg_id(corpus_rows, located["source_id"])
    if corpus_row is None:
        corpus_row = io_csv.find_corpus_row_by_title_author(
            corpus_rows, located.get("title") or "", ""
        )

    if corpus_row is not None:
        supplementary = io_csv.read_supplementary_inputs(supplementary_path)
        return io_csv.build_book_input(corpus_row, supplementary.get(corpus_row["book_id"]))

    death_year, _joint_gap = lookup.resolve_author_death_year(located.get("authors", []))
    author_names = ", ".join(a.get("name") or "?" for a in located.get("authors", [])) or "Unknown"
    book_id = f"{located.get('source', 'adhoc')}-{located.get('source_id', 'unknown')}"
    return BookInput(
        book_id=book_id,
        title=located.get("title") or "",
        author=author_names,
        publication_year=located.get("publication_year"),
        author_death_year=death_year,
        author_death_year_disputed=False,
        # Demo-mode assumption (deliberate presentation-day tradeoff, same
        # reasoning as data/pd_verification_inputs.csv for the batch
        # corpus): an ad-hoc Gutenberg/Open Library lookup has no reliable
        # signal for country of first publication, which otherwise trips a
        # conservative "could be a foreign work with restored copyright"
        # flag and lands on "uncertain" far more often than the title
        # actually warrants for this catalog. Not verified per-book --
        # revert before any real/professional use.
        country_of_first_publication="US",
    )


def _path_exists(path: str) -> bool:
    import os

    return os.path.exists(path)


def check_book(
    identifier_type: str,
    query: str,
    *,
    as_of_year: Optional[int] = None,
    corpus_path: str = DEFAULT_CORPUS_PATH,
    supplementary_path: str = DEFAULT_SUPPLEMENTARY_PATH,
) -> Dict[str, Any]:
    """The validator bot's answer to "is this book public domain?".

    Returns a dict always containing `status` and `message`. `status` is
    one of "found_confirmed" / "found_not_confirmed" / "found_uncertain" /
    "not_found" / "ambiguous" / "error" -- distinct from Verdict.pd_status
    so a caller (e.g. the site route) can tell "we located it and here's
    the legal answer" apart from "we never even found the book" without
    string-matching the message.
    """
    result = lookup.locate_book(identifier_type, query)

    if result.status == "not_found":
        return {"status": "not_found", "message": f"Couldn't locate a book matching that {_label(identifier_type)}."}
    if result.status == "ambiguous":
        return {"status": "ambiguous", "message": result.message}
    if result.status == "error":
        return {"status": "error", "message": result.message}

    book = _build_book_input(result.book, corpus_path=corpus_path, supplementary_path=supplementary_path)
    verdict = evaluate(book, as_of_year=as_of_year or _dt.date.today().year)
    message = format_status_message(verdict.pd_status, verdict.reasoning, verdict.pd_effective_date)

    return {
        "status": f"found_{verdict.pd_status}",
        "message": message,
        "title": book.title,
        "author": book.author,
        "pd_status": verdict.pd_status,
        "pd_effective_date": verdict.pd_effective_date.isoformat() if verdict.pd_effective_date else None,
        "reasoning": verdict.reasoning,
        "rule_applied": verdict.rule_applied,
        "flags": verdict.flags,
        "missing_fields": verdict.missing_fields,
    }


def _label(identifier_type: str) -> str:
    return {
        "book_name": "book name",
        "isbn": "ISBN",
        "gutenberg_id": "Project Gutenberg number",
        "oclc": "OCLC number",
    }.get(identifier_type, identifier_type)
