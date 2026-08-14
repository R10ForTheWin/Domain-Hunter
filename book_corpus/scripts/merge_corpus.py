#!/usr/bin/env python3
"""
Merges the three Book Corpus batches into the final data/book_corpus.csv:
  - data/book_corpus.csv itself (Gutenberg batch -- read first, then overwritten
    at the end with the merged result)
  - data/book_corpus_deathyear.csv (life+70 batch)
  - data/book_corpus_pubyear.csv (-96 publication-year batch, Rado)

Dedup strategy: group by (title, author) case-insensitively across all three
sources. Within a group, keep the most complete row and fill in any blank
fields (author_death_year, publication_year) from whichever other row in the
group has a value. If two sources disagree on a non-blank value, keep the
first and note the conflict rather than silently picking one.
"""
import csv
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

GUTENBERG_PATH = DATA_DIR / "book_corpus_gutenberg.csv"
DEATHYEAR_PATH = DATA_DIR / "book_corpus_deathyear.csv"
PUBYEAR_PATH = DATA_DIR / "book_corpus_pubyear.csv"
OUT_PATH = DATA_DIR / "book_corpus.csv"

# OUT_PATH is intentionally never one of the input paths above -- this script
# was once buggy in a way where re-running it read its own previous output
# back in as if it were the raw Gutenberg batch and merged it a second time.
# Dedup happened to absorb it without changing the final row count, but it's
# not something to rely on. Keep the three raw batches and the merged output
# as strictly separate files.

FIELDNAMES = [
    "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
    "publication_year", "source", "source_url", "language", "notes",
]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+")


def normalize_title_for_dedup(title: str) -> str:
    """Dedup key only, never written to the CSV: strips a leading article
    and collapses whitespace so "The Hound of the Baskervilles" and "Hound
    of the Baskervilles" group as the same work. Found live: two source
    batches disagreed on the leading "The" for the same real book (one
    Gutenberg+OpenLibrary row with a death year, one OpenLibrary-only row
    without), so they merged as two separate books and the same title sat
    at two different ranks on the shortlist.
    """
    text = " ".join(title.strip().lower().split())
    return _LEADING_ARTICLE_RE.sub("", text)


def normalize_author(name: str) -> str:
    """Contract requires 'Last, First' -- the three source batches didn't
    agree (Gutenberg/Wikidata already gave 'Last, First'; the pub-year
    batch gave 'First Last'), so 908 rows were one format and 1,856 were
    the other, with 99 authors appearing as both and getting treated as
    two different people by anything that groups on author. Normalize
    everyone to the same format instead of trusting whatever the source
    happened to use.
    """
    name = name.strip()
    if "," in name:
        return name  # already "Last, First" (or "Last, First Jr." etc.)
    parts = name.split()
    if len(parts) < 2:
        return name  # single-token name (e.g. "Homer", "Voltaire") -- nothing to reorder
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last}, {first}"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge_group(rows: list[dict]) -> dict:
    def completeness(r):
        return sum(1 for f in ("author_death_year", "publication_year") if r.get(f))

    rows_sorted = sorted(rows, key=completeness, reverse=True)
    primary = dict(rows_sorted[0])

    conflict_notes = []
    for field in ("author_death_year", "publication_year"):
        if primary.get(field):
            continue
        for other in rows_sorted[1:]:
            if other.get(field):
                primary[field] = other[field]
                break

    for field in ("author_death_year", "publication_year"):
        values = {r[field] for r in rows if r.get(field)}
        if len(values) > 1:
            conflict_notes.append(f"sources disagree on {field}: {sorted(values)}, kept {primary.get(field)!r}")
            if field == "author_death_year":
                primary["author_death_year_disputed"] = "true"

    sources = sorted({r["source"] for r in rows})
    if len(sources) > 1:
        primary["source"] = "+".join(sources)

    all_notes = [r["notes"] for r in rows if r.get("notes")]
    combined_notes = "; ".join(dict.fromkeys(all_notes + conflict_notes))  # dedup, preserve order
    primary["notes"] = f"merged from {len(rows)} source rows ({'+'.join(sources)}); {combined_notes}"

    title_slug = slugify(primary["title"])
    author_slug = slugify(primary["author"])
    primary["book_id"] = f"{title_slug}__{author_slug}__{primary['publication_year'] or 'unk'}"
    return primary


