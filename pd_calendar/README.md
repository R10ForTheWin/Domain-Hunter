# Package 1 — Forward-Looking PD Calendar

**Owner:** Ross · Branch: `ROSS-development`

## Goal

For each of the next 5 January 1sts, produce a list of authors (and their works) whose U.S.
copyright protection expires.

- Determine which term rule governs each work, and compute the January 1st it enters the public
  domain (see **Which rule governs** below — this is the part the original brief got wrong)
- Where the death year is the governing input, cross-check disputed ones against a second source
- Cross-reference against the book corpus (`data/book_corpus.csv`, from Package 3) so the output
  is actual titles, not just names
- Output: a table/report — Year → Authors entering PD → Notable works

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 1.

## Which rule governs

**This README previously said the calendar uses life-of-author + 70, computing Jan 1 of
(death year + 71). That is the wrong rule for this corpus and the guidance has been corrected.**

U.S. works published **before 1978** run **95 years from publication**, no matter when the author
died. Only works published **1978 or later** use life + 70. Measured against the 2,630 rows of
`book_corpus.csv`: `pub+95` governs 1,597 books, `life+70` governs 9.

Why it matters — Agatha Christie died in 1976, and *Murder on the Orient Express* was published in
1934:

| rule | result |
|---|---|
| life+70 | 1976 + 71 = public domain in **2047** ❌ |
| pub+95 | 1934 + 96 = public domain in **2030** ✅ |

The error also runs in the dangerous direction. An author who died in 1951 with a book published in
1950 comes out as public domain in 2022 under life+70, when the real date is 2046 — i.e. the wrong
rule declares free a work that is still in copyright.

Three complications are flagged rather than guessed at, per
[`../docs/project-plan.md`](../docs/project-plan.md) §5:

- **Renewal era (published 1923–1963)** — copyright had to be renewed in its 28th year. An
  un-renewed work is already public domain, often decades early, so `pub+95` is only the *latest
  possible* date. Renewal is a fact about a filing and cannot be derived from the corpus.
- **§303 (created pre-1978, first published 1978–2002)** — protected through at least Dec 31 2047.
- **Foreign publication** — a work that lapsed on a U.S. formality may have been restored by the
  URAA. `language` is a weak proxy; the corpus has no country-of-first-publication column.

## Input

- `data/book_corpus.csv` (Package 3)

## Output

- `data/pd_calendar.csv` — schema in [`../docs/data-contracts.md`](../docs/data-contracts.md)
- `data/pd_calendar.md` — the readable Year → Authors → Works report

## How to run

From the repo root, no dependencies beyond the standard library:

```bash
python3 pd_calendar/scripts/build_calendar.py
```

```bash
python3 -m unittest discover -s pd_calendar/scripts -t pd_calendar/scripts
```

Useful flags: `--as-of-year` pins the year so a report can be regenerated exactly as produced;
`--horizon` changes how many cliffs to cover; `--all` writes every book rather than just the
window, for auditing the rules against the whole corpus.

## Layout

| file | what |
|---|---|
| `scripts/pd_rules.py` | the term rules — pure logic, no I/O |
| `scripts/build_calendar.py` | corpus → `pd_calendar.csv` + report |
| `scripts/test_pd_rules.py` | rule tests |
| `scripts/test_build_calendar.py` | producer tests |
| `scripts/test_cross_check.py` | agreement with Package 2's engine |

`test_cross_check.py` exists because this repo implements the same statute twice — here and in
`pd_verification/rules.py`. They answer different questions (*which year* vs. *confirmed today*),
so neither is redundant, but they share statutory constants and had already drifted once. **It
skips silently when `pd_verification` is absent**, so a green run on a branch without Package 2 is
not evidence the engines agree.

## Notes

- Works don't trickle in through the year — they all drop on January 1st. See project-plan.md §1.
- Mark disputed death years rather than picking one silently. Note that a disputed death year is
  irrelevant when `pub+95` governs, since that rule never reads it.
- A date here is **not** clearance. Package 2 (`pd_verification/`) confirms whether a specific
  book's public-domain claim holds; this package only says when a term is scheduled to end.
- Expect a short, heavily `uncertain` window. All 34 works currently entering 2027–2031 are
  renewal-era publications the corpus cannot resolve. That reflects a corpus sourced from
  Gutenberg and Open Library — repositories of works that are *already* public domain. See
  [`../docs/branch-audit-2026-08-12.md`](../docs/branch-audit-2026-08-12.md).
