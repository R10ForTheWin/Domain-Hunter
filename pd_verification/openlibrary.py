"""Open Library metadata client — ISBN, OCLC number, and title lookups.

Project Gutenberg's own catalog (see gutenberg.py) has no concept of ISBN or
OCLC numbers, so the public validator bot's ISBN/OCLC entry points go through
Open Library (https://openlibrary.org) instead: free, no API key, and it
indexes both identifiers directly.

Like gutenberg.py, this only fetches catalog metadata. It does not and
cannot tell you a book's copyright status -- that's rules.py's job. Open
Library's author birth/death dates are free-text strings (e.g. "1809",
"22 January 1561", "circa 1800") rather than clean years, so
`_extract_year` below does best-effort parsing and returns None rather than
guessing when it can't confidently pull out a year -- same "never fabricate
a fact" posture as the rest of this package.

Stdlib only (urllib), matching the rest of this project's "no pip install
needed" approach (see docs/data-contracts.md).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

_BOOKS_URL = "https://openlibrary.org/api/books"
_SEARCH_URL = "https://openlibrary.org/search.json"
_AUTHOR_URL_TEMPLATE = "https://openlibrary.org{author_key}.json"
# See gutenberg.py's _get() for why these were shortened from (10s, 3, 1.5s):
# a 34.5s worst-case silent stall is bad live in front of a class.
_TIMEOUT_SECONDS = 5
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 1
_YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")  # a bare 4-digit year, 1500-2099


class OpenLibraryLookupError(Exception):
    """Raised when Open Library can't be reached or returns something we
    don't understand. Never silently returns fabricated data -- callers
    should treat this as "couldn't verify," not as "book doesn't exist."
    """


def _get(url: str) -> Any:
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
        raise OpenLibraryLookupError(f"Could not reach Open Library ({url}): {last_exc}") from last_exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenLibraryLookupError(f"Open Library returned something that wasn't valid JSON: {exc}") from exc


def _extract_year(text: Optional[str]) -> Optional[int]:
    """Best-effort year extraction from Open Library's free-text date
    fields. Returns None (never a guess) if no confident 4-digit year is
    found, or if the string looks like an approximation (e.g. starts with
    "circa"/"c.") that shouldn't be treated as a firm fact.
    """
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered.startswith(("circa", "c.", "approximately", "?", "unknown")):
        return None
    match = _YEAR_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def _author_death_year(author_key: str) -> Optional[int]:
    """Follow an author record to pull a death year, if Open Library has
    one on file. Returns None on any lookup failure rather than raising --
    a missing/unreachable author record just means "unknown," which is the
    same outcome as Open Library never having had the data at all.
    """
    try:
        data = _get(_AUTHOR_URL_TEMPLATE.format(author_key=author_key))
    except OpenLibraryLookupError:
        return None
    return _extract_year(data.get("death_date"))


def _normalize_book(*, title: str, author_names: List[str], author_keys: List[str],
                     publish_year: Optional[int], source_id: str) -> Dict[str, Any]:
    authors = []
    for name, key in zip(author_names, author_keys):
        authors.append({"name": name, "birth_year": None, "death_year": _author_death_year(key) if key else None})
    # Author names with no matching key (rare, some search results) still
    # get a row so the caller sees them -- just with no death year to offer.
    for name in author_names[len(author_keys):]:
        authors.append({"name": name, "birth_year": None, "death_year": None})
    return {
        "source": "openlibrary",
        "source_id": source_id,
        "title": title,
        "authors": authors,
        "publication_year": publish_year,
    }


def fetch_by_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """Look up one book by ISBN (10 or 13 digit, hyphens/spaces ok)."""
    cleaned = re.sub(r"[^0-9Xx]", "", isbn)
    return _fetch_by_bibkey(f"ISBN:{cleaned}")


def fetch_by_oclc(oclc_number: str) -> Optional[Dict[str, Any]]:
    """Look up one book by OCLC control number (digits only)."""
    cleaned = re.sub(r"[^0-9]", "", oclc_number)
    return _fetch_by_bibkey(f"OCLC:{cleaned}")


def _fetch_by_bibkey(bibkey: str) -> Optional[Dict[str, Any]]:
    encoded = urllib.parse.urlencode({"bibkeys": bibkey, "format": "json", "jscmd": "data"})
    data = _get(f"{_BOOKS_URL}?{encoded}")
    record = data.get(bibkey)
    if record is None:
        return None
    authors = record.get("authors", [])
    author_names = [a.get("name", "?") for a in authors]
    author_keys = [a.get("url", "").replace("https://openlibrary.org", "").split("/", 3)
                   for a in authors]
    # authors[i]["url"] looks like "https://openlibrary.org/authors/OL123A/Name" --
    # we only need the "/authors/OL123A" portion to hit the author endpoint.
    author_keys = ["/".join(parts[:3]) if len(parts) >= 3 else "" for parts in author_keys]
    publish_date = record.get("publish_date")
    return _normalize_book(
        title=record.get("title", ""),
        author_names=author_names,
        author_keys=author_keys,
        publish_year=_extract_year(publish_date),
        source_id=bibkey,
    )


def search_by_title(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Title search. Returns up to `limit` normalized matches, most-relevant
    first (Open Library's own relevance ranking). Empty list if nothing
    matched.
    """
    encoded = urllib.parse.urlencode({"title": query, "limit": limit})
    data = _get(f"{_SEARCH_URL}?{encoded}")
    results = []
    for doc in data.get("docs", [])[:limit]:
        author_names = doc.get("author_name", []) or []
        author_keys = doc.get("author_key", []) or []
        results.append(
            _normalize_book(
                title=doc.get("title", ""),
                author_names=author_names,
                author_keys=[f"/authors/{k}" for k in author_keys],
                publish_year=doc.get("first_publish_year"),
                source_id=doc.get("key", ""),
            )
        )
    return results
