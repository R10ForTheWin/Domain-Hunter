# Package 5 — How to run

Builds the final top-10 shortlist from the upstream package outputs.
Standard library Python only — no installs, no virtualenv.

## Run against the real shared data (normal use)

From this `shortlist_output/` folder:

```bash
python3 build_shortlist.py
```

Reads from the repo's shared `data/` folder:

- `data/pd_verification.csv`  (Package 2)
- `data/studio_scores.csv`    (Package 4)
- `data/book_corpus.csv`      (Package 3 — supplies title & author)

Writes:

- `data/shortlist.csv`  — the contract output (schema in `../docs/data-contracts.md`)
- `data/shortlist.md`   — human-readable report for review

## Run the built-in demo (no real data needed)

```bash
python3 build_shortlist.py --data-dir sample_data
```

`sample_data/` holds small fixture CSVs so the script can be run and reviewed
before Packages 2/3/4 have delivered. It also exercises the edge cases:

- a top-scoring book that is **not** PD-confirmed (correctly excluded)
- an "uncertain" book (excluded)
- a scored book missing from verification (skipped, with a warning)
- a confirmed book missing from the corpus (kept, blank title, with a warning)

## The one rule that never bends

Only rows whose joined `pd_status == confirmed` are eligible for the top 10.
A high score never overrides this. If fewer than 10 books are confirmed, the
shortlist is shorter than 10 — it is never padded with unconfirmed books.

## Notes for the team

- Title and author come from `book_corpus.csv` (Package 3) — `pd_verification.csv`
  and `studio_scores.csv` only carry `book_id`.
- Any CSV field that contains a comma must be quoted, or the join will mis-parse it.
