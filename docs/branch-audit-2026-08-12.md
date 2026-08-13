# Branch audit — 2026-08-12

Cross-branch review looking for defects, contract violations, and data-quality problems.
Written for DJ (Package 6, Infra/QA) and intended to be actionable by an AI coding agent.

**Nothing in this document has been fixed.** Every issue below lives on a branch owned by
someone else, and `CLAUDE.md` is explicit: *"Do not delete or substantially rewrite another
team member's work without approval."* Each issue names its owner. Get their sign-off first.

Branch state when this was written:

| branch | SHA |
|---|---|
| `main` | `e05d993` |
| `dj-development` | `14e7165` |
| `dj-book-corpus` | `bfbda80` |
| `radoslav-book-corpus` | `a46c6a6` |
| `jason-pd-verification` | `edc8b67` |
| `chantell-mandate-scoring` | `e05d993` (no commits) |

All figures below come from `data/book_corpus.csv` at `origin/dj-book-corpus` (2,764 rows).
Reproduce any of them with:

```bash
git show origin/dj-book-corpus:data/book_corpus.csv > /tmp/corpus.csv
```

---

## ISSUE-1 — The live site shows zero books while reporting Package 3 as done

**Severity:** high (visible on the deployed demo) · **Owner:** DJ · **Branch:** `dj-development`

`site/app.py` resolves `DATA_DIR` to `site/data/` if it exists, else `../data/`. On
`dj-development` **neither contains `book_corpus.csv`** — `data/` holds only `README.md`, and
there is no `site/data/` at all. Consequences:

- `load_corpus_stats()` returns `None`, so `/status` renders an empty corpus panel
- `/producers` search returns no results for every query
- meanwhile `STAGES` in `site/app.py` hardcodes Package 3 as `"status": "done"`

So the demo asserts the corpus is complete and simultaneously displays nothing.

**Root cause:** `dj-book-corpus` (`bfbda80`) has never been merged into `dj-development`. Two
commits are outstanding.

**Verify:**
```bash
git ls-tree -r --name-only origin/dj-development -- data/ site/
```

**Fix:** merge `dj-book-corpus` into `dj-development`. Note that ISSUE-5 means that merge does
not currently reproduce from source. Separately, consider deriving the `STAGES` status from
whether the files exist rather than hand-maintaining it — a hardcoded "done" that contradicts
the page it renders is the kind of thing a demo audience notices.

---

## ISSUE-2 — The same author exists twice under two name formats

**Severity:** high · **Owner:** Package 3 (Radoslav / DJ) · **Branch:** `dj-book-corpus`

`docs/data-contracts.md` specifies `author` as *"full name, 'Last, First' preferred."* The
merged corpus is inconsistent:

- `Last, First` — 908 rows
- `First Last` — 1,856 rows
- **99 authors appear in both formats** — e.g. Henrik Ibsen, Virginia Woolf, Joris-Karl Huysmans

Any operation that groups or joins by author splits those 99 into two distinct people. Package 1
groups by author to build the calendar; Package 4 may key mandate research off author identity.

**Fix:** normalise `author` to a single format during the merge, and add a validator that fails
when both formats are present. The format should be whichever the contract settles on — amend
the contract if `First Last` is preferred, rather than leaving it ambiguous.

---

## ISSUE-3 — 324 rows record a reprint date as the original publication year

**Severity:** high · **Owner:** Package 3 · **Branch:** `dj-book-corpus`

324 rows have `publication_year` **later than** `author_death_year`. Examples: *A book for
parents* (pub 1950, author died 1939); *A guide to the history of physics* (pub 1923, author died
1922). These are Open Library "first publish year" values that are actually modern reprint or
collected-edition dates. `build_corpus.py` already discards some of these as implausible, so the
problem is known — the filter just does not catch the ones where the gap is small.

This matters more than it looks: `publication_year` is the field that **determines** the
public-domain date for pre-1978 works (95 years from publication). A wrong publication year
produces a wrong PD date, inflated, in the direction of "still in copyright."

`docs/data-contracts.md` already requires this field be *"original publication, not a reprint
edition."* So this is a contract violation, not just untidy data.

**Fix:** treat `publication_year > author_death_year` as a validation failure at merge time and
blank the field rather than recording a value known to be wrong. Package 1 now refuses to publish
a calendar date for these rows, so they are currently dropped downstream rather than trusted.

---

## ISSUE-4 — `author_death_year_disputed` is never populated

**Severity:** medium · **Owner:** Package 3 · **Branch:** `dj-book-corpus`

The column is `false` on all 2,764 rows. The `notes` column shows single-source Wikidata lookups
(`author death year from Wikidata (Q44972)`) with no second source, so no dispute could ever have
been detected — the column is structurally always-false rather than genuinely all-undisputed.

This has a downstream cost. `pd_calendar/README.md` requires cross-checking disputed death years,
and both `pd_calendar.csv` and `pd_verification.csv` carry a `disputed` state that currently has
no upstream signal to fire on. Two packages have a code path that can never execute.

