# Evaluation spec — proposal

**Status:** proposal, unowned. Written by Package 1 to give the gap a shape so it can be assigned.
**Suggested owner:** Package 6 (DJ), whose remit already includes "spot-check each package's output."

## The gap

Domain Huntress has a rigorous independent verifier for the half of the problem that is
objectively checkable, and nothing at all for the half where the judgment lives.

Public-domain status is a fact. It is deterministic, testable against known answers, and Package 2
verifies it independently, with a hard gate and `uncertain` as a first-class result. That part is
well built.

Adaptation potential is a judgment. Package 4 produces a `total_score` from 0–100 for every book,
and **nothing checks whether those numbers mean anything.** No ground truth, no held-out set, no
second opinion, no calibration. The score decides the final ten; the verification only decides who
is eligible.

The project put its verification effort on the part a paralegal could check, and left the part
requiring actual expertise unexamined.

## What an evaluation would check

Six checks, roughly in order of value per unit of effort.

### 1. Score agreement (highest value, lowest cost)

Run Package 4 twice over the same books with the same mandate, independently, and report the
agreement between runs — rank correlation, and mean absolute difference in `total_score`.

Low agreement means the rubric is underspecified and the two-decimal precision in
`studio_scores.csv` is decorative. This needs no new owner and no ground truth: it is Package 4
running its own agent a second time.

### 2. Source verification

Every citation in `studio_scoring/mandate_brief.md` should resolve to a real, retrievable
document. Fabricated-but-plausible citations are the most likely failure mode in any
LLM-assisted research task, and nothing currently checks for them.

Report: sources cited, sources that resolve, sources that do not. Anything that does not resolve
comes out of the brief or gets relabelled as inference.

### 3. Fact vs. inference audit

`project-plan.md` §5 requires the mandate to distinguish observed evidence from inferred criteria.
Check that every claim in the brief is labelled, and that the inferred ones are actually supported
by the cited evidence rather than merely adjacent to it.

### 4. Funnel report

Corpus in, shortlist out, with the drop-off at every stage and the reason for each.

```
2,764 corpus
  -> N PD-confirmed        (M uncertain, K rejected)
  -> N scored
  -> 10 shortlisted
```

The current numbers are already informative: the gate rejects 3 books out of 2,764, and Package
2's renewal-era logic fires on 0.0% of rows. Neither fact is visible anywhere in the product. A
funnel makes "the gate has nothing to catch" impossible to miss.

### 5. Recall probe

The pipeline can be wrong in two directions: a bad book on the list, or a good book missing from
it. Only the first is visible. Seed a handful of titles that clearly ought to surface for the
chosen mandate and check whether they do. A strong candidate that vanishes points at something
upstream silently dropping rows.

### 6. Contract validation

Assert that every `data/*.csv` matches `docs/data-contracts.md` — required columns present,
enumerated values in range, `book_id` resolvable against `book_corpus.csv`.

Roughly 50 lines of stdlib Python, and it would have caught two defects already found by hand:
`data/studio_scores.csv` being unwritable to git (ISSUE-8), and `book_id` values shifting between
merge runs (ISSUE-5). This is the one check worth automating rather than doing once.

## What this is not

Not a quality bar the project has to pass before shipping. Several of these checks will produce
uncomfortable numbers — that is the point. "We measured where our system is weak" is a stronger
result than an unexamined top ten, and considerably stronger than discovering the weakness during
a demo.

## Dependency

Checks 1–3 need Package 4 to have run for real at least once. As of this writing its scoring agent
has never been executed against real data (needs an API key), so the entire shortlist has only
ever been validated against synthetic placeholder scores. Check 6 can be built today.

## Related

- `docs/branch-audit-2026-08-12.md` — ISSUE-7 (mandate research vs. the live mad-lib mechanic),
  ISSUE-8 (the gitignore blocker), and the integration dry-run findings.
- `docs/data-contracts.md` — the proposed `summary` / `subjects` columns. Without content fields,
  check 1 measures agreement between two guesses made from a title, which is a much weaker test
  than agreement between two readings of a book.
