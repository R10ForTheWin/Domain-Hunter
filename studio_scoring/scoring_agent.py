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
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

FIELDNAMES = ["book_id", "studio", "total_score", "reasoning", "book_summary"] + [
    f"{cat}_{suffix}" for cat in ALL_CATEGORIES for suffix in ("score", "reasoning")
]

# The schema is deliberately FLAT (12 primitive fields, not 6 nested {score, reasoning} objects).
# With the nested shape, Haiku frequently dropped out of JSON partway through and emitted a
# different tool-call syntax instead -- a category's value would come back as the literal string
# '\n<parameter name="score">25' and every field after it was lost, leaving 1/6 categories usable
# on roughly half of a 50-book run. Note the leaked parameter name is a bare "score", which only
# existed *inside* the nested objects. Flattening removes that ambiguity entirely; the CSV written
# by build_row() is unchanged either way, so nothing downstream is affected.
SCORE_TOOL = {
    "name": "record_score",
    "description": "Record the A24 studio-fit score for one book, one sub-score per rubric category.",
    "input_schema": {
        "type": "object",
        "properties": {
            "book_summary": {
                "type": "string",
                "description": "What you actually know about this specific book's plot, genre, and "
                                "themes, based on its title and author — 1-3 sentences. If you don't "
                                "confidently recognize this exact title/author, say so explicitly "
                                "(e.g. 'not confidently recognized') instead of guessing or inventing "
                                "a plot. All scores below must be based on this summary, not the bare "
                                "title string.",
            },
            **{
                f"{cat}_score": {
                    "type": "number",
                    "description": f"0-100 fit score for {cat.replace('_', ' ')}",
                }
                for cat in ALL_CATEGORIES
            },
            **{
                f"{cat}_reasoning": {
                    "type": "string",
                    "description": f"One short sentence on why {cat.replace('_', ' ')} scored that "
                                    f"way. Be concise.",
                }
                for cat in ALL_CATEGORIES
            },
            "overall_reasoning": {
                "type": "string",
                "description": "One concise sentence summarizing the book's overall fit against the mandate.",
            },
        },
        "required": (
            ["book_summary"]
            + [f"{cat}_score" for cat in ALL_CATEGORIES]
            + [f"{cat}_reasoning" for cat in ALL_CATEGORIES]
            + ["overall_reasoning"]
        ),
    },
}


MAX_SUMMARY_CHARS = 1000  # longer raw summaries (some CMU entries run 20k+ chars) have been
                          # observed to destabilize the model's structured tool-call output


