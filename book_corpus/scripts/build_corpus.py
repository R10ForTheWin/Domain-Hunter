#!/usr/bin/env python3
"""
Builds data/book_corpus.csv (Package 3).

Sources:
  - Gutendex (https://gutendex.com) for the candidate list: title, author,
    author birth/death year. Gutendex mirrors Project Gutenberg's catalog,
    which is the starting point the project plan suggests.
  - Open Library search API for original publication year, since Gutendex
    only has the ebook's *release* date, not the work's original pub year.
    Heuristic: query title+author, take the earliest plausible
    first_publish_year across returned editions. This is an approximation,
    not a verified fact -- rows where it's missing or where the result
    looks unreliable are flagged in `notes` for manual follow-up rather
    than guessed at silently.

This script only assembles candidates. It does not determine public-domain
status -- that's Package 2's independent job.
"""
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

GUTENDEX_URL = "https://gutendex.com/books/"
OPENLIBRARY_URL = "https://openlibrary.org/search.json"
TARGET_COUNT = 500          # candidate books to collect
MAX_GUTENDEX_PAGES = 25     # safety cap
OL_SLEEP_SECONDS = 0.3      # be polite to Open Library
CURRENT_YEAR = 2026

OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "book_corpus.csv"

HEADERS = {"User-Agent": "DomainHuntress-BookCorpus/1.0 (student project; contact: djnurre@gmail.com)"}


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
            time.sleep(1.5 * (attempt + 1))
    raise last_err


def fetch_gutendex_candidates(target_count: int) -> list[dict]:
    candidates = []
    seen_keys = set()
    url = GUTENDEX_URL
    params = {"languages": "en", "sort": "popular"}
    pages = 0

    while url and len(candidates) < target_count and pages < MAX_GUTENDEX_PAGES:
        resp = get_with_retry(url, params=params if pages == 0 else None, headers=HEADERS, timeout=20)
        data = resp.json()
        pages += 1

        for book in data["results"]:
            authors = book.get("authors") or []
            if not authors:
                continue  # skip anonymous/no-author entries -- can't assess PD without an author
            author = authors[0]
            author_name = author.get("name", "").strip()
            if not author_name:
                continue

            title = book["title"].strip()
            key = (title.lower(), author_name.lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)

            candidates.append({
                "title": title,
                "author": author_name,
                "author_birth_year": author.get("birth_year"),
                "author_death_year": author.get("death_year"),
                "gutenberg_id": book["id"],
                "co_authors": len(authors) - 1,
            })

        url = data.get("next")
        params = None  # 'next' already includes query params

    return candidates[:target_count]


def lookup_publication_year(title: str, author: str) -> tuple[str, str]:
    """Returns (publication_year_str, note). Never guesses -- blank + note if unsure."""
    try:
        resp = get_with_retry(
            OPENLIBRARY_URL,
            params={
                "title": title,
                "author": author,
                "fields": "first_publish_year",
                "limit": 50,
            },
            headers=HEADERS,
            timeout=15,
        )
        docs = resp.json().get("docs", [])
    except requests.RequestException as e:
        return "", f"Open Library lookup failed ({e.__class__.__name__}); needs manual research"

    years = [
        d["first_publish_year"] for d in docs
        if isinstance(d.get("first_publish_year"), int)
        and 1450 <= d["first_publish_year"] <= CURRENT_YEAR
    ]
    if not years:
        return "", "publication year not found via Open Library; needs manual research"

    return str(min(years)), "publication year via Open Library (earliest edition found; not independently verified)"


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
    print(f"Fetching candidates from Gutendex (target {TARGET_COUNT})...", file=sys.stderr)
    candidates = fetch_gutendex_candidates(TARGET_COUNT)
    print(f"Got {len(candidates)} unique title/author candidates. Looking up publication years...", file=sys.stderr)

    rows = []
    used_ids: set[str] = set()
    for i, c in enumerate(candidates, 1):
        death_year = c["author_death_year"]

        if death_year is not None and death_year < 1400:
            # Classical/ancient authors (e.g. Homer) predate any real "first
            # publish year" -- the Open Library min-edition heuristic just
            # returns a random modern reprint/translation date and presents
            # it as fact. Don't look it up; flag for manual research instead.
            pub_year, pub_note = "", (
                "classical/ancient work (author died before 1400) -- original "
                "composition predates reliable publication-year records, not "
                "looked up automatically; needs manual research"
            )
        else:
            pub_year, pub_note = lookup_publication_year(c["title"], c["author"])
            time.sleep(OL_SLEEP_SECONDS)

            birth_year = c.get("author_birth_year")
            if pub_year and birth_year is not None and int(pub_year) < birth_year + 5:
                # Sanity check: a publication year before the author was
                # even a plausible age to have written it means Open
                # Library's search matched the wrong book/edition. Don't
                # keep a confidently-wrong year.
                pub_note = (
                    f"Open Library match discarded: returned {pub_year}, "
                    f"which predates author's birth year ({birth_year}) -- "
                    f"likely a mismatched search result; needs manual research"
                )
                pub_year = ""
            elif pub_year and death_year is not None and int(pub_year) > death_year + 5:
                # Same idea in the other direction: a "first publish year"
                # long after the author died is almost always Open Library's
                # earliest-indexed *reprint*, not the original edition.
                pub_note = (
                    f"Open Library match discarded: returned {pub_year}, "
                    f"which is more than 5 years after author's death "
                    f"({death_year}) -- likely an indexed reprint rather than "
                    f"the original edition; needs manual research"
                )
                pub_year = ""

        notes_parts = [pub_note]
        if c["co_authors"]:
            notes_parts.append(f"{c['co_authors']} additional co-author(s) not recorded, primary author only")
        if death_year is None:
            notes_parts.append("author death year unknown (Gutendex has no record)")

        book_id = build_book_id(c["title"], c["author"], pub_year, used_ids)

        rows.append({
            "book_id": book_id,
            "title": c["title"],
            "author": c["author"],
            "author_death_year": death_year if death_year is not None else "",
            "author_death_year_disputed": "false",
            "publication_year": pub_year,
            "source": "gutenberg",
            "source_url": f"https://www.gutenberg.org/ebooks/{c['gutenberg_id']}",
            "language": "en",
            "notes": "; ".join(notes_parts),
        })

        if i % 25 == 0:
            print(f"  {i}/{len(candidates)}", file=sys.stderr)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
        "publication_year", "source", "source_url", "language", "notes",
    ]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    missing_pub_year = sum(1 for r in rows if not r["publication_year"])
    missing_death_year = sum(1 for r in rows if not r["author_death_year"])
    print(f"Wrote {len(rows)} rows to {OUT_PATH}", file=sys.stderr)
    print(f"  missing publication_year: {missing_pub_year}", file=sys.stderr)
    print(f"  missing author_death_year: {missing_death_year}", file=sys.stderr)


if __name__ == "__main__":
    main()
