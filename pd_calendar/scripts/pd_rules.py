#!/usr/bin/env python3
"""
U.S. public-domain term rules for the Forward-Looking PD Calendar (Package 1).

Pure logic, no I/O: hand it a publication year and an author death year and it
returns which January 1st the work enters the public domain, which rule produced
that date, and how much the answer should be trusted.

THE THING TO UNDERSTAND BEFORE READING FURTHER
----------------------------------------------
For the books in this corpus the death year usually does NOT govern. U.S. works
published before 1978 run 95 years from PUBLICATION no matter when the author
died; only works published 1978 or later use life+70.

Both pd_calendar/README.md and the notes column of data/book_corpus.csv describe
the calendar as a life+70 calculation ("PD via life+70 rule ... independent of
publication year"). That is the wrong rule for a corpus of pre-1978 books. It
happens to give the right answer for very old titles, where both rules resolved
decades ago, and goes badly wrong at the recent end -- which is exactly the end a
five-year forward calendar is looking at:

    Agatha Christie died 1976; "Murder on the Orient Express" published 1934.
      life+70 -> 1976 + 71 = PD in 2047     (wrong)
      pub+95  -> 1934 + 96 = PD in 2030     (correct)

The error runs in the dangerous direction too. An author who died in 1951 with a
book published in 1950 comes out as PD in 2022 under life+70, when the real date
is 2046 -- i.e. life+70 declares a work free that is still in copyright.

RULES IMPLEMENTED (17 U.S.C. 302-304)
-------------------------------------
    pub+95   published before 1978   -> PD on Jan 1 of publication_year + 96
    life+70  published 1978 onward   -> PD on Jan 1 of death_year + 71

with three complications that are flagged rather than guessed at, per the
"when unsure, mark it uncertain" ground rule in docs/project-plan.md section 5:

    renewal era (published 1929-1963)
        Copyright had to be renewed in its 28th year. Un-renewed works fell into
        the public domain early, often decades ago. Renewal is a fact about a
        filing, not something derivable from the four fields we hold, so pub+95
        is only the LATEST possible date. Marked uncertain.

    section 303 (created before 1978, first published 1978-2002)
        Protected through at least Dec 31 2047 even when life+70 has already
        elapsed. Raises the date rather than lowering it.

    foreign publication
        A work that lapsed in the U.S. on a formality may have been restored by
        the URAA. The real test is country of first publication, which the corpus
        has no column for, so `language` is used as a weak proxy -- it
        under-detects (Conrad and Joyce both read as `en`). Marked uncertain.

Deliberately not implemented: corporate/anonymous authorship, which runs 95 years
from publication or 120 from creation, whichever expires first. The corpus has no
column distinguishing it, so every row is treated as individually authored.

SCOPE
-----
This answers "WHEN does this enter the public domain", which is the calendar's
question. It is not Package 2's verification agent, which answers the different
question "is this specific PD claim confirmed" and lives on its own branch. The
underlying statute is shared; the outputs are not. Keep them separate.
"""
from __future__ import annotations

from dataclasses import dataclass

# 17 U.S.C. 302: works created 1978 onward run for the life of the author plus 70
# years. Everything published before that cutoff runs 95 years from publication
# under 17 U.S.C. 304.
CURRENT_TERM_START = 1978
LIFE_PLUS_TERM = 70
PUBLISHED_TERM = 95

# Copyright runs through Dec 31 of the final year of its term, so a work whose
# term ends in year N is public domain on Jan 1 of N+1. Every date this module
# produces is a January 1st -- see docs/project-plan.md section 1 for why works
# do not trickle into the public domain through the year.
_ENTERS_YEAR_AFTER = 1

# Renewal required in the 28th year; renewal became automatic for 1964-1977, so
# those need no flag.
#
# The start year is 1923, matching RENEWAL_ERA in pd_verification/rules.py.
# pd_calendar/README.md and the original data-contracts.md both say 1929-1963,
# which is the figure that was correct while the Sonny Bono Act had the
# public-domain line frozen at 1923 through 2018. 1923 is the statutory start.
# The difference is inert either way -- works published 1923-1930 are already
# public domain under pub+95 as of 2026 -- but the two engines must not carry
# different numbers for the same statute. See test_cross_check.py.
RENEWAL_ERA_START = 1923
RENEWAL_ERA_END = 1963

# 17 U.S.C. 303: works created before 1978 but first published in this window
# stay protected through at least Dec 31 2047.
SECTION_303_START = 1978
SECTION_303_END = 2002
SECTION_303_FLOOR = 2048

