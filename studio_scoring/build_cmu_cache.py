"""One-time (re-run when book_corpus.csv changes) preprocessing: match our corpus against the
CMU Book Summary Dataset (Bamman & Smith 2013, https://www.cs.cmu.edu/~dbamman/booksummaries.html,
16,559 Wikipedia-sourced plot summaries, CC BY-SA 3.0) and write a small local cache of just the
matches, so scoring_agent.py doesn't need the full 17MB dataset at scoring time.

Matching is deliberately conservative (normalized title AND author must both match) to avoid
attaching the wrong book's plot to one of ours -- a false match is worse than no match, per the
same reasoning as the corpus's own author-attribution bug (see mandate_brief.md).

Usage:
    python build_cmu_cache.py
    python build_cmu_cache.py --input ../data/book_corpus.csv --output cmu_summaries.csv
"""

import argparse
import csv
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE_DIR = HERE / ".cmu_cache"
DATASET_URL = "https://www.cs.cmu.edu/~dbamman/data/booksummaries.tar.gz"


def norm_title(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[:;].*\$b.*", "", t)  # strip MARC subfield junk seen in this corpus
    t = re.sub(r"[^a-z0-9 ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def norm_author(a: str) -> str:
    a = a.strip()
    if "," in a:
        last, _, first = a.partition(",")
        a = f"{first.strip()} {last.strip()}"
    a = a.lower()
    a = re.sub(r"[^a-z ]", "", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a


def ensure_dataset() -> Path:
    txt_path = CACHE_DIR / "booksummaries" / "booksummaries.txt"
    if txt_path.exists():
        return txt_path
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tar_path = CACHE_DIR / "booksummaries.tar.gz"
    print(f"Downloading CMU Book Summary Dataset (~17MB) to {tar_path} ...")
    urllib.request.urlretrieve(DATASET_URL, tar_path)
    with tarfile.open(tar_path) as tar:
        tar.extractall(CACHE_DIR)
    tar_path.unlink()
    return txt_path


def load_cmu_index(txt_path: Path) -> dict:
    index = {}
    with open(txt_path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 7:
                continue
            title, author, summary = parts[2], parts[3], parts[6]
            if not summary.strip():
                continue
            index[(norm_title(title), norm_author(author))] = summary.strip()
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(HERE.parent / "data" / "book_corpus.csv"))
    parser.add_argument("--output", default=str(HERE / "cmu_summaries.csv"))
    args = parser.parse_args()

    txt_path = ensure_dataset()
    cmu_index = load_cmu_index(txt_path)
    print(f"CMU dataset: {len(cmu_index)} summaries loaded.")

    with open(args.input, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    matches = []
    for book in books:
        key = (norm_title(book["title"]), norm_author(book["author"]))
        summary = cmu_index.get(key)
        if summary:
            matches.append({"book_id": book["book_id"], "summary": summary})

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["book_id", "summary"])
        writer.writeheader()
        writer.writerows(matches)

    print(f"Matched {len(matches)}/{len(books)} books ({len(matches)/len(books)*100:.1f}%). "
          f"Wrote {args.output}")


if __name__ == "__main__":
    main()
