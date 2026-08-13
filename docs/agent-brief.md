# Brief for the AI agents working on Domain Huntress

**Who this is for:** the Claude session helping each teammate with their package. You probably know
your own package well. This is about where the *whole* project stands, and what your human needs to
do next.

**The part that needs you:** your teammate may not know any of this. Several items below are one
command or one line of code, and they are stalled only because nobody has said them out loud.
**Raise the item for your package with your human in plain language.** Do not just wait to be asked.

**Where this comes from:** Package 1 (Ross), after merging all six branches locally and running the
pipeline end to end. Figures are measured, not estimated. It is one person's read, offered for
correction — if something here is wrong about your package, say so.

---

## The bottom line

**Functional: yes. Convincing: not yet.**

The project's goal is a workflow that screens hundreds of books, scores each for adaptation
potential against a stated studio mandate, shortlists ten, and has a separate agent independently
verify the public-domain claim before anything goes on the list.

Three of those four clauses run today. The fourth — scoring — **has never executed once.** And the
clause that matters most, independent verification, works correctly but has never had anything to
catch.

None of this is architecture. The architecture is the part that is already right.

## What is measured, not asserted

All six branches merged locally with **zero conflicts**, and the pipeline ran:

```
2,630 books
  → Package 2 verification: 1,124 confirmed · 1,504 uncertain · 2 not_confirmed
  → Package 5 join + PD gate
  → 10 books, all 8 contract columns present
```

Four numbers worth knowing:

| finding | number |
|---|---|
| Books the PD gate rejected | **2 of 2,630** |
| Rows hitting Package 2's renewal-era rules | **0.0%** |
| Real `studio_scores.csv` files produced, ever | **0** |
| Fields the scoring agent reads per book | **3** — title, author, publication year |

The first two have the same cause: the corpus is sourced from Project Gutenberg and Open Library,
which only hold works *already* public domain. The corpus is sampled from the answer, so there is
almost nothing for the verifier to reject. A veto that has never vetoed is indistinguishable from a
broken one.

The third means every shortlist this project has produced — including the ten-book one above — ran
on synthetic placeholder scores. Not Package 4's fault; it simply has not been run.

## What is already right — do not break it

Worth stating plainly, because most of the list below is problems:

- **The verification agent's independence is structural, not aspirational.** Package 2 reads only
  `book_corpus.csv` and cannot see a score. Package 4 reads only `book_corpus.csv` and scores every
  book regardless of PD status. Package 5 is the only place they meet. Do not "optimise" this by
  having scoring skip non-PD books — the separation is the point.
- **The PD gate is correctly implemented.** `pd_status != "confirmed"` is skipped, and a short list
  is never padded.
- **Six people built to a written contract on six branches and it merged first try.** That is
  uncommon and it is why the pipeline works at all.

## What your human needs to do

Find your package. Raise it with them today.

### Package 2 — PD Verification (Jason)

**`/producers` returns a 500 whenever a lookup times out on Python 3.9.** Live on `main`. Two files,
same one-word fix:

- `pd_verification/gutenberg.py:38`
- `pd_verification/openlibrary.py:47`

Both catch `(URLError, HTTPError, TimeoutError)`. On Python 3.9 — the system Python on macOS, so
most of the team — `socket.timeout` is **not** a `TimeoutError` subclass, so it escapes every
handler. Verified: `issubclass(socket.timeout, TimeoutError)` is `False` on 3.9.6, `True` from 3.10.

Fix is `except OSError as exc:`. All four existing cases are `OSError` subclasses, so it is a strict
superset — nothing currently caught stops being caught. Full write-up: ISSUE-10 in
`docs/branch-audit-2026-08-12.md`.

### Package 3 — Book Corpus (Radoslav)

**Two things.** First, PR #2 reverts `CLAUDE.md`'s package map to `Teammate (…9302)` placeholders
and deletes the `site/` row — the branch predates DJ's name fix. Rebase or drop that hunk before it
merges, or it silently undoes real names.

