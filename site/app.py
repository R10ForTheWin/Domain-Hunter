"""
Domain Huntress — live demo site.

Reads the pipeline's real output files (starting with the book corpus; wires
in PD verification / scoring / shortlist as those packages land) and renders
a dashboard for showing the project to class. No database -- everything is
computed from the CSVs already checked into the repo.
"""
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCORING_MODEL = "claude-haiku-4-5-20251001"

from flask import Flask, render_template, request

app = Flask(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
# Normal case: data/ lives one level up, as a sibling of site/ (true in git
# checkouts and in a real GitHub-linked Railway deploy, which uploads the
# whole repo and just changes the working directory for build/start).
# Fallback: a "railway up" CLI deploy only uploads site/'s own contents, so
# if a local site/data/ snapshot exists (bundled in for that kind of
# deploy), prefer it over a ../data/ that won't exist in that container.
_LOCAL_DATA = Path(__file__).resolve().parent / "data"
DATA_DIR = _LOCAL_DATA if _LOCAL_DATA.exists() else REPO_ROOT / "data"

# Same "repo root may or may not actually be there" reality as DATA_DIR
# above applies to importing the sibling pd_verification/ package (Package
# 2) for the real public-domain validator on the /producers page. Degrade
# gracefully instead of crashing the whole site if it's missing.
# This exact gotcha (railway up only uploads site/'s own contents) bit
# data/ and studio_scoring/ too -- both got a local-bundle fallback:
# this one never did, so the live validator silently never worked in
# production until caught by testing the deployed site directly.
_LOCAL_PD_VERIFICATION = Path(__file__).resolve().parent / "pd_verification"
_IMPORT_ROOT = _LOCAL_PD_VERIFICATION.parent if _LOCAL_PD_VERIFICATION.exists() else REPO_ROOT
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))
try:
    from pd_verification.public_status import check_book as _check_book
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False

    def _check_book(*_args, **_kwargs):
        return {"status": "error", "message": "The validator isn't available on this deploy."}

# Same sibling-import situation for studio_scoring/ (Package 4), used by the live mandate demo
# on /networks. Needs ANTHROPIC_API_KEY in the server environment to actually score -- absent
# that, the page falls back to showing the committed results instead of offering the live form.
_LOCAL_STUDIO_SCORING = Path(__file__).resolve().parent / "studio_scoring"
_SCORING_ROOT = _LOCAL_STUDIO_SCORING.parent if _LOCAL_STUDIO_SCORING.exists() else REPO_ROOT
if str(_SCORING_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCORING_ROOT))
try:
    from studio_scoring import scoring_agent as _scoring
    from studio_scoring import collect_mandate_freeform as _freeform
    SCORING_AVAILABLE = True
except ImportError:
    _scoring = None
    _freeform = None
    SCORING_AVAILABLE = False

# Stage status is maintained by hand here (mirrors the team status update) --
# there's no automated way to know "is Chantell done with scoring yet", so
# this just needs updating as packages land. Keep it short and factual.
STAGES = [
    {"n": 1, "name": "Forward-Looking PD Calendar", "owner": "Ross", "status": "done"},
    {"n": 2, "name": "PD Verification Agent", "owner": "Jason Brown", "status": "done"},
    {"n": 3, "name": "Book Corpus & Data Pipeline", "owner": "Radoslav Raychev", "status": "done"},
    {"n": 4, "name": "Studio Mandate Research & Scoring", "owner": "Chantell Ferrell", "status": "ongoing"},
    {"n": 5, "name": "Shortlist & Output", "owner": "Luis R.", "status": "ongoing"},
    {"n": 6, "name": "Infra, QA & Docs", "owner": "DJ", "status": "ongoing"},
]


