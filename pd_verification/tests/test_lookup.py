"""Tests for the identifier-dispatch layer. All lookups are mocked -- no
real network calls.
"""
from pd_verification import gutenberg, lookup, openlibrary


def _gb_book(**overrides):
    base = {
        "source": "gutenberg", "source_id": "84", "gutenberg_id": 84,
        "title": "Frankenstein", "authors": [{"name": "Mary Shelley", "birth_year": 1797, "death_year": 1851}],
        "publication_year": None,
    }
    base.update(overrides)
    return base


# --- resolve_author_death_year ----------------------------------------------

def test_resolve_death_year_single_author_known():
    year, gap = lookup.resolve_author_death_year([{"name": "A", "death_year": 1950}])
    assert year == 1950
    assert gap is False


def test_resolve_death_year_no_authors():
    year, gap = lookup.resolve_author_death_year([])
    assert year is None
    assert gap is False


def test_resolve_death_year_joint_work_all_known_uses_latest():
    authors = [{"name": "A", "death_year": 1950}, {"name": "B", "death_year": 1980}]
    year, gap = lookup.resolve_author_death_year(authors)
    assert year == 1980
    assert gap is False


def test_resolve_death_year_joint_work_one_unknown_is_a_gap():
    authors = [{"name": "A", "death_year": 1950}, {"name": "B", "death_year": None}]
    year, gap = lookup.resolve_author_death_year(authors)
    assert year is None
    assert gap is True


def test_resolve_death_year_single_author_unknown_no_gap_flag():
    # Not a "joint work gap" -- just an ordinary unknown for a solo author.
    year, gap = lookup.resolve_author_death_year([{"name": "A", "death_year": None}])
    assert year is None
    assert gap is False


# --- locate_book: gutenberg_id -----------------------------------------------

def test_locate_by_gutenberg_id_found(monkeypatch):
    monkeypatch.setattr(gutenberg, "fetch_by_id", lambda gid: _gb_book())
    result = lookup.locate_book("gutenberg_id", "84")
    assert result.status == "found"
    assert result.book["title"] == "Frankenstein"


def test_locate_by_gutenberg_id_not_found(monkeypatch):
    monkeypatch.setattr(gutenberg, "fetch_by_id", lambda gid: None)
    result = lookup.locate_book("gutenberg_id", "999999999")
    assert result.status == "not_found"
    assert "Project Gutenberg" in result.message


def test_locate_by_gutenberg_id_non_numeric_input():
    result = lookup.locate_book("gutenberg_id", "not-a-number")
    assert result.status == "not_found"


# --- locate_book: isbn / oclc -------------------------------------------------

def test_locate_by_isbn_found(monkeypatch):
    monkeypatch.setattr(openlibrary, "fetch_by_isbn", lambda isbn: {"title": "1984", "source": "openlibrary"})
    result = lookup.locate_book("isbn", "0451524934")
    assert result.status == "found"
    assert result.book["title"] == "1984"


def test_locate_by_isbn_not_found(monkeypatch):
    monkeypatch.setattr(openlibrary, "fetch_by_isbn", lambda isbn: None)
    result = lookup.locate_book("isbn", "0000000000")
    assert result.status == "not_found"
    assert "ISBN" in result.message


def test_locate_by_oclc_not_found(monkeypatch):
    monkeypatch.setattr(openlibrary, "fetch_by_oclc", lambda oclc: None)
    result = lookup.locate_book("oclc", "123")
    assert result.status == "not_found"
    assert "OCLC" in result.message


# --- locate_book: book_name (search + ambiguity policy) ----------------------

def test_locate_by_name_single_gutenberg_match(monkeypatch):
    monkeypatch.setattr(gutenberg, "search", lambda q, limit=5: [_gb_book()])
    result = lookup.locate_book("book_name", "Frankenstein")
    assert result.status == "found"
    assert result.book["title"] == "Frankenstein"


def test_locate_by_name_multiple_matches_picks_most_relevant(monkeypatch):
    # Demo-mode behavior (deliberate presentation-day tradeoff, see
    # lookup.py's comment on this branch): several plausible matches no
    # longer stops to ask for a unique identifier -- it takes the first
    # (most-relevant, per Gutendex/Open Library's own ranking) result.
    first, second = _gb_book(), _gb_book(title="Frankenstein Junior")
    monkeypatch.setattr(gutenberg, "search", lambda q, limit=5: [first, second])
    result = lookup.locate_book("book_name", "Frankenstein")
    assert result.status == "found"
    assert result.book == first


def test_locate_by_name_known_override_is_network_free(monkeypatch):
    # "bible" is deliberately overridden (lookup.py's
    # _KNOWN_AMBIGUOUS_OVERRIDES) to fixed, static data -- not just a
    # different Gutenberg endpoint -- since Gutendex itself has been
    # observed flaky/timing out. Neither network function should ever be
    # called for an overridden query.
    def _fail_if_called(*_a, **_kw):
        raise AssertionError("network lookup should not be called for an overridden query")

    monkeypatch.setattr(gutenberg, "search", _fail_if_called)
    monkeypatch.setattr(gutenberg, "fetch_by_id", _fail_if_called)
    monkeypatch.setattr(openlibrary, "search_by_title", _fail_if_called)

    result = lookup.locate_book("book_name", "Bible")
    assert result.status == "found"
    assert result.book["title"] == "The King James Version of the Bible"
    assert result.book["publication_year"] == 1611

    # Case-insensitive.
    result_lower = lookup.locate_book("book_name", "bible")
    assert result_lower.status == "found"


def test_locate_by_name_falls_back_to_open_library_when_gutenberg_empty(monkeypatch):
    monkeypatch.setattr(gutenberg, "search", lambda q, limit=5: [])
    monkeypatch.setattr(
        openlibrary, "search_by_title",
        lambda q, limit=5: [{"source": "openlibrary", "source_id": "/works/OL1W", "title": "Some Modern Book"}],
    )
    result = lookup.locate_book("book_name", "Some Modern Book")
    assert result.status == "found"
    assert result.book["title"] == "Some Modern Book"


def test_locate_by_name_nothing_anywhere_is_not_found(monkeypatch):
    monkeypatch.setattr(gutenberg, "search", lambda q, limit=5: [])
    monkeypatch.setattr(openlibrary, "search_by_title", lambda q, limit=5: [])
    result = lookup.locate_book("book_name", "zzzznonexistentzzzz")
    assert result.status == "not_found"


def test_locate_by_name_empty_query():
    result = lookup.locate_book("book_name", "   ")
    assert result.status == "not_found"


# --- error propagation --------------------------------------------------------

def test_lookup_error_surfaces_as_error_status(monkeypatch):
    def raise_error(gid):
        raise gutenberg.GutenbergLookupError("network is down")

    monkeypatch.setattr(gutenberg, "fetch_by_id", raise_error)
    result = lookup.locate_book("gutenberg_id", "84")
    assert result.status == "error"
    assert "network is down" in result.message


def test_unknown_identifier_type_is_an_error():
    result = lookup.locate_book("carrier_pigeon", "84")
    assert result.status == "error"