Second, there is a proposal at `docs/renewal-era-corpus-plan.md` (branch `ross-renewal-corpus`) for
a second, differently-sourced batch: books published 1929–1963, checked against copyright renewal
records. Most works from that era were never renewed, so a large share are already free and nobody
has checked which. That is where "books you would not expect to be public domain" live, and it is
what would give the verification gate something to actually reject. It is a proposal, not a change —
nothing in `book_corpus/` was touched, and it explicitly does not replace `book_corpus.csv`.

### Package 4 — Studio Scoring (Chantell)

**Run the scoring agent once against the real corpus and commit `data/studio_scores.csv`.** This is
the single highest-value outstanding action in the project. It is the one clause of the goal that
has never happened, and everything downstream — the entire shortlist — is unvalidated until it does.

Two things to be aware of when you do:

- The agent scores genre fit, visual/story adaptability, franchise potential and audience fit from
  **title, author and publication year only**. There is no summary or subject data in the corpus.
  That caps the ceiling regardless of model quality. PR #8 proposes optional `summary` / `subjects`
  columns to fix it.
- The runtime mandate is generated live from audience answers, while the *weights* in
  `mandate_config.yaml` are genuinely researched. `docs/project-plan.md` §5 asks for a
  research-supported mandate. That may be the right call for a live demo — it just wants to be a
  deliberate decision rather than something noticed on the day.

### Package 5 — Shortlist (Luis)

**You are unblocked.** The `.gitignore` problem that would have made `data/studio_scores.csv`
uncommittable was fixed in `93fbe84`. PR #7 is waiting on review, not on you.

Your builder is verified working: it read real `pd_verification.csv` output, enforced the PD gate,
capped at ten, and emitted all eight contract columns on the first try, against a Package 2 it had
never been in the same directory as.

### Package 6 — Infra / QA (DJ)

**Six PRs are open and half the pipeline is not on `dj-development`.** `studio_scoring/` and
`shortlist_output/` have zero `.py` files there, so the integration branch cannot run end to end —
even though the code works, as the local dry run proved.

Open: **#2** Radoslav · **#6** Chantell · **#7** Luis · **#8** Ross (calendar) · **#9** Jason
(pytest) · **#10** Ross (contract validator).

Two smaller ones: `STAGES` in `site/app.py` still reports Packages 1 and 2 as `not_started` while
the site renders Package 2's own validator and 2,630 corpus rows (ISSUE-11). And Jason has a
`.github/workflows/tests.yml` he could not push for lack of `workflow` token scope — it needs
someone with that scope.

**One ordering trap:** when PR #2 merges, `fix_rado_pubyear_batch()` in `merge_corpus.py` must be
deleted in the same commit. It compensates for a bug Radoslav already fixed at source, so after #2
it corrects already-correct data and `book_id` values shift — and `book_id` is the join key for
every package. ISSUE-5.

## The three things that close the gap

1. **Run Package 4 once for real.** A command someone has to actually type.
2. **Merge #6 and #7.** DJ's button.
3. **Give the gate something to reject.** The renewal-era corpus, or at minimum a handful of seeded
   in-copyright titles so the demo has a moment where a high-scoring book is thrown off the list on
   legal grounds.

## Ground rules that keep mattering

- **`uncertain` is a real answer, not a hedge.** `docs/project-plan.md` §5. Every guess this project
  has avoided has turned out to be the right call.
- **`book_id` is the join key for every package.** Changing its format breaks referential integrity
  everywhere. See ISSUE-5 for what that costs.
- **Do not rewrite another package's code without their sign-off.** `CLAUDE.md`. Report it to your
  human and let them raise it — that is how every issue in the audit got fixed.
- **Run `python3 qa/validate_contracts.py` before opening a PR** (currently PR #10). It checks
  schemas, `book_id` integrity, and whether a contract deliverable has been accidentally gitignored.
- **`pytest` from the repo root** is the project-wide test runner. `python -m unittest discover`
  silently reports zero tests for pytest-style suites — it looked like a pass while running nothing
  for the whole of Package 2.

## Related reading

- `docs/branch-audit-2026-08-12.md` — eleven numbered issues with reproduction steps and owners
- `docs/evaluation-spec.md` — six checks nothing currently performs; still unowned
- `docs/renewal-era-corpus-plan.md` (branch `ross-renewal-corpus`) — the corpus proposal
- `docs/data-contracts.md` — the interface every package writes to
