# Package 3 — Book Corpus & Data Pipeline

**Owner:** Radoslav Raychev · Branch suggestion: `radoslav-book-corpus`

## Goal

Assemble the pool of hundreds of candidate books that everything else runs against. This is the
first thing the other packages depend on — Packages 1, 2, and 4 all read your output.

- Source candidates (e.g. Project Gutenberg's catalog is a good starting point)
- Collect the metadata the other agents need: title, author, author death year, original
  publication year
- Clean it up — consistent format, no duplicates, obvious errors caught
- Output: one clean file (CSV) the rest of the team can build against

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 3.

## Output

- `data/book_corpus.csv` — exact schema, including the `book_id` primary-key format every other
  package joins on, in [`../docs/data-contracts.md`](../docs/data-contracts.md)

## Notes

- `book_id` is minted here and used everywhere downstream — get the slug format right
  (`slugified-title__slugified-author__pub-year`) since Packages 1, 2, 4, and 5 all key off it.
- This package has no upstream dependency — you can start immediately.

## Status: first-pass draft already in progress (DJ)

DJ started this package to unblock everyone else while waiting on things — **treat this as a
draft, not a finished package.** Feel free to take it over, rework it, or throw it out; nothing
here is precious.

What exists so far:

- `scripts/build_corpus.py` — pulls the ~500 most-downloaded English titles from
  [Gutendex](https://gutendex.com) (a JSON API over Project Gutenberg's catalog), then tries to
  find each book's *original* publication year via the Open Library search API (Gutendex only has
  the ebook's release date, not the work's real pub year).
- `data/book_corpus.csv` — the output of one run of that script. 500 rows, 500 unique `book_id`s.

**Known limitations to fix or improve:**

- Only 250/500 (50%) rows have a `publication_year` — the automated Open Library lookup is a
  "take the earliest plausible edition year" heuristic, and it's genuinely unreliable a lot of the
  time (wrong editions, mismatched titles, no data for ancient/classical works). Rather than keep
  a guessed year, rows where the lookup failed or looked implausible (e.g. published before the
  author was born, or decades after they died — both happened before this was caught) are left
  blank with a reason in `notes`. Those 250 gaps need real research, not another automated pass.
- `author_death_year` comes from a single source (Gutendex/Wikidata-derived) with no
  cross-corroboration — `author_death_year_disputed` is always `false` because there's only one
  source to disagree with itself. A real second source should be added, especially since Package 1
  needs solid death years too.
- Only the primary author is captured; co-authored/multi-author works note the omission in
  `notes` but don't record the other authors.
- No manual QA pass yet on titles/authors themselves (e.g. translated-title duplicates, series
  vs. individual volumes) — only exact title+author string matching was used to dedupe.
- Corpus is capped at 500 and skewed toward already-popular titles (`sort=popular` on Gutendex) —
  worth deciding if that's the right sampling strategy or if it should be broadened.

To re-run: `python3 book_corpus/scripts/build_corpus.py` (requires `requests`; regenerates
`data/book_corpus.csv` from scratch, takes a few minutes due to rate-limited API calls).

## Expansion in progress: two more batches, split three ways

The Gutenberg batch above tops out at 500 books and leans heavily on already-popular fiction. To
get "many more" candidates, the corpus is being expanded along the two actual legal routes to
public domain, split across three people so nobody blocks on the others:

| Batch | Rule | Who | Output file |
|---|---|---|---|
| Gutenberg (above) | mixed / Gutendex-curated | DJ (done, first pass) | `data/book_corpus.csv` |
| Publication-year ("-96") | anything published 96+ years ago is PD regardless of death year | Rado | `data/book_corpus_pubyear.csv` |
| Death-year ("life+70") | an author's works are PD once 71 years have passed since their death | DJ | `data/book_corpus_deathyear.csv` |

**Death-year batch — done, first pass** (`scripts/build_corpus_deathyear.py`):

- Source: [Wikidata](https://query.wikidata.org) for notable authors (occupation = writer) who
  died between 1850 and 1955 (i.e. death year + 71 ≤ 2026, so already PD via life+70 right now),
  ranked by sitelink count as a notability proxy — then each author's actual books are looked up
  via the Open Library search API.
- Result: **1,826 books from 691 authors**, 0 duplicate `book_id`s, 0 rows violating the death-year
  cutoff, 0 title/author overlap with the existing Gutenberg batch.
- Because PD eligibility here is gated by *death year* (verified from Wikidata), not publication
  year, a missing/uncertain `publication_year` is much lower-stakes than in the Gutenberg batch —
  it's just descriptive metadata, not what's making the PD claim.
- Known characteristic, not a bug: Wikidata's "writer" occupation is broad — political and
  scientific figures (Einstein, Marx, Gandhi) show up alongside novelists (Tolstoy, Nietzsche).
  Left in deliberately rather than filtered to fiction-only, since their own writings are
  legitimate adaptation source material too (e.g. biopics); Package 4's scoring is where actual
  adaptation fit gets judged, not corpus assembly.
- Known limitation: Open Library's "title" field is the work's original-language title even when
  filtered to `language=eng` editions (e.g. Nietzsche's works show German titles) — the language
  filter only checks that *an* English edition exists, not that the returned title is the English
  one. Not fixed in this pass.
- To re-run: `python3 book_corpus/scripts/build_corpus_deathyear.py` (requires `requests`; takes
  a few minutes).

**Publication-year batch — Rado, in progress.** See his branch / PR for status.

**Not merged yet.** All three files currently coexist unmerged. Once all three batches are in,
they need to be combined into a single deduped `data/book_corpus.csv` (matching on title+author
across sources) — whoever finishes last, flag it in the group chat so that merge happens once,
deliberately, rather than each batch overwriting the others.
