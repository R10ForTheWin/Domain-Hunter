#!/usr/bin/env python3
"""
Merges the three Book Corpus batches into the final data/book_corpus.csv:
  - data/book_corpus.csv itself (Gutenberg batch -- read first, then overwritten
    at the end with the merged result)
  - data/book_corpus_deathyear.csv (life+70 batch)
  - data/book_corpus_pubyear.csv (-96 publication-year batch, Rado)

Rado's raw file has two known issues (flagged on PR #2, not yet fixed on his
branch as of this merge): book_id uses "First Last" slug order instead of the
"Last, First" order the other two batches use, and a few duplicate
title+author rows exist with conflicting publication years. Both are
corrected on a LOCAL COPY here purely so the merge can proceed -- this does
not touch his branch or his PR. When his fix lands for real, re-running this
script should produce the same result.

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


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fix_rado_pubyear_batch(rows: list[dict]) -> list[dict]:
    """Local-only correction of the two issues flagged on PR #2."""
    from collections import defaultdict

    groups = defaultdict(list)
    for r in rows:
        groups[(r["title"].strip().lower(), r["author"].strip().lower())].append(r)

    fixed = []
    for (title_key, author_key), group in groups.items():
        primary = group[0]
        years = {g["publication_year"] for g in group if g["publication_year"]}
        if len(years) > 1:
            # Conflicting publication years across duplicate records for the
            # same book -- don't guess which is right, blank it and say why.
            pub_year = ""
            note_suffix = f"; publication year conflict across duplicate Open Library records ({', '.join(sorted(years))}), blanked pending manual research"
        else:
            pub_year = primary["publication_year"]
            note_suffix = ""

        author_slug = slugify(primary["author"])  # already "Last, First" in this column
        title_slug = slugify(primary["title"])
        book_id = f"{title_slug}__{author_slug}__{pub_year or 'unk'}"

        fixed.append({
            **primary,
            "book_id": book_id,
            "publication_year": pub_year,
            "notes": primary["notes"] + note_suffix,
        })
    return fixed


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
    pubyear_raw = read_csv(PUBYEAR_PATH)
    pubyear = fix_rado_pubyear_batch(pubyear_raw)

    print(f"Gutenberg: {len(gutenberg)} rows", file=sys.stderr)
    print(f"Death-year: {len(deathyear)} rows", file=sys.stderr)
    print(f"Pub-year (local-fixed): {len(pubyear)} rows (was {len(pubyear_raw)} before dedup)", file=sys.stderr)

    from collections import defaultdict
    groups = defaultdict(list)
    for r in gutenberg + deathyear + pubyear:
        key = (r["title"].strip().lower(), r["author"].strip().lower())
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
        if gap_after > 50 or gap_before > 100:
            reason = (
                f"more than 50 years after death ({death_year})" if gap_after > 50
                else f"more than 100 years before death ({death_year}), implausible for a single lifetime"
            )
            r["notes"] += f"; publication year ({pub_year}) discarded post-merge as implausible ({reason}); needs manual research"
            r["publication_year"] = ""
            r["book_id"] = f"{slugify(r['title'])}__{slugify(r['author'])}__unk"
            implausible_fixed += 1
    if implausible_fixed:
        print(f"Post-merge plausibility pass: blanked {implausible_fixed} implausible publication years", file=sys.stderr)

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