# Weak proxy for country of first publication -- see the module docstring.
ENGLISH_LANGUAGE_CODES = frozenset({"en", "eng", "en-us", "en-gb"})

CONFIRMED = "confirmed"
DISPUTED = "disputed"
UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class Term:
    """One book's public-domain determination.

    `pd_year` is None whenever the inputs cannot support a date. That is a real
    answer, not a failure -- it maps to `confidence == "uncertain"` and belongs
    in the calendar as such rather than being dropped or guessed at.
    """

    pd_year: int | None
    rule_applied: str
    confidence: str
    flags: tuple[str, ...]
    reasoning: str

    @property
    def pd_date(self) -> str:
        """`YYYY-01-01`, or empty string when no date could be determined."""
        return f"{self.pd_year}-01-01" if self.pd_year is not None else ""

    def already_public_domain(self, as_of_year: int) -> bool:
        return self.pd_year is not None and self.pd_year <= as_of_year

    def flags_field(self) -> str:
        """Semicolon-separated, matching the `flags` convention in docs/data-contracts.md."""
        return ";".join(self.flags)


def public_domain_term(
    publication_year: int | None,
    death_year: int | None,
    *,
    as_of_year: int,
    language: str = "en",
    death_year_disputed: bool = False,
) -> Term:
    """Determine when a work enters the U.S. public domain.

    `as_of_year` is required rather than read from the system clock so results
    are reproducible and testable -- a calendar that silently changes answers
    depending on the day it was run is not reviewable.
    """
    flags: list[str] = []

    if death_year_disputed:
        flags.append("disputed_death_year")
    if language and language.strip().lower() not in ENGLISH_LANGUAGE_CODES:
        flags.append("foreign_publication")

    if publication_year is None:
        return _without_publication_year(death_year, flags, as_of_year)

    if publication_year >= CURRENT_TERM_START:
        return _life_plus_seventy(publication_year, death_year, flags, death_year_disputed)

    return _publication_plus_ninety_five(publication_year, death_year, flags, as_of_year)


def _publication_plus_ninety_five(
    publication_year: int,
    death_year: int | None,
    flags: list[str],
    as_of_year: int,
) -> Term:
    """The rule that governs almost everything in this corpus."""
    pd_year = publication_year + PUBLISHED_TERM + _ENTERS_YEAR_AFTER

    if RENEWAL_ERA_START <= publication_year <= RENEWAL_ERA_END:
        flags.append("renewal_era")
    if death_year is not None and publication_year > death_year:
        # Either a genuine posthumous publication or, more often in this corpus,
        # a modern reprint date that Open Library recorded as first publication.
        flags.append("publication_after_death")

        # 324 rows of data/book_corpus.csv are in this state, so the recorded
        # year cannot be trusted as FIRST publication -- and pub+95 keys off
        # exactly that. Both readings agree the work is public domain once
        # pub+96 has passed (a reprint date only ever moves the true date
        # EARLIER), so an elapsed date is still safe to publish. A future one is
        # not: if the year is a reprint, the real date could be decades sooner,
        # and a calendar entry is a claim about a specific January 1st. Refuse
        # the date rather than propagate a wrong one -- docs/project-plan.md
        # section 5, "mark it uncertain rather than guessing".
        if pd_year > as_of_year:
            return Term(
                None,
                "pub+95",
                UNCERTAIN,
                tuple(flags),
                f"Recorded publication year {publication_year} is later than the author's death in"
                f" {death_year}, so it is most likely a reprint date rather than first publication."
                f" pub+95 would give Jan 1 {pd_year}, but if the year is a reprint the true date is"
                " earlier by an unknown amount, so no calendar date is published. Needs a verified"
                " first-publication year.",
            )

    confidence = UNCERTAIN if _uncertain_flags(flags) else CONFIRMED

    reasoning = (
        f"Published {publication_year}, before the {CURRENT_TERM_START} cutoff, so the term is "
        f"{PUBLISHED_TERM} years from publication and the work enters the public domain on "
        f"Jan 1 {pd_year}. The author's death year does not affect this."
    )
    if "renewal_era" in flags:
        reasoning += (
            f" Published in the {RENEWAL_ERA_START}-{RENEWAL_ERA_END} renewal era, so this date is"
            " the latest possible one: if copyright was never renewed the work is already public"
            " domain. Renewal records are needed to say which."
        )
    if "publication_after_death" in flags:
        reasoning += (
            f" Publication year {publication_year} is later than the author's death year"
            f" {death_year}, which usually means a reprint date rather than first publication."
        )
    if "foreign_publication" in flags:
        reasoning += " Non-English work, so URAA copyright restoration may apply."

    return Term(pd_year, "pub+95", confidence, tuple(flags), reasoning)


