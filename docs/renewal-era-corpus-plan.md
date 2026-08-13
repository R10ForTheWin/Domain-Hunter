# Renewal-era corpus — proof-of-concept plan

**Status:** proposal for **Package 3 (Radoslav)**. Written by Package 1 (Ross) as a plan, not as
code. Nothing in `book_corpus/` has been touched.

**This is not a replacement for the existing corpus.** `data/book_corpus.csv` works, it is merged,
and the pipeline runs on it. This proposes a *second, differently-sourced* batch alongside it,
because the current sourcing cannot produce the kind of result the project is supposed to produce.
If the experiment fails, nothing is lost and the existing corpus is unaffected.

---

## 1. The problem, in numbers

The project's pitch is finding books that are legally usable and worth adapting. The interesting
version of that is finding books **you would not expect to be free**. The current corpus cannot
contain any, and this is measurable rather than a matter of opinion.

Measured on `data/book_corpus.csv` at `b04e2ae` (2,630 rows):

| publication window | books | share of dated rows |
|---|---|---|
| pre-1929 | 1,466 | 91.3% |
| 1929–1963 (renewal era) | 131 | 8.2% |
| 1964–1977 | 0 | 0.0% |
| 1978+ | 9 | 0.6% |

Sources: `openlibrary` 2,135 · `gutenberg` 435 · both 60.

**Both sources only hold works already believed to be public domain.** So the corpus is sampled
*from the answer*. Two consequences, both observed:

- Running Package 2 over all 2,630 books returns **1,124 confirmed, 1,504 uncertain, 2
  not_confirmed**. The verification gate — the part of the architecture the project is proudest of —
  rejects two books out of 2,630. It is well built and has essentially nothing to stop.
- Package 2's renewal-era rules (`renewal-era-not-renewed`, and the `renewal_filed` column in
  `data/pd_verification_inputs.csv`) fire on **0.0% of rows**. Jason built that machinery and it has
  never once executed.

Scaling the current sourcing up does not fix this. Ten times as many Gutenberg books is ten times
as many books everyone already knows are free.

## 2. Why the renewal era is where the answer is

U.S. works published 1929–1963 had to have their copyright **renewed in the 28th year** or they fell
into the public domain. Renewal rates were low — a minority of works were renewed, and the figure is
commonly cited well under a third, though it varies by year and category. **Verify the actual rate
as part of this work rather than taking that number on faith.**

That means a large share of mid-century books are already public domain and effectively nobody
knows which, because they are not on Gutenberg and no one has checked.

Renewal is a fact about a *filing*. It cannot be derived from title, author, death year and
publication year — which is exactly why Package 2 correctly returns `uncertain` for these books
today. Supplying the renewal fact is what turns those into real answers.

## 3. Sources

All public and already digitised. **Check reachability before designing around any of them** — this
environment's network is unreliable, and an unhandled timeout against a lookup API is already a
known live bug (ISSUE-10 in `docs/branch-audit-2026-08-12.md`).

| source | what it gives |
|---|---|
| Stanford Copyright Renewal Database | book (Class A) renewals covering 1923–1963 — the core lookup |
| NYPL's digitised Catalog of Copyright Entries | the underlying renewal filings, when Stanford is ambiguous |
| HathiTrust Copyright Review Program | determinations already made at scale, useful for spot-checking |

For the *candidate* side — which books to check in the first place — the frame should be
**cultural or commercial significance in 1929–1963**, not availability. Bestseller lists, prize
lists (Pulitzer, National Book Award), and contemporary review coverage are all reasonable starting
points. The whole point is to start from "worth adapting" and *discover* the legal status, rather
than starting from "already free" and hoping something good is in there.

## 4. Scope

**Aim for 100–300 titles, not thousands.** This is a proof of concept and the cost is per-book
lookup work, not row count. A precise frame beats volume: 200 books from the right window will
prove or disprove the thesis, and 20,000 more Gutenberg rows will not.

## 5. Output

Write a **separate batch file**, `data/book_corpus_renewal.csv`, in exactly the
`data/book_corpus.csv` schema from `docs/data-contracts.md`. Do not modify `book_corpus.csv` in this
work. Merging the batches is a later decision and a separate PR.

Two fields carry the findings:

- `notes` — record the renewal determination and its source, e.g.
  `renewal searched: Stanford CRD, no Class A renewal found for 1938 registration`.
- Populate **`data/pd_verification_inputs.csv`** (Package 2's supplementary input, already in
  `docs/data-contracts.md`) with `renewal_filed` and `country_of_first_publication` per book. This
  is the file that turns Package 2's `uncertain` into a real verdict, and it is the single highest-
  value output of this work.

Leave a field blank rather than guessing. `docs/project-plan.md` §5 is explicit: when unsure, mark
it uncertain. A blank is a known gap; a plausible invented value is a silent error that propagates
into the shortlist's stated reasoning.

Run `python3 qa/validate_contracts.py` before opening the PR — it checks the schema, `book_id`
uniqueness and referential integrity (currently PR #10).

## 6. Acceptance criteria

The experiment has succeeded if **all four** hold:

1. `data/book_corpus_renewal.csv` contains 100+ titles published 1929–1963, sourced by
   significance rather than availability.
2. Each has a recorded renewal determination — found, not found, or explicitly unresolved — with
   its source cited in `notes`.
3. Running Package 2 over the batch produces a **non-trivial number of `not_confirmed` results.**
   This is the real test. The current corpus yields 2 out of 2,630. A batch that also rejects almost
   nothing means the frame is still wrong.
4. Package 2's renewal-era rules fire on a meaningful share of rows, instead of 0.0%.

**A negative result is still a result.** If it turns out most notable mid-century books *were*
renewed and few are free, that is a genuine finding, and it should be written up rather than
buried. It would tell the team the thesis is wrong, which is worth knowing before it is presented.

## 7. What not to do

- **Do not modify `data/book_corpus.csv`.** It is merged and the pipeline depends on it.
- **Do not change `book_id` formats.** `book_id` is the join key for every package. ISSUE-5 in the
  branch audit is about exactly this: regenerating the corpus shifted IDs and broke referential
  integrity. Mint new IDs in the existing format only.
- **Do not guess a renewal status.** Unverified is a valid, expected answer.
- **Do not scrape aggressively.** These are small public services. Rate-limit, cache locally, and
  handle timeouts — see ISSUE-10 for what an unhandled one costs.

## 8. Open questions for the team

1. **Who owns this?** It is corpus sourcing, so Package 3 by default. It was proposed by Package 1
   and can be built by either. Worth agreeing before anyone starts.
2. **Does the demo want it?** A shortlist of mid-century titles nobody realised were free is a
   finding. A shortlist headed by *Dr. Jekyll and Mr. Hyde* is a lookup. That is a presentation
   decision as much as a technical one.
3. **Do content fields land alongside this?** PR #8 proposes optional `summary` / `subjects`
   columns on `book_corpus.csv`. Package 4 currently scores genre fit and visual adaptability from
   a title string. If a new batch is being assembled by hand anyway, collecting summaries at the
   same time is much cheaper than a second pass.

## 9. Related

- `docs/branch-audit-2026-08-12.md` — ISSUE-5 (`book_id` stability), ISSUE-10 (timeout handling),
  and the integration dry-run figures.
- `docs/data-contracts.md` — the `book_corpus.csv` and `pd_verification_inputs.csv` schemas.
- `docs/evaluation-spec.md` — check 4's funnel report is what would make the before/after
  difference legible.
- `pd_verification/rules.py` — the renewal-era logic this work exists to feed.
