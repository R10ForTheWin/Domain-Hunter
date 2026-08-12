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

One row per (author, PD year) once cross-referenced to actual titles in the corpus.

| column | type | notes |
|---|---|---|
| `pd_date` | date `YYYY-01-01` | always January 1st, see project-plan.md §1 |
| `author` | string | |
| `author_death_year` | int | |
| `book_id` | string or blank | link into `book_corpus.csv`; blank if the author has no title in the corpus yet |
| `title` | string or blank | denormalized for readability, matches `book_id` if set |
| `confidence` | `confirmed` / `disputed` | mirrors `author_death_year_disputed` reasoning |
| `source` | string | e.g. `wikidata`, plus a second corroborating source in `notes` |
| `notes` | string | optional |

## `data/pd_verification.csv` — Package 2 output (reads `book_corpus.csv`)

One row per `book_id`. This file is produced **independently** of Package 4 — it must never take
score into account.

| column | type | notes |
|---|---|---|
| `book_id` | string | |
| `pd_status` | `confirmed` / `not_confirmed` / `uncertain` | never blank — "uncertain" is a valid, expected answer |
| `reasoning` | string | plain-language explanation of the determination |
| `rule_applied` | string | which rule fired, e.g. `life+70`, `renewal-era-1929-1963`, `foreign-pub` |
| `flags` | string | semicolon-separated, e.g. `disputed_death_year;renewal_era` |
| `verified_date` | date `YYYY-MM-DD` | when this row was produced |

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
