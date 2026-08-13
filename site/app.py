"""
Domain Huntress — live demo site.

Reads the pipeline's real output files (starting with the book corpus; wires
in PD verification / scoring / shortlist as those packages land) and renders
a dashboard for showing the project to class. No database -- everything is
computed from the CSVs already checked into the repo.
"""
import csv
import sys
from pathlib import Path

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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
try:
    from pd_verification.public_status import check_book as _check_book
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False

    def _check_book(*_args, **_kwargs):
        return {"status": "error", "message": "The validator isn't available on this deploy."}

# Stage status is maintained by hand here (mirrors the team status update) --
# there's no automated way to know "is Chantell done with scoring yet", so
# this just needs updating as packages land. Keep it short and factual.
STAGES = [
    {"n": 1, "name": "Forward-Looking PD Calendar", "owner": "Ross", "status": "not_started"},
    {"n": 2, "name": "PD Verification Agent", "owner": "Jason Brown", "status": "not_started"},
    {"n": 3, "name": "Book Corpus & Data Pipeline", "owner": "Radoslav Raychev", "status": "done"},
    {"n": 4, "name": "Studio Mandate Research & Scoring", "owner": "Chantell Ferrell", "status": "not_started"},
    {"n": 5, "name": "Shortlist & Output", "owner": "Luis R.", "status": "not_started"},
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


@app.route("/networks")
def networks():
    return render_template("networks.html")


@app.route("/forward-looking")
def forward_looking():
    return render_template("forward_looking.html")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
