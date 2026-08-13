"""Tests for the public validator bot's entry point (public_status.py).

Covers: the four "can't proceed" outcomes (not found / ambiguous / error /
lookup succeeded), and that a Gutenberg-sourced match with no publication
year on file honestly comes back "Unclear" rather than guessing -- unless
the book is already in the team's researched book_corpus.csv, in which case
that real data is used.
"""
import csv
import datetime as _dt

from pd_verification import lookup, public_status
from pd_verification.lookup import LookupResult


def test_format_status_message_confirmed():
    msg = public_status.format_status_message("confirmed", "because reasons", _dt.date(2021, 1, 1))
    assert msg == "Public as of 2021-01-01."


def test_format_status_message_not_confirmed():
    msg = public_status.format_status_message("not_confirmed", "because reasons", _dt.date(2071, 1, 1))
    assert msg == "Private now but will be public on 2071-01-01."


def test_format_status_message_uncertain_includes_reasoning():
    msg = public_status.format_status_message("uncertain", "the author's death year is not on file", None)
    assert msg == "Unclear because the author's death year is not on file"


def test_check_book_not_found(monkeypatch):
    # check_book always speaks in the exact required phrasing, regardless of
    # whatever raw message lookup.py produced internally.
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("not_found", message="some internal detail"))
    result = public_status.check_book("isbn", "0000000000")
    assert result["status"] == "not_found"
    assert result["message"] == "Couldn't locate a book matching that ISBN."


def test_check_book_ambiguous(monkeypatch):
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("ambiguous", message="Found 3 matches."))
    result = public_status.check_book("book_name", "Emma")
    assert result["status"] == "ambiguous"


def test_check_book_error(monkeypatch):
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("error", message="network down"))
    result = public_status.check_book("gutenberg_id", "84")
    assert result["status"] == "error"


def test_check_book_gutenberg_match_with_no_corpus_data_is_honestly_unclear(monkeypatch, tmp_path):
    # Gutendex has no first-publication-year field at all, and this book
    # isn't in book_corpus.csv either -- there is genuinely nothing to
    # compute a verdict from, and the bot must say so rather than guess.
    book = {
        "source": "gutenberg", "source_id": "999", "title": "Some Untracked Book",
        "authors": [{"name": "Someone", "death_year": 1950}],
        "publication_year": None,
    }
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("found", book=book))

    empty_corpus = tmp_path / "book_corpus.csv"
    empty_corpus.write_text("book_id,title,author,author_death_year,author_death_year_disputed,publication_year,source,source_url,language,notes\n")

    result = public_status.check_book(
        "gutenberg_id", "999", as_of_year=2026,
        corpus_path=str(empty_corpus), supplementary_path=str(tmp_path / "pd_verification_inputs.csv"),
    )
    assert result["status"] == "found_uncertain"
    assert result["message"].startswith("Unclear because")
    assert "publication year" in result["message"]


def test_check_book_uses_corpus_data_when_gutenberg_id_matches(monkeypatch, tmp_path):
    book = {
        "source": "gutenberg", "source_id": "84", "title": "Frankenstein",
        "authors": [{"name": "Mary Wollstonecraft Shelley", "death_year": 1851}],
        "publication_year": None,
    }
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("found", book=book))

    corpus_path = tmp_path / "book_corpus.csv"
    with corpus_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["book_id", "title", "author", "author_death_year", "author_death_year_disputed",
                          "publication_year", "source", "source_url", "language", "notes"])
        writer.writerow(["frankenstein__mary-shelley__1818", "Frankenstein", "Shelley, Mary", "1851", "false",
                          "1818", "gutenberg", "https://gutenberg.org/ebooks/84", "en", ""])

    result = public_status.check_book(
        "gutenberg_id", "84", as_of_year=2026,
        corpus_path=str(corpus_path), supplementary_path=str(tmp_path / "pd_verification_inputs.csv"),
    )
    assert result["status"] == "found_confirmed"
    assert result["message"] == "Public as of 1922-01-01."  # death 1851 + 71


def test_check_book_openlibrary_match_with_publish_date_resolves_directly(monkeypatch, tmp_path):
    # No corpus match needed here -- Open Library's own publish_date is
    # enough to run the rule engine directly.
    book = {
        "source": "openlibrary", "source_id": "ISBN:0000000001", "title": "A Modern Novel",
        "authors": [{"name": "A. Living Author", "death_year": None}],
        "publication_year": 2015,
    }
    monkeypatch.setattr(lookup, "locate_book", lambda t, q: LookupResult("found", book=book))

    empty_corpus = tmp_path / "book_corpus.csv"
    empty_corpus.write_text("book_id,title,author,author_death_year,author_death_year_disputed,publication_year,source,source_url,language,notes\n")

    result = public_status.check_book(
        "isbn", "0000000001", as_of_year=2026,
        corpus_path=str(empty_corpus), supplementary_path=str(tmp_path / "pd_verification_inputs.csv"),
    )
    assert result["status"] == "found_uncertain"
    assert "death" in result["message"].lower() or "life" in result["message"].lower()
