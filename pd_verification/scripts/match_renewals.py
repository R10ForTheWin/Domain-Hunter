"""Match book_corpus.csv (1923-1963 books) against NYPL's Catalog of Copyright
Entries data to determine `renewal_filed`, and write results into
data/pd_verification_inputs.csv.

## Why this exists

U.S. works first published 1923-1963 needed an affirmative copyright renewal
filed in their 28th year, or they fell into the public domain automatically.
rules.py's renewal-era branch needs to know, per book, whether that renewal
happened -- this script answers that from real historical records instead of
manual lookup.

## Data sources (not vendored here -- download separately, see below)

- Registrations: https://github.com/NYPL/catalog_of_copyright_entries_project
  xml/<year>/*.xml for year in 1923..1963. The full repo is ~2GB (mostly OCR
  scan images under alto/ subdirectories you don't need) -- fetch only the
  xml/<year>/ files, e.g. via the GitHub Contents API, not a full clone.
- Renewals: https://github.com/NYPL/cce-renewals (~110MB, safe to clone in
  full -- `git clone --depth 1`). Tab-delimited, one file per year,
  data/*.tsv.

Point --registrations-dir and --renewals-dir at wherever you put these.

## Method

Two-stage match, because our corpus has no registration ID:

1. Fuzzy-match each corpus book (by normalized title + author) against the
   registration records to find its regnum + regdate. An inverted word
   index blocks candidates before running the expensive character-level
   comparison (difflib), which is why this is fast despite ~700K
   registration records.
2. Exact-match that (regnum, regdate) against the renewals dataset --
   renewals are keyed on exactly that pair (registration numbers restarted
   in the "Third Series", so id alone is ambiguous; NYPL's data is
   specifically formatted to make this join reliable).

Results are split three ways:
- HIGH_CONF_THRESHOLD combined title+author similarity -> written directly
  to data/pd_verification_inputs.csv with source and the matched
  registration ID so it's auditable.
- REVIEW_THRESHOLD..HIGH_CONF_THRESHOLD -> data/pd_verification_renewal_review_queue.csv,
  for a human to confirm or reject.
- Below REVIEW_THRESHOLD, or no word overlap at all -> left untouched.
  Still "uncertain". Never guessed.

## What this does NOT do

Does not determine `country_of_first_publication`. Investigated separately:
the only reliable per-record signal (registration class `AI`, meaning
"confirmed published abroad") has no leverage over the rule engine's
verdict either way -- an explicitly-foreign country and a blank one hit the
identical `is_foreign_or_unknown` branch in rules.py. The signal that WOULD
move a verdict is a confident affirmative "US", and nothing in this dataset
supports that without guessing (a book's *registering publisher's* city is
not the same fact as the book's legal country of first publication -- see
the "New York and London" joint-publication case, which is exactly the
ambiguity 17 U.S.C. 104A / URAA restoration risk turns on). Left for manual
research by design, not an oversight.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import difflib
import glob
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HIGH_CONF_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.75
STOPWORDS = {"the", "a", "an", "of", "and", "to", "in", "on", "for", "is", "with", "by"}
RENEWAL_ERA = (1923, 1963)


def normalize_name(name: str) -> str:
    """'Last, First' and 'First Last' both reduce to the same sorted-token
    form, so either ordering of the same name compares equal -- needed
    because book_corpus.csv itself mixes both conventions (ISSUE-2,
    docs/branch-audit-2026-08-12.md)."""
    name = re.sub(r"[.,;*\[\]()]", " ", name)
    return " ".join(sorted(t.lower() for t in name.split() if t))


def normalize_title(title: str) -> str:
    title = re.sub(r"[.,;:!?'\"\[\]()]", " ", title)
    title = re.sub(r"^(the|a|an)\s+", "", title.strip().lower())
    return re.sub(r"\s+", " ", title).strip()


def significant_words(norm_title: str) -> set:
    return {w for w in norm_title.split() if len(w) >= 4 and w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def parse_registrations(registrations_dir: Path):
    """Returns (registrations list, word_index dict, by_title dict)."""
    registrations = []
    files = sorted(glob.glob(str(registrations_dir / "*.xml")))
    if not files:
        raise SystemExit(f"No XML files found in {registrations_dir} -- see module "
                          f"docstring for where to get them.")
    for path in files:
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            print(f"  PARSE ERROR {path}: {e}", file=sys.stderr)
            continue
        for entry in tree.getroot().iter("copyrightEntry"):
            regnum = entry.get("regnum")
            regdate_el = entry.find("regDate")
            if regnum is None or regdate_el is None or regdate_el.get("date") is None:
                continue
            author_names = [a.text for a in entry.iter("authorName") if a.text]
            title_el = entry.find("title")
            title = "".join(title_el.itertext()).strip() if title_el is not None else ""
            if not title or not author_names:
                continue
            registrations.append((
                normalize_name(author_names[0]), normalize_title(title),
                regnum.replace(" ", ""), regdate_el.get("date"), author_names[0], title,
            ))

    by_title = defaultdict(list)
    word_index = defaultdict(list)
    for idx, r in enumerate(registrations):
        by_title[r[1]].append(r)
        for w in significant_words(r[1]):
            word_index[w].append(idx)
    return registrations, word_index, by_title


def parse_renewals(renewals_dir: Path) -> set:
    files = sorted(glob.glob(str(renewals_dir / "*.tsv")))
    if not files:
        raise SystemExit(f"No TSV files found in {renewals_dir} -- see module "
                          f"docstring for where to get them.")
    renewed = set()
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                oreg, odat = row.get("oreg", "").strip(), row.get("odat", "").strip()
                if oreg and odat:
                    renewed.add((oreg.replace(" ", ""), odat))
    return renewed


def match_book(book, registrations, word_index, by_title):
    """Returns (candidates_used_title_score, best_registration_or_None)."""
    norm_author = normalize_name(book["author"])
    norm_title = normalize_title(book["title"])

    exact = by_title.get(norm_title, [])
    if exact:
        candidates, title_score = exact, 1.0
    else:
        candidate_idxs = set()
        for w in significant_words(norm_title):
            candidate_idxs.update(word_index.get(w, []))
        if not candidate_idxs:
            return None, None
        best, best_score = None, 0.0
        for idx in candidate_idxs:
            r = registrations[idx]
            score = similarity(norm_title, r[1])
            if score > best_score:
                best_score, best = score, r
        candidates = [best] if best and best_score >= REVIEW_THRESHOLD else []
        title_score = best_score if candidates else 0.0

    if not candidates:
        return None, None

    scored = sorted(((similarity(norm_author, c[0]), c) for c in candidates), key=lambda x: -x[0])
    author_score, best_reg = scored[0]
    combined = (title_score + author_score) / 2
    return combined, (best_reg, title_score, author_score)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/book_corpus.csv")
    ap.add_argument("--registrations-dir", required=True, help="dir of xml/<year>/*.xml files (see docstring)")
    ap.add_argument("--renewals-dir", required=True, help="dir of NYPL/cce-renewals data/*.tsv files")
    ap.add_argument("--out-inputs", default="data/pd_verification_inputs.csv")
    ap.add_argument("--out-review", default="data/pd_verification_renewal_review_queue.csv")
    args = ap.parse_args()

    print("Parsing registration records...")
    registrations, word_index, by_title = parse_registrations(Path(args.registrations_dir))
    print(f"  {len(registrations)} registrations, {len(word_index)} indexed words")

    print("Parsing renewal records...")
    renewed = parse_renewals(Path(args.renewals_dir))
    print(f"  {len(renewed)} renewal records")

    corpus = list(csv.DictReader(open(args.corpus, encoding="utf-8")))
    in_era = [r for r in corpus if r.get("publication_year") and r["publication_year"].isdigit()
              and RENEWAL_ERA[0] <= int(r["publication_year"]) <= RENEWAL_ERA[1]]
    print(f"Corpus books in {RENEWAL_ERA[0]}-{RENEWAL_ERA[1]}: {len(in_era)}")

    high_conf, review = [], []
    for book in in_era:
        combined, match = match_book(book, registrations, word_index, by_title)
        if combined is None:
            continue
        best_reg, title_score, author_score = match
        was_renewed = (best_reg[2], best_reg[3]) in renewed
        row = {"book": book, "match": best_reg, "title_score": title_score,
               "author_score": author_score, "combined": combined, "renewed": was_renewed}
        if combined >= HIGH_CONF_THRESHOLD:
            high_conf.append(row)
        elif combined >= REVIEW_THRESHOLD:
            review.append(row)

    print(f"HIGH CONFIDENCE: {len(high_conf)}  REVIEW: {len(review)}  "
          f"NO MATCH (left blank): {len(in_era) - len(high_conf) - len(review)}")

    today = datetime.date.today().isoformat()
    cols = ["book_id", "country_of_first_publication", "simultaneous_us_publication",
            "is_anonymous_pseudonymous_or_corporate", "had_copyright_notice_at_publication",
            "renewal_filed", "creation_year", "source", "notes"]
    with open(args.out_inputs, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in high_conf:
            b, m = row["book"], row["match"]
            w.writerow({
                "book_id": b["book_id"], "country_of_first_publication": "",
                "simultaneous_us_publication": "", "is_anonymous_pseudonymous_or_corporate": "",
                "had_copyright_notice_at_publication": "",
                "renewal_filed": "true" if row["renewed"] else "false",
                "creation_year": "", "source": "nypl-cce-registrations+renewals",
                "notes": f"matched regnum={m[2]} regdate={m[3]} "
                         f"title_score={row['title_score']:.2f} author_score={row['author_score']:.2f} on {today}",
            })
    print(f"Wrote {len(high_conf)} rows to {args.out_inputs}")

    with open(args.out_review, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["book_id", "corpus_title", "corpus_author", "publication_year",
                    "candidate_registration_title", "candidate_registration_author",
                    "regnum", "regdate", "combined_score", "likely_renewed_if_confirmed"])
        for row in review:
            b, m = row["book"], row["match"]
            w.writerow([b["book_id"], b["title"], b["author"], b["publication_year"],
                        m[5], m[4], m[2], m[3], f"{row['combined']:.2f}", row["renewed"]])
    print(f"Wrote {len(review)} rows to {args.out_review}")


if __name__ == "__main__":
    main()