def truncate_summary(summary: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    if len(summary) <= max_chars:
        return summary
    cut = summary[:max_chars]
    last_period = cut.rfind(". ")  # prefer a clean sentence boundary over a mid-word cut
    if last_period > max_chars * 0.5:
        cut = cut[: last_period + 1]
    return cut.strip() + " [truncated]"


def build_prompt(book: dict, mandate: dict) -> str:
    blanks = mandate["blanks"]
    verified_summary = truncate_summary((book.get("summary") or "").strip())

    if verified_summary:
        grounding = f"""VERIFIED SUMMARY (sourced, not a guess — use this as ground truth for the
book's actual plot/genre/themes): {verified_summary}

Restate this (in your own words, 1-3 sentences) as book_summary, then score all six categories
0-100 against it."""
    else:
        grounding = """No verified summary is available for this book. First fill in book_summary
based on what you actually know about this specific book's plot, genre, and themes from its title
and author — do not guess or invent a plot for a title you don't recognize; say so explicitly
instead (e.g. "not confidently recognized"). Then score all six categories 0-100 against that
summary."""

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
- Original publication year: {book.get('publication_year', '(unknown)')}
- Notes: {book.get('notes') or '(none)'}

Known data issue: this corpus has confirmed author-attribution errors (e.g. some titles are
attached to the wrong author). The title is more reliable than the author field — if they seem to
conflict (e.g. this title is well-known to be written by someone else), trust what you know about
the actual book from its title, note the conflict in book_summary, and score based on the real
book, not a false pairing.

{grounding}

Then call record_score. Keep every reasoning field to one short, concise sentence — no more."""


# Observed live at scale (~50% of a large batch): forced tool-use occasionally emits a category's
# value as a raw fragment of a different tool-call syntax, e.g. '\n<parameter name="score">25',
# instead of {"score": 25, "reasoning": "..."} -- across simple, famous books (Pride and Prejudice,
# A Christmas Carol), so this isn't about content complexity. Retrying the API call for the whole
# book only fixes it about half the time and doubles cost/time for no gain the other half.
# The actual score is sitting right there in the malformed string -- salvage it instead of
# discarding an otherwise-complete response over one bad field.
MALFORMED_SCORE_PATTERN = re.compile(r'<parameter\s+name="score"\s*>\s*(-?\d+(?:\.\d+)?)')


def salvage_category_field(value):
    if isinstance(value, str):
        m = MALFORMED_SCORE_PATTERN.search(value)
        if m:
            return {
                "score": float(m.group(1)),
                "reasoning": "(not provided — recovered from a malformed model response)",
            }
    return value


MIN_USABLE_CATEGORIES = 4  # of 6 -- below this, treat as a bad response worth retrying rather
                           # than silently shipping a "total_score" based on 1-2 categories


def validate_score_result(result: dict) -> dict:
    """Reads the flat tool-call shape ({cat}_score / {cat}_reasoning) and normalizes it into the
    internal {cat: {"score", "reasoning"}} form the rest of this module expects.

    A category that is missing or unusable becomes None and is excluded from the weighted score
    (see build_row's renormalization) rather than failing the whole book; MIN_USABLE_CATEGORIES
    enforces a floor so a mostly-empty response triggers a retry instead of shipping a
    total_score built from one or two fields. The salvage path is kept as a defensive measure for
    the malformed-string case that motivated flattening the schema in the first place."""
    if not isinstance(result, dict):
        raise ValueError(f"expected a dict, got {type(result).__name__}: {result!r}")
    if not isinstance(result.get("book_summary"), str) or not result["book_summary"].strip():
        raise ValueError(f"missing or empty 'book_summary' field: {result.get('book_summary')!r}")
    # overall_reasoning is a nice-to-have summary, not load-bearing scoring data -- fall back to
    # None + a placeholder in build_row rather than failing the whole book over one missing field.
    if not isinstance(result.get("overall_reasoning"), str) or not result["overall_reasoning"].strip():
        result["overall_reasoning"] = None

    usable_count = 0
    for cat in ALL_CATEGORIES:
        score = result.get(f"{cat}_score")
        reasoning = result.get(f"{cat}_reasoning")
        if not isinstance(score, (int, float)):
            salvaged = salvage_category_field(score)
            if isinstance(salvaged, dict) and isinstance(salvaged.get("score"), (int, float)):
                score, reasoning = salvaged["score"], salvaged["reasoning"]
            else:
                result[cat] = None
                continue
        if not isinstance(reasoning, str) or not reasoning.strip():
            reasoning = "(not provided by model)"
        result[cat] = {"score": score, "reasoning": reasoning}
        usable_count += 1

    if usable_count < MIN_USABLE_CATEGORIES:
        raise ValueError(
            f"only {usable_count}/{len(ALL_CATEGORIES)} categories usable "
            f"(need >= {MIN_USABLE_CATEGORIES}) -- response looks truncated/degraded"
        )
    return result


def score_book(client: Anthropic, model: str, book: dict, mandate: dict) -> dict:
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "record_score"},
        messages=[{"role": "user", "content": build_prompt(book, mandate)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return validate_score_result(block.input)
    raise RuntimeError(f"No tool_use block in response for {book['book_id']}")


def score_book_with_retry(client: Anthropic, model: str, book: dict, mandate: dict, attempts: int = 3) -> dict:
    last_error = None
    for attempt in range(attempts):
        try:
            return score_book(client, model, book, mandate)
        except Exception as e:  # noqa: BLE001 - deliberately broad, this is a long unattended batch job
            last_error = e
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise last_error


def build_row(book: dict, studio: str, weights: dict, result: dict) -> dict:
    # A category can be None (validate_score_result gave up salvaging it) -- exclude it from the
    # weighted average and renormalize over whatever categories are actually present, rather than
    # silently treating a missing score as 0 (which would unfairly tank the total).
    present = [cat for cat in ALL_CATEGORIES if result.get(cat) is not None]
    weight_sum = sum(weights[cat] for cat in present)
    total = sum(weights[cat] * result[cat]["score"] for cat in present) / weight_sum
    overall_reasoning = (
        clean_text(result["overall_reasoning"]) if result.get("overall_reasoning") is not None
        else "(overall reasoning not provided by model — see per-category reasoning columns)"
    )
    row = {
        "book_id": book["book_id"],
        "studio": studio,
        "total_score": round(total, 2),
        "reasoning": overall_reasoning,
        "book_summary": clean_text(result["book_summary"]),
    }
    for cat in ALL_CATEGORIES:
        if result.get(cat) is not None:
            row[f"{cat}_score"] = result[cat]["score"]
            row[f"{cat}_reasoning"] = clean_text(result[cat]["reasoning"])
        else:
            row[f"{cat}_score"] = ""
            row[f"{cat}_reasoning"] = "(not provided by model)"
    return row


def with_retry(fn, attempts: int = 6, base_delay: int = 10):
    """Retry a zero-arg callable through transient errors (e.g. a WiFi blip during a long
    batch poll loop) with linear backoff, instead of crashing a job that may run for a while."""
    last_error = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - network/API errors of any kind are worth retrying here
            last_error = e
            if attempt < attempts - 1:
                delay = base_delay * (attempt + 1)
                print(f"  (transient error: {e}; retrying in {delay}s)")
                time.sleep(delay)
    raise last_error


def run_live(client: Anthropic, model: str, books: list, mandate: dict, weights: dict,
             studio: str, writer, out_file, workers: int, write_lock: threading.Lock,
             label: str = "scored") -> list:
    """Score books via live threaded calls (score_book_with_retry already retries transient and
    malformed-shape failures 3x). Returns list of (book_id, error) failures."""
    total = len(books)
    completed = 0
    failures = []

    def process(book):
        nonlocal completed
        try:
            result = score_book_with_retry(client, model, book, mandate)
            row = build_row(book, studio, weights, result)
            with write_lock:
                writer.writerow(row)
                out_file.flush()
                completed += 1
                print(f"[{completed}/{total}] {label}: {book['title']}")
        except Exception as e:  # noqa: BLE001 - log and keep going, don't lose the rest of the batch
            with write_lock:
                completed += 1
                failures.append((book["book_id"], str(e)))
                print(f"[{completed}/{total}] FAILED: {book['title']} ({e})")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process, book) for book in books]
        for f in as_completed(futures):
            f.result()  # re-raise unexpected errors from process() itself, if any

    return failures


def manifest_path_for(output_path: Path) -> Path:
    return output_path.with_name(output_path.stem + "_batches.json")


def save_batch_manifest(output_path: Path, batch_id: str, id_to_book: dict) -> None:
    """Record exactly which book_id was assigned to which custom_id at submission time, so a
    later --resume-batch can reattach correctly even if the local 'remaining' list has since
    changed (e.g. because some books got scored in the meantime)."""
    path = manifest_path_for(output_path)
    data = json.loads(path.read_text()) if path.exists() else {}
    data[batch_id] = {cid: book["book_id"] for cid, book in id_to_book.items()}
    path.write_text(json.dumps(data))


def load_batch_manifest(output_path: Path, batch_id: str) -> dict:
    path = manifest_path_for(output_path)
    if not path.exists():
        return None
    return json.loads(path.read_text()).get(batch_id)


def run_batch(client: Anthropic, model: str, remaining: list, mandate: dict, weights: dict,
              studio: str, writer, out_file, poll_interval: int, resume_batch_id: str = None) -> list:
    """Score books via the Message Batches API (50% cheaper, async). Returns list of
    (book_id, error) failures. Writes successes to `writer`/`out_file` as they come back.

    If resume_batch_id is given, skips submitting a new batch and polls/collects that existing
    one instead — for recovering from a local crash without resubmitting (and re-paying for)
    work already in flight. Reattaches using the manifest saved at submission time (NOT the
    current `remaining` list, which may have drifted if anything got scored in the meantime)."""
    output_path = Path(out_file.name)
    id_to_book = {f"b{i}": book for i, book in enumerate(remaining)}

    if resume_batch_id:
        batch_id = resume_batch_id
        manifest = load_batch_manifest(output_path, batch_id)
        if manifest is None:
            sys.exit(
                f"No manifest found for batch {batch_id} at {manifest_path_for(output_path)}. "
                f"Can't safely reattach without risking book_id misattribution — the current "
                f"book list may not match what was actually submitted. If you're certain no "
                f"books were scored between submitting this batch and now, you can manually "
                f"reconstruct id_to_book, but that's not done automatically."
            )
        id_to_book = {cid: {"book_id": bid} for cid, bid in manifest.items()}
        print(f"Resuming existing batch {batch_id} using saved manifest ({len(id_to_book)} requests).")
    else:
        requests = [
            {
                "custom_id": cid,
                "params": {
                    "model": model,
                    "max_tokens": 2048,
                    "tools": [SCORE_TOOL],
                    "tool_choice": {"type": "tool", "name": "record_score"},
                    "messages": [{"role": "user", "content": build_prompt(book, mandate)}],
                },
            }
            for cid, book in id_to_book.items()
        ]
        batch = with_retry(lambda: client.messages.batches.create(requests=requests))
        batch_id = batch.id
        save_batch_manifest(output_path, batch_id, id_to_book)
        print(f"Submitted batch {batch_id} with {len(requests)} requests.")
        print(f"  If this script gets interrupted, re-run with --resume-batch {batch_id} to pick "
              f"up this same batch instead of submitting (and paying for) a new one.")

    while True:
        batch = with_retry(lambda: client.messages.batches.retrieve(batch_id))
        c = batch.request_counts
        print(f"  status={batch.processing_status} "
              f"succeeded={c.succeeded} errored={c.errored} processing={c.processing} "
              f"canceled={c.canceled} expired={c.expired}")
        if batch.processing_status == "ended":
            break
        time.sleep(poll_interval)

    results = with_retry(lambda: list(client.messages.batches.results(batch_id)))
    already_written = load_done_ids(output_path)  # re-check: a prior crash may have written some of these already

    failures = []
    for item in results:
        book = id_to_book[item.custom_id]
        if book["book_id"] in already_written:
            continue
        if item.result.type == "succeeded":
            tool_input = None
            for block in item.result.message.content:
                if block.type == "tool_use":
                    tool_input = block.input
                    break
            if tool_input is None:
                failures.append((book["book_id"], "no tool_use block in batch result"))
                continue
            try:
                tool_input = validate_score_result(tool_input)
            except ValueError as e:
                failures.append((book["book_id"], f"malformed model response: {e}"))
                continue
            row = build_row(book, studio, weights, tool_input)
            writer.writerow(row)
        else:
            failures.append((book["book_id"], f"{item.result.type}: {getattr(item.result, 'error', '')}"))
    out_file.flush()
    return failures


def load_summary_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["book_id"]: row["summary"] for row in csv.DictReader(f)}


def enrich_with_summaries(books: list, cache: dict) -> None:
    """Fill in book['summary'] from the CMU cache, but never overwrite a real summary already
    present in book_corpus.csv itself (once Radoslav's package supplies that column, it wins)."""
    for book in books:
        if not (book.get("summary") or "").strip():
            cached = cache.get(book["book_id"])
            if cached:
                book["summary"] = cached


def load_done_ids(output_path: Path) -> set:
    if not output_path.exists():
        return set()
    with open(output_path, newline="", encoding="utf-8") as f:
        return {row["book_id"] for row in csv.DictReader(f)}


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
    parser.add_argument("--workers", type=int, default=8,
                         help="concurrent API calls (default 8)")
    parser.add_argument("--limit", type=int, default=None,
                         help="only score the first N remaining books (for a quick test run)")
    parser.add_argument("--batch", action="store_true",
                         help="use the Message Batches API (50%% cheaper, async, no live progress) "
                              "instead of live threaded calls — recommended for large runs")
    parser.add_argument("--poll-interval", type=int, default=30,
                         help="seconds between batch status checks (--batch mode only)")
    parser.add_argument("--fresh", action="store_true",
                         help="delete any existing output for this --output path before scoring, "
                              "so every book is re-scored. Use this for a live demo re-run: "
                              "without it, resume logic sees the previous run's rows and skips "
                              "every book, producing no new scores.")
    parser.add_argument("--resume-batch", default=None,
                         help="an existing batch ID to resume polling/collecting instead of "
                              "submitting a new batch — use this if scoring_agent.py crashed "
                              "after submission (see the 'Submitted batch ...' line it printed). "
                              "Only valid with the same --input/--limit as the original run.")
    parser.add_argument("--summary-cache", default=str(HERE / "cmu_summaries.csv"),
                         help="book_id -> real summary lookup from build_cmu_cache.py, used to "
                              "ground scoring instead of the model's own recall where available")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it before running this script.")

    if not Path(args.mandate).exists():
        sys.exit(f"No mandate file at {args.mandate} — run collect_madlib.py first.")

    config = yaml.safe_load(Path(args.config).read_text())
    mandate = yaml.safe_load(Path(args.mandate).read_text())
    weights = config["weights"]
    studio = config["studio"]

    client = Anthropic()

    with open(args.input, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    summary_cache = load_summary_cache(Path(args.summary_cache))
    enrich_with_summaries(books, summary_cache)
    if summary_cache:
        grounded = sum(1 for b in books if (b.get("summary") or "").strip())
        print(f"Summary grounding: {grounded}/{len(books)} books have a verified summary "
              f"({len(summary_cache)} available in {args.summary_cache}).")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.fresh:
        for stale in (output_path, manifest_path_for(output_path),
                       output_path.with_name(output_path.stem + "_failures.txt")):
            if stale.exists():
                stale.unlink()
                print(f"--fresh: removed {stale.name}")

    done_ids = load_done_ids(output_path)
    remaining = [b for b in books if b["book_id"] not in done_ids]
    if done_ids:
        print(f"Resuming: {len(done_ids)} already scored, {len(remaining)} remaining.")
    if args.limit:
        remaining = remaining[: args.limit]

    write_header = not output_path.exists()
    out_file = open(output_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_file, fieldnames=FIELDNAMES)
    if write_header:
        writer.writeheader()
        out_file.flush()

    total = len(remaining)
    write_lock = threading.Lock()
    failures = []

    if args.batch:
        try:
            failures = run_batch(client, args.model, remaining, mandate, weights, studio,
                                  writer, out_file, args.poll_interval, args.resume_batch)

            # validate_score_result() already salvages the common malformed-shape case (a category
            # field as a raw '<parameter name="score">N' string), so most of these are now handled
            # without any extra API call. What's left here is the rarer case where a field is
            # malformed in some other, unsalvageable way -- worth one live retry before giving up,
            # since that's at least a different sample from the model.
            retryable = [(bid, err) for bid, err in failures if "malformed model response" in err]
            if retryable:
                print(f"\n{len(retryable)} batch results failed validation even after salvage — "
                      f"retrying those live...")
                book_by_id = {b["book_id"]: b for b in remaining}
                retry_books = [book_by_id[bid] for bid, _ in retryable if bid in book_by_id]
                still_failed = run_live(client, args.model, retry_books, mandate, weights, studio,
                                         writer, out_file, args.workers, write_lock,
                                         label="recovered")
                non_retryable = [f for f in failures if "malformed model response" not in f[1]]
                failures = non_retryable + still_failed
                print(f"Live retry recovered {len(retryable) - len(still_failed)}/{len(retryable)}.")
        finally:
            out_file.close()
    else:
        try:
            failures = run_live(client, args.model, remaining, mandate, weights, studio,
                                 writer, out_file, args.workers, write_lock)
        finally:
            out_file.close()

    print(f"\nDone. {total - len(failures)} scored, {len(failures)} failed, written to {output_path}")
    if failures:
        failures_path = output_path.with_name(output_path.stem + "_failures.txt")
        failures_path.write_text("\n".join(f"{bid}\t{err}" for bid, err in failures))
        print(f"Failed book_ids logged to {failures_path} — re-run this script to retry them "
              f"(already-scored books are skipped automatically).")


if __name__ == "__main__":
    main()
