"""Deterministic U.S. public-domain rule engine.

THIS IS NOT LEGAL ADVICE. It is a conservative, code-only implementation of
the major, well-settled rules of U.S. copyright duration, written so a
non-lawyer team can screen a large corpus without guessing. It is written to
fail closed: whenever a fact needed to fully resolve a book's status is
missing, or a rule this engine does not model might apply, the verdict is
"uncertain" (or, where we're confident the work is simply not yet expired,
"not_confirmed") rather than a guessed "confirmed". Before any book coming
out of this engine is used in an actual production, a human with real
copyright-law expertise should independently confirm "confirmed" verdicts —
especially anything involving a foreign publication, a corporate/anonymous
author, or a 1923-1988 publication date. See pd_verification/README.md for
the full explanation of what's modeled here and what isn't.

Statutory basis (current U.S. law, 17 U.S.C.):
  - Sec. 302(a):  Works first published/created 1978+ by an identified
                   individual author: life of the author + 70 years.
  - Sec. 302(c):  Anonymous works, pseudonymous works (true identity not on
                   record), and works made for hire: 95 years from
                   publication, or 120 years from creation, whichever is
                   shorter. In practice, for anything actually published,
                   the 95-year-from-publication prong is virtually always
                   the binding (shorter) one, so that's what this engine
                   checks.
  - Sec. 304:     Works first published before 1978: an initial 28-year
                   term plus a renewal term, capped at 95 years from
                   publication overall (after the Sonny Bono Copyright Term
                   Extension Act). Works published 1923-1963 needed an
                   affirmative renewal filed in their 28th year or the
                   initial term simply ran out and the work fell into the
                   public domain at that point (publication_year + 28);
                   works published 1964-1977 were automatically renewed by
                   the Copyright Renewal Act of 1992, so they always get the
                   full 95 years. Before 1978, publication without the
                   required copyright notice (and no cure) put a work into
                   the public domain immediately — there was no cure period.
  - Sec. 104A:    URAA restoration. Certain foreign works that fell into
                   the U.S. public domain solely for failing to comply with
                   U.S. formalities (notice, renewal, etc.) — NOT because
                   their term had genuinely run out — had their U.S.
                   copyright restored, running for the same term they would
                   have had if they'd never lost protection. This is the
                   single biggest trap for a "looks public domain" screen:
                   a foreign work that appears to qualify under Sec. 304's
                   renewal rules can still be under copyright today via
                   restoration, on a life-of-the-author-plus-70 clock.

Because of Sec. 104A, this engine treats "foreign, or country of first
publication unknown" as its own hazard independent of the publication-year
rules, and will only return "confirmed" for such a book when BOTH the
domestic 95-year theory AND the life+70 theory have independently expired
(so it doesn't matter which one actually controls) — see FOREIGN WORKS
below. If you can't confirm the book is a "United States work" (domestic
first publication, or first published outside the U.S. but also published
in the U.S. within 30 days), assume restoration risk is possible.

Every Verdict also carries `pd_effective_date` when the controlling rule
makes one knowable: for "confirmed", the Jan 1 date the work actually
entered the public domain; for "not_confirmed", the Jan 1 date it WILL
enter the public domain (every current "not_confirmed" branch is fully
resolved enough to know this). "uncertain" never carries a date. Where two
independent theories could each explain a "confirmed" result (the
foreign/URAA-safe double-expiry case) and we don't know which one is
legally the real one, the LATER of the two candidate dates is reported —
that date is guaranteed correct under either theory, which the earlier one
isn't.

What this engine deliberately does NOT try to fully resolve, and always
routes to "uncertain" instead of guessing:
  - Unpublished works (Sec. 303 has its own, narrower rules).
  - Whether a given foreign work's SOURCE-COUNTRY copyright had already
    expired as of its URAA restoration date (this is genuinely
    country-and-date-specific and outside what a deterministic screen
    should attempt).
  - Government works, works dedicated to the public domain, or works under
    a specific license (CC0 etc.) — those aren't a "term expired" question
    at all and need a different check entirely.
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional, Set, Tuple

from .models import BookInput, Verdict

# --- Constants (statutory) --------------------------------------------------

PRE1978_TERM_YEARS = 96  # publication_year + 96 => Jan 1 the work enters the PD (17 U.S.C. 304)
LIFE70_OFFSET = 71  # author_death_year + 71 => Jan 1 the work enters the PD (17 U.S.C. 302(a))
INITIAL_TERM_YEARS = 28  # the pre-renewal initial term (17 U.S.C. 304); lapses at publication_year + 28

RENEWAL_ERA: Tuple[int, int] = (1923, 1963)  # affirmative renewal required
AUTO_RENEWAL_ERA: Tuple[int, int] = (1964, 1977)  # renewal automatic (Copyright Renewal Act of 1992)

# Berne Convention Implementation Act took effect March 1, 1989, eliminating
# mandatory copyright notice for U.S. publication going forward. Before that
# date, a work — including one first published in the U.S. under license by
# a foreign work's rights holder — could still fall into the public domain
# for lack of notice. On/after this year we treat "foreign vs. domestic" as
# no longer changing the term analysis for a named-author work.
FORMALITY_RISK_LAST_YEAR = 1988

_US_ALIASES: Set[str] = {
    "US", "USA", "U.S.", "U.S.A.", "UNITED STATES", "UNITED STATES OF AMERICA",
}
_ANONYMOUS_AUTHOR_STRINGS: Set[str] = {"anonymous", "anon.", "anon", "unknown"}


def _normalize_country(value: str) -> str:
    return value.strip().upper()


def _jan1(year: int) -> _dt.date:
    return _dt.date(year, 1, 1)


def _v(
    status: str,
    reasoning: str,
    rule_applied: str,
    flags: List[str],
    missing: List[str],
    effective_date: Optional[_dt.date] = None,
) -> Verdict:
    """Build a Verdict, making sure `missing_fields` and `pd_effective_date`
    only ever show up in ways that actually make sense together:

    - `missing_fields` only on a genuinely "uncertain" result. A field that
      happened to be unset but didn't actually block a confirmed/
      not_confirmed determination isn't "missing" in any sense that matters
      to whoever reads this output.
    - `pd_effective_date` never on "uncertain" — an undetermined status has
      no date to give, even if a date happened to get computed along the
      way in some earlier branch.
    """
    return Verdict(
        status,
        reasoning,
        rule_applied,
        list(flags),
        list(missing) if status == "uncertain" else [],
        effective_date if status != "uncertain" else None,
    )


def evaluate(book: BookInput, *, as_of_year: int) -> Verdict:
    """Return a Verdict for `book`, as of Jan 1 of `as_of_year`.

    Pass the current year for `as_of_year` in normal use; the parameter
    exists mainly so tests can pin a fixed "today" instead of depending on
    the wall clock.
    """
    missing: List[str] = []
    flags: List[str] = []

    # ---- 0. Bare minimum: do we even have a publication year? ----
    if book.publication_year is None:
        return _v(
            "uncertain",
            "No publication year on file, and unpublished works are governed by a "
            "separate, narrower rule (17 U.S.C. 303) this engine does not evaluate. "
            "Confirm whether the work was ever published and, if not, get a human "
            "copyright-law review before using it.",
            "insufficient-data",
            ["unpublished_or_unknown_publication_year"],
            ["publication_year (or an explicit confirmation the work is unpublished)"],
        )

    pub = book.publication_year

    # ---- Derived facts ----
    effective_anonymous = book.is_anonymous_pseudonymous_or_corporate is True or (
        book.author.strip().lower() in _ANONYMOUS_AUTHOR_STRINGS
        and book.is_anonymous_pseudonymous_or_corporate is not False
    )

    if book.author_death_year_disputed:
        flags.append("disputed_death_year")
    has_clean_death_year = (
        book.author_death_year is not None and not book.author_death_year_disputed
    )

    country_known = book.country_of_first_publication is not None
    is_us = country_known and _normalize_country(book.country_of_first_publication) in _US_ALIASES
    is_confirmed_domestic = is_us or book.simultaneous_us_publication is True
    is_foreign_or_unknown = not is_confirmed_domestic

    # ---- Branch A: anonymous / pseudonymous / corporate authorship ----
    # This term category (95 years from publication, or 120 from creation if
    # shorter) is the same whether the work is domestic or a restored
    # foreign work, so country doesn't change the analysis here.
    if effective_anonymous:
        expiry_year = pub + PRE1978_TERM_YEARS
        if as_of_year >= expiry_year:
            return _v(
                "confirmed",
                f"'{book.title}' was published {pub} under anonymous, pseudonymous, or "
                f"corporate (work-for-hire) authorship. That category's term — the "
                f"shorter of 95 years from publication or 120 years from creation "
                f"(17 U.S.C. 302(c)) — is at most 95 years from publication, which "
                f"expired Jan 1, {expiry_year}. This holds regardless of country of "
                f"first publication, because even a restored foreign copyright "
                f"(17 U.S.C. 104A) for an anonymous/corporate work runs under the "
                f"same 95-year ceiling.",
                "anonymous-95yr-expired",
                flags,
                missing,
                _jan1(expiry_year),
            )
        return _v(
            "not_confirmed",
            f"'{book.title}' was published {pub} under anonymous, pseudonymous, or "
            f"corporate authorship. That category's term runs 95 years from "
            f"publication (17 U.S.C. 302(c)), which does not expire until Jan 1, "
            f"{expiry_year}. Still under copyright.",
            "anonymous-95yr-not-yet-expired",
            flags,
            missing,
            _jan1(expiry_year),
        )

    # ---- Branch B: named individual author(s), published 1989 or later ----
    # Berne-era: mandatory notice was eliminated March 1, 1989, so there's no
    # formality trap left to create a restoration wrinkle. Life+70 governs
    # cleanly regardless of country.
    if pub >= 1989:
        if has_clean_death_year:
            expiry_year = book.author_death_year + LIFE70_OFFSET
            if as_of_year >= expiry_year:
                return _v(
                    "confirmed",
                    f"'{book.title}' was first published {pub} (Berne-era; no U.S. "
                    f"notice formality applies). The author died {book.author_death_year}, "
                    f"so the life+70 term (17 U.S.C. 302(a)) expired Jan 1, {expiry_year}.",
                    "life+70-expired",
                    flags,
                    missing,
                    _jan1(expiry_year),
                )
            return _v(
                "not_confirmed",
                f"'{book.title}' was first published {pub}. The author died "
                f"{book.author_death_year}; the life+70 term does not expire until "
                f"Jan 1, {expiry_year}. Still under copyright.",
                "life+70-not-yet-expired",
                flags,
                missing,
                _jan1(expiry_year),
            )
        if book.author_death_year is None:
            missing.append("author_death_year")
        if book.author_death_year_disputed:
            death_year_clause = "the author's death year is disputed"
        else:
            death_year_clause = (
                "no death year is on file for the author — most likely because "
                "they're still living, not because the record is incomplete"
            )
        return _v(
            "uncertain",
            f"'{book.title}' was first published {pub}, so the controlling term is "
            f"life-of-the-author-plus-70 (17 U.S.C. 302(a)), but {death_year_clause}. "
            f"Either way, the work is still well within its copyright term and is not "
            f"public domain; an exact expiration date just can't be calculated yet.",
            "life+70-missing-death-year",
            flags,
            missing,
        )

    # ---- Branch C: named individual author(s), published 1978-1988 ----
    # Modern life+70 term applies, but U.S. notice was still technically
    # mandatory through Feb 1989, so a foreign work could in theory have
    # fallen into the PD for lack of notice and then been restored onto the
    # same life+70 clock by URAA. Net effect: country doesn't change which
    # theory controls (life+70 either way) — it only matters for the rare
    # domestic no-notice case.
    if 1978 <= pub <= FORMALITY_RISK_LAST_YEAR:
        if is_confirmed_domestic and book.had_copyright_notice_at_publication is False:
            return _v(
                "confirmed",
                f"'{book.title}' was published {pub} in the U.S. without a copyright "
                f"notice. Before March 1, 1989 there was no cure period for that, so "
                f"the work entered the public domain immediately on publication "
                f"(the exact day isn't tracked here, so {pub} is used as an "
                f"approximate effective date).",
                "no-notice-instant-pd-1978-1988",
                flags,
                missing,
                _jan1(pub),
            )
        if is_confirmed_domestic and book.had_copyright_notice_at_publication is None:
            missing.append("had_copyright_notice_at_publication")
            flags.append("copyright_notice_status_unknown")
        if is_foreign_or_unknown:
            flags.append("foreign_publication_or_unknown_country")
            if book.country_of_first_publication is None:
                missing.append("country_of_first_publication")
            if book.simultaneous_us_publication is None:
                missing.append("simultaneous_us_publication (within 30 days of first publication)")

        if has_clean_death_year:
            expiry_year = book.author_death_year + LIFE70_OFFSET
            if as_of_year >= expiry_year:
                return _v(
                    "confirmed",
                    f"'{book.title}' was first published {pub}. The author died "
                    f"{book.author_death_year}, so the life+70 term (17 U.S.C. 302(a)) "
                    f"expired Jan 1, {expiry_year}. This holds even if the work was "
                    f"originally foreign and formality-restored under URAA, since "
                    f"restoration would run on the same life+70 clock.",
                    "life+70-expired-1978-1988",
                    flags,
                    missing,
                    _jan1(expiry_year),
                )
            return _v(
                "not_confirmed",
                f"'{book.title}' was first published {pub}. The author died "
                f"{book.author_death_year}; the life+70 term does not expire until "
                f"Jan 1, {expiry_year}. Still under copyright.",
                "life+70-not-yet-expired-1978-1988",
                flags,
                missing,
                _jan1(expiry_year),
            )
        if book.author_death_year is None:
            missing.append("author_death_year")
        if book.author_death_year_disputed:
            death_year_clause = "the author's death year is disputed"
        else:
            death_year_clause = (
                "no death year is on file for the author — they may still be "
                "living, or it may simply not be recorded"
            )
        return _v(
            "uncertain",
            f"'{book.title}' was first published {pub} (1978-1988 window — mandatory "
            f"U.S. notice still applied). The controlling term is life+70, but "
            f"{death_year_clause}. Either way, the work is still well within its "
            f"copyright term and is not public domain; an exact expiration date just "
            f"can't be calculated yet.",
            "life+70-missing-death-year-1978-1988",
            flags,
            missing,
        )

    # ---- Legacy regime: named individual author(s), published <= 1977 ----
    # 17 U.S.C. 304: capped at 95 years from publication, with renewal
    # formalities for 1923-1963 (and instant PD for missing notice, any
    # pre-1978 year). Foreign/unknown-country works carry independent URAA
    # restoration risk on the life+70 clock, on top of (not instead of) the
    # domestic analysis.
    pre1978_expiry_year = pub + PRE1978_TERM_YEARS
    pre1978_expired = as_of_year >= pre1978_expiry_year

    if pre1978_expired and has_clean_death_year and as_of_year >= (
        book.author_death_year + LIFE70_OFFSET
    ):
        life70_expiry_year = book.author_death_year + LIFE70_OFFSET
        # We don't know which theory actually governs (domestic 95-year vs.
        # a hypothetically-restored life+70), so report the LATER of the two
        # dates -- that one is correct no matter which theory turns out to
        # be the real one.
        safe_expiry_year = max(pre1978_expiry_year, life70_expiry_year)
        return _v(
            "confirmed",
            f"'{book.title}' was published {pub}; the author died {book.author_death_year}. "
            f"Both the 95-years-from-publication ceiling (17 U.S.C. 304, expired "
            f"{pre1978_expiry_year}) and the life+70 ceiling (17 U.S.C. 302(a), "
            f"expired {life70_expiry_year}) have passed, so this "
            f"is public domain regardless of country of first publication or URAA "
            f"restoration status.",
            "life+70-and-pre1978-both-expired",
            flags,
            missing,
            _jan1(safe_expiry_year),
        )

    if pre1978_expired and is_confirmed_domestic:
        return _v(
            "confirmed",
            f"'{book.title}' was published {pub} as a United States work (confirmed "
            f"domestic first publication"
            + (" / simultaneous U.S. publication" if book.simultaneous_us_publication else "")
            + f"), so URAA restoration (17 U.S.C. 104A) does not apply to it. The "
            f"95-year term from publication (17 U.S.C. 304) expired Jan 1, "
            f"{pre1978_expiry_year}.",
            "pre1978-95yr-expired-domestic",
            flags,
            missing,
            _jan1(pre1978_expiry_year),
        )

    if pre1978_expired and is_foreign_or_unknown:
        flags.append("foreign_publication_or_unknown_country")
        flags.append("uraa_restoration_risk")
        if book.country_of_first_publication is None:
            missing.append("country_of_first_publication")
        if book.simultaneous_us_publication is None:
            missing.append("simultaneous_us_publication (within 30 days of first foreign publication)")
        if book.author_death_year is None:
            missing.append("author_death_year (needed to rule out a restored life+70 term)")
        elif book.author_death_year_disputed:
            missing.append("author_death_year (disputed — needs corroboration)")
        return _v(
            "uncertain",
            f"'{book.title}' was published {pub} outside the U.S. (or country of first "
            f"publication is not on file). The 95-year domestic term has expired, but "
            f"if this work's U.S. copyright was restored under URAA (17 U.S.C. 104A) — "
            f"which happens for foreign works that lost U.S. protection only for lack "
            f"of notice or renewal, not because the term genuinely ran out — the "
            f"controlling term is instead life-of-the-author-plus-70, which may still "
            f"be running. Using this book without confirming the country of first "
            f"publication, whether it was published in the U.S. within 30 days, and "
            f"the author's death year creates real U.S. copyright liability exposure "
            f"if it turns out to be restored.",
            "foreign-uraa-risk-life70-not-ruled-out",
            flags,
            missing,
        )

    # Not yet past the 95-year mark (pub + 96 > as_of_year).
    if is_confirmed_domestic:
        if book.had_copyright_notice_at_publication is False:
            return _v(
                "confirmed",
                f"'{book.title}' was published {pub} in the U.S. without a copyright "
                f"notice, which (for a pre-1978 publication) put the work into the "
                f"public domain immediately — there was no cure period before 1978 "
                f"(the exact day isn't tracked here, so {pub} is used as an "
                f"approximate effective date).",
                "no-notice-instant-pd",
                flags,
                missing,
                _jan1(pub),
            )
        if book.had_copyright_notice_at_publication is None:
            missing.append("had_copyright_notice_at_publication")
            flags.append("copyright_notice_status_unknown")

        if RENEWAL_ERA[0] <= pub <= RENEWAL_ERA[1]:
            if book.renewal_filed is False:
                lapse_year = pub + INITIAL_TERM_YEARS
                return _v(
                    "confirmed",
                    f"'{book.title}' was published {pub} in the U.S. (the 1923-1963 "
                    f"renewal-era window) and, per records on file, was never renewed "
                    f"in its 28th year, so the initial term simply ran out and it fell "
                    f"into the public domain Jan 1, {lapse_year} (28 years after "
                    f"publication).",
                    "renewal-era-not-renewed",
                    flags,
                    missing,
                    _jan1(lapse_year),
                )
            if book.renewal_filed is True:
                return _v(
                    "not_confirmed",
                    f"'{book.title}' was published {pub} in the U.S. and was renewed "
                    f"in its 28th year, giving it the full 95-year term, which does "
                    f"not expire until Jan 1, {pre1978_expiry_year}. Still under "
                    f"copyright.",
                    "renewal-era-renewed-still-in-term",
                    flags,
                    missing,
                    _jan1(pre1978_expiry_year),
                )
            missing.append(
                "renewal_filed (check the Stanford Copyright Renewal Database or the "
                "Catalog of Copyright Entries for this exact title/year)"
            )
            flags.append("renewal_status_unknown")
            return _v(
                "uncertain",
                f"'{book.title}' was published {pub} in the U.S., in the 1923-1963 "
                f"renewal-era window — where roughly 85% of registered works were "
                f"never renewed and fell into the public domain — but renewal status "
                f"has to be looked up per title and isn't on file for this book.",
                "renewal-era-unknown",
                flags,
                missing,
            )

        if AUTO_RENEWAL_ERA[0] <= pub <= AUTO_RENEWAL_ERA[1]:
            return _v(
                "not_confirmed",
                f"'{book.title}' was published {pub} in the U.S. Works first published "
                f"1964-1977 were automatically renewed by the Copyright Renewal Act of "
                f"1992, so they get the full 95-year term regardless of whether anyone "
                f"filed a renewal. Term does not expire until Jan 1, "
                f"{pre1978_expiry_year}.",
                "automatic-renewal-1964-1977",
                flags,
                missing,
                _jan1(pre1978_expiry_year),
            )

        # pub < 1923 but somehow not yet past the 95-year mark — only possible
        # if this is being evaluated far in the past. Kept as a safety net.
        return _v(
            "uncertain",
            f"'{book.title}' (published {pub}) falls outside every publication "
            f"window this engine has an explicit rule for as of {as_of_year}. Needs "
            f"manual legal review.",
            "unhandled-legacy-window",
            flags,
            missing,
        )

    # Foreign/unknown-country and not yet past the 95-year mark. Renewal and
    # notice are domestic formalities that don't determine a restored work's
    # status one way or the other, so there's no affirmative path to
    # "confirmed" here at all — and we already know life+70 hasn't expired
    # either, or we'd have returned above.
    flags.append("foreign_publication_or_unknown_country")
    flags.append("uraa_restoration_risk")
    if book.country_of_first_publication is None:
        missing.append("country_of_first_publication")
    if book.simultaneous_us_publication is None:
        missing.append("simultaneous_us_publication (within 30 days of first foreign publication)")
    if book.author_death_year is None:
        missing.append("author_death_year")
    elif book.author_death_year_disputed:
        missing.append("author_death_year (disputed — needs corroboration)")
    return _v(
        "uncertain",
        f"'{book.title}' was published {pub} outside the U.S. (or country of first "
        f"publication unknown). Neither the 95-years-from-publication ceiling nor a "
        f"life+70 ceiling has clearly passed. If this work was restored under URAA "
        f"(17 U.S.C. 104A), it is very likely still under U.S. copyright today. "
        f"Treat it as copyrighted (do not use) until a human confirms country of "
        f"first publication, U.S.-simultaneous-publication status, and the author's "
        f"death year.",
        "foreign-not-yet-expired",
        flags,
        missing,
    )
