# Package 3 — Book Corpus & Data Pipeline

**Owner:** Radoslav Raychev · Branch suggestion: `radoslav-book-corpus`

## Goal

Assemble the pool of hundreds of candidate books that everything else runs against. This is the
first thing the other packages depend on — Packages 1, 2, and 4 all read your output.

- Source candidates (e.g. Project Gutenberg's catalog is a good starting point)
- Collect the metadata the other agents need: title, author, author death year, original
  publication year
- Clean it up — consistent format, no duplicates, obvious errors caught
- Output: one clean file (CSV) the rest of the team can build against

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 3.

## Output

- `data/book_corpus.csv` — exact schema, including the `book_id` primary-key format every other
  package joins on, in [`../docs/data-contracts.md`](../docs/data-contracts.md)

## Notes

- `book_id` is minted here and used everywhere downstream — get the slug format right
  (`slugified-title__slugified-author__pub-year`) since Packages 1, 2, 4, and 5 all key off it.
- This package has no upstream dependency — you can start immediately.
