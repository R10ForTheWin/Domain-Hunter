#!/usr/bin/env python3
"""
Cross-check: Package 1's calendar rules against Package 2's verification rules.

The same statute is implemented twice in this repo -- pd_calendar/scripts/pd_rules.py
answers "which January 1st does this work enter the public domain", and
pd_verification/rules.py answers "is this work's public-domain claim confirmed
today". Neither is redundant; they are different questions. But they read the same
sections of Title 17, and nothing else in the project checks that they agree.

Two engines that disagree about the same book is the failure this file exists to
catch. It has already caught one: the two carried different renewal-era start
years (1923 vs 1929) before this suite was written.

Package 2 lives on its own branch, so these tests SKIP when it is not present.
That is deliberate -- the suite runs green on this branch alone and starts
actually checking things once both packages are merged into dj-development.
Run it from the repo root so `pd_verification` is importable:

    python3 -m unittest discover -s pd_calendar/scripts -t pd_calendar/scripts -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pd_rules

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from pd_verification import rules as pd_verification_rules
    from pd_verification.models import BookInput

    PACKAGE_2_AVAILABLE = True
except ImportError:
    PACKAGE_2_AVAILABLE = False

needs_package_2 = unittest.skipUnless(
    PACKAGE_2_AVAILABLE,
    "pd_verification is not on this branch — merge Package 2 to run the cross-check",
)

NOW = 2026

# Cases chosen to straddle every boundary the two engines share: the 1978 cutoff,
# the renewal era, the auto-renewal window, and the already/not-yet-public-domain
# line. (publication_year, death_year, label)
SHARED_FIXTURES = [
    (1818, 1851, "long-expired pre-1978 work"),
    (1899, 1904, "turn-of-the-century work"),
    (1922, 1950, "published just before the renewal era"),
    (1923, 1950, "renewal era, first year"),
    (1931, 1940, "enters the public domain in 2027"),
    (1934, 1976, "the Christie case: pub+95 governs, not life+70"),
    (1950, 1951, "life+70 would wrongly free this one"),
    (1963, 1970, "renewal era, last year"),
    (1964, 1980, "auto-renewal window, first year"),
    (1977, 2000, "last year before the 1978 cutoff"),
    (1978, 2000, "first year of life+70"),
    (2005, 2010, "modern work"),
]


class TestStatutoryConstantsMatch(unittest.TestCase):
    """Cheapest possible drift detector: the shared numbers must be identical.

    This fails the moment somebody edits one engine's constants and not the
    other's, which is exactly how the 1923/1929 split happened.
    """

    @needs_package_2
    def test_pre_1978_term_offset(self):
        self.assertEqual(
            pd_rules.PUBLISHED_TERM + 1,
            pd_verification_rules.PRE1978_TERM_YEARS,
            "publication+N offset differs between the two engines",
        )

    @needs_package_2
    def test_life_plus_seventy_offset(self):
        self.assertEqual(
            pd_rules.LIFE_PLUS_TERM + 1,
            pd_verification_rules.LIFE70_OFFSET,
            "life+N offset differs between the two engines",
        )

    @needs_package_2
    def test_renewal_era(self):
        self.assertEqual(
            (pd_rules.RENEWAL_ERA_START, pd_rules.RENEWAL_ERA_END),
            pd_verification_rules.RENEWAL_ERA,
            "renewal era differs between the two engines",
        )

    @needs_package_2
    def test_current_term_cutoff(self):
        """Package 2 has no named constant for 1978; it is written into its branches.

        Assert our value directly so the pairing is at least recorded in one place.
        """
        self.assertEqual(pd_rules.CURRENT_TERM_START, 1978)


class TestNoContradictoryVerdicts(unittest.TestCase):
    """The engines may differ in certainty. They must never flatly contradict.

    A contradiction is one of exactly two things:
      - we date a work to a FUTURE January 1st, and Package 2 says it is
        already confirmed public domain
      - we say a work is ALREADY public domain with confidence, and Package 2
        says the claim is not confirmed

    Either side answering "uncertain" is never a contradiction — that is the
    engines correctly declining to guess, per docs/project-plan.md section 5.
    """

    def _verdict(self, publication_year, death_year):
        book = BookInput(
            book_id="fixture",
            title="Fixture",
            author="Fixture, A.",
            publication_year=publication_year,
            author_death_year=death_year,
        )
        return pd_verification_rules.evaluate(book, as_of_year=NOW)

    @needs_package_2
    def test_future_dates_are_never_confirmed_public_domain(self):
        for pub, death, label in SHARED_FIXTURES:
            term = pd_rules.public_domain_term(pub, death, as_of_year=NOW)
            if term.pd_year is None or term.pd_year <= NOW:
                continue
            with self.subTest(case=label, pd_year=term.pd_year):
                self.assertNotEqual(
                    self._verdict(pub, death).pd_status,
                    "confirmed",
                    f"calendar dates this to {term.pd_year}, but Package 2 confirms it as already"
                    " public domain",
                )

    @needs_package_2
    def test_confidently_elapsed_works_are_never_rejected(self):
        for pub, death, label in SHARED_FIXTURES:
            term = pd_rules.public_domain_term(pub, death, as_of_year=NOW)
            if not term.already_public_domain(NOW) or term.confidence != pd_rules.CONFIRMED:
                continue
            with self.subTest(case=label, pd_year=term.pd_year):
                self.assertNotEqual(
                    self._verdict(pub, death).pd_status,
                    "not_confirmed",
                    f"calendar says this entered the public domain in {term.pd_year}, but Package 2"
                    " rejects the claim",
                )

    @needs_package_2
    def test_every_fixture_produces_a_verdict_from_both_engines(self):
        """Neither engine should crash or return an out-of-contract status."""
        for pub, death, label in SHARED_FIXTURES:
            with self.subTest(case=label):
                term = pd_rules.public_domain_term(pub, death, as_of_year=NOW)
                self.assertIn(
                    term.confidence,
                    (pd_rules.CONFIRMED, pd_rules.DISPUTED, pd_rules.UNCERTAIN),
                )
                self.assertIn(
                    self._verdict(pub, death).pd_status,
                    ("confirmed", "not_confirmed", "uncertain"),
                )


class TestSkipIsVisible(unittest.TestCase):
    def test_reports_whether_the_cross_check_actually_ran(self):
        """Guards against the suite passing green while silently checking nothing."""
        if not PACKAGE_2_AVAILABLE:
            self.skipTest(
                "Package 2 absent — cross-check inactive on this branch. This is expected until "
                "pd_verification merges; it is NOT evidence the two engines agree."
            )
        self.assertTrue(hasattr(pd_verification_rules, "evaluate"))


if __name__ == "__main__":
    unittest.main()
