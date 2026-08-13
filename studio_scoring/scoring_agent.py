"""Package 4 scoring agent: scores every book in the corpus against the live A24 mandate
(mandate_live.yaml, produced by collect_madlib.py) using mandate_config.yaml's weights.

Writes data/studio_scores.csv per the schema in docs/data-contracts.md — one row per book_id,
every book scored regardless of PD status (verification is Package 2's job, not this one's).

Requires ANTHROPIC_API_KEY in the environment.

Usage:
    python scoring_agent.py
    python scoring_agent.py --input ../data/book_corpus.csv --output ../data/studio_scores.csv
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml
from anthropic import Anthropic

HERE = Path(__file__).parent

MADLIB_CATEGORIES = [
    "genre_fit",
    "visual_story_adaptability",
    "audience_fit",
    "franchise_potential",
    "budget_scale_fit",
]
ALL_CATEGORIES = MADLIB_CATEGORIES + ["name_recognition"]

SCORE_TOOL = {
    "name": "record_score",
    "description": "Record the A24 studio-fit score for one book, one sub-score per rubric category.",
    "input_schema": {
        "type": "object",
        "properties": {
            **{
                cat: {
                    "type": "object",
                    "properties": {
                        "score": {
                            "type": "number",
                            "description": "0-100 fit score for this category",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "One or two sentences on why this score",
                        },
                    },
                    "required": ["score", "reasoning"],
                }
                for cat in ALL_CATEGORIES
            },
            "overall_reasoning": {
                "type": "string",
                "description": "2-3 sentence summary of the book's overall fit against the mandate",
            },
        },
        "required": ALL_CATEGORIES + ["overall_reasoning"],
    },
}


def build_prompt(book: dict, mandate: dict) -> str:
    blanks = mandate["blanks"]
    return f"""You are scoring a public-domain book for adaptation potential against a live-generated
studio mandate for A24.

MANDATE (generated live from an audience mad-lib): "{mandate['sentence']}"

What each mad-lib blank was scoring for:
- GENRE = "{blanks['GENRE']}" -> genre_fit: how well the book's actual genre matches this
- ADJECTIVE = "{blanks['ADJECTIVE']}" -> visual_story_adaptability: how well the book's tone/style
  matches this mood, and how visually/cinematically adaptable it is
- CHARACTER = "{blanks['CHARACTER']}" -> audience_fit: how well the book's characters/themes would
  land with A24's core 18-34, cinephile, urban/college-town audience, filtered through this
  character type
- VERB = "{blanks['VERB']}" -> franchise_potential: how much sequel/world-building potential the
  book has, filtered through this action
- SETTING = "{blanks['SETTING']}" -> budget_scale_fit: whether adapting the book implies a scale
  consistent with A24's budget range ($15-20M contained films, up to ~$50M for event films),
  filtered through this setting

A sixth category, name_recognition, is NOT from the mad-lib — score it on how well-known this
specific book/author already is to a general audience (a famous classic like Dracula scores high,
an obscure title scores low).

BOOK:
- Title: {book['title']}
- Author: {book['author']}
- Original publication year: {book['publication_year']}
- Notes: {book.get('notes') or '(none)'}

Score all six categories 0-100 and call record_score with your scores and reasoning."""


def score_book(client: Anthropic, model: str, book: dict, mandate: dict) -> dict:
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "record_score"},
        messages=[{"role": "user", "content": build_prompt(book, mandate)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError(f"No tool_use block in response for {book['book_id']}")


def clean_text(value: str) -> str:
    """Occasionally the model double-wraps a reasoning field as a JSON string
    (e.g. '{"overall_reasoning": "..."}') even with a forced tool schema. Unwrap it."""
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict) and len(parsed) == 1:
                return str(next(iter(parsed.values())))
        except json.JSONDecodeError:
            pass
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(HERE / "sample_books.csv"),
                         help="book_corpus.csv-shaped input (default: sample_books.csv test fixture)")
    parser.add_argument("--mandate", default=str(HERE / "mandate_live.yaml"),
                         help="mandate_live.yaml from collect_madlib.py")
    parser.add_argument("--config", default=str(HERE / "mandate_config.yaml"))
    parser.add_argument("--output", default=str(HERE.parent / "data" / "studio_scores.csv"))
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it before running this script.")

    if not Path(args.mandate).exists():
        sys.exit(f"No mandate file at {args.mandate} — run collect_madlib.py first.")

    config = yaml.safe_load(Path(args.config).read_text())
    mandate = yaml.safe_load(Path(args.mandate).read_text())
    weights = config["weights"]

    client = Anthropic()

    with open(args.input, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    rows = []
    for book in books:
        print(f"Scoring {book['title']}...")
        result = score_book(client, args.model, book, mandate)
        total = sum(weights[cat] * result[cat]["score"] for cat in ALL_CATEGORIES)
        row = {
            "book_id": book["book_id"],
            "studio": config["studio"],
            "total_score": round(total, 2),
            "reasoning": clean_text(result["overall_reasoning"]),
        }
        for cat in ALL_CATEGORIES:
            row[f"{cat}_score"] = result[cat]["score"]
            row[f"{cat}_reasoning"] = clean_text(result[cat]["reasoning"])
        rows.append(row)

    fieldnames = ["book_id", "studio", "total_score", "reasoning"] + [
        f"{cat}_{suffix}" for cat in ALL_CATEGORIES for suffix in ("score", "reasoning")
    ]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
