# Package 5 — Shortlist & Output Formatting

**Owner:** Luis R. · Branch suggestion: `luis-shortlist`

## Goal

Take the scored, PD-confirmed books and produce the final top-10 shortlist in a clean, shareable
format.

- Combine Package 2's verification result + Package 4's score for each book
- Sort and select the top 10 (only books that passed PD verification are eligible — no exceptions)
- Output: a clean report showing rank, title, author, score reasoning, and PD verification basis
  for each of the 10

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 5.

## Input

- `data/pd_verification.csv` (Package 2)
- `data/studio_scores.csv` (Package 4)

## Output

- `data/shortlist.csv` — schema in [`../docs/data-contracts.md`](../docs/data-contracts.md)
- `data/shortlist.md` (or similar) — human-readable version for review; formatting is up to you,
  the CSV columns are the contract

## Ground rule

Only rows where `pd_status == confirmed` are eligible for the top 10 — no exceptions, even for a
high-scoring book. If fewer than 10 books pass verification, the shortlist is shorter than 10; it
doesn't get padded with unconfirmed books.
