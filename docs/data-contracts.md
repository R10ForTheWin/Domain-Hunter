# Data contracts

This is the interface between packages. Everyone can build in parallel because these shapes are
fixed up front — if your package needs to change one, edit this file in your PR and call it out
explicitly so downstream packages aren't silently broken.

All interchange files are plain CSV (UTF-8, comma-delimited, header row required) so every package
can read/write them with nothing more than Python's stdlib `csv` module. They live in `data/`.

## Primary key: `book_id`

Every file that references a book uses the same `book_id`, minted by **Package 3** (Book Corpus).
Format: `slugified-title__slugified-author__pub-year`, lowercase, spaces → hyphens, no punctuation.

Example: `frankenstein__mary-shelley__1818`

Package 3 is the source of truth for which `book_id`s exist. If a book isn't in `book_corpus.csv`,
no other file should reference it.

## `data/book_corpus.csv` — Package 3 output → feeds Packages 1, 2, 4

| column | type | notes |
|---|---|---|
| `book_id` | string | primary key, see above |
| `title` | string | |
| `author` | string | full name, "Last, First" preferred |
| `author_death_year` | int or blank | blank if unknown — do not guess |
| `author_death_year_disputed` | bool (`true`/`false`) | true if sources disagree |
| `publication_year` | int | original publication, not a reprint edition |
| `source` | string | e.g. `gutenberg` |
| `source_url` | string | link to the catalog entry |
| `language` | string | ISO code, e.g. `en` |
| `notes` | string | free text, optional |

## `data/pd_calendar.csv` — Package 1 output (reads `book_corpus.csv`)

One row per **work** (`book_id`), not per author. Under the rule that governs most of this corpus
the public-domain date comes from *publication*, so a single author can hold several different
dates — a 1931 title and a 1935 title by the same person are five years apart. An author-grained
row cannot represent that.

**Which rule governs.** U.S. works published before 1978 run 95 years from publication no matter
when the author died; only works published 1978 or later use life+70. Measured against the 2,764
rows of `book_corpus.csv`: `pub+95` governs 2,015 books, `life+70` governs 44. Earlier versions of
this file and of `pd_calendar/README.md` described the calendar as a life+70 calculation. That is
the wrong rule for a pre-1978 corpus, and it errs toward declaring free a work that is still in
copyright — an author who died in 1951 with a book published in 1950 comes out as public domain in
2022 under life+70, when the real date is 2046.

| column | type | notes |
|---|---|---|
| `pd_date` | date `YYYY-01-01` or blank | always January 1st, see project-plan.md §1; blank when the inputs cannot support a date |
| `book_id` | string or blank | link into `book_corpus.csv`; blank if the author has no title in the corpus yet |
| `title` | string or blank | denormalized for readability, matches `book_id` if set |
| `author` | string | |
| `author_death_year` | int or blank | blank if unknown — do not guess; not read at all when `rule_applied` is `pub+95` |
| `publication_year` | int or blank | original publication, matching `book_corpus.csv`; governs `pd_date` for pre-1978 works |
| `rule_applied` | string | which rule produced `pd_date`: `pub+95`, `life+70`, `lifetime-pub-bound`, `unknown` — same convention as `pd_verification.csv` |
| `confidence` | `confirmed` / `disputed` / `uncertain` | see below |
| `flags` | string | semicolon-separated, e.g. `renewal_era;foreign_publication` — same convention as `pd_verification.csv` |
| `source` | string | e.g. `wikidata`, plus a second corroborating source in `notes` |
| `notes` | string | optional |

**`confidence` values.** `confirmed` — the governing rule applied cleanly to complete inputs.
`disputed` — sources disagree on an input that the applied rule actually reads; note that a disputed
death year matters under `life+70` and is irrelevant under `pub+95`, so this is not a straight mirror
of `author_death_year_disputed`. `uncertain` — the date is not reliable: renewal-era publication
(1929–1963, where an un-renewed work is already public domain and renewal records are needed to tell),
possible URAA restoration of a foreign work, or a date inferred rather than computed. Per
project-plan.md §5, `uncertain` is a required answer rather than a fallback — every book in the
current five-year window comes out `uncertain`, so a schema without this value cannot express the
file's actual contents.

## `data/pd_verification.csv` — Package 2 output (reads `book_corpus.csv`)

One row per `book_id`. This file is produced **independently** of Package 4 — it must never take
score into account.

