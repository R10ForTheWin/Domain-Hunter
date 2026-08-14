#!/usr/bin/env python3
"""
Package 3 — Renewal-era corpus batch (proof of concept)

Implements the plan in docs/renewal-era-corpus-plan.md: source *significant* 1929-1963
novels (not "already free" ones) and discover their U.S. copyright status by looking up
whether the copyright was RENEWED in its 28th year. U.S. works published 1923-1963 that
were never renewed fell into the public domain.

Candidate side (significance, not availability):
  Publishers Weekly annual bestseller lists (via Wikipedia), 1929-1963. Each year's
  top sellers are unambiguously significant, and the lists are full of once-popular
  novels nobody now checks the status of.

Determination side (the fact that can't be derived from metadata):
  The Stanford Copyright Renewal Database (bulk CSV, ~246k book renewals 1923-1963).
  A candidate with a matching renewal record => renewed. No match => not renewed => PD
  candidate. "renewal_filed" is written verbatim; PD status itself is left to Package 2's
  rule engine, which also needs country_of_first_publication (left blank here, never guessed).

Guardrails honored (see the plan, §7):
  * Writes SEPARATE files (data/book_corpus_renewal.csv, data/pd_verification_inputs_renewal.csv).
    Never touches data/book_corpus.csv or Package 2's pd_verification_inputs.csv.
  * book_id uses the existing contract format; author slugged from the "Last, First" form
    so ids line up with the merged corpus (ISSUE-5).
  * The renewal DB is read locally -- no per-book scraping, no timeout exposure (ISSUE-10).
    The only network calls are ~5 Wikipedia page fetches, with a timeout + clear failure.
  * Never guesses: unknown renewal -> flagged, blank rather than invented.

Usage:
  python3 build_corpus_renewal.py --renewals /path/to/stanford-renewals.csv \
      [--max-per-year 6] [--out-dir ../../data]
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

# U.S. renewal rule applies to works published in this window.
YEAR_MIN, YEAR_MAX = 1929, 1963

WIKI_PAGES = [
    "Publishers Weekly list of bestselling novels in the United States in the 1920s",
    "Publishers Weekly list of bestselling novels in the United States in the 1930s",
    "Publishers Weekly list of bestselling novels in the United States in the 1940s",
    "Publishers Weekly list of bestselling novels in the United States in the 1950s",
    "Publishers Weekly list of bestselling novels in the United States in the 1960s",
]

USER_AGENT = "DomainHuntress-Renewal/1.0 (radoslav@neuronicsmedical.ai)"

CORPUS_FIELDS = [
    "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
    "publication_year", "source", "source_url", "language", "notes",
]
PDINPUT_FIELDS = [
    "book_id", "country_of_first_publication", "simultaneous_us_publication",
    "is_anonymous_pseudonymous_or_corporate", "had_copyright_notice_at_publication",
    "renewal_filed", "creation_year", "source", "notes",
]


# ----------------------------- helpers -----------------------------

def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip().replace(" ", "-")


def normalize(text):
    """Loose normalization for fuzzy title/author matching."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(text):
    """normalize() plus dropping a leading article, so 'The Woman of Andros' and
    'Woman of Andros' land in the same bucket."""
    t = normalize(text)
    return re.sub(r"^(the|a|an)\s+", "", t)


def to_last_first(name):
    name = name.strip()
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def surname_of(name):
    name = name.strip()
    return name.split()[-1] if name.split() else name


# ----------------------- candidate sourcing ------------------------

def fetch_wikitext(title):
    params = {"action": "parse", "page": title, "prop": "wikitext",
              "format": "json", "formatversion": "2"}
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("parse", {}).get("wikitext", "")


def clean_wikilink(s):
    """Turn '[[Target|Display]]' / '[[Page]]' / italics into plain text."""
    s = s.strip().strip("'").strip()
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)  # [[t|d]] -> d
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)            # [[x]]   -> x
    s = s.replace("''", "").strip()
    s = re.sub(r"\s*\((?:novel|play|book)\)\s*$", "", s, flags=re.I)  # drop disambig
    return s.strip()


LINE_RE = re.compile(r"^#\s*(?P<title>.+?)\s+by\s+(?P<author>.+?)\s*$")
YEAR_RE = re.compile(r"^==\s*(?P<year>\d{4})\s*==")


