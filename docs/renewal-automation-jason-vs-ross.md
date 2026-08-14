# Renewal-status automation — Jason's build vs. Ross's proposal

**For:** Ross, to compare against `ross-renewal-corpus` / PR #14 (Radoslav) before anyone opens a
PR for `jason-renewal-automation`.
**From:** Jason (Package 2).
**Why this exists:** we built overlapping work independently — same underlying question (which
1923–1963 books had their copyright renewed), two different data sources, no file collision, but
worth reconciling before either lands. Nothing here has been merged; this is a side-by-side so we
can decide together what to do with it.

---

## What I built (`jason-renewal-automation`, not yet a PR)

- **Source:** NYPL's digitised Catalog of Copyright Entries — registrations
  (`catalog_of_copyright_entries_project`) + renewals (`cce-renewals`).
- **Candidate set:** every book in `data/book_corpus.csv` with `publication_year` in 1923–1963 (the
  full existing corpus, not a curated subset) — 217 books in that window.
- **Method:** two-stage.
  1. Fuzzy-match each book (normalized title + author, `difflib`, inverted word-index blocking for
     speed) against ~700K registration records to find its `regnum`/`regdate`.
  2. **Exact** match of `(regnum, regdate)` against the renewals dataset — no fuzzy matching on the
     renewal side at all, since NYPL's renewal records key on that pair rather than on title text.
- **Output:** `data/pd_verification_inputs.csv` (75 rows, high-confidence ≥0.90 combined
  title+author score, written straight through) and
  `data/pd_verification_renewal_review_queue.csv` (20 rows, 0.75–0.90, flagged for a human).
  Below 0.75, or no candidate at all: left blank, never guessed.
- **`country_of_first_publication`:** always left blank. Investigated separately — the only signal
  available (registration class `AI`, "published abroad") doesn't move `rules.py`'s verdict either
  way, and nothing in the data supports a confident "US" without guessing.
- **Script:** [`pd_verification/scripts/match_renewals.py`](../pd_verification/scripts/match_renewals.py)

## What you proposed / found (`ross-renewal-corpus`, docs only, no code)

- [`docs/renewal-era-corpus-plan.md`](renewal-era-corpus-plan.md) — proposal: 100–300 titles
  selected by **cultural/commercial significance** (bestseller lists, prize lists), not by what's
  already digitised, using Stanford's Copyright Renewal Database as the core lookup. This is what
  Radoslav built as PR #14 (179 books, Publishers Weekly bestsellers, Stanford CRD).
- [`docs/dataset-linkage-analysis.md`](dataset-linkage-analysis.md) — feasibility study on
  CMU Book Summary Corpus + Stanford renewals. Found that naive title matching against renewal
  records looks like it finds 653 "no renewal" books, and every sampled one is a false positive
  (*The Hobbit*, *Waiting for Godot* — still very much in copyright). Root causes: renewal titles
  are stored as `"Gaudy night, by Dorothy L. Sayers"` (needs stripping before comparing), and a
  **miss on a foreign author means the opposite of what it means for a US author** (no US renewal
  needed ≠ public domain, because of URAA restoration).
- [`docs/corpus-attribution-audit.md`](corpus-attribution-audit.md) — separate finding, not about
  renewals: 90 confirmed title/author mismatches in `book_corpus.csv` (e.g. *Twelfth Night*
  credited to Henry Ford), 316 of 337 affected rows traced to the Open Library sourcing path. Real
  bug, still unfixed on `main` as of this writing.

## Side by side

| | Mine | Yours (as implemented in PR #14) |
|---|---|---|
| Renewal data source | NYPL CCE registrations + renewals | Stanford Copyright Renewal Database |
| Candidate books | Full `book_corpus.csv`, 1923–1963 (217) | Curated: PW bestsellers, top 6/yr 1929–1963 (179) |
| Title matching happens against | Registration records only | Renewal records directly |
| Renewal-side matching | Exact key join (`regnum`+`regdate`) | Text match (per PR #14 description) |
| Output file | `data/pd_verification_inputs.csv` | `data/pd_verification_inputs_renewal.csv` (separate, by design) |
| `country_of_first_publication` | Always blank | Always blank |
| Unmatched/low-confidence handling | Blank, or review queue | Flagged "uncertain," per PR #14 |

## Open questions for you

1. **Does the title-format trap in your linkage analysis apply to my registration-side matching
   too?** I match against NYPL's structured `<title>` XML field, not free text with a `", by
   Author"` suffix — but I haven't verified that field is clean across all years. Worth a sanity
   check before I'd trust the 75 high-confidence rows.
2. **Does my exact `(regnum, regdate)` join sidestep the "miss is weak evidence" problem you
   flagged?** My matcher never fuzzy-matches on the renewal side — it only needs to find the right
   registration once, then the renewal lookup is a deterministic key match. Want your read on
   whether that actually closes the gap or just moves it.
3. **My candidate set overlaps with the corpus your attribution audit flagged as buggy.** 316 of
   the 337 mismatched rows came from the Open Library sourcing path, which is also where a chunk of
   my 217-book renewal-era candidate set comes from. Can you tell whether any of my 75 matched
   books sit in that mismatched set? If a book's author is wrong, my author-similarity score would
   likely (but not certainly — see below) drop it out of the high-confidence tier, but I haven't
   checked this against your list directly.
4. **Do we merge, keep separate, or pick one?** Mine covers the whole existing corpus but with a
   less precise candidate-selection story; yours is smaller but intentionally curated for
   significance and has real methodology writeups for the failure modes. Different files, so no
   git conflict — but two teammates' independent answers to "was this renewed" is a problem if they
   ever disagree on the same book.

## Where to look

- My script: [`pd_verification/scripts/match_renewals.py`](../pd_verification/scripts/match_renewals.py)
- My output: [`data/pd_verification_inputs.csv`](../data/pd_verification_inputs.csv),
  [`data/pd_verification_renewal_review_queue.csv`](../data/pd_verification_renewal_review_queue.csv)
- Your docs: [`renewal-era-corpus-plan.md`](renewal-era-corpus-plan.md),
  [`dataset-linkage-analysis.md`](dataset-linkage-analysis.md),
  [`corpus-attribution-audit.md`](corpus-attribution-audit.md)
- Radoslav's implementation: PR #14, `book_corpus/scripts/build_corpus_renewal.py`
