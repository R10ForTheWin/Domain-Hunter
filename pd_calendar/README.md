# Package 1 — Forward-Looking PD Calendar

**Owner:** Teammate (phone ending 9302) · Branch suggestion: `yourname-pd-calendar`

## Goal

For each of the next 5 January 1sts, produce a list of authors (and their works) whose U.S.
copyright protection expires — using the life-of-author + 70-years rule.

- Find a reliable source of author death years (e.g. Wikidata) and cross-check disputed ones
- Compute: an author's works enter the public domain on Jan 1 of (death year + 71)
- Cross-reference against the book corpus (`data/book_corpus.csv`, from Package 3) once it exists,
  so the output is actual titles, not just names
- Output: a simple table/report — Year → Authors entering PD → Notable works

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 1.

## Input

- `data/book_corpus.csv` (produced by Package 3 — may not exist yet; you can start on the
  author/death-year research independently and cross-reference once it lands)

## Output

- `data/pd_calendar.csv` — exact schema in [`../docs/data-contracts.md`](../docs/data-contracts.md)

## Notes

- Works don't trickle in through the year — they all drop on a single date, January 1st. See
  project-plan.md §1 for why.
- Mark disputed death years as such rather than picking one silently — that's what the
  `author_death_year_disputed` / `confidence` columns are for.
