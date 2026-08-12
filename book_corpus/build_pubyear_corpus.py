#!/usr/bin/env python3
"""
Package 3 — Book Corpus (publication-year batch)

Builds data/book_corpus_pubyear.csv from Open Library, using the publication-year
public-domain rule ("-96"): as of 2026, any work first published in 1930 or earlier
(i.e. before 1931) is already public domain in the U.S., regardless of author death year.

Design notes:
  * Source is Open Library's search API with the query first_publish_year:[1500 TO 1930].
    The query itself only returns in-range books, so first_publish_year is TRUSTED
    DIRECTLY -- we never cross-reference or guess a publication year (the bug the first
    Gutenberg batch hit).
  * author_death_year is intentionally left blank: this batch proves PD via publication
    year, so death year is irrelevant here, and the data contract says "blank if unknown
    -- do not guess." The death-year batch covers that dimension; the three source files
    get merged and deduped together at the end.
  * Output matches docs/data-contracts.md exactly and is written to its OWN file so it
    never overwrites the existing book_corpus.csv.

Usage:
    python3 build_pubyear_corpus.py --target 500
"""

import argparse
import csv
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import json

# As of 2026: published <= 1930 (before 1931) => public domain in the U.S.
PD_PUBYEAR_CUTOFF = 1930

API_URL = "https://openlibrary.org/search.json"
USER_AGENT = "DomainHuntress-BookCorpus/1.0 (radoslav@neuronicsmedical.ai)"

# Columns, in the exact order the data contract pins them.
FIELDNAMES = [
    "book_id",
    "title",
    "author",
    "author_death_year",
    "author_death_year_disputed",
    "publication_year",
    "source",
    "source_url",
    "language",
    "notes",
]

# Authors that are institutions / governments / corporate bodies rather than people.
# These produce junk rows like "Laws, etc" by "Great Britain." -- drop them.
INSTITUTION_MARKERS = (
    "great britain",
    "united states",
    "congress",
    "parliament",
    "department",
    "commission",
    "committee",
    "ministry",
    "board of",
    "church of",
    "catholic church",
    "council",
    "association",
    "society for",
    "bureau",
    "office of",
    "corporation",
    "company",
    "assembly",
    "the",  # only when it's the whole name; handled below
)


def slugify(text):
    """Lowercase, strip accents/punctuation, spaces -> hyphens. For book_id parts."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")  # drop accents
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)  # remove punctuation
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "-")


def to_last_first(name):
    """Best-effort 'First Last' -> 'Last, First'. Single-token names pass through."""
    name = name.strip()
    parts = name.split()
    if len(parts) < 2:
        return name  # e.g. "Homer", "Voltaire" -- leave as-is
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last}, {first}"


def looks_institutional(author):
    a = author.strip().lower()
    if a.endswith("."):  # e.g. "Great Britain."
        return True
    for marker in INSTITUTION_MARKERS:
        if marker == "the":
            continue
        if marker in a:
            return True
    return False


def fetch_page(page, per_page):
    params = {
        "q": f"first_publish_year:[1500 TO {PD_PUBYEAR_CUTOFF}]",
        "sort": "editions",  # popularity proxy
        "language": "eng",
        "fields": "key,title,author_name,author_key,first_publish_year,language,edition_count",
        "limit": str(per_page),
        "page": str(page),
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def build_row(doc):
    """Turn one Open Library search doc into a contract row, or None to skip."""
    title = (doc.get("title") or "").strip()
    authors = doc.get("author_name") or []
    year = doc.get("first_publish_year")
    key = doc.get("key") or ""

    if not title or not authors or year is None:
        return None, "missing title/author/year"
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None, "unparseable year"
    if year > PD_PUBYEAR_CUTOFF:
        # Query should prevent this; belt-and-suspenders so a bad row never slips PD.
        return None, "year out of PD range"

    author_raw = authors[0].strip()
    if looks_institutional(author_raw):
        return None, "institutional author"

    title_slug = slugify(title)
    author_slug = slugify(author_raw)
    if not title_slug or not author_slug:
        return None, "empty slug after cleaning"

    book_id = f"{title_slug}__{author_slug}__{year}"
    row = {
        "book_id": book_id,
        "title": title,
        "author": to_last_first(author_raw),
        "author_death_year": "",            # unknown here; do not guess (death-year batch fills this)
        "author_death_year_disputed": "false",
        "publication_year": year,
        "source": "openlibrary",
        "source_url": "https://openlibrary.org" + key,
        "language": "en",
        "notes": "pd_basis=pub_year<=1930",
    }
    return row, None


def main():
    parser = argparse.ArgumentParser(description="Build the publication-year book corpus batch.")
    parser.add_argument("--target", type=int, default=500, help="target number of clean rows")
    parser.add_argument("--per-page", type=int, default=100, help="results per API page (max 100)")
    parser.add_argument("--max-pages", type=int, default=40, help="safety cap on API pages")
    parser.add_argument("--sleep", type=float, default=1.0, help="seconds between API calls (be polite)")
    default_out = os.path.join(os.path.dirname(__file__), "..", "data", "book_corpus_pubyear.csv")
    parser.add_argument("--out", default=default_out, help="output CSV path")
    args = parser.parse_args()

    seen_ids = set()
    rows = []
    dropped = {}  # reason -> count
    page = 1

    print(f"Target: {args.target} clean rows. Query: first_publish_year:[1500 TO {PD_PUBYEAR_CUTOFF}], English, by editions.\n")

    while len(rows) < args.target and page <= args.max_pages:
        try:
            data = fetch_page(page, args.per_page)
        except Exception as e:
            print(f"  ! page {page} fetch failed: {e}", file=sys.stderr)
            break

        docs = data.get("docs", [])
        if not docs:
            print(f"  page {page}: no more results.")
            break

        kept_this_page = 0
        for doc in docs:
            if len(rows) >= args.target:
                break
            row, reason = build_row(doc)
            if row is None:
                dropped[reason] = dropped.get(reason, 0) + 1
                continue
            if row["book_id"] in seen_ids:
                dropped["duplicate book_id"] = dropped.get("duplicate book_id", 0) + 1
                continue
            seen_ids.add(row["book_id"])
            rows.append(row)
            kept_this_page += 1

        print(f"  page {page}: {len(docs)} docs -> kept {kept_this_page} (total {len(rows)})")
        page += 1
        if len(rows) < args.target:
            time.sleep(args.sleep)

    # Write output
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows -> {out_path}")
    if dropped:
        print("Dropped during cleaning:")
        for reason, n in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>6}  {reason}")


if __name__ == "__main__":
    main()
