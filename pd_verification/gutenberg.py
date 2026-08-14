"""Minimal Project Gutenberg metadata client.

Uses the Gutendex API (https://gutendex.com), a free, unofficial read-only
mirror of the Gutenberg catalog as structured JSON — no API key needed. This
module only fetches catalog metadata (title, listed author(s), and whatever
birth/death years Gutenberg has on file for them); it does not and cannot
tell you a book's copyright status. Gutenberg only hosts books it already
believes are public domain in the U.S., but "Gutenberg published it" is not
itself a legal determination — that's what rules.py is for.

Stdlib only (urllib), matching the rest of this project's "no pip install
needed" approach (see docs/data-contracts.md).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

_BASE_URL = "https://gutendex.com/books"
_TIMEOUT_SECONDS = 10
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.5


class GutenbergLookupError(Exception):
    """Raised when the Gutendex API can't be reached or returns something we
    don't understand. Never silently returns fabricated data — callers
    should treat this as "couldn't verify," not as "book doesn't exist."
    """


def _get(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "domain-hunter-pd-verification/1.0"})
    last_exc: Optional[OSError] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = response.read()
            break
        except OSError as exc:
            # Not (URLError, HTTPError, TimeoutError): on Python 3.9, socket.timeout
            # is an OSError subclass but NOT a TimeoutError subclass (that alias
            # was only added in 3.10), so a timeout escaped this handler entirely
            # on 3.9 -- the system Python on macOS. OSError is a strict superset
            # of all four previously-caught types.
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))
    else:
        # A single 10s attempt with no retry meant one slow response from a
        # third-party API (observed happening from Railway's network, not
        # just a hypothetical) failed the whole lookup outright. Retrying a
        # transient network hiccup a couple of times before giving up is a
        # narrow reliability fix, not a behavior change -- still raises the
        # same error type/message shape callers already handle.
        raise GutenbergLookupError(f"Could not reach Gutendex ({url}): {last_exc}") from last_exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise GutenbergLookupError(f"Gutendex returned something that wasn't valid JSON: {exc}") from exc


def _normalize_book(raw: Dict[str, Any]) -> Dict[str, Any]:
    authors = [
        {
            "name": a.get("name"),
            "birth_year": a.get("birth_year"),
            "death_year": a.get("death_year"),
        }
        for a in raw.get("authors", [])
    ]
    return {
        # "source"/"source_id"/"publication_year" match the shape openlibrary.py
        # produces, so lookup.py and public_status.py can treat either origin
        # uniformly. "gutenberg_id" is kept alongside for existing callers.
        "source": "gutenberg",
        "source_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "gutenberg_id": raw.get("id"),
        "title": raw.get("title"),
        "authors": authors,
        "languages": raw.get("languages", []),
        "subjects": raw.get("subjects", []),
        "download_count": raw.get("download_count"),
        # Gutendex's catalog has no reliable first-publication-year field --
        # it's an ebook-edition catalog, not a bibliographic one. Left None
        # here on purpose; public_status.py fills this in from
        # data/book_corpus.csv when this Gutenberg ID is already in the
        # team's researched corpus, and the interactive CLI (agent.py) asks
        # the user directly. Never guess it from, say, the ebook's release
        # date -- that's not the same thing as the original publication year.
        "publication_year": None,
    }


def fetch_by_id(gutenberg_id: int) -> Optional[Dict[str, Any]]:
    """Look up one book by its Project Gutenberg ID (the number in its URL).

    Returns the normalized dict, or None if no book with that ID exists.
    Raises GutenbergLookupError if the API itself couldn't be reached.
    """
    data = _get(f"{_BASE_URL}/{int(gutenberg_id)}")
    if "detail" in data and "title" not in data:
        return None  # Gutendex's "not found" shape
    return _normalize_book(data)


def search(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Search Gutenberg by title/author text. Returns up to `limit` matches,
    normalized the same way as fetch_by_id. Empty list if nothing matched.
    """
    encoded = urllib.parse.urlencode({"search": query})
    data = _get(f"{_BASE_URL}?{encoded}")
    results = data.get("results", [])
    return [_normalize_book(r) for r in results[:limit]]


def death_years_for_author(book: Dict[str, Any]) -> List[Optional[int]]:
    """Convenience: the death_year Gutendex has on file for each author of a
    normalized book dict, in author order. A None in the list means
    Gutendex doesn't have a death year for that author either — still needs
    independent corroboration either way, per data-contracts.md's
    `author_death_year_disputed` convention.
    """
    return [a.get("death_year") for a in book.get("authors", [])]
