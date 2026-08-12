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

## Deployed

**Live at: https://domain-huntress-site-production.up.railway.app**

Deployed via the Railway CLI (`railway` was already installed and logged in as
djnurre@gmail.com), project `domain-huntress-site` in the `r10forthewin's Projects` workspace.
This was a CLI upload deploy, not a GitHub-linked one yet -- see the gotcha below and the redeploy
steps.

### Redeploying after a change

`railway up` only uploads `site/`'s own contents, not `../data/` (which is one level up) -- so a
fresh data snapshot needs bundling into `site/data/` before each deploy, and the upload needs
`--no-gitignore` since `site/data/` is (correctly) gitignored so it never gets committed as a
stale duplicate of the real `data/book_corpus.csv`. `app.py` checks `site/data/` first and falls
back to `../data/`, so this only matters for this CLI-upload style of deploy.

```
cd site
git show origin/dj-book-corpus:data/book_corpus.csv > data/book_corpus.csv   # refresh the snapshot
railway up --detach --no-gitignore
```

(Swap `dj-book-corpus` for wherever the current merged corpus lives once PR #3 merges into
`dj-development`/`main`.)

### Moving to GitHub-linked deploys (better long-term)

Right now every update needs a manual `railway up`. Connecting the service to the GitHub repo
directly (Settings → Source → connect `Domain-Hunter`, root directory `site`) would make it
redeploy automatically on every push, the same way Artie works — and would also make the
`../data/` gotcha above disappear, since a GitHub-linked deploy uploads the whole repo rather than
just the `site/` subfolder. That connection step needs the Railway dashboard (OAuth-style GitHub
App install), not something scriptable from the CLI or this repo alone.

## Updating pipeline status

`app.py`'s `STAGES` list is maintained by hand — there's no automated way to detect "is Chantell
done with scoring yet." Update the `status` field (`"not_started"` / `"ongoing"` / `"done"`) as
packages land.
