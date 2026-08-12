# Domain Huntress — live demo site

A small Flask dashboard for showing the project to class the same way DJ's other projects (Artie,
Reggie) get demoed: a real deployed URL, not a slide deck.

Reads directly from the pipeline's own output files in `../data/` — no database, no separate data
entry. As packages finish and their output files land in `data/`, the site picks them up
automatically on next load. Sections that don't have data yet render an honest "not produced yet"
message rather than hiding or faking anything.

## Running locally

```
cd site
pip install -r requirements.txt
python3 app.py
```

Then open http://127.0.0.1:5050

**Note:** the dashboard only shows real numbers if `data/book_corpus.csv` (and eventually
`data/shortlist.csv`) actually exist in the repo root at `../data/`. As of 2026-08-12 those files
exist on the `dj-book-corpus` branch (PR #3) but not yet on `dj-development` or `main` — if you
run this locally on a branch without that data, you'll correctly see "No corpus data yet" rather
than an error. That's not a bug; it's the dashboard being honest about what's actually merged.

## Deploying (Railway)

`railway.json` in this folder is set up the same way as Artie's deployment:

1. In the Railway dashboard: New Project → Deploy from GitHub repo → `Domain-Hunter`
2. In the service's Settings: set **Root Directory** to `site` (Railway builds from repo root by
   default, and `railway.json` alone doesn't redirect that — this has to be set in the dashboard)
3. Railway should pick up `railway.json` automatically from there (build:
   `pip install -r requirements.txt`, start: `gunicorn --bind 0.0.0.0:$PORT app:app`)
4. Deploy from whichever branch has the real data merged in (`main`, once PRs land) — deploying
   from a branch without `data/book_corpus.csv` will just show empty states, not break
5. Railway auto-assigns a `*.up.railway.app` URL once it deploys successfully (same as
   `artie-production-1b13.up.railway.app`) — that's the link to share/demo

This step needs to happen from DJ's own Railway account — not something that can be done through
this repo alone.

## Updating pipeline status

`app.py`'s `STAGES` list is maintained by hand — there's no automated way to detect "is Chantell
done with scoring yet." Update the `status` field (`"not_started"` / `"ongoing"` / `"done"`) as
packages land.
