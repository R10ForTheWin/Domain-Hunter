#!/usr/bin/env python3
"""
Tests for pd_rules.

Run from the repo root:  python3 -m unittest discover -s pd_calendar/scripts -v

Every case pins as_of_year explicitly so the suite does not start failing on
Jan 1 of some future year.
"""
from __future__ import annotations

import unittest

from pd_rules import (
    CONFIRMED,
    DISPUTED,
    SECTION_303_FLOOR,
    UNCERTAIN,
    entering_in,
    next_cliffs,
    public_domain_term,
)

NOW = 2026


def term(publication_year=None, death_year=None, **kwargs):
    kwargs.setdefault("as_of_year", NOW)
    return public_domain_term(publication_year, death_year, **kwargs)


class TestPublicationRule(unittest.TestCase):
    """Works published before 1978 run 95 years from publication."""

    def test_old_work_is_already_public_domain(self):
        t = term(publication_year=1818, death_year=1851)
        self.assertEqual(t.rule_applied, "pub+95")
        self.assertEqual(t.pd_year, 1914)
        self.assertTrue(t.already_public_domain(NOW))
        self.assertEqual(t.confidence, CONFIRMED)

    def test_1931_enters_in_2027(self):
        t = term(publication_year=1931, death_year=1940)
        self.assertEqual(t.pd_year, 2027)
        self.assertEqual(t.pd_date, "2027-01-01")

    def test_death_year_does_not_affect_the_date(self):
        early_death = term(publication_year=1934, death_year=1935)
        late_death = term(publication_year=1934, death_year=1976)
        self.assertEqual(early_death.pd_year, late_death.pd_year)
        self.assertEqual(early_death.pd_year, 2030)

    def test_christie_regression(self):
        """The worked example from the module docstring.

        Died 1976, published 1934. life+70 would say 2047; the correct answer is
        2030. This is the case that motivated the whole module, so it is pinned.
        """
        t = term(publication_year=1934, death_year=1976)
        self.assertEqual(t.pd_year, 2030)
        self.assertNotEqual(t.pd_year, 1976 + 71)

    def test_life_plus_seventy_would_wrongly_free_a_protected_work(self):
        """Died 1951, published 1950: life+70 says 2022, pub+95 says 2046.

        The dangerous direction -- declaring free something still in copyright.
        """
        t = term(publication_year=1950, death_year=1951)
        self.assertEqual(t.pd_year, 2046)
        self.assertFalse(t.already_public_domain(NOW))

    def test_disputed_death_year_is_irrelevant_under_this_rule(self):
        """The rule never reads the death year, so a dispute cannot taint it.

        The flag is still recorded for traceability, but confidence stays
        confirmed -- flagging it as disputed would misreport the reason.
        """
        t = term(publication_year=1900, death_year=1910, death_year_disputed=True)
        self.assertEqual(t.confidence, CONFIRMED)
        self.assertIn("disputed_death_year", t.flags)


class TestRenewalEra(unittest.TestCase):
    def test_renewal_era_is_uncertain(self):
        t = term(publication_year=1950, death_year=1970)
        self.assertIn("renewal_era", t.flags)
        self.assertEqual(t.confidence, UNCERTAIN)

    def test_renewal_era_date_is_the_latest_possible(self):
        t = term(publication_year=1950, death_year=1970)
        self.assertEqual(t.pd_year, 2046)
        self.assertIn("already public domain", t.reasoning)

    def test_boundaries(self):
        """Start year is 1923, matching pd_verification/rules.py -- see test_cross_check.py."""
        self.assertIn("renewal_era", term(publication_year=1923, death_year=1950).flags)
        self.assertIn("renewal_era", term(publication_year=1963, death_year=1970).flags)
        self.assertNotIn("renewal_era", term(publication_year=1922, death_year=1950).flags)
        self.assertNotIn("renewal_era", term(publication_year=1964, death_year=1980).flags)

    def test_automatic_renewal_window_is_confirmed(self):
        """1964-1977 renewal was automatic, so no flag and no uncertainty."""
        t = term(publication_year=1964, death_year=1980)
        self.assertNotIn("renewal_era", t.flags)
        self.assertEqual(t.confidence, CONFIRMED)
        self.assertEqual(t.pd_year, 2060)


class TestLifeRule(unittest.TestCase):
    """Works published 1978 onward run life plus 70."""

    def test_modern_work_uses_death_year(self):
        t = term(publication_year=2005, death_year=2010)
        self.assertEqual(t.rule_applied, "life+70")
        self.assertEqual(t.pd_year, 2081)

    def test_cutoff_boundary(self):
        self.assertEqual(term(publication_year=1977, death_year=2000).rule_applied, "pub+95")
        self.assertEqual(term(publication_year=1978, death_year=2000).rule_applied, "life+70")

    def test_disputed_death_year_makes_it_disputed(self):
        t = term(publication_year=2005, death_year=2010, death_year_disputed=True)
        self.assertEqual(t.confidence, DISPUTED)

    def test_missing_death_year_is_uncertain_with_no_date(self):
        t = term(publication_year=2005, death_year=None)
        self.assertIsNone(t.pd_year)
        self.assertEqual(t.pd_date, "")
        self.assertEqual(t.confidence, UNCERTAIN)
        self.assertIn("missing_death_year", t.flags)

    def test_section_303_floor_raises_an_elapsed_term(self):
        """Created pre-1978, first published 1985, author died 1950.

        life+70 alone gives 2021 -- already elapsed. Section 303 holds it to 2048.
        """
        t = term(publication_year=1985, death_year=1950)
        self.assertEqual(t.pd_year, SECTION_303_FLOOR)
        self.assertIn("section_303_floor", t.flags)
        self.assertFalse(t.already_public_domain(NOW))

    def test_section_303_does_not_lower_a_later_date(self):
        t = term(publication_year=1985, death_year=2000)
        self.assertEqual(t.pd_year, 2071)
        self.assertNotIn("section_303_floor", t.flags)