def load_corpus_rows():
    path = DATA_DIR / "book_corpus.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_corpus_stats():
    rows = load_corpus_rows()
    if not rows:
        return None

    total = len(rows)
    has_death = sum(1 for r in rows if r.get("author_death_year"))
    has_pub = sum(1 for r in rows if r.get("publication_year"))

    sources = {}
    for r in rows:
        s = r.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1

    # A small, varied sample for display -- every Nth row rather than just
    # the first few, so it doesn't look like one source dominates the preview.
    sample = rows[:: max(1, total // 8)][:8] if total else []

    return {
        "total": total,
        "has_death_pct": round(has_death / total * 100) if total else 0,
        "has_pub_pct": round(has_pub / total * 100) if total else 0,
        "sources": sorted(sources.items(), key=lambda kv: -kv[1]),
        "sample": sample,
    }


def load_shortlist():
    path = DATA_DIR / "shortlist.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_top_scores(limit=10):
    """Highest-scoring books from Package 4's scoring run, for /networks.

    studio_scores.csv holds a score per book_id but not the title/author, so
    this joins against book_corpus.csv the same way Package 5 does. Returns
    None when there is no scoring output yet, so the page can say so plainly
    rather than rendering an empty table.
    """
    # Prefer a live-demo run (the 50-book demo_pool.csv, scored on stage against whatever
    # mandate the audience just generated) over the full-corpus batch run. Falls back to the
    # full run so the page still shows real results when no demo has been run.
    demo_path = DATA_DIR / "studio_scores_demo.csv"
    path = demo_path if demo_path.exists() else DATA_DIR / "studio_scores.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    def _score(row):
        try:
            return float(row.get("total_score") or 0)
        except (TypeError, ValueError):
            return 0.0

    corpus = {b.get("book_id"): b for b in load_corpus_rows()}
    rows.sort(key=_score, reverse=True)
    top = []
    for row in rows[:limit]:
        book = corpus.get(row.get("book_id"), {})
        top.append({
            "title": book.get("title") or row.get("book_id", ""),
            "author": book.get("author", ""),
            "score": round(_score(row)),
            "reasoning": row.get("reasoning", ""),
        })
    return top


def _demo_pool_path():
    local = Path(__file__).resolve().parent / "studio_scoring" / "demo_pool.csv"
    return local if local.exists() else REPO_ROOT / "studio_scoring" / "demo_pool.csv"


def scoring_ready():
    """Live scoring needs the package importable, an API key, and the demo pool present."""
    return bool(
        SCORING_AVAILABLE
        and os.environ.get("ANTHROPIC_API_KEY")
        and _demo_pool_path().exists()
    )


def build_mandate_from_form(form):
    """Turn either intake method's form input into the mandate shape scoring_agent expects.

    Mad-lib needs no model call (the five blanks are already the answers); free-form needs one
    quick call to map prose onto the same five slots. Returns (mandate, error_message).
    """
    template_path = _demo_pool_path().parent / "madlib_template.yaml"
    template = _scoring.yaml.safe_load(template_path.read_text(encoding="utf-8"))
    method = form.get("method", "madlib")

    if method == "freeform":
        text = (form.get("freeform_text") or "").strip()
        if not text:
            return None, "Describe what you're looking for first."
        try:
            client = _scoring.Anthropic()
            blanks = _freeform.validate_blanks(
                _freeform.extract_blanks(client, SCORING_MODEL, text)
            )
        except Exception as exc:  # noqa: BLE001 - surface any API/parse failure to the page
            return None, f"Couldn't read that mandate: {exc}"
        raw_input_text = text
    else:
        blanks = {k: (form.get(k) or "").strip() for k in _freeform.BLANK_KEYS}
        missing = [k for k, v in blanks.items() if not v]
        if missing:
            return None, "Fill in all five blanks: " + ", ".join(m.lower() for m in missing)
        raw_input_text = None

    return {
        "sentence": template["sentence"].format(**blanks),
        "blanks": blanks,
        "source": method,
        "raw_input": raw_input_text,
    }, None


def score_demo_pool(mandate, limit=10):
    """Score the 50-book demo pool against a live mandate and return the top matches.

    Deliberately in-memory rather than writing a CSV: this is a live demo path, and the
    scoring agent's resume logic would otherwise skip every book on a second run.
    """
    with _demo_pool_path().open(newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))
    cache = _scoring.load_summary_cache(_demo_pool_path().parent / "cmu_summaries.csv")
    _scoring.enrich_with_summaries(books, cache)

    cfg = load_mandate_config() or {"studio": "A24", "weights": []}
    weights = dict(cfg["weights"])
    client = _scoring.Anthropic()

    rows, failures = [], 0
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {
            pool.submit(_scoring.score_book_with_retry, client, SCORING_MODEL, book, mandate): book
            for book in books
        }
        for fut in as_completed(futures):
            book = futures[fut]
            try:
                rows.append(_scoring.build_row(book, cfg["studio"], weights, fut.result()))
            except Exception:  # noqa: BLE001 - one bad book shouldn't sink the demo
                failures += 1

    titles = {b["book_id"]: b for b in books}
    rows.sort(key=lambda r: r.get("total_score") or 0, reverse=True)
    top = [
        {
            "title": titles.get(r["book_id"], {}).get("title") or r["book_id"],
            "score": round(float(r.get("total_score") or 0)),
            "reasoning": r.get("reasoning", ""),
        }
        for r in rows[:limit]
    ]
    return top, len(rows), failures


def load_mandate_config():
    """Tiny hand-rolled parser for studio_scoring/mandate_config.yaml -- the
    file is a simple flat "key: value" + one nested "weights:" block, so a
    real YAML dependency isn't worth adding just for this one read-only file.
    """
    # Same "railway up only uploads site/'s own contents" reality as
    # DATA_DIR above -- studio_scoring/ is a sibling of site/, so it never
    # ships in a CLI deploy unless a local copy is bundled into site/ too.
    _local = Path(__file__).resolve().parent / "studio_scoring" / "mandate_config.yaml"
    path = _local if _local.exists() else REPO_ROOT / "studio_scoring" / "mandate_config.yaml"
    if not path.exists():
        return None

    studio = None
    weights = {}
    in_weights = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        if stripped.startswith("studio:"):
            studio = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.strip() == "weights:":
            in_weights = True
        elif in_weights and line.startswith((" ", "\t")) and ":" in stripped:
            key, val = stripped.split(":", 1)
            try:
                weights[key.strip()] = float(val.strip())
            except ValueError:
                pass
        elif in_weights and not line.startswith((" ", "\t")):
            in_weights = False

    if not studio:
        return None
    return {"studio": studio, "weights": sorted(weights.items(), key=lambda kv: -kv[1])}


def load_pd_calendar():
    path = DATA_DIR / "pd_calendar.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    by_year = {}
    for r in rows:
        year = (r.get("pd_date") or "")[:4]
        if not year:
            continue
        by_year.setdefault(year, []).append(r)
    return sorted(by_year.items())


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/status")
def status():
    return render_template(
        "status.html",
        stages=STAGES,
        corpus=load_corpus_stats(),
        shortlist=load_shortlist(),
    )


VALIDATOR_IDENTIFIER_TYPES = {"book_name", "isbn", "gutenberg_id", "oclc"}


@app.route("/producers")
def producers():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        q_lower = query.lower()
        results = [r for r in load_corpus_rows() if q_lower in r["title"].lower()][:25]

    # The actual PD Verification agent (Package 2) -- three separate
    # fields on the form (book name / ISBN / Gutenberg #), but the agent
    # takes one identifier at a time, so use whichever field was actually
    # filled in.
    identifier_type, identifier_value = "book_name", ""
    for field, itype in (("book_name", "book_name"), ("isbn", "isbn"), ("gutenberg_id", "gutenberg_id")):
        val = request.args.get(field, "").strip()
        if val:
            identifier_type, identifier_value = itype, val
            break
    validator_result = None
    if identifier_value:
        try:
            validator_result = _check_book(identifier_type, identifier_value)
        except Exception:
            # A network hiccup talking to Gutendex/Open Library shouldn't
            # 500 the whole page -- degrade to an honest error message.
            validator_result = {"status": "error", "message": "Lookup failed (network issue) -- try again in a moment."}

    return render_template(
        "producers.html",
        query=query,
        results=results,
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        validator_result=validator_result,
        validator_available=VALIDATOR_AVAILABLE,
    )


@app.route("/networks", methods=["GET", "POST"])
def networks():
    mandate = load_mandate_config()
    live = scoring_ready()
    live_mandate = live_error = None
    scored_count = failed_count = 0

    if request.method == "POST" and live:
        live_mandate, live_error = build_mandate_from_form(request.form)
        if live_mandate:
            try:
                top_scores, scored_count, failed_count = score_demo_pool(live_mandate)
                if not scored_count:
                    # Every book failed individually (bad API key, no credit, network down).
                    # score_demo_pool swallows per-book errors by design, so nothing raised --
                    # say so plainly instead of rendering an empty results card.
                    raise RuntimeError(
                        "no books could be scored — check ANTHROPIC_API_KEY and API credit"
                    )
            except Exception as exc:  # noqa: BLE001 - never 500 mid-demo
                live_error = f"Scoring failed: {exc}"
                live_mandate, top_scores = None, load_top_scores()
        else:
            top_scores = load_top_scores()
    else:
        top_scores = load_top_scores()

    return render_template(
        "networks.html",
        mandate=mandate,
        # Keyed off rows actually loaded, not just a file existing -- an empty or
        # unreadable file shouldn't make the page claim scores are ready.
        scores_exist=bool(top_scores),
        top_scores=top_scores,
        is_demo_run=bool(live_mandate),
        live_available=live,
        live_mandate=live_mandate,
        live_error=live_error,
        scored_count=scored_count,
        failed_count=failed_count,
        blank_keys=_freeform.BLANK_KEYS if SCORING_AVAILABLE else [],
    )


@app.route("/forward-looking")
def forward_looking():
    calendar_by_year = load_pd_calendar()
    return render_template("forward_looking.html", calendar_by_year=calendar_by_year)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