def main():
    gutenberg = read_csv(GUTENBERG_PATH)
    deathyear = read_csv(DEATHYEAR_PATH)
    pubyear = read_csv(PUBYEAR_PATH)  # PR #2 merged -- Rado's file is correct as-is now

    print(f"Gutenberg: {len(gutenberg)} rows", file=sys.stderr)
    print(f"Death-year: {len(deathyear)} rows", file=sys.stderr)
    print(f"Pub-year: {len(pubyear)} rows", file=sys.stderr)

    all_rows = gutenberg + deathyear + pubyear
    for r in all_rows:
        r["author"] = normalize_author(r["author"])

    from collections import defaultdict
    groups = defaultdict(list)
    for r in all_rows:
        key = (normalize_title_for_dedup(r["title"]), r["author"].strip().lower())
        groups[key].append(r)

    merged_rows = [merge_group(g) for g in groups.values()]

    # Final plausibility pass. Each source batch had its own per-row sanity
    # checks (e.g. the Gutenberg script blanks a pub_year that's too far
    # after the author's death), but merge_group()'s "fill a blank field
    # from another source row" step can silently reintroduce a value one
    # source had already discarded, if another source's row for the same
    # book didn't have the same guard (e.g. Rado's pub-year batch and the
    # death-year batch don't cross-check against each other's rejected
    # values). Re-check plausibility once more on the final merged value.
    implausible_fixed = 0
    for r in merged_rows:
        if not (r["author_death_year"] and r["publication_year"]):
            continue
        death_year = int(r["author_death_year"])
        pub_year = int(r["publication_year"])
        gap_after = pub_year - death_year
        gap_before = death_year - pub_year
        # Per Ross's branch audit (ISSUE-3): any publication_year after the
        # author's death is treated as a reprint/collected-edition date
        # misrecorded as the original -- not just large gaps. This field
        # determines the actual PD date for pre-1978 works, so a wrong
        # value here is a contract violation, not just untidy metadata.
        if gap_after > 0 or gap_before > 100:
            reason = (
                f"after author's death ({death_year}) -- publication_year must be "
                f"the original publication, not a reprint/collected edition (audit ISSUE-3)" if gap_after > 0
                else f"more than 100 years before death ({death_year}), implausible for a single lifetime"
            )
            r["notes"] += f"; publication year ({pub_year}) discarded post-merge as implausible ({reason}); needs manual research"
            r["publication_year"] = ""
            r["book_id"] = f"{slugify(r['title'])}__{slugify(r['author'])}__unk"
            implausible_fixed += 1
    if implausible_fixed:
        print(f"Post-merge plausibility pass: blanked {implausible_fixed} implausible publication years", file=sys.stderr)

    # Disputed-authorship filter. The death-year batch queries Open Library
    # by author name and trusts whatever work titles come back -- but OL
    # work records list every edition's contributors (translators, editors,
    # introduction-writers) as if they were candidate "authors" of separate
    # works. Result: the same real work (same title + same OL source_url)
    # shows up multiple times attributed to unrelated people (e.g.
    # "Adventures of Huckleberry Finn" attributed to Twain, but also to
    # Kipling, Orwell, and 7 others via the same work record). There is no
    # reliable way to algorithmically pick the correct one from this data
    # alone -- per the project's own ground rule (mark uncertain rather
    # than guess), drop every row in a group like this rather than risk
    # shipping a book under the wrong author's name. Found via real output
    # inspection: the #1 shortlisted book was "Titus Andronicus" credited
    # to naturalist John Muir instead of Shakespeare.
    by_work = defaultdict(list)
    for r in merged_rows:
        by_work[(r["title"].strip().lower(), r["source_url"].strip())].append(r)
    disputed_ids = {
        r["book_id"]
        for rows in by_work.values()
        if len(rows) > 1 and len({r["author"] for r in rows}) > 1
        for r in rows
    }
    if disputed_ids:
        before = len(merged_rows)
        merged_rows = [r for r in merged_rows if r["book_id"] not in disputed_ids]
        print(f"Disputed-authorship filter: dropped {before - len(merged_rows)} rows across "
              f"{sum(1 for rows in by_work.values() if len(rows) > 1 and len({r['author'] for r in rows}) > 1)} "
              f"works with conflicting author attributions for the same source record", file=sys.stderr)

    # Resolve any book_id collisions (distinct books that happened to slug identically)
    seen_ids = set()
    for r in merged_rows:
        base = r["book_id"]
        candidate = base
        suffix = 2
        while candidate in seen_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1
        seen_ids.add(candidate)
        r["book_id"] = candidate

    merged_rows.sort(key=lambda r: (r["title"].lower(), r["author"].lower()))

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in merged_rows:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})

    multi_source = sum(1 for r in merged_rows if "+" in r["source"])
    print(f"\nWrote {len(merged_rows)} merged rows to {OUT_PATH}", file=sys.stderr)
    print(f"  {len(gutenberg) + len(deathyear) + len(pubyear)} input rows -> {len(merged_rows)} deduped rows", file=sys.stderr)
    print(f"  {multi_source} rows merged from more than one source", file=sys.stderr)


if __name__ == "__main__":
    main()
