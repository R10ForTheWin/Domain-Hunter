"""PD Verification Agent — CLI entry point.

Two modes:

  Interactive (default) — check one book at a time. Opens by explaining the
  legal fields it needs, looks the book up on Project Gutenberg if you have
  an ID (or lets you search / enter it manually), then asks — one at a
  time, only when actually needed for that specific book's legal path —
  for whatever additional fields are required to reach a determination.
  Never guesses: if you don't know an answer, it leaves the book
  "uncertain" and tells you exactly what's missing.

      python -m pd_verification.agent

  Batch — run every book in data/book_corpus.csv through the same rule
  engine (using data/pd_verification_inputs.csv for supplementary legal
  fields where available) and write data/pd_verification.csv, per the
  Package 2 -> Package 5 data contract. Non-interactive by design — any
  book missing a fact it needs comes out "uncertain" rather than prompting.

      python -m pd_verification.agent --batch data/book_corpus.csv \\
          --supplementary data/pd_verification_inputs.csv \\
          --out data/pd_verification.csv

This agent is independent of Package 4 (studio scoring) by design — it
never sees a score, and a book's determination here must never be
influenced by how "good" it scored. See pd_verification/README.md.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from typing import Optional

from . import gutenberg, io_csv
from .models import BookInput, Verdict
from .rules import evaluate

DISCLAIMER = (
    "This agent applies a conservative, code-only reading of U.S. copyright-duration "
    "law. It is NOT legal advice, and it is deliberately biased toward 'uncertain' or "
    "'not_confirmed' over a guessed 'confirmed'. Before any book marked 'confirmed' "
    "here is used in an actual production, get a human with real copyright-law "
    "expertise to independently verify it -- especially anything foreign-published, "
    "anonymous/corporate-authored, or published 1923-1988."
)

REQUIRED_FIELDS_EXPLANATION = """\
Fields this agent needs (in order of how often they matter):

  ALWAYS REQUIRED
    - title, author
    - publication_year          Year of first publication. If the work was
                                 never published, say so -- unpublished works
                                 follow a different rule this agent doesn't
                                 evaluate, and will always come back "uncertain".

  USUALLY REQUIRED (most named-author books need this)
    - author_death_year         Required whenever the life-of-author-plus-70
                                 rule controls (post-1977 publications, or
                                 foreign/uncertain-country pre-1978 works).
                                 If sources disagree on the year, say so --
                                 a disputed death year alone is enough to
                                 mark a book "uncertain".

  SITUATIONAL (only asked when the book's specific path needs it)
    - country_of_first_publication      Anything other than a confirmed U.S.
                                         first publication carries a real risk
                                         that the work's U.S. copyright was
                                         *restored* under URAA (17 U.S.C. 104A)
                                         even if it looks expired by the normal
                                         U.S. publication-year rules.
    - simultaneous_us_publication       Was it also published in the U.S.
                                         within 30 days of the foreign
                                         publication? That makes it a "United
                                         States work" for URAA purposes even
                                         though first published abroad.
    - had_copyright_notice_at_publication   Only matters for pre-1989 U.S.
                                         publications -- omitting notice put
                                         a work straight into the public
                                         domain before that date, no cure.
    - renewal_filed              Only matters for U.S. works first published
                                  1923-1963 -- these needed an affirmative
                                  renewal in their 28th year or they lapsed
                                  into the public domain. (1964-1977 U.S.
                                  works were automatically renewed by statute
                                  -- no lookup needed for those.)
    - is_anonymous_pseudonymous_or_corporate   Defaults to "no" (i.e. a named,
                                  identified individual author) unless you say
                                  otherwise, or the author field literally
                                  says "Anonymous"/"Unknown". Anonymous,
                                  pseudonymous (true identity not on record),
                                  and work-for-hire authorship get a fixed
                                  95-year-from-publication term instead of
                                  life+70.

This agent never guesses at any of these -- an unanswered field that would
matter to the book's specific path just means the verdict is "uncertain",
with that field named explicitly.
"""


def print_intro() -> None:
    print("=" * 78)
    print("PD Verification Agent -- Package 2, Domain Huntress")
    print("=" * 78)
    print(DISCLAIMER)
    print()
    print(REQUIRED_FIELDS_EXPLANATION)


def _prompt(text: str) -> str:
    return input(text).strip()


def _prompt_optional_int(text: str) -> Optional[int]:
    raw = _prompt(text)
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        print("  (not a number -- leaving blank)")
        return None


def _prompt_optional_bool(text: str) -> Optional[bool]:
    raw = _prompt(f"{text} [y/n/unknown, default unknown]: ").strip().lower()
    if raw in {"y", "yes", "true"}:
        return True
    if raw in {"n", "no", "false"}:
        return False
    return None


# Maps the leading token of a rules.py "missing field" string to a prompt
# that fills in the corresponding BookInput attribute.
_ASKABLE_FIELDS = {
    "author_death_year": (
        "What year did the author die? (blank if unknown, or 'disputed' if sources disagree)",
        "death",
    ),
    "country_of_first_publication": (
        "Country of first publication (e.g. 'US', 'UK', 'France'; blank if unknown)",
        "text",
    ),
    "simultaneous_us_publication": (
        "Was it also published in the U.S. within 30 days of first publication?",
        "bool",
    ),
    "had_copyright_notice_at_publication": (
        "Did the first publication carry a copyright notice?",
        "bool",
    ),
    "renewal_filed": (
        "Was the U.S. copyright renewed in its 28th year (check the Stanford "
        "Copyright Renewal Database)?",
        "bool",
    ),
}


def _field_key(missing_entry: str) -> str:
    return missing_entry.split(" ", 1)[0]


def _ask_for_missing_field(book: BookInput, missing_entry: str) -> bool:
    """Prompt for one missing field and mutate `book` in place. Returns True
    if the user supplied something new, False if they skipped it.
    """
    key = _field_key(missing_entry)
    spec = _ASKABLE_FIELDS.get(key)
    if spec is None:
        print(f"  (this agent doesn't have an interactive prompt for '{key}' -- "
              f"leave it for manual research)")
        return False

    prompt_text, kind = spec
    print(f"\n  Missing: {missing_entry}")
    if kind == "death":
        raw = _prompt(f"  {prompt_text}: ").strip()
        if raw == "":
            return False
        if raw.lower() == "disputed":
            book.author_death_year_disputed = True
            return True
        try:
            book.author_death_year = int(raw)
            book.author_death_year_disputed = False
            return True
        except ValueError:
            print("  (not a number -- leaving blank)")
            return False
    if kind == "text":
        raw = _prompt(f"  {prompt_text}: ").strip()
        if raw == "":
            return False
        book.country_of_first_publication = raw
        return True
    if kind == "bool":
        answer = _prompt_optional_bool(f"  {prompt_text}")
        if answer is None:
            return False
        setattr(book, key, answer)
        return True
    return False


def run_interactive() -> None:
    print_intro()

    mode = _prompt("Look up by Project Gutenberg ID, search Gutenberg by title, "
                    "or enter manually? [id/search/manual]: ").strip().lower()

    book_id: Optional[str] = None
    title = ""
    author = ""
    publication_year: Optional[int] = None
    author_death_year: Optional[int] = None
    author_death_year_disputed = False

    if mode in {"id", "search"}:
        try:
            if mode == "id":
                gid = int(_prompt("Project Gutenberg ID: "))
                found = gutenberg.fetch_by_id(gid)
                if found is None:
                    print(f"No Gutenberg book found with ID {gid}. Falling back to manual entry.")
                    mode = "manual"
            else:
                query = _prompt("Search text: ")
                results = gutenberg.search(query)
                if not results:
                    print("No matches. Falling back to manual entry.")
                    mode = "manual"
                else:
                    for i, r in enumerate(results):
                        names = ", ".join(a["name"] or "?" for a in r["authors"]) or "(no author on file)"
                        print(f"  [{i}] {r['title']} -- {names} (gutenberg id {r['gutenberg_id']})")
                    choice = _prompt("Pick a number (blank to enter manually): ")
                    if choice == "":
                        mode = "manual"
                    else:
                        found = results[int(choice)]
        except gutenberg.GutenbergLookupError as exc:
            print(f"Could not reach Project Gutenberg ({exc}). Falling back to manual entry.")
            mode = "manual"

        if mode != "manual":
            title = found["title"] or ""
            authors = found["authors"]
            author = ", ".join(a["name"] or "?" for a in authors) or "Unknown"
            death_years = [a["death_year"] for a in authors]
            known_death_years = [d for d in death_years if d is not None]
            if authors and len(known_death_years) == len(authors):
                # every author's death year is on file -- the joint-work rule
                # is controlled by whichever author died LAST
                author_death_year = max(known_death_years)
                if len(authors) > 1:
                    print(f"  Note: joint work by {len(authors)} authors; using the "
                          f"latest death year ({author_death_year}) per the joint-work rule.")
            else:
                author_death_year = None
                if len(authors) > 1 and known_death_years:
                    print("  Note: this is a joint work and Gutenberg doesn't have death "
                          "years for all authors -- treating author_death_year as unknown "
                          "rather than guessing.")
            print(f"  Gutenberg death-year data is catalog metadata, not a verified source "
                  f"-- corroborate independently before relying on it (matches this "
                  f"project's own author_death_year_disputed convention).")
            print(f"\nFound: '{title}' by {author}")
            pub_raw = _prompt("Original publication year (Gutenberg doesn't reliably know "
                               "this -- it's the *ebook* edition date, not necessarily first "
                               "publication): ")
            publication_year = int(pub_raw) if pub_raw.strip() else None
            book_id = f"gutenberg-{found['gutenberg_id']}"

    if mode == "manual":
        title = _prompt("Title: ")
        author = _prompt("Author: ")
        pub_raw = _prompt("Publication year (blank if unpublished): ")
        publication_year = int(pub_raw) if pub_raw.strip() else None
        death_raw = _prompt("Author death year (blank if unknown, 'disputed' if sources "
                             "disagree): ").strip()
        if death_raw.lower() == "disputed":
            author_death_year_disputed = True
        elif death_raw:
            author_death_year = int(death_raw)

    book = BookInput(
        book_id=book_id or "adhoc-check",
        title=title,
        author=author,
        publication_year=publication_year,
        author_death_year=author_death_year,
        author_death_year_disputed=author_death_year_disputed,
    )

    # Progressive disclosure: only ask for what the book's own legal path
    # actually still needs, one round at a time.
    while True:
        verdict = evaluate(book, as_of_year=_dt.date.today().year)
        if verdict.pd_status != "uncertain" or not verdict.missing_fields:
            break
        print("\n--- Need more information to narrow this down ---")
        any_answered = False
        for missing_entry in list(verdict.missing_fields):
            if _ask_for_missing_field(book, missing_entry):
                any_answered = True
        if not any_answered:
            break

    _print_verdict(book, verdict)

    if book_id and book_id != "adhoc-check":
        save = _prompt("\nSave the supplementary legal fields you entered to "
                        "data/pd_verification_inputs.csv for next time? [y/n]: ").strip().lower()
        if save in {"y", "yes"}:
            io_csv.upsert_supplementary_row(
                "data/pd_verification_inputs.csv",
                book_id,
                {
                    "country_of_first_publication": book.country_of_first_publication,
                    "simultaneous_us_publication": book.simultaneous_us_publication,
                    "is_anonymous_pseudonymous_or_corporate": book.is_anonymous_pseudonymous_or_corporate,
                    "had_copyright_notice_at_publication": book.had_copyright_notice_at_publication,
                    "renewal_filed": book.renewal_filed,
                    "source": "interactive-session",
                },
            )
            print("Saved.")


def _print_verdict(book: BookInput, verdict: Verdict) -> None:
    print("\n" + "=" * 78)
    print(f"VERDICT for '{book.title}' by {book.author}: {verdict.pd_status.upper()}")
    print("=" * 78)
    print(f"Rule applied: {verdict.rule_applied}")
    print(f"Reasoning: {verdict.reasoning}")
    if verdict.flags:
        print(f"Flags: {verdict.flags_str()}")
    if verdict.missing_fields:
        print(f"Still missing: {verdict.missing_fields_str()}")
    print()


def run_batch(book_corpus_path: str, supplementary_path: str, out_path: str) -> None:
    corpus_rows = io_csv.read_book_corpus(book_corpus_path)
    supplementary = io_csv.read_supplementary_inputs(supplementary_path)
    as_of_year = _dt.date.today().year

    results = []
    counts = {"confirmed": 0, "not_confirmed": 0, "uncertain": 0}
    for row in corpus_rows:
        book = io_csv.build_book_input(row, supplementary.get(row["book_id"]))
        verdict = evaluate(book, as_of_year=as_of_year)
        counts[verdict.pd_status] += 1
        results.append((row["book_id"], verdict))

    io_csv.write_verification_csv(out_path, results)
    print(f"Evaluated {len(results)} books -> {out_path}")
    print(f"  confirmed:     {counts['confirmed']}")
    print(f"  not_confirmed: {counts['not_confirmed']}")
    print(f"  uncertain:     {counts['uncertain']}")
    print(f"\n{DISCLAIMER}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", metavar="BOOK_CORPUS_CSV", help="Run non-interactively over data/book_corpus.csv")
    parser.add_argument("--supplementary", default="data/pd_verification_inputs.csv",
                         help="Supplementary legal-fields CSV this package owns (default: %(default)s)")
    parser.add_argument("--out", default="data/pd_verification.csv",
                         help="Where to write the verification output (default: %(default)s)")
    args = parser.parse_args(argv)

    if args.batch:
        run_batch(args.batch, args.supplementary, args.out)
    else:
        run_interactive()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