| column | type | notes |
|---|---|---|
| `book_id` | string | |
| `pd_status` | `confirmed` / `not_confirmed` / `uncertain` | never blank — "uncertain" is a valid, expected answer |
| `reasoning` | string | plain-language explanation of the determination |
| `rule_applied` | string | which rule fired — see `pd_verification/rules.py` for the full set (e.g. `life+70-expired`, `pre1978-95yr-expired-domestic`, `renewal-era-not-renewed`, `foreign-uraa-risk-life70-not-ruled-out`, `anonymous-95yr-expired`) |
| `flags` | string | semicolon-separated, e.g. `disputed_death_year`, `uraa_restoration_risk`, `renewal_status_unknown`, `foreign_publication_or_unknown_country`, `copyright_notice_status_unknown` |
| `verified_date` | date `YYYY-MM-DD` | when this row was produced |

### `data/pd_verification_inputs.csv` — Package 2's own supplementary input (new, added with the rule engine)

`book_corpus.csv` (above) only carries the fields Package 3 already collects. Getting a legally
sound public-domain determination — especially ruling out URAA restoration risk on foreign works —
needs a few more facts per book that aren't part of Package 3's contract. Rather than change
Package 3's schema, Package 2 owns and produces this file itself: its interactive mode offers to
save what you enter here so the batch run (and reruns) don't have to ask again. Every column is
optional/blank-allowed — a blank means "unknown," which the rule engine treats as unknown, never
guessed.

| column | type | notes |
|---|---|---|
| `book_id` | string | matches `book_corpus.csv` |
| `country_of_first_publication` | string or blank | e.g. `US`, `UK`, `France` |
| `simultaneous_us_publication` | bool (`true`/`false`) or blank | published in the U.S. within 30 days of a foreign first publication |
| `is_anonymous_pseudonymous_or_corporate` | bool or blank | defaults to "no" (identified author) when blank |
| `had_copyright_notice_at_publication` | bool or blank | only relevant for pre-1989 U.S. publications |
| `renewal_filed` | bool or blank | only relevant for U.S. works first published 1923–1963 |
| `creation_year` | int or blank | rarely needed — see `pd_verification/README.md` |
| `source` | string | e.g. `manual-research`, `interactive-session`, `loc-copyright-renewal-db` |
| `notes` | string | free text, optional |

## `studio_scoring/mandate_config.{yaml,json}` — Package 4 config (not a data/ file, lives with the code)

Editable weights, not hardcoded. Example shape:

```yaml
studio: "Target Studio Name"
weights:
  genre_fit: 0.25
  name_recognition: 0.15
  visual_story_adaptability: 0.20
  franchise_potential: 0.20
  budget_scale_fit: 0.10
  audience_fit: 0.10
```

## `data/studio_scores.csv` — Package 4 output (reads `book_corpus.csv`)

One row per `book_id`, scored regardless of PD status (scoring stays independent of verification —
Package 5 is what enforces the PD gate).

**Contract columns (required — Package 5 reads these):**

| column | type | notes |
|---|---|---|
| `book_id` | string | |
| `studio` | string | matches `mandate_config` |
| `total_score` | float 0–100 | weighted sum |
| `reasoning` | string | why it scored the way it did |

**Everything else about the rubric is Package 4's call.** The six categories and weights shown in
the `mandate_config` example above (genre fit, name recognition, etc.) are a placeholder
illustration of the config's *shape*, not a rubric — the real categories, weights, and any
per-category sub-score columns get defined by Package 4 based on actual studio research. Add
whatever sub-score columns your rubric needs (they can have any names); nothing downstream depends
on them, only on the four contract columns above.

## `data/shortlist.csv` — Package 5 output (reads `pd_verification.csv` + `studio_scores.csv`)

Final output. Only rows where the joined `pd_status == confirmed` are eligible — no exceptions,
per the ground rules in project-plan.md §5.

| column | type | notes |
|---|---|---|
| `rank` | int 1–10 | |
| `book_id` | string | |
| `title` | string | |
| `author` | string | |
| `total_score` | float | from `studio_scores.csv` |
| `score_reasoning` | string | from `studio_scores.csv` |
| `pd_status` | string | always `confirmed` in this file |
| `pd_reasoning` | string | from `pd_verification.csv`, so the PD basis is visible in the final report |

A human-readable `data/shortlist.md` (or similar) built from this CSV is expected too — the CSV is
the data contract, the formatting for review is up to Package 5.

## Why CSV and not a database

The team is mostly first-time builders working in separate Claude Code sessions on separate
branches. Plain files that merge cleanly in git and need no shared server keep every package
independently runnable and reviewable in a PR diff. Revisit this if/when the corpus grows past
what CSV can comfortably handle.
