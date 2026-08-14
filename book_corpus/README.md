# Package 3 — Book Corpus & Data Pipeline

**Owner:** Radoslav Raychev · Branch suggestion: `radoslav-book-corpus`

## Goal

Assemble the pool of candidate books that everything else runs against. This is the first thing
the other packages depend on — Packages 1, 2, and 4 all read the output.

- Source candidates (e.g. Project Gutenberg's catalog is a good starting point)
- Collect the metadata the other agents need: title, author, author death year, original
  publication year
- Clean it up — consistent format, no duplicates, obvious errors caught
- Output: one clean file (CSV) the rest of the team can build against

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 3.

## Output

- `data/book_corpus.csv` — the merged, deduped corpus. Exact schema, including the `book_id`
  primary-key format every other package joins on, in
  [`../docs/data-contracts.md`](../docs/data-contracts.md). **This is the file downstream packages
  should read.**

## Status: merged corpus ready — 2,764 books

This started as DJ's first-pass draft to unblock everyone else, then got split three ways across
DJ and Rado to cover both actual legal routes to public domain (not just Gutenberg's curated,
popularity-skewed catalog), then merged into the final corpus. **Treat all of this as a draft to
improve, not a finished package** — feel free to rework, extend, or replace any of it.

### The three source batches

| Batch | Rule | Built by | Raw output file |
|---|---|---|---|
| Gutenberg | Gutendex-curated candidates, `copyright:false`-only | DJ | `data/book_corpus_gutenberg.csv` (495 rows) |
| Publication-year ("-96") | anything published 96+ years ago is PD regardless of death year | Rado | `data/book_corpus_pubyear.csv` (497 rows, deduped) — PR #2 |
| Death-year ("life+70") | an author's works are PD once 71 years have passed since their death | DJ | `data/book_corpus_deathyear.csv` (1,826 rows) |

**Gutenberg batch** (`scripts/build_corpus.py`): pulls the ~500 most-downloaded English titles
from [Gutendex](https://gutendex.com), then cross-references Open Library for each book's
*original* publication year. Filters out anything Gutendex itself flags `copyright:true` (hosted
with a rights-holder's permission, not because it's actually PD — e.g. a modern translation of an
otherwise-PD original; 5 titles were caught and removed this way, including *Metamorphosis* and
*Twenty Thousand Leagues Under the Seas*, where the specific translations Gutenberg hosts are
still under copyright even though the original works aren't).

**Death-year batch** (`scripts/build_corpus_deathyear.py`): queries
[Wikidata](https://query.wikidata.org) for notable authors (occupation = writer) who died
1850–1955 (already PD via life+70 as of 2026), ranked by sitelink count, then looks up each
author's actual books via Open Library. PD eligibility here is gated by *death year*, not
publication year, so a missing pub year is lower-stakes than in the other batches — it's
descriptive metadata, not what's making the PD claim. Known characteristic, not a bug: Wikidata's
"writer" occupation is broad (Einstein, Marx, and Gandhi show up alongside Tolstoy and Nietzsche)
— left in deliberately since their own writings are legitimate adaptation source material too
(e.g. biopics); Package 4's scoring is where actual adaptation fit gets judged, not corpus
assembly.

**Publication-year batch** (Rado, `book_corpus/build_pubyear_corpus.py` on his branch, PR #2):
queries Open Library directly for `first_publish_year:[1500 TO 1930]`, trusting the query-bound
year rather than cross-referencing (the right call — avoids the bug the Gutenberg batch hit).
Also adds institutional-author filtering (drops things like "Great Britain. Parliament") that the
other two batches don't have.

### The merge (`scripts/merge_corpus.py`)

Combines all three raw batches into `data/book_corpus.csv`, deduping on (title, author)
case-insensitively. Where the same book appears in more than one source, the most complete row
wins and any blank fields get filled in from whichever other row has a value; if sources
genuinely disagree on a value, the row is flagged (`author_death_year_disputed=true` for death
year conflicts, a note for others) rather than silently picking one.

A final plausibility pass runs after merging: any `publication_year` more than 50 years after the
author's death, or more than 100 years before it, gets discarded (blanked + noted) even if it
came from a source batch that didn't itself catch the problem — this matters because merging can
reintroduce a bad value one batch had already correctly discarded, if another source's row for
the same book didn't have the same guard. Caught real examples this way, e.g. "As You Like It"
showing publication year 1734 (Shakespeare died 1616) and "A Portrait of the Artist as a Young
Man" showing 1818 (Joyce wasn't born until 1882) — both from Open Library returning a mismatched
edition/work record.

**Note on Rado's batch:** as of this merge, PR #2 has two open review comments Rado hasn't fixed
yet (book_id name-order convention, a few in-file duplicate titles). The merge script corrects
both **on a local copy only** — it does not touch his branch or PR. Once his real fix lands and
merges, re-running `merge_corpus.py` should produce an equivalent result; if it doesn't, that's
worth a second look.

### Final corpus stats (2,764 rows)

- 0 duplicate `book_id`s, 0 duplicate title+author pairs
- 83% have `author_death_year`, 74% have `publication_year`
- 0 rows with an implausible publication year relative to author death year (checked both
  directions: >50 years after death, >100 years before it)

### Known limitations still open

- No birth-year cross-check for the death-year batch specifically (only the Gutenberg batch fetches
  author birth year) — the post-merge plausibility pass catches the worst offenders via the
  death-year bound instead, but a real birth-year check would be more precise.
- Open Library's "title" field is the work's original-language title even when filtered to
  `language=eng` editions (e.g. some German/Russian titles slip through) — the language filter
  only checks that *an* English edition exists, not that the returned title is the English one.
- Only the primary author is captured for multi-author works; co-authorship is noted in `notes`
  but other authors aren't recorded as separate fields.
- No corroborating second source for most `author_death_year` values (Wikidata for the death-year
  batch, Gutendex for the Gutenberg batch) — `author_death_year_disputed` only trips when two of
  our three *batches* disagree with each other, not from any independent cross-check within a
  single source.
- ~26% of rows still lack a `publication_year` — left blank rather than guessed, per the project's
  own ground rules, but real research would fill in more of these.

### Re-running

Each script can be re-run independently; re-run the merge afterward to regenerate the final file:

```
python3 book_corpus/scripts/build_corpus.py            # -> data/book_corpus_gutenberg.csv
python3 book_corpus/scripts/build_corpus_deathyear.py   # -> data/book_corpus_deathyear.csv
# (Rado's script produces data/book_corpus_pubyear.csv on his branch)
python3 book_corpus/scripts/merge_corpus.py             # -> data/book_corpus.csv (final)
```

All three fetch scripts require `requests` and take a few minutes due to rate-limited API calls.
`merge_corpus.py` is pure local CSV processing and runs instantly, so it's cheap to re-run any
time one of the three sources changes.
