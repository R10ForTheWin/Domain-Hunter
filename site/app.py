"""
Domain Huntress — live demo site.

Reads the pipeline's real output files (starting with the book corpus; wires
in PD verification / scoring / shortlist as those packages land) and renders
a dashboard for showing the project to class. No database -- everything is
computed from the CSVs already checked into the repo.
"""
import csv
import fcntl
import json
import os
import sys
import threading
import time
from collections import deque
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


def _score(row):
    try:
        return float(row.get("total_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def load_top_scores(limit=10):
    """The real top matches for /networks: Package 5's shortlist.csv, which
    only includes books Package 2 independently confirmed public domain
    (the project's own ground rule -- "only PD-confirmed books eligible, no
    exceptions"). Returns None when there is no shortlist yet, so the page
    can say so plainly rather than rendering an empty table.
    """
    # A one-off terminal demo run (scoring_agent.py written to this path by
    # hand) takes priority when present, same as before -- otherwise this is
    # the committed, PD-gated shortlist that ships with the repo.
    demo_path = DATA_DIR / "studio_scores_demo.csv"
    if demo_path.exists():
        with demo_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
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

    path = DATA_DIR / "shortlist.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    # Already PD-gated, scored, and ranked by build_shortlist.py -- just take
    # the top `limit` in the order it wrote them.
    return [
        {
            "title": row.get("title", ""),
            "author": row.get("author", ""),
            "score": round(_score({"total_score": row.get("total_score")})),
            "reasoning": row.get("score_reasoning", ""),
        }
        for row in rows[:limit]
    ]


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


# Reachable by anyone who scans the QR code, and each submission is a real
# Claude API call (a live scoring run over 50 books) -- unlike everything
# else on this site, this one costs real money per click. These caps bound
# the worst case (accidental rapid re-click/refresh, or a room full of
# classmates trying it) rather than trying to be an exact abuse-prevention
# system. In-memory and per-process: gunicorn runs multiple workers, so the
# real ceiling is roughly (limit x worker count), not an exact number --
# fine for a class demo, not a production rate limiter.
_RATE_LIMIT_WINDOW_SECONDS = 3600
_RATE_LIMIT_MAX_PER_WINDOW = 40
_RATE_LIMIT_COOLDOWN_SECONDS = 20
_recent_submissions = deque()
_last_submission_by_ip = {}


def _client_ip():
    # Railway sits in front of the app as a reverse proxy, so request.remote_addr
    # is the proxy's address, not the visitor's -- read the forwarded header instead.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "unknown")


def _rate_limit_error():
    """None if this submission may proceed; otherwise a message to show instead
    of spending an API call."""
    now = time.time()
    ip = _client_ip()

    last = _last_submission_by_ip.get(ip)
    if last and now - last < _RATE_LIMIT_COOLDOWN_SECONDS:
        wait = round(_RATE_LIMIT_COOLDOWN_SECONDS - (now - last))
        return f"Just scored one -- wait {wait}s before trying again."

    while _recent_submissions and now - _recent_submissions[0] > _RATE_LIMIT_WINDOW_SECONDS:
        _recent_submissions.popleft()
    if len(_recent_submissions) >= _RATE_LIMIT_MAX_PER_WINDOW:
        return "Live scoring has hit its demo limit for this hour — check back later, or see the results below."

    _last_submission_by_ip[ip] = now
    _recent_submissions.append(now)
    return None


# Hard dollar ceiling on top of the rate limiter above, per DJ: never let live scoring spend
# past this without him seeing it, enforced in the app itself rather than requiring a manual
# spending-limit setup in the Anthropic console. Rates are Haiku's approximate published
# pricing -- close enough to gate on, not a substitute for checking the real usage dashboard.
_BUDGET_LIMIT_USD = 5.00
_HAIKU_USD_PER_MTOK_INPUT = 1.00
_HAIKU_USD_PER_MTOK_OUTPUT = 5.00
# Conservative per-submission estimate (measured actual is ~$0.15-0.20 for a 50-book run) used
# only for the pre-flight check, so a submission is refused *before* spending anything if it
# could plausibly push the running total over the cap -- the real, exact cost from the API's
# own usage data is what actually gets added to the persisted total afterward.
_EST_SUBMISSION_COST_USD = 0.30
_BUDGET_LOCK = threading.Lock()


def _budget_file_path():
    return DATA_DIR / "_live_scoring_budget.json"


def _read_budget_spent():
    """Persisted to disk (not just in-memory) so the cap survives a process
    restart, not only individual requests. Note: a fresh `railway up` deploy
    still resets it -- that builds a brand-new container from scratch, same
    as it resets any other runtime-written file. A restart within the same
    deploy does not reset it.
    """
    path = _budget_file_path()
    if not path.exists():
        return 0.0
    try:
        with path.open("r", encoding="utf-8") as f:
            return float(json.load(f).get("spent_usd", 0.0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0.0


def _add_budget_spend(usd_amount):
    """Atomically add usd_amount to the persisted running total; returns the new total.
    File-locked (not just the in-process _BUDGET_LOCK) so gunicorn's multiple worker
    processes don't race each other writing this file.
    """
    path = _budget_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _BUDGET_LOCK:
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read()
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {}
            total = float(data.get("spent_usd", 0.0)) + usd_amount
            data["spent_usd"] = round(total, 4)
            f.seek(0)
            f.truncate()
            json.dump(data, f)
            fcntl.flock(f, fcntl.LOCK_UN)
    return total


def _usage_cost_usd(usage_totals):
    return (
        usage_totals.get("input_tokens", 0) / 1_000_000 * _HAIKU_USD_PER_MTOK_INPUT
        + usage_totals.get("output_tokens", 0) / 1_000_000 * _HAIKU_USD_PER_MTOK_OUTPUT
    )


def _budget_error():
    """None if a submission may proceed under the $5 cap; otherwise a message to show
    instead of spending anything. Checked *before* any API call -- refuses pre-flight
    using a conservative estimate, rather than letting a submission start and finding
    out partway through that it should not have."""
    spent = _read_budget_spent()
    if spent + _EST_SUBMISSION_COST_USD > _BUDGET_LIMIT_USD:
        print(
            f"[BUDGET CAP] Live scoring blocked: ${spent:.2f} already spent of "
            f"${_BUDGET_LIMIT_USD:.2f} cap -- next submission refused.",
            file=sys.stderr,
        )
        return (
            f"Live scoring has hit its ${_BUDGET_LIMIT_USD:.2f} demo budget cap "
            f"(${spent:.2f} spent) — showing the results below instead. Ask DJ to reset it."
        )
    return None


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
    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {
            pool.submit(_scoring.score_book_with_retry, client, SCORING_MODEL, book, mandate): book
            for book in books
        }
        for fut in as_completed(futures):
            book = futures[fut]
            try:
                result = fut.result()
                usage = result.get("_usage") or {}
                usage_totals["input_tokens"] += usage.get("input_tokens", 0)
                usage_totals["output_tokens"] += usage.get("output_tokens", 0)
                rows.append(_scoring.build_row(book, cfg["studio"], weights, result))
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
    return top, len(rows), failures, usage_totals


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


# The full pd_calendar.csv (Package 1's real, honest output) is 34 entries,
# all pub+95/renewal-era/uncertain -- nobody in the current corpus has a
# life+70 date landing in this 5-year window, so that's genuinely everything
# there is. Package 1's own commit explains why. For the presentation-facing
# page specifically, DJ asked to curate down to entries with real name/IP
# recognition rather than showing all 34 (mostly foreign-language, obscure
# to a general audience) -- this is a display-only curation, judged by hand,
# not a data correction. The underlying file and every other consumer of it
# are untouched. Keyed on book_id, not title, since a couple of these share
# an author with other (excluded) entries.
CURATED_CALENDAR_BOOK_IDS = {
    "vol-de-nuit__saint-exupery-antoine-de__1931",
    "die-vierzig-tage-des-musa-dagh__werfel-franz__1933",
    "radetzkymarsch__roth-joseph__1932",
    "the-autobiography-of-alice-b-toklas__stein-gertrude__1933",
    "la-guerre-de-troie-n-aura-pas-lieu__giraudoux-jean__1935",
    "living-my-life__goldman-emma__1931",
    "mein-weltbild__einstein-albert__1934",
    "my-own-story__dressler-marie__1934",
    "short-stories__bunin-ivan__1933",
    "the-indian-struggle-1920-1934__bose-subhas-chandra__1935",
    "war-memoirs__george-david-lloyd__1933",
    "whispers-from-eternity__yogananda-paramahansa__1935",
    "unknown__trotsky-leon__1931",
}

# Well-known English title in place of the original-language one, for the
# handful of curated entries best known in English translation. Anything
# not listed here keeps its original title as-is.
CURATED_CALENDAR_TITLE_OVERRIDES = {
    "vol-de-nuit__saint-exupery-antoine-de__1931": "Night Flight",
    "die-vierzig-tage-des-musa-dagh__werfel-franz__1933": "The Forty Days of Musa Dagh",
    "radetzkymarsch__roth-joseph__1932": "The Radetzky March",
    "la-guerre-de-troie-n-aura-pas-lieu__giraudoux-jean__1935": "Tiger at the Gates",
    "mein-weltbild__einstein-albert__1934": "The World As I See It",
    "unknown__trotsky-leon__1931": "History of the Russian Revolution",
}


def load_pd_calendar(curated=True):
    path = DATA_DIR / "pd_calendar.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    if curated:
        rows = [r for r in rows if r.get("book_id") in CURATED_CALENDAR_BOOK_IDS]
        for r in rows:
            override = CURATED_CALENDAR_TITLE_OVERRIDES.get(r.get("book_id"))
            if override:
                r["title"] = override
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
        live_scoring_spend=_read_budget_spent(),
        live_scoring_cap=_BUDGET_LIMIT_USD,
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
        limit_error = _rate_limit_error() or _budget_error()
        if limit_error:
            live_error = limit_error
            top_scores = load_top_scores()
        else:
            live_mandate, live_error = build_mandate_from_form(request.form)
            if live_mandate:
                try:
                    top_scores, scored_count, failed_count, usage_totals = score_demo_pool(live_mandate)
                    _add_budget_spend(_usage_cost_usd(usage_totals))
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


@app.route("/under-the-hood")
def under_the_hood():
    return render_template("under_the_hood.html", mandate=load_mandate_config())


@app.route("/forward-looking")
def forward_looking():
    calendar_by_year = load_pd_calendar()
    return render_template("forward_looking.html", calendar_by_year=calendar_by_year)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
