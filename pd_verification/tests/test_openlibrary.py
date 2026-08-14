"""Tests for the Open Library client. HTTP is mocked throughout -- these
must never make a real network call, so they run offline and deterministically.
"""
from pd_verification import openlibrary


def test_extract_year_plain_four_digit_string():
    assert openlibrary._extract_year("1935") == 1935


def test_extract_year_from_full_date_string():
    assert openlibrary._extract_year("June 12, 1940") == 1940


def test_extract_year_none_for_blank():
    assert openlibrary._extract_year(None) is None
    assert openlibrary._extract_year("") is None


def test_extract_year_none_for_approximate_dates():
    # "circa"/"c."/"approximately" dates are explicitly not treated as firm
    # facts -- this engine never guesses, and an approximate death year is
    # exactly the kind of soft fact that should stay "unknown" rather than
    # silently anchoring a life+70 calculation.
    assert openlibrary._extract_year("circa 1800") is None
    assert openlibrary._extract_year("c. 1750") is None
    assert openlibrary._extract_year("unknown") is None


def test_fetch_by_isbn_not_found(monkeypatch):
    monkeypatch.setattr(openlibrary, "_get", lambda url: {})
    assert openlibrary.fetch_by_isbn("0000000000") is None


def test_fetch_by_isbn_found(monkeypatch):
    def fake_get(url):
        assert "ISBN%3A0451524934" in url or "ISBN:0451524934" in url
        return {
            "ISBN:0451524934": {
                "title": "1984",
                "authors": [{"name": "George Orwell", "url": "https://openlibrary.org/authors/OL118077A/George_Orwell"}],
                "publish_date": "1950",
            }
        }

    monkeypatch.setattr(openlibrary, "_get", fake_get)
    monkeypatch.setattr(openlibrary, "_author_death_year", lambda key: 1950)

    book = openlibrary.fetch_by_isbn("0451524934")
    assert book is not None
    assert book["title"] == "1984"
    assert book["source"] == "openlibrary"
    assert book["publication_year"] == 1950
    assert book["authors"][0]["name"] == "George Orwell"
    assert book["authors"][0]["death_year"] == 1950


def test_fetch_by_isbn_strips_non_digit_characters(monkeypatch):
    seen_bibkey = {}

    def fake_get(url):
        seen_bibkey["url"] = url
        return {}

    monkeypatch.setattr(openlibrary, "_get", fake_get)
    openlibrary.fetch_by_isbn("978-0-45-152493-4")
    assert "9780451524934" in seen_bibkey["url"]


def test_fetch_by_oclc_found(monkeypatch):
    def fake_get(url):
        return {"OCLC:12345": {"title": "Some Book", "authors": [], "publish_date": "1960"}}

    monkeypatch.setattr(openlibrary, "_get", fake_get)
    book = openlibrary.fetch_by_oclc("12345")
    assert book["title"] == "Some Book"
    assert book["source"] == "openlibrary"
    assert book["publication_year"] == 1960
    assert book["authors"] == []


def test_search_by_title_returns_normalized_results(monkeypatch):
    def fake_get(url):
        return {
            "docs": [
                {
                    "title": "Emma",
                    "author_name": ["Jane Austen"],
                    "author_key": ["OL21594A"],
                    "first_publish_year": 1815,
                    "key": "/works/OL138052W",
                },
            ]
        }

    monkeypatch.setattr(openlibrary, "_get", fake_get)
    monkeypatch.setattr(openlibrary, "_author_death_year", lambda key: 1817)

    results = openlibrary.search_by_title("Emma")
    assert len(results) == 1
    assert results[0]["title"] == "Emma"
    assert results[0]["publication_year"] == 1815
    assert results[0]["authors"][0]["death_year"] == 1817


def test_search_by_title_empty_results(monkeypatch):
    monkeypatch.setattr(openlibrary, "_get", lambda url: {"docs": []})
    assert openlibrary.search_by_title("zzzznonexistentzzzz") == []


def test_get_wraps_bare_oserror_not_just_urllib_types(monkeypatch):
    # Regression test for ISSUE-10 (branch-audit-2026-08-12.md): on Python
    # 3.9, socket.timeout is an OSError subclass but NOT a TimeoutError
    # subclass (that alias was only added in 3.10). A handler written as
    # `except (URLError, HTTPError, TimeoutError)` therefore let a real
    # timeout on 3.9 escape uncaught and 500 the /producers route. This
    # simulates that gap directly with a bare OSError -- neither a URLError,
    # an HTTPError, nor a TimeoutError -- which must still be caught.
    def _raise(*a, **k):
        raise OSError("simulated socket.timeout-shaped failure, pre-3.10 style")
    monkeypatch.setattr(openlibrary.urllib.request, "urlopen", _raise)
    try:
        openlibrary._get("https://openlibrary.org/isbn/0000000000.json")
        assert False, "expected OpenLibraryLookupError -- bare OSError must not escape"
    except openlibrary.OpenLibraryLookupError:
        pass