def _life_plus_seventy(
    publication_year: int,
    death_year: int | None,
    flags: list[str],
    death_year_disputed: bool,
) -> Term:
    if death_year is None:
        flags.append("missing_death_year")
        return Term(
            None,
            "life+70",
            UNCERTAIN,
            tuple(flags),
            f"Published {publication_year}, so the term is life plus {LIFE_PLUS_TERM} years, but no"
            " author death year is recorded and the date cannot be computed.",
        )

    pd_year = death_year + LIFE_PLUS_TERM + _ENTERS_YEAR_AFTER
    reasoning = (
        f"Published {publication_year}, on or after the {CURRENT_TERM_START} cutoff, so the term is"
        f" life plus {LIFE_PLUS_TERM} years from the author's death in {death_year}: public domain"
        f" on Jan 1 {pd_year}."
    )

    if SECTION_303_START <= publication_year <= SECTION_303_END and pd_year < SECTION_303_FLOOR:
        flags.append("section_303_floor")
        reasoning += (
            f" First published in the {SECTION_303_START}-{SECTION_303_END} window from a work"
            f" created earlier, so 17 U.S.C. 303 holds protection through Dec 31"
            f" {SECTION_303_FLOOR - 1}, overriding the life+{LIFE_PLUS_TERM} date of {pd_year}."
        )
        pd_year = SECTION_303_FLOOR

    if death_year_disputed:
        confidence = DISPUTED
        reasoning += " Sources disagree on the death year, so this date is disputed."
    elif _uncertain_flags(flags):
        confidence = UNCERTAIN
    else:
        confidence = CONFIRMED

    if "foreign_publication" in flags:
        reasoning += " Non-English work, so URAA copyright restoration may apply."

    return Term(pd_year, "life+70", confidence, tuple(flags), reasoning)


def _without_publication_year(
    death_year: int | None,
    flags: list[str],
    as_of_year: int,
) -> Term:
    """Salvage what can be salvaged from a missing publication year.

    A quarter of data/book_corpus.csv has no publication year, so falling straight
    to "unknown" would throw away 700-odd books. One sound inference is available:
    anything published during the author's lifetime was published no later than
    the year they died, so its public-domain date is at most death_year + 96. When
    that bound has already passed, the work is public domain regardless of the
    exact publication year.

    The bound only concludes anything when it proves the work is ALREADY public
    domain. It cannot produce a future date, because a future bound is consistent
    with any publication year at all -- including one past the 1978 cutoff, where
    a different rule would apply.
    """
    flags.append("missing_publication_year")

    if death_year is None:
        flags.append("missing_death_year")
        return Term(
            None,
            "unknown",
            UNCERTAIN,
            tuple(flags),
            "Neither a publication year nor an author death year is recorded, so no rule can be"
            " applied.",
        )

    bound = death_year + PUBLISHED_TERM + _ENTERS_YEAR_AFTER
    if bound <= as_of_year:
        flags.append("inferred_from_death_year")
        return Term(
            bound,
            "lifetime-pub-bound",
            UNCERTAIN,
            tuple(flags),
            f"No publication year recorded. The author died in {death_year}, so any work published"
            f" in their lifetime entered the public domain by Jan 1 {bound} at the latest, which"
            f" has already passed as of {as_of_year}. The exact date needs a publication year;"
            " a posthumous first publication would break this inference.",
        )

    return Term(
        None,
        "lifetime-pub-bound",
        UNCERTAIN,
        tuple(flags),
        f"No publication year recorded. The author died in {death_year}, giving a latest-possible"
        f" date of Jan 1 {bound}, which is still in the future as of {as_of_year}. Without a"
        " publication year there is no way to tell whether pub+95 or life+70 governs.",
    )


def _uncertain_flags(flags: list[str]) -> bool:
    return any(f in flags for f in ("renewal_era", "foreign_publication", "publication_after_death"))


def next_cliffs(as_of_year: int, count: int = 5) -> list[int]:
    """The next `count` January 1sts: the one coming up, plus the following ones.

    Called with as_of_year=2026 this gives [2027, 2028, 2029, 2030, 2031] -- five
    cliff edges, not five dates within a year. See docs/project-plan.md section 1.
    """
    return list(range(as_of_year + _ENTERS_YEAR_AFTER, as_of_year + _ENTERS_YEAR_AFTER + count))


def entering_in(term: Term, years: list[int]) -> bool:
    """True when this work crosses one of the given January 1st cliffs."""
    return term.pd_year in years