def parse_candidates(max_per_year, cache_dir):
    candidates = []
    for page in WIKI_PAGES:
        cache = os.path.join(cache_dir, slugify(page) + ".wikitext") if cache_dir else None
        wt = None
        if cache and os.path.exists(cache):
            wt = open(cache, encoding="utf-8").read()
        if wt is None:
            try:
                wt = fetch_wikitext(page)
                if cache:
                    open(cache, "w", encoding="utf-8").write(wt)
                time.sleep(0.5)
            except Exception as e:
                print(f"  ! could not fetch '{page}': {e}", file=sys.stderr)
                continue
        cur_year, rank = None, 0
        for line in wt.splitlines():
            ym = YEAR_RE.match(line)
            if ym:
                cur_year, rank = int(ym.group("year")), 0
                continue
            if cur_year is None or not (YEAR_MIN <= cur_year <= YEAR_MAX):
                continue
            lm = LINE_RE.match(line)
            if not lm:
                continue
            rank += 1
            if rank > max_per_year:
                continue
            title = clean_wikilink(lm.group("title"))
            author = clean_wikilink(lm.group("author"))
            if title and author:
                candidates.append({"title": title, "author": author,
                                   "year": cur_year, "rank": rank, "list_page": page})
    return candidates


# ------------------------ renewal matching -------------------------

def load_renewals(path):
    """Index renewal records by article-stripped title, and by author word."""
    from collections import defaultdict
    idx = defaultdict(list)             # normalize_title(TITLE) -> [records]
    author_word_idx = defaultdict(list) # each author word -> [records]  (loose match)
    n = 0
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            n += 1
            idx[normalize_title(row.get("TITLE", ""))].append(row)
            for w in set(normalize(row.get("AUTHOR", "")).split()):
                if len(w) >= 3:
                    author_word_idx[w].append(row)
    return idx, author_word_idx, n


