# Brief for the AI agents working on Domain Huntress

**Last updated:** 13 Aug 2026, against `dj-development`. **This file is replaced, not appended to** —
if it contradicts something you remember, this is newer.

**Who this is for:** the Claude session helping each teammate. You know your own package. This is
the project-wide state and what your human needs to do next.

**Raise your package's item with your human in plain language.** Most of what is outstanding is one
command or one small change, stalled only because nobody said it out loud.

---

## Where the project actually is

**The pipeline works end to end on real data.** A full run: 2,251 books → PD verification → scored
against a live studio mandate → PD-gated shortlist of 10. Every package has shipped working code.

**All 14 pull requests are merged** into `dj-development`. There are no open PRs.

**The single biggest gap is that `main` is 40 commits behind `dj-development`** — roughly 8,400
line-insertions. Everything real from the last two days lives on `dj-development`. Anything built
from `main` is working from a stale snapshot. **Branch from `dj-development`.**

## What got fixed since the last brief

- **The author-misattribution bug is fixed** (`0d16072`). Books were being attributed to the wrong
  authors because the corpus builder searched Open Library *by author* and stamped every returned
  title with the author it searched for. Measured against the CMU corpus, the mismatch rate went
  **19.0% → 9.2%**, and most of what remains is a false positive in the check itself: *Cosmopolis*
  is both Bourget (1893) and DeLillo (2003), so a title-based comparison flags a real book as wrong.
  The corpus went 2,630 → 2,251 rows as bad rows were dropped; titles carrying more than one author
  went 99 → 26, and the residual is largely legitimate (many poets published a book called *Poems*).
- **Package 4 has run for real.** `data/studio_scores.csv` exists with 2,523 scored books. That was
  the one clause of the project's goal that had never executed.
- **Live scoring is deployed** on `/networks`, with a hard $5 server-side spend cap and rate
  limiting — so the QR code in the room cannot drain the API budget.
- **Renewal-era work is underway by two people.** Radoslav shipped a renewal corpus batch (PR #14,
  merged): `build_corpus_renewal.py` plus 180 renewal-era books. Jason built renewal-status
  automation on `jason-renewal-automation`.
- **`/producers` no longer 500s** on a timed-out lookup (the Python 3.9 `socket.timeout` gap).
- **The status page no longer contradicts itself** — stage states are current.

## What still needs doing

### Package 2 — Jason

**Your renewal automation is built and not merged.** `jason-renewal-automation` has
`match_renewals.py`, a populated `pd_verification_inputs.csv`, a review queue, and a comparison
doc — and **no PR has been opened**, so it is invisible to everyone and cannot land. That is the
highest-value single action available to anyone right now.

### Package 3 — Radoslav

**`language` is `en` on all 2,251 rows.** It is a hardcoded default, not real data — at least 200
rows have visibly non-English titles (*Bahnwärter Thiel*, *Arsène Lupin contre Herlock Sholmès*).

This is not cosmetic. `language` is the only signal either rule engine has for foreign publication,
and foreign publication is what triggers URAA restoration analysis. That path has **never fired**.
Foreign works are being assessed as if they were American, which is the unsafe direction — a
foreign work with no US renewal record may have been *restored*, not freed. Both Gutenberg and Open
Library expose the real value.

### Package 6 — DJ

**Promote `dj-development` to `main`.** 40 commits, including every fix above. Until that happens,
anyone branching from `main` inherits bugs that were fixed two days ago.

### Packages 4 and 5 — Chantell, Luis

Nothing blocking. Both are merged and working.

## What is still true and worth not breaking

- **The verification agent's independence is structural.** Package 2 reads only the corpus and
  cannot see a score. Package 4 scores every book regardless of PD status. Package 5 is the only
  place they meet. Do not "optimise" this by having scoring skip non-PD books.
- **The PD gate is correctly implemented** — non-confirmed rows are skipped and a short list is
  never padded.
- **`uncertain` is a real answer**, not a hedge (`docs/project-plan.md` §5).
- **`book_id` is the join key for every package.** Treat it as opaque and stable.
- **`pytest` from the repo root** is the test runner. `python -m unittest discover` silently
  collects zero tests from pytest-style suites.
- **Run `python3 qa/validate_contracts.py` before opening a PR.** It checks schemas, `book_id`
  integrity, and whether a contract deliverable has been accidentally gitignored.

## Known limitation worth understanding

The corpus is sourced from Project Gutenberg and Open Library, which hold works **already** in the
public domain. So the verification gate rejects almost nothing — it is being handed a rigged deck,
not malfunctioning. Radoslav's and Jason's renewal work is what changes this: mid-century books
whose copyright was never renewed are public domain for a reason nobody has checked, and those are
the books the gate can actually do work on.

## Related

- `docs/renewal-era-corpus.md` — Radoslav's renewal corpus
- `docs/renewal-automation-jason-vs-ross.md` — Jason's approach comparison
- `docs/data-contracts.md` — the interface every package writes to
- `docs/evaluation-spec.md` — six checks nothing currently performs; still unowned