class TestMissingPublicationYear(unittest.TestCase):
    """A quarter of the corpus has no publication year."""

    def test_long_dead_author_is_already_public_domain(self):
        t = term(publication_year=None, death_year=1919)
        self.assertEqual(t.rule_applied, "lifetime-pub-bound")
        self.assertEqual(t.pd_year, 2015)
        self.assertTrue(t.already_public_domain(NOW))
        self.assertEqual(t.confidence, UNCERTAIN)
        self.assertIn("inferred_from_death_year", t.flags)

    def test_recent_author_yields_no_date(self):
        """A future bound is consistent with any publication year, so it concludes nothing."""
        t = term(publication_year=None, death_year=1990)
        self.assertIsNone(t.pd_year)
        self.assertEqual(t.confidence, UNCERTAIN)
        self.assertNotIn("inferred_from_death_year", t.flags)

    def test_nothing_recorded_is_unknown(self):
        t = term(publication_year=None, death_year=None)
        self.assertEqual(t.rule_applied, "unknown")
        self.assertIsNone(t.pd_year)
        self.assertEqual(t.confidence, UNCERTAIN)
        self.assertIn("missing_publication_year", t.flags)
        self.assertIn("missing_death_year", t.flags)

    def test_inference_is_never_confirmed(self):
        """It assumes publication during the author's lifetime, which can be false."""
        self.assertEqual(term(publication_year=None, death_year=1800).confidence, UNCERTAIN)


class TestFlags(unittest.TestCase):
    def test_foreign_language_is_uncertain(self):
        t = term(publication_year=1900, death_year=1910, language="fr")
        self.assertIn("foreign_publication", t.flags)
        self.assertEqual(t.confidence, UNCERTAIN)

    def test_english_variants_are_not_flagged(self):
        for code in ("en", "eng", "EN", " en "):
            self.assertNotIn(
                "foreign_publication",
                term(publication_year=1900, death_year=1910, language=code).flags,
                f"{code!r} should read as English",
            )

    def test_publication_after_death_is_flagged(self):
        """Open Library reprint dates show up this way -- see the corpus notes column."""
        t = term(publication_year=1970, death_year=1932)
        self.assertIn("publication_after_death", t.flags)
        self.assertEqual(t.confidence, UNCERTAIN)

    def test_future_date_is_refused_when_publication_year_is_untrustworthy(self):
        """324 corpus rows record a reprint date as first publication.

        pub+95 would put this at 2066, but a reprint date only ever moves the
        true date earlier, so the calendar publishes nothing rather than a date
        that could be decades wrong.
        """
        t = term(publication_year=1970, death_year=1932)
        self.assertIsNone(t.pd_year)
        self.assertEqual(t.pd_date, "")
        self.assertIn("reprint", t.reasoning)

    def test_elapsed_date_survives_an_untrustworthy_publication_year(self):
        """Both readings agree once pub+96 has passed, so the date is still safe.

        A reprint date can only move the true date earlier, and earlier than
        "already public domain" is still already public domain.
        """
        t = term(publication_year=1910, death_year=1900)
        self.assertIn("publication_after_death", t.flags)
        self.assertEqual(t.pd_year, 2006)
        self.assertTrue(t.already_public_domain(NOW))
        self.assertEqual(t.confidence, UNCERTAIN)

    def test_refusal_needs_both_a_bad_year_and_a_future_date(self):
        """A trustworthy publication year keeps its future date."""
        t = term(publication_year=1970, death_year=1980)
        self.assertNotIn("publication_after_death", t.flags)
        self.assertEqual(t.pd_year, 2066)

    def test_flags_field_matches_the_contract_format(self):
        t = term(publication_year=1950, death_year=1970, language="de")
        self.assertEqual(t.flags_field(), "foreign_publication;renewal_era")


class TestCliffs(unittest.TestCase):
    def test_next_five_cliffs_from_2026(self):
        self.assertEqual(next_cliffs(2026), [2027, 2028, 2029, 2030, 2031])

    def test_count_is_adjustable(self):
        self.assertEqual(next_cliffs(2026, count=2), [2027, 2028])

    def test_entering_in_window(self):
        window = next_cliffs(2026)
        self.assertTrue(entering_in(term(publication_year=1931, death_year=1940), window))
        self.assertFalse(entering_in(term(publication_year=1818, death_year=1851), window))

    def test_undetermined_work_never_matches_a_cliff(self):
        self.assertFalse(entering_in(term(), next_cliffs(2026)))


if __name__ == "__main__":
    unittest.main()
