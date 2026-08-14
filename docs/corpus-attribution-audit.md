# Corpus attribution audit — wrong authors on real books

> ## STATUS: FIXED
>
> DJ fixed the root cause in `0d16072`, *"Fix root cause of author-misattribution bug in the
> death-year corpus batch."* Re-running the verification recipe in this document against the
> corrected corpus:
>
> | | before | after |
> |---|---|---|
> | Corpus rows | 2,630 | 2,251 |
> | Mismatches vs CMU | **90 of 474 (19.0%)** | **38 of 413 (9.2%)** |
> | Titles carrying >1 author | 99 | 26 |
>
> **The real improvement is larger than 9.2% suggests**, because the check has a known false
> positive: it compares by title, so two genuinely different books sharing a title read as a
> mismatch. *Cosmopolis* is Bourget (1893) **and** DeLillo (2003); *Cosmos* is Humboldt **and**
> Sagan. Several other residual rows are CMU records with a blank author field. The remaining 26
> multi-author titles are largely legitimate — many poets published a book called *Poems*.
>
> This document is retained for the record: the diagnosis, the root cause, and the verification
> recipe, which is worth re-running whenever the corpus is rebuilt.

**Originally for:** the AI agents working on Domain Huntress, and their teammates.
**Owner of the fix:** Package 3 (Radoslav + DJ). Nothing in `book_corpus/` was changed here.
**Found by:** Package 1 (Ross), on branch `ross-renewal-corpus`, 2026-08-13.

---

## The symptom

The first shortlist built on real scores put these at ranks 1 and 3:

| rank | title | corpus says | actually |
|---|---|---|---|
| 1 | The Tragedy of Titus Andronicus | **Muir, John** | Shakespeare |
| 3 | The Mysterious Affair at Styles | **Gilman, Charlotte Perkins** | Agatha Christie |

Both trace to `data/book_corpus.csv`, not to the scoring or the shortlist builder. The death years
are wrong too, and confidently sourced — `Q379580` is John Muir the naturalist, `Q287752` is
Charlotte Perkins Gilman. Wikidata was asked about the wrong person and answered correctly.

## How widespread

Two independent measurements.

**Cross-referenced against the CMU Book Summary Corpus** (16,559 books with author metadata), for
corpus titles that appear there:

```
corpus books found in CMU by title : 474
  author agrees                    : 384
  AUTHOR MISMATCH                  :  90   (19.0% of checkable rows)
```

**Titles carrying more than one author inside the corpus itself:**

```
distinct titles                      : 2,384
titles with more than one author     :    99
rows involved                        :   337   (12.8% of the corpus)
```

**Read the 337 carefully — a large share of it is legitimate.** "Poems" appears under 31 different
authors, and that is simply true: many poets published a book called *Poems*. Same for "Essays",
"Letters", anthologies like "Best Russian short stories". Generic titles are supposed to repeat.

The defensible number is **90** — those are distinctive works with a known author, checked against
an independent source. Cases like these are unambiguous:

| title | authors the corpus attaches to it |
|---|---|
| Adventures of Huckleberry Finn | 11, including Andersen, Kipling, Jack London, Wilkie Collins |
| The Adventures of Tom Sawyer | 7, including Orwell, Johanna Spyri, Stevenson |
| Twelfth Night | 7, including Henry Ford, André Gide, John Muir |
| Die Leiden des jungen Werthers | 6, including Thomas Mann, Carlyle |

## Root cause

`book_corpus/scripts/build_corpus_deathyear.py`, the Open Library step.

Its pipeline is:

1. Wikidata SPARQL → authors who died in the target window (this part is sound)
2. **Open Library search → "for each author, look up their books"**, then pair each returned
   `title` with the author name that was searched for

Step 2 never verifies that the returned work's own author field matches the author being searched.
Open Library's search is full-text and fuzzy: querying an author name returns works that *mention*
them, are *about* them, were *translated* or *introduced* by them, appear in the same anthology, or
are simply mis-catalogued. All of those come back as titles, and every one gets stamped with the
searched author's name and their Wikidata death year.

That explains the shape of the damage precisely:

- **316 of the 337 affected rows are `source: openlibrary`** — this batch, not Gutenberg's.
- **Famous titles collect the most wrong authors**, because popular works surface in many
  different authors' search results.
- **The death year is always internally consistent with the wrong author**, because it came from
  Wikidata for the person who was searched.

The script's docstring anticipates a related risk and dismisses it:

> *"a wrong/uncertain publication year from Open Library is a much lower-stakes problem … it's
> just descriptive metadata, not the thing making the PD claim."*

That reasoning is correct about the publication year and does not extend to the title. The title
comes from the same unverified search, and a wrong title/author pair is not descriptive metadata —
it is a different book.

## Why it matters beyond the embarrassment

*The Mysterious Affair at Styles* really is public domain: Christie published it in 1920, so
pub+95 has elapsed. The corpus reached the right answer through Gilman's 1935 death year — right
verdict, wrong reasoning, by luck.

Flip the luck and the same defect ships a copyrighted book to the shortlist. Attach a 1950s title
to a long-dead author and the pipeline will confidently mark it public domain, with a cited
Wikidata ID backing it up. **Every downstream check would pass**, because they all trust
`book_corpus.csv` as the source of truth for who wrote what.

## Suggested fix

In `build_corpus_deathyear.py`, request the `author_name` field from the Open Library search and
**drop any returned work whose author does not match the author being searched for**. The search
already requests `fields: title,first_publish_year,edition_count,key` — adding `author_name` and
filtering on it is a small change at the point where the bad rows are created.

Two things worth doing alongside it:

- **Re-run the corpus and diff.** Some good rows will disappear along with the bad ones; that is
  the correct trade.
- **Watch `book_id` stability.** IDs are built from title+author+year, so corrections will move
  them. That is ISSUE-5's failure mode — anything already keyed to the old IDs needs regenerating
  in the same change.

## Verifying a fix

The CMU cross-reference is the cheapest check and needs no network:

1. Match `book_corpus.csv` titles against the CMU corpus.
2. Compare author surnames.
3. **90 mismatches today. It should approach zero.**

Worth adding to `qa/validate_contracts.py` as a corpus-quality check once the fix lands, so it
cannot regress silently.

## What was not established

- **An overall error rate for the corpus.** 19% is the rate among books that appear in CMU, and
  those skew famous. The true rate across all 2,630 rows could be higher or lower.
- **Whether the Gutenberg-sourced rows are affected.** 21 of 337 came from Gutenberg paths; that
  is a much smaller signal and was not investigated.
- **Whether `build_corpus.py`'s Gutendex path has the same flaw.** It takes `authors[0]` from the
  catalogue record itself rather than from a search, so it looks structurally safer — unverified.
