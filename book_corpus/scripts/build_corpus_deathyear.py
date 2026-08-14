#!/usr/bin/env python3
"""
Builds data/book_corpus_deathyear.csv -- the "life+70" half of the Book Corpus
expansion (DJ's half; Rado is building the "-96 publication year" half
separately into data/book_corpus_pubyear.csv).

Rule: an author's works are public domain once 71 years have passed since
their death (life-of-author + 70 years, entering the public domain on the
following Jan 1). As of {CURRENT_YEAR}, that means authors who died in
{CURRENT_YEAR - 71} or earlier. This is the rule that catches books
published AFTER the -96 cutoff (1930) by long-dead authors -- exactly the
gap the pub-year approach can't reach.

Two-step pipeline:
  1. Wikidata SPARQL: find notable authors (occupation = writer, Q36180)
     who died in the target window, ranked by sitelink count (a rough
     notability proxy -- more Wikipedia language editions = more likely to
     have adaptation-worthy, actually-in-print work).
  2. Open Library search API: for each author, look up their actual books
     (title, first_publish_year, edition_count) to turn "this person is
     PD-eligible" into real book_id rows.

Since PD status here is gated by DEATH YEAR (verified from Wikidata), not
publication year, a wrong/uncertain publication year from Open Library is a
much lower-stakes problem than in the pub-year batch -- it's just
descriptive metadata, not the thing making the PD claim. Still recorded
carefully and never guessed, for consistency with the rest of the corpus.
"""
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

WIKIDATA_URL = "https://query.wikidata.org/sparql"
OPENLIBRARY_URL = "https://openlibrary.org/search.json"
CURRENT_YEAR = 2026
DEATH_YEAR_CUTOFF = CURRENT_YEAR - 71  # 1955: authors who died this year or earlier are PD via life+70
DEATH_YEAR_FLOOR = 1850                 # keep the Wikidata query bounded / avoid ancient noise
MIN_SITELINKS = 3                       # notability floor
TARGET_AUTHORS = 700
WORKS_PER_AUTHOR = 3                    # top N most-edition-count works per author

HEADERS = {"User-Agent": "DomainHuntress-BookCorpus/1.0 (student project; contact: djnurre@gmail.com)"}

OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "book_corpus_deathyear.csv"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def get_with_retry(url, **kwargs):
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def fetch_authors(target_count: int) -> list[dict]:
    query = f"""
    SELECT ?author ?authorLabel ?dod WHERE {{
      ?author wdt:P106 wd:Q36180 .
      ?author wdt:P570 ?dod .
      ?author wikibase:sitelinks ?sitelinks .
      FILTER(YEAR(?dod) >= {DEATH_YEAR_FLOOR} && YEAR(?dod) <= {DEATH_YEAR_CUTOFF})
      FILTER(?sitelinks >= {MIN_SITELINKS})
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {target_count}
    """
    resp = get_with_retry(
        WIKIDATA_URL,
        params={"query": query},
        headers={**HEADERS, "Accept": "application/sparql-results+json"},
        timeout=60,
    )
    authors = []
    for row in resp.json()["results"]["bindings"]:
        name = row["authorLabel"]["value"]
        qid = row["author"]["value"].rsplit("/", 1)[-1]
        if name == qid or re.fullmatch(r"Q\d+", name):
            # No English label available -- Wikidata fell back to the raw
            # entity ID. Not usable as an author name for Open Library
            # cross-referencing or as CSV data, so skip it.
            continue
        dod = row["dod"]["value"]  # e.g. "1955-04-18T00:00:00Z"
        death_year = int(dod[:4])
        authors.append({"name": name, "death_year": death_year, "wikidata_id": qid})
    return authors


def fetch_author_works(author_name: str, limit: int) -> list[dict]:
    try:
        resp = get_with_retry(
            OPENLIBRARY_URL,
            params={
                "author": author_name,
                "language": "eng",
                "sort": "editions",
                "fields": "title,first_publish_year,edition_count,key",
                "limit": limit,
            },
            headers=HEADERS,
            timeout=20,
        )
    except requests.RequestException:
        return []
    return resp.json().get("docs", [])


def build_book_id(title: str, author: str, pub_year: str, used_ids: set[str]) -> str:
    base = f"{slugify(title)}__{slugify(author)}__{pub_year or 'unk'}"
    book_id = base
    suffix = 2
    while book_id in used_ids:
        book_id = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(book_id)
    return book_id


def main():
    print(f"Querying Wikidata for authors who died {DEATH_YEAR_FLOOR}-{DEATH_YEAR_CUTOFF}...", file=sys.stderr)
    authors = fetch_authors(TARGET_AUTHORS)
    print(f"Got {len(authors)} authors. Looking up their works on Open Library...", file=sys.stderr)

    rows = []
    used_ids: set[str] = set()
    seen_book_keys = set()

    for i, author in enumerate(authors, 1):
        works = fetch_author_works(author["name"], WORKS_PER_AUTHOR)
        time.sleep(0.3)

        for w in works:
            title = w.get("title", "").strip()
            if not title:
                continue
            key = (title.lower(), author["name"].lower())
            if key in seen_book_keys:
                continue
            seen_book_keys.add(key)

            pub_year = w.get("first_publish_year")
            pub_year_str = str(pub_year) if isinstance(pub_year, int) else ""
            note = (
                f"author death year from Wikidata ({author['wikidata_id']}); PD via life+70 rule "
                f"(death year {author['death_year']} + 71 <= {CURRENT_YEAR}), independent of "
                f"publication year"
            )
            if not pub_year_str:
                note += "; publication year not available from Open Library"
            elif int(pub_year_str) - author["death_year"] > 50:
                # Almost certainly Open Library indexing a modern reprint/
                # collected edition as "first publish year", not a genuine
                # posthumous first publication decades after death.
                note += (
                    f"; publication year ({pub_year_str}) discarded as implausible "
                    f"(>50 years after author's death, likely a modern reprint/collected "
                    f"edition); needs manual research"
                )
                pub_year_str = ""

            book_id = build_book_id(title, author["name"], pub_year_str, used_ids)
            rows.append({
                "book_id": book_id,
                "title": title,
                "author": author["name"],
                "author_death_year": author["death_year"],
                "author_death_year_disputed": "false",
                "publication_year": pub_year_str,
                "source": "openlibrary",
                "source_url": f"https://openlibrary.org{w['key']}",
                "language": "en",
                "notes": note,
            })

        if i % 50 == 0:
            print(f"  {i}/{len(authors)} authors, {len(rows)} books so far", file=sys.stderr)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
        "publication_year", "source", "source_url", "language", "notes",
    ]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_PATH}", file=sys.stderr)
    print(f"  from {len(authors)} unique authors", file=sys.stderr)


if __name__ == "__main__":
    main()
