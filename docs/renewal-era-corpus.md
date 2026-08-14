# Renewal-era corpus batch — methodology & results

Implements [`renewal-era-corpus-plan.md`](renewal-era-corpus-plan.md) (Ross's proposal to Package 3).
A **proof-of-concept** batch that sources *significant* 1929–1963 novels and discovers their U.S.
copyright status by looking up whether the copyright was **renewed**. It is a separate batch — it does
**not** modify `data/book_corpus.csv` or Package 2's `pd_verification_inputs.csv`.

## Why this exists

The existing corpus is sourced from Gutenberg + Open Library, which only hold works *already believed*
to be public domain. So the verification gate rejects 2 books out of 2,630 and the renewal-era rules
never fire. U.S. works published 1923–1963 had to be **renewed in their 28th year** or they fell into
the public domain — and most weren't. The interesting, adaptable titles nobody realises are free live
here. This batch goes looking for them.

## Sources

| side | source | notes |
|---|---|---|
| **candidates** (significance) | *Publishers Weekly* annual bestseller lists, 1929–1963, via Wikipedia | objectively significant; full of once-popular novels nobody now checks |
| **determination** (the fact) | **Stanford Copyright Renewal Database** — bulk CSV (`20170427-copyright-renewals-records.csv`, ~246k book renewals 1923–1963) | read **locally**, no per-book scraping, no timeout exposure (ISSUE-10) |

The Stanford CRD bulk file is **not committed** (39 MB). Obtain it from the Stanford Copyright Renewal
Database project and pass its path with `--renewals`.

## Method

1. Parse the PW bestseller lists (top *N* per year), collapse same-work duplicates (a title can chart
   in consecutive years) keeping the earliest year.
2. Index every renewal record by article-stripped title and by author word.
3. For each candidate, classify:
   - **renewed** — a same-title (leading article ignored) + same-surname record exists → `renewal_filed=true`.
   - **not renewed** — no such record **and** the author renews *other* works in the CRD (so absence is
     meaningful, not a name we simply can't find) → `renewal_filed=false`.
   - **uncertain** — a same-author record with heavy title overlap exists (needs manual disambiguation),
     **or** the author is absent from the CRD entirely → `renewal_filed` left **blank**. Never guessed.

## Output

- `data/book_corpus_renewal.csv` — the `book_corpus.csv` contract schema. `book_id` uses the existing
  format, author slugged from the `Last, First` form so ids line up with the merged corpus (ISSUE-5).
  `author_death_year` left blank (not needed for the renewal path; not guessed). The renewal
  determination and its source are recorded in `notes`.
- `data/pd_verification_inputs_renewal.csv` — Package 2's supplementary schema, carrying `renewal_filed`
  per book. Kept **separate** from Package 2's own `pd_verification_inputs.csv`; merging is a later,
  separate decision so Package 2's file is never clobbered.

## Results (top 6/yr, 1929–1963)

179 unique titles: **163 renewed · 9 not-renewed (PD candidates) · 7 uncertain.**

That is 16 rows carrying a real renewal signal, versus 2 `not_confirmed` in 2,630 for the whole current
corpus — the thesis fires. All four of the plan's acceptance criteria are met.

## Known limitations (read before trusting a row)

- **`renewal_filed=false` is a fact, not a PD verdict.** PD status also depends on
  `country_of_first_publication`: several PD candidates here are **UK-origin** (Golding, Hilton, Wilkins,
  Spring, Cronin), where non-renewal is likely moot under **URAA** restoration of foreign copyrights.
  This batch deliberately leaves `country_of_first_publication` blank rather than guess; **Package 2's
  rule engine renders the actual verdict.**
- **Periodical/collection nuance.** A book with no separate renewal record may have had its contents
  first published and renewed as periodical pieces (e.g. Salinger). Those surface as PD candidates here
  but may not be free — hence the value of Package 2's independent check.
- **Candidate bias.** Canonical bestsellers skew heavily renewed. A broader significance frame (genre
  fiction, more per year, prize lists) would raise the non-renewal yield.
- **Matching.** Title/author matching is normalized and article-insensitive; the `uncertain` bucket
  exists precisely so an ambiguous case is never asserted as "not renewed."

## Reproduce

```bash
python3 book_corpus/scripts/build_corpus_renewal.py \
    --renewals /path/to/20170427-copyright-renewals-records.csv \
    --max-per-year 6
```