def find_renewal(cand, idx, author_word_idx):
    """Return (status, record). status in renewed / possible / not_found.
       renewed  = strong title+author match (safe to call it renewed)
       possible = a same-author record with heavy title overlap exists -> needs manual
                  disambiguation; must NOT be asserted as 'not renewed'
       not_found= nothing plausible for this author+title."""
    tnorm = normalize_title(cand["title"])
    surname = normalize(surname_of(cand["author"]))

    # 1) strong: same article-stripped title, author surname present
    for rec in idx.get(tnorm, []):
        if surname and surname in normalize(rec.get("AUTHOR", "")):
            return "renewed", rec
    # 2) strong: candidate title is a prefix of a longer CRD title (subtitles), same author
    for key, recs in idx.items():
        if key != tnorm and key.startswith(tnorm + " ") and len(tnorm) >= 6:
            for rec in recs:
                if surname and surname in normalize(rec.get("AUTHOR", "")):
                    return "renewed", rec
    # 3) possible: any same-surname record sharing >= half the significant title words
    title_words = {w for w in tnorm.split() if len(w) > 3}
    if surname and title_words:
        seen_ids = set()
        for rec in author_word_idx.get(surname, []):
            if rec["ID"] in seen_ids:
                continue
            seen_ids.add(rec["ID"])
            rec_words = set(normalize(rec.get("TITLE", "")).split())
            if len(title_words & rec_words) >= max(1, len(title_words) // 2):
                return "possible", rec
    return "not_found", None


def author_active_in_renewals(cand, author_word_idx):
    """True if this author renews *anything* in the CRD -> absence of a given title is
    then a meaningful 'not renewed' rather than a name we simply can't find."""
    surname = normalize(surname_of(cand["author"]))
    return bool(surname and len(surname) >= 3 and author_word_idx.get(surname))


# ------------------------------ main -------------------------------

def main():
    ap = argparse.ArgumentParser(description="Build the renewal-era book corpus batch.")
    ap.add_argument("--renewals", required=True, help="path to Stanford CRD bulk CSV")
    ap.add_argument("--max-per-year", type=int, default=6, help="top-N bestsellers per year")
    here = os.path.dirname(__file__)
    ap.add_argument("--out-dir", default=os.path.join(here, "..", "..", "data"))
    ap.add_argument("--cache-dir", default=None, help="optional dir to cache Wikipedia wikitext")
    args = ap.parse_args()

    print(f"Sourcing PW bestsellers {YEAR_MIN}-{YEAR_MAX} (top {args.max_per_year}/yr)...")
    candidates = parse_candidates(args.max_per_year, args.cache_dir)
    # A title can chart in consecutive years -> same work, two rows. Keep the earliest
    # year (closest to original publication) so each work appears once.
    best = {}
    for c in candidates:
        key = (normalize_title(c["title"]), normalize(surname_of(c["author"])))
        if key not in best or c["year"] < best[key]["year"]:
            best[key] = c
    dropped_dupes = len(candidates) - len(best)
    candidates = sorted(best.values(), key=lambda c: (c["year"], c["rank"]))
    print(f"  {len(candidates)} candidates ({dropped_dupes} same-work duplicates collapsed).\n")

    print(f"Loading renewal DB: {args.renewals}")
    idx, author_word_idx, nrec = load_renewals(args.renewals)
    print(f"  {nrec} renewal records indexed.\n")

    corpus_rows, pdinput_rows = [], []
    seen_ids = set()
    counts = {"renewed": 0, "not_renewed": 0, "uncertain": 0, "dup": 0}

    for c in candidates:
        author_lf = to_last_first(c["author"])
        book_id = f"{slugify(c['title'])}__{slugify(author_lf)}__{c['year']}"
        if book_id in seen_ids:
            counts["dup"] += 1
            continue
        seen_ids.add(book_id)

        status, rec = find_renewal(c, idx, author_word_idx)
        if status == "renewed":
            renewal_filed = "true"
            det = (f"renewal FOUND in Stanford CRD (id {rec['ID']}, "
                   f"renewed {rec['DATE']}, class {rec['OCLS']})")
            counts["renewed"] += 1
        elif status == "possible":
            # A same-author record with heavy title overlap exists -> do NOT assert
            # 'not renewed'. Leave renewal_filed blank; flag for manual disambiguation.
            renewal_filed = ""
            det = (f"UNCERTAIN: possible renewal for this author needs manual check "
                   f"(closest CRD id {rec['ID']}, {rec['TITLE'][:40]!r}, renewed {rec['DATE']})")
            counts["uncertain"] += 1
        elif status == "not_found" and author_active_in_renewals(c, author_word_idx):
            # Author renews other works in the CRD, so absence of this title is meaningful.
            renewal_filed = "false"
            det = "no renewal found in Stanford CRD (author renews other works there)"
            counts["not_renewed"] += 1
        else:
            # Author absent from the CRD entirely -> can't confirm matching works; stay uncertain.
            renewal_filed = ""
            det = "UNCERTAIN: author not found in Stanford CRD (cannot confirm a match either way)"
            counts["uncertain"] += 1

        note = (f"significance=PW bestseller #{c['rank']} of {c['year']}; "
                f"renewal_determination: {det}")
        corpus_rows.append({
            "book_id": book_id, "title": c["title"], "author": author_lf,
            "author_death_year": "", "author_death_year_disputed": "false",
            "publication_year": c["year"], "source": "publishers-weekly-bestsellers",
            "source_url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(c["list_page"].replace(" ", "_")),
            "language": "en", "notes": note,
        })
        pdinput_rows.append({
            "book_id": book_id, "country_of_first_publication": "",  # never guessed
            "simultaneous_us_publication": "", "is_anonymous_pseudonymous_or_corporate": "",
            "had_copyright_notice_at_publication": "",
            "renewal_filed": renewal_filed, "creation_year": "",
            "source": "stanford-copyright-renewal-db",
            "notes": det,
        })

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    corpus_path = os.path.join(out_dir, "book_corpus_renewal.csv")
    pdinput_path = os.path.join(out_dir, "pd_verification_inputs_renewal.csv")
    with open(corpus_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CORPUS_FIELDS); w.writeheader(); w.writerows(corpus_rows)
    with open(pdinput_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PDINPUT_FIELDS); w.writeheader(); w.writerows(pdinput_rows)

    total = len(corpus_rows)
    print(f"Wrote {total} rows:")
    print(f"  {corpus_path}")
    print(f"  {pdinput_path}\n")
    print("Renewal findings:")
    print(f"  renewed (found in CRD):        {counts['renewed']}")
    print(f"  NOT renewed -> PD candidate:   {counts['not_renewed']}")
    print(f"  uncertain (manual check):      {counts['uncertain']}")
    if total:
        print(f"  => {100*counts['not_renewed']//total}% likely PD by non-renewal, "
              f"{100*counts['uncertain']//total}% need a manual renewal check")
    if counts["dup"]:
        print(f"  ({counts['dup']} duplicate book_ids skipped)")


if __name__ == "__main__":
    main()
