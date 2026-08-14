# Dataset linkage analysis — CMU summaries + copyright renewals

**Status:** feasibility study. **No pipeline file was touched, no dataset was committed.** This
measures whether two external datasets can do what we want before anyone builds against them.

**Run on:** branch `ross-renewal-corpus`, 2026-08-13, against `data/book_corpus.csv` (2,630 rows).

**The headline is a warning, not a green light.** The linkage works. The obvious way to interpret
it is badly wrong, and would have put copyrighted books on a public-domain list.

---

## The two datasets

| | rows | what it gives |
|---|---|---|
| **CMU Book Summary Corpus** | 16,559 | Wikipedia plot summaries + author, publication date, Freebase genres |
| **Stanford Copyright Renewal Records** | 246,449 | US copyright renewals: title, author, original registration date, renewal date |

CMU is CC BY-SA (derived from Wikipedia) — attribution obligations apply, and provenance belongs in
`notes` rather than being presented as ours.

## What CMU could do for us

**Publication spread of the 10,949 CMU books that carry a date:**

| window | books |
|---|---|
| pre-1929 | 1,095 |
| **1929–1963 (renewal era)** | **1,477** |
| 1964–1977 | 1,117 |
| 1978+ | 7,260 |

**All 1,477 renewal-era books have a plot summary.** That is the candidate frame the project has
been missing: books sourced by *cultural significance* (they have Wikipedia articles), in the
window where copyright status is genuinely uncertain, with the content Package 4 needs already
attached.

**Overlap with the existing corpus:**

```
CMU titles also in book_corpus.csv :     439
CMU titles NOT in the corpus       :  16,120
```

So CMU is far more valuable as a **source of new candidates** than as an annotation layer on what
we already have. Our corpus is 91% pre-1929; adding summaries to it mostly enriches books that were
never the problem.

This also bears directly on Package 4. Of 2,523 books scored, **229 used a CMU-sourced summary and
2,294 used one the model recalled from its own knowledge.** Better matching against the full 16,559
is the difference between scores grounded in real content and scores partly resting on invention.

## The renewal question — and the trap

Most US works published 1929–1963 had to be renewed in their 28th year or they fell into the public
domain. So "in the renewal era, no renewal record" looks like it should mean "public domain."

Naive title matching gave:

```
CMU renewal-era books (1929–1963)   : 1,477
  no renewal record found           :   725   (49.1%)
```

**Do not report that number.** Here is what is in it:

> The Hobbit · Waiting for Godot · The Great Divorce · The Myth of Sisyphus · Gaudy Night ·
> Keep the Aspidistra Flying

Every one is unambiguously still in copyright. The 49% is a **measurement of our matcher's failure
rate**, not a discovery.

### Failure 1 — the renewal title field is not a title

Renewal records store titles as registered:

```
"Gaudy night, by Dorothy L. Sayers"        renewed 1963
"The great divorce, by C. S. Lewis"        renewed 1973
"Tunnel in the sky; novel."                renewed 1983
```

Stripping `", by X"` and `"; subtitle"` before comparing recovered 72 books:

```
title matches a renewal record : 824  (55.8%)   — 745 also agree on author
no renewal record found        : 653  (44.2%)
```

Better, and still not the answer.

### Failure 2 — absence means the opposite for foreign works

The residual 653 is dominated by non-US authors: Tolkien, Beckett, Camus, Orwell, Hergé,
Pauline Réage. **A foreign work has no US renewal record because it never needed one** — and the
URAA restored the copyright of foreign works that had lapsed on US formalities.

So for a foreign work, "no renewal found" is evidence it is *still protected*, the exact inverse of
the inference for a US work. Package 2 already models this correctly: its
`foreign-uraa-risk-life70-not-ruled-out` rule and the `country_of_first_publication` column in
`data/pd_verification_inputs.csv` exist for precisely this. Neither dataset supplies that country.

### Failure 3 — a miss is weak evidence even for US works

Heinlein appears three times in the residual (*Methuselah's Children*, *Farmer in the Sky*, *Red
Planet*), and he is American and was well-renewed. Those are more title-variant misses. A renewal
*hit* is strong evidence; a *miss* is only ever "not found," never "not renewed."

## What this means for the build

**Viable, with three conditions.**

1. **Match on title AND author, after normalising the registered-title format.** Author agreement
   already holds on 745 of 824 title matches, so it is a usable second key.
2. **Restrict PD inference to US-published works.** Without country of first publication, a
   no-renewal result is uninterpretable. This is the single biggest blocker, and neither dataset
   solves it — it needs a third source, or manual research on a small set.
3. **Record `no renewal found`, never `not renewed`.** Feed it to Package 2 as a blank
   `renewal_filed`, not `false`. Per `docs/project-plan.md` §5, uncertain is a real answer.

Under those conditions the honest pitch is not "we found 653 free books." It is: *from 1,477
culturally significant mid-century books, we can identify a smaller set where no renewal exists and
US publication is established — books that are public domain for a reason nobody checked.* That set
has not been sized yet, and sizing it requires condition 2.

## Suggested next step

Take a **deliberately small slice** — 100–200 US-published, renewal-era titles where country of
publication can be established — and run the full loop end to end: match, verify with Package 2,
score with Package 4 using the real CMU summary. That produces a number worth presenting and
exercises the verification gate, which currently rejects 2 books out of 2,630.

Scale is not the constraint. Interpretation is.

## Reproducing this

Datasets are in `book data/` locally and are **not committed** — 29 MB of third-party archives.
They should stay out of the repo; if anything is committed later it should be a small derived
subset, with CMU attribution recorded.

## Related

- `docs/renewal-era-corpus-plan.md` — the original proposal, which this study tests
- `docs/corpus-attribution-audit.md` — a separate defect found while running this
- `docs/data-contracts.md` — the `summary` / `subjects` columns, and `pd_verification_inputs.csv`
- `pd_verification/rules.py` — the URAA logic that condition 2 exists to satisfy
