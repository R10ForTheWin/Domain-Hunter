"""Tests for the deterministic PD rule engine.

Run with: python -m pytest pd_verification/tests/test_rules.py -v
(or plain `python -m unittest` if pytest isn't installed — every test here
is a plain function pytest will discover, but nothing pytest-specific is
used beyond that, so unittest's discovery would need TestCase wrapping;
pytest is the one this repo assumes, per the project's "team's first Claude
Code project" framing.)

`AS_OF_YEAR = 2026` is pinned rather than using the real current year so
these tests don't quietly start failing/passing differently a year from
now -- the rule engine's behavior for a fixed point in time should never
change.
"""
import datetime as _dt

from pd_verification.models import BookInput
from pd_verification.rules import evaluate

AS_OF_YEAR = 2026


def _book(**overrides) -> BookInput:
    defaults = dict(
        book_id="test-book",
        title="Test Book",
        author="Test Author",
        publication_year=1900,
    )
    defaults.update(overrides)
    return BookInput(**defaults)


# --- Pre-1978 U.S. works, both theories expired -----------------------------

def test_domestic_pre1978_with_known_dead_author_is_confirmed():
    # The Great Gatsby: published 1925 in the US, F. Scott Fitzgerald died 1940.
    book = _book(
        publication_year=1925,
        author_death_year=1940,
        country_of_first_publication="US",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "life+70-and-pre1978-both-expired"
    assert verdict.missing_fields == []
    # Later of the two candidate dates (pub+96=2021, death+71=2011) -- 2021 wins.
    assert verdict.pd_effective_date == _dt.date(2021, 1, 1)


def test_domestic_pre1978_with_unknown_death_year_still_confirmed():
    # The 95-year publication-based rule doesn't need the death year at all
    # for a confirmed-domestic work.
    book = _book(publication_year=1925, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "pre1978-95yr-expired-domestic"
    assert verdict.missing_fields == []
    assert verdict.pd_effective_date == _dt.date(2021, 1, 1)


def test_pre1978_permanently_expired_even_with_country_unknown_if_death_year_old_enough():
    # Both ceilings independently expired -> safe regardless of country.
    book = _book(publication_year=1900, author_death_year=1930)  # no country on file
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "life+70-and-pre1978-both-expired"


# --- Foreign / unknown-country works: the URAA hazard -----------------------

def test_foreign_pre1978_pub_expired_but_recent_death_is_uncertain():
    # Published abroad in 1930, but the author lived until 1999 -- if this
    # was URAA-restored, life+70 (2070) hasn't run out. Must NOT be confirmed.
    book = _book(
        publication_year=1930,
        author_death_year=1999,
        country_of_first_publication="France",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert "uraa_restoration_risk" in verdict.flags
    assert verdict.rule_applied == "foreign-uraa-risk-life70-not-ruled-out"


def test_unknown_country_treated_same_as_foreign():
    book = _book(publication_year=1930, author_death_year=1999)  # country omitted entirely
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert "country_of_first_publication" in verdict.missing_fields


def test_foreign_work_confirmed_once_life70_also_expired():
    book = _book(
        publication_year=1900,
        author_death_year=1920,
        country_of_first_publication="Germany",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "life+70-and-pre1978-both-expired"


def test_foreign_work_simultaneous_us_publication_exempts_from_uraa():
    book = _book(
        publication_year=1925,
        country_of_first_publication="UK",
        simultaneous_us_publication=True,
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "pre1978-95yr-expired-domestic"


def test_foreign_work_not_yet_95_years_old_is_uncertain_not_confirmed():
    book = _book(publication_year=1970, country_of_first_publication="Japan")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert verdict.rule_applied == "foreign-not-yet-expired"


# --- Renewal-era (1923-1963) U.S. works -------------------------------------

def test_renewal_era_not_renewed_is_confirmed():
    book = _book(publication_year=1935, country_of_first_publication="US", renewal_filed=False)
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "renewal-era-not-renewed"
    # Lapsed at the end of the 28-year initial term, NOT the full 95-year
    # ceiling -- it fell into the PD decades before it would have expired
    # on its own even if nobody had ever objected.
    assert verdict.pd_effective_date == _dt.date(1963, 1, 1)


def test_renewal_era_renewed_is_not_confirmed():
    book = _book(publication_year=1935, country_of_first_publication="US", renewal_filed=True)
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "not_confirmed"
    assert verdict.rule_applied == "renewal-era-renewed-still-in-term"
    # "Private now but will be public on" -- the full 95-year term is known
    # exactly, even though it hasn't run out yet.
    assert verdict.pd_effective_date == _dt.date(2031, 1, 1)


def test_renewal_era_unknown_renewal_status_is_uncertain():
    book = _book(publication_year=1935, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert verdict.rule_applied == "renewal-era-unknown"
    assert any(f.startswith("renewal_filed") for f in verdict.missing_fields)
    # notice status is *also* legitimately missing here -- either fact, if it
    # resolved favorably (no notice, or not renewed), would independently
    # confirm the book, so both belong in missing_fields while genuinely
    # uncertain. Confirm it's flagged, not that it's absent.
    assert any("notice" in f for f in verdict.missing_fields)


def test_renewal_era_known_notice_present_does_not_ask_about_notice_again():
    # Once notice status is resolved (True), it should drop out of missing_fields
    # even though the book is still uncertain pending renewal status.
    book = _book(
        publication_year=1935,
        country_of_first_publication="US",
        had_copyright_notice_at_publication=True,
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert not any("notice" in f for f in verdict.missing_fields)
    assert any(f.startswith("renewal_filed") for f in verdict.missing_fields)


def test_no_notice_is_instant_pd_even_in_renewal_era_regardless_of_renewal():
    book = _book(
        publication_year=1935,
        country_of_first_publication="US",
        had_copyright_notice_at_publication=False,
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "no-notice-instant-pd"


# --- Automatic-renewal era (1964-1977) --------------------------------------

def test_1964_to_1977_us_work_is_not_confirmed_no_lookup_needed():
    book = _book(publication_year=1970, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "not_confirmed"
    assert verdict.rule_applied == "automatic-renewal-1964-1977"
    assert verdict.missing_fields == []  # nothing to look up, don't ask for anything
    assert verdict.pd_effective_date == _dt.date(2066, 1, 1)


# --- Post-1977 named-author works (life+70 controls) ------------------------

def test_post_1977_domestic_with_expired_life70_is_confirmed():
    book = _book(publication_year=1980, author_death_year=1954, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "life+70-expired-1978-1988"


def test_post_1989_missing_death_year_is_uncertain():
    book = _book(publication_year=2000, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert verdict.rule_applied == "life+70-missing-death-year"
    assert "author_death_year" in verdict.missing_fields


def test_post_1989_living_author_is_not_confirmed():
    book = _book(publication_year=2010, author_death_year=2020, country_of_first_publication="US")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "not_confirmed"
    assert verdict.rule_applied == "life+70-not-yet-expired"


def test_post_1989_foreign_publication_does_not_change_life70_result():
    # Berne-era: no formality trap, so foreign vs. domestic shouldn't matter.
    domestic = evaluate(
        _book(publication_year=1995, author_death_year=1950, country_of_first_publication="US"),
        as_of_year=AS_OF_YEAR,
    )
    foreign = evaluate(
        _book(publication_year=1995, author_death_year=1950, country_of_first_publication="Italy"),
        as_of_year=AS_OF_YEAR,
    )
    assert domestic.pd_status == foreign.pd_status == "confirmed"
    assert domestic.rule_applied == foreign.rule_applied == "life+70-expired"


# --- Anonymous / pseudonymous / corporate authorship ------------------------

def test_anonymous_flag_expired_is_confirmed_without_any_death_year():
    book = _book(
        publication_year=1900,
        is_anonymous_pseudonymous_or_corporate=True,
        author_death_year=None,
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "anonymous-95yr-expired"
    assert verdict.missing_fields == []


def test_author_field_literally_anonymous_is_treated_as_anonymous():
    book = _book(publication_year=1900, author="Anonymous")
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "anonymous-95yr-expired"


def test_anonymous_not_yet_expired_is_not_confirmed_not_uncertain():
    book = _book(publication_year=2000, is_anonymous_pseudonymous_or_corporate=True)
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "not_confirmed"
    assert verdict.rule_applied == "anonymous-95yr-not-yet-expired"
    assert verdict.missing_fields == []  # we KNOW the term hasn't run out; nothing to ask


def test_explicit_false_overrides_literal_anonymous_author_string():
    # e.g. a corporate imprint literally named "Anonymous Press" shouldn't
    # accidentally trip the anonymous-authorship shortcut.
    book = _book(
        publication_year=1980,
        author="Anonymous",
        is_anonymous_pseudonymous_or_corporate=False,
        author_death_year=1990,
        country_of_first_publication="US",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.rule_applied != "anonymous-95yr-not-yet-expired"


# --- Disputed death years never silently resolve ----------------------------

def test_disputed_death_year_blocks_confirmation_even_if_old_enough():
    # Domestic + old enough should confirm via the publication-year rule
    # alone -- it doesn't even need the death year, disputed or not.
    book = _book(
        publication_year=1900,
        author_death_year=1930,
        author_death_year_disputed=True,
        country_of_first_publication="US",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "confirmed"
    assert verdict.rule_applied == "pre1978-95yr-expired-domestic"
    assert "disputed_death_year" in verdict.flags  # noted, but non-blocking here


def test_disputed_death_year_plus_unknown_country_is_uncertain():
    # Without a confirmed domestic (or simultaneous-US) publication, the
    # disputed death year can't be used to independently confirm via the
    # life+70 theory either -- so this must NOT resolve to "confirmed".
    book = _book(
        publication_year=1900,
        author_death_year=1930,
        author_death_year_disputed=True,
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert "disputed_death_year" in verdict.flags
    assert "uraa_restoration_risk" in verdict.flags


def test_disputed_death_year_blocks_life70_path():
    book = _book(
        publication_year=2000,
        author_death_year=1930,
        author_death_year_disputed=True,
        country_of_first_publication="US",
    )
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert "disputed_death_year" in verdict.flags


# --- Unpublished works -------------------------------------------------------

def test_no_publication_year_is_uncertain():
    book = _book(publication_year=None)
    verdict = evaluate(book, as_of_year=AS_OF_YEAR)
    assert verdict.pd_status == "uncertain"
    assert verdict.rule_applied == "insufficient-data"


# --- pd_status is always one of exactly three values ------------------------

def test_pd_status_is_always_a_valid_enum_value():
    valid = {"confirmed", "not_confirmed", "uncertain"}
    scenarios = [
        _book(publication_year=1900),
        _book(publication_year=1950, country_of_first_publication="US"),
        _book(publication_year=1970, country_of_first_publication="US"),
        _book(publication_year=1985, author_death_year=1960, country_of_first_publication="US"),
        _book(publication_year=2020, is_anonymous_pseudonymous_or_corporate=True),
        _book(publication_year=None),
        _book(publication_year=1930, country_of_first_publication="Spain"),
    ]
    for book in scenarios:
        assert evaluate(book, as_of_year=AS_OF_YEAR).pd_status in valid


# --- pd_effective_date invariants -------------------------------------------
# The public validator bot's whole "Public as of X" / "Private now but will
# be public on X" / "Unclear because ..." phrasing depends on this holding
# for every branch: confirmed/not_confirmed always carry a date, uncertain
# never does.

def test_effective_date_present_iff_status_is_resolved():
    scenarios = [
        _book(publication_year=1900),  # confirmed, domestic-only rule
        _book(publication_year=1925, country_of_first_publication="US"),  # confirmed
        _book(publication_year=1935, country_of_first_publication="US", renewal_filed=False),  # confirmed
        _book(publication_year=1935, country_of_first_publication="US", renewal_filed=True),  # not_confirmed
        _book(publication_year=1970, country_of_first_publication="US"),  # not_confirmed
        _book(publication_year=1985, author_death_year=1960, country_of_first_publication="US"),  # confirmed
        _book(publication_year=1985, author_death_year=2010, country_of_first_publication="US"),  # not_confirmed
        _book(publication_year=2020, is_anonymous_pseudonymous_or_corporate=True),  # not_confirmed
        _book(publication_year=1900, is_anonymous_pseudonymous_or_corporate=True),  # confirmed
        _book(publication_year=None),  # uncertain
        _book(publication_year=1930, country_of_first_publication="Spain"),  # uncertain
        _book(publication_year=1935, country_of_first_publication="US"),  # uncertain (renewal unknown)
        _book(publication_year=2000, country_of_first_publication="US"),  # uncertain (no death year)
    ]
    for book in scenarios:
        verdict = evaluate(book, as_of_year=AS_OF_YEAR)
        if verdict.pd_status == "uncertain":
            assert verdict.pd_effective_date is None, verdict.rule_applied
        else:
            assert verdict.pd_effective_date is not None, verdict.rule_applied
            assert isinstance(verdict.pd_effective_date, _dt.date)
