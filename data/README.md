# data/

Shared interchange files produced and consumed by the packages. Exact schemas are pinned in
[`../docs/data-contracts.md`](../docs/data-contracts.md) — treat that file as the contract, this
one as just an index.

| file | produced by | consumed by |
|---|---|---|
| `book_corpus.csv` | Package 3 (Book Corpus) | Packages 1, 2, 4 |
| `pd_calendar.csv` | Package 1 (PD Calendar) | — (standalone report) |
| `pd_verification.csv` | Package 2 (PD Verification) | Package 5 |
| `studio_scores.csv` | Package 4 (Studio Scoring) | Package 5 |
| `shortlist.csv` | Package 5 (Shortlist) | — (final output) |

None of these files exist yet — each package owner creates their own when their pipeline runs.
If you change a column or add one, update `docs/data-contracts.md` in the same PR and flag it in
the group chat so downstream packages aren't silently broken.
