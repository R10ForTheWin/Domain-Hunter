"""Data shapes for the PD Verification Agent (Package 2).

BookInput is everything the rule engine in rules.py might need. Verdict is
what it hands back. Nothing here touches disk or the network — see
gutenberg.py (Project Gutenberg lookups) and io_csv.py (reading/writing the
data/ CSVs) for that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BookInput:
    """One book's facts, as far as we know them.

    `book_id`, `title`, `author`, and `publication_year` are the only fields
    that are always expected to be present (they come straight from
    `data/book_corpus.csv`, Package 3's output). Everything else is
    supplementary legal metadata this package collects itself (see
    `data/pd_verification_inputs.csv`) and is optional.

    Never fill in a guessed value for an unknown field — leave it None (or
    False only when you actually know the answer is "no"). The rule engine
    treats missing fields as missing and will say so in its output instead
    of assuming.
    """

    book_id: str
    title: str
    author: str
    publication_year: Optional[int]  # None means "not on file" / possibly unpublished

    # From book_corpus.csv (Package 3), already part of the existing contract:
    author_death_year: Optional[int] = None
    author_death_year_disputed: bool = False

    # Supplementary fields this package (Package 2) collects and owns, via
    # data/pd_verification_inputs.csv — see docs/data-contracts.md.
    is_anonymous_pseudonymous_or_corporate: Optional[bool] = None
    country_of_first_publication: Optional[str] = None
    simultaneous_us_publication: Optional[bool] = None
    had_copyright_notice_at_publication: Optional[bool] = None
    renewal_filed: Optional[bool] = None
    creation_year: Optional[int] = None


@dataclass
class Verdict:
    """The rule engine's determination for one book."""

    pd_status: str  # "confirmed" | "not_confirmed" | "uncertain" — never anything else
    reasoning: str
    rule_applied: str
    flags: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)

    def flags_str(self) -> str:
        return ";".join(self.flags)

    def missing_fields_str(self) -> str:
        return ";".join(self.missing_fields)