**Fix:** corroborate death years against a second source (VIAF or Library of Congress alongside
Wikidata) and set the flag where they disagree. If that is out of scope for now, say so in
`book_corpus/README.md` so downstream packages stop treating the column as meaningful.

---

## ISSUE-5 — The merged corpus cannot be reproduced from the branches

**Severity:** high (was medium — see the proof below) · **Owner:** Radoslav + DJ ·
**Branches:** `radoslav-book-corpus`, `dj-book-corpus`

`book_corpus/scripts/merge_corpus.py`'s docstring states that Radoslav's input has two defects
and that the script corrects them *on a local copy* because his branch is unfixed.

That claim checked out: in `data/book_corpus_pubyear.csv` at `a46c6a6`, the `author` column was
`Austen, Jane` while the `book_id` slug was `pride-and-prejudice__jane-austen__1813` — 493 of 494
slugs used `First Last` order, contradicting the `author` column beside them.

**Radoslav has since fixed this at source** (`0de89ca`, PR #2): 485 of 494 slugs now follow
`Last, First`, and `pride-and-prejudice__austen-jane__1813` is the new form.

**Proven, not predicted.** The merge script's own docstring says *"When his fix lands for real,
re-running this script should produce the same result."* It does not. Merging all six branches
locally and re-running `merge_corpus.py` produced:

```
2,764 rows  ->  2,767 rows
2 book_ids vanished, 5 new book_ids appeared
e.g.  flatland__abbott-edwin-abbott__unk  ->  flatland__abbott-edwin-abbott__1886
```

The change is an improvement — Radoslav's fix supplied publication years that were previously
unknown. But `book_id` is the primary key every package joins on, and it moved.

**Fix, and it is now time-critical:** PRs #2 and #3 must land in the same change, with
`fix_rado_pubyear_batch()` deleted from `merge_corpus.py` and `data/book_corpus.csv` regenerated
from the corrected inputs. Do this before any package commits a file keyed on the current IDs —
`data/pd_verification.csv` already exists in a dry run and would be invalidated. After that point
this stops being a merge and becomes a migration.

Note also: the merge script's plausibility pass blanked 45 implausible publication years on that
run, which is partial coverage of ISSUE-3 (324 rows are affected).

---

## ISSUE-6 — `book_id` format deviates from the contract for 705 rows

**Severity:** low · **Owner:** Package 3 · **Branch:** `dj-book-corpus`

The contract pins `book_id` as `slugified-title__slugified-author__pub-year`. 705 rows end in
`__unk` instead of a year, because the publication year is unknown. The convention is reasonable —
it just is not written down, and `book_id` is the primary key every package joins on.

**Fix:** document `unk` in `docs/data-contracts.md`, or mint a stable surrogate. Note that if
ISSUE-3 is fixed by blanking bad publication years, more rows will become `__unk`, and the ID of a
row must not change once other packages reference it.

---

## ISSUE-7 — Package 4 has started; two things to settle

**Severity:** medium · **Owner:** Chantell + DJ · **Branch:** `chantell-mandate-scoring` (PR #6)

Superseded: this said "not started." Package 4 now exists (`8471d20`) with genuine A24 research —
cited trade sources, real budget figures, fact and inference separated as `project-plan.md` §5
requires. Two open questions remain:

1. **The scoring agent has never been run.** It needs an API key, so no real `studio_scores.csv`
   has ever been produced. Everything downstream of Package 4 — the entire shortlist — is
   currently validated only against synthetic placeholder scores.
2. **The operative mandate is not the researched one.** `madlib_template.yaml` assembles a mandate
   live from audience shout-outs during the demo: *"A {ADJECTIVE} {GENRE} where a {CHARACTER}
   {VERB} at a {SETTING}."* The research grounds the template's *design*, but what actually scores
   books at runtime is an improvised sentence. `project-plan.md` §5 says the mandate must be
   supported by research. This may well be the right call for a live demo — it just needs to be a
   decision DJ makes deliberately rather than discovers on the day.

---

## ISSUE-8 — `data/studio_scores.csv` is gitignored, which silently breaks Package 5

**Severity:** blocker · **Owner:** Chantell · **Branch:** `chantell-mandate-scoring` (PR #6)

PR #6 adds three lines to the **repo-root** `.gitignore`:

```
# Package 4 — per-run generated artifacts (regenerated each demo run / test run)
studio_scoring/mandate_live.yaml
data/studio_scores.csv
```

`data/studio_scores.csv` is a contract deliverable, not a scratch artifact. `docs/data-contracts.md`
defines it as Package 4's output; `data/README.md` lists it as an interchange file consumed by
Package 5; the stated rationale for the whole CSV architecture is *"plain files that merge cleanly
in git."*

**Proven on a local merge of all six branches:**

```
$ git add data/studio_scores.csv
The following paths are ignored by one of your .gitignore files:
data/studio_scores.csv
hint: Use -f if you really want to add them.

$ git check-ignore -v data/studio_scores.csv
.gitignore:16:data/studio_scores.csv	data/studio_scores.csv
```

**Why this is worse than it looks.** `.gitignore` does not stop the file being *written*, only
committed. So the pipeline works perfectly on the machine that just ran Package 4, and produces an
empty shortlist on every fresh clone, with no error explaining why. Package 5 would report
"PD-confirmed & scored books: 0" and look like the bug.

A dry-run commit on the integration branch demonstrates the failure mode exactly: it contains
`pd_verification.csv`, `shortlist.csv`, and `shortlist.md`, and is missing `studio_scores.csv` —
the shortlist is committed but cannot be regenerated from what is in the repo.

The instinct behind the change is reasonable; generated files often should not be committed. It
just conflicts with an architecture that uses committed CSVs as the transport between packages.

**Fix:** drop the `data/studio_scores.csv` line. `studio_scoring/mandate_live.yaml` is genuinely
a per-run artifact and should stay ignored. One line, and it is worth doing before PR #6 merges —
`.gitignore` is repo-root, so once merged it silences that path for every teammate.

---

## Integration dry run — the pipeline does work end to end

All six branches were merged into a local throwaway branch and the pipeline was run. Recorded here
so nobody has to repeat it.

**Merging:** all six merge with **zero conflicts**, and all 15 pairwise combinations are clean.
Only `jason-pd-verification` and `ROSS-development` touch `docs/data-contracts.md`, in different
sections. No secrets on any branch.

**Running:**

```
2,764 books (Package 3)
   -> Package 2 verification: 1,318 confirmed | 1,443 uncertain | 3 not_confirmed
   -> Package 5 join + PD gate
   -> 10 books, all 8 contract columns present
```

Package 5 correctly enforced `pd_status == confirmed`, capped at 10, and emitted both
`shortlist.csv` and `shortlist.md`. Package 4's scoring was **synthetic placeholder data**, so the
3 -> 4 hop is the one link still unproven.

**Two numbers worth the team's attention:**

- **The PD gate rejected 3 books out of 2,764.** On a corpus sourced from Project Gutenberg and
  Open Library — both of which hold works that are already public domain — there is almost nothing
  for the verification agent to catch. The gate is well built and has close to nothing to do.
- **Package 2's renewal-era logic fired on 0.0% of rows.** `renewal-era-not-renewed` and the
  `renewal_filed` supplementary column exist and have never once been exercised, because only
  11.4% of the corpus was published 1929–1963 and 83.9% predates 1929 entirely.

Both point at the same thing: the corpus is sampled from the answer. See the corpus note below.

---

## Not defects — checked and clean

- **Site security.** `site/railway.json` starts the app under gunicorn, so the `debug=True` in
  `app.py`'s `__main__` block never runs in production (no exposed Werkzeug console). No template
  uses `|safe`, so Jinja2 autoescaping covers the `/producers` query parameter. No injection path
  found — there is no database and no shell invocation.
- **`book_id` uniqueness.** 2,764 rows, 2,764 unique IDs, no duplicates.
- **CSV integrity.** No short rows, no empty titles, no future publication years. The site's
  `r["title"].lower()` in `/producers` cannot currently raise, though it would if a malformed row
  ever landed — `r.get("title") or ""` would be sturdier.
- **Package 2's rule engine.** `pd_verification/rules.py` is the strongest code in the repo. It
  applies the correct 95-years-from-publication rule for pre-1978 works, handles URAA restoration,
  §302(c) corporate/anonymous authorship, and notice formalities. It also adds
  `data/pd_verification_inputs.csv` to capture `country_of_first_publication`, which is exactly the
  field needed to resolve the foreign-work uncertainty Package 1 hit. Package 1 should consume that
  file rather than duplicate the research.

---

## Context: what Package 1 changed on its own branch

Two related fixes are already applied on `ROSS-development`, listed here so they are not
double-counted as outstanding work:

1. **`docs/data-contracts.md` — `pd_calendar.csv` schema amended.** Added `publication_year`,
   `rule_applied`, and `flags`; added `uncertain` to `confidence`; relaxed `author_death_year` and
   `pd_date` to allow blanks; changed the row grain from per-author to per-work. Reason: the
   original schema assumed life+70, which governs 44 of 2,764 books, while publication+95 governs
   2,015. The old schema had no column for the field that determines the answer, and could not
   represent `uncertain` — which is the verdict for every book in the current five-year window.
   This merges cleanly with Jason's edits to the same file (verified with `git merge-tree`).

2. **`pd_calendar/scripts/` — rule engine plus cross-check.** `RENEWAL_ERA_START` aligned to 1923
   to match `pd_verification/rules.py`, and `test_cross_check.py` added, which asserts the two
   engines carry identical statutory constants and never return contradictory verdicts on a shared
   fixture set. **The cross-check skips silently when `pd_verification` is absent**, which is the
   case on any branch that has not merged Package 2 — a green run there is not evidence the engines
   agree. It has been verified to run and to fail correctly on drift by materialising both packages
   in a scratch tree.
