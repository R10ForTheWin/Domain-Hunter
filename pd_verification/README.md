# Package 2 — PD Verification Agent

**Owner:** Teammate (phone ending 8253) · Branch suggestion: `yourname-pd-verification`

## Goal

Build the independent check that confirms — or rejects — a specific book's public-domain claim
before it's allowed anywhere near the shortlist.

- Encode the U.S. public-domain rules as a deterministic rule engine (not a guess/vibe check)
- Input: one book (title, author, death year, publication year) → Output: PD confirmed / not
  confirmed / uncertain, with the reasoning shown
- This agent must run independently from the scoring agent (Package 4) — it should never be
  influenced by how "good" a book scored
- Flag anything ambiguous (disputed death year, foreign publication, renewal-era quirks
  1929–1963) as "uncertain," never guess

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 2.

## ⚠️ Not legal advice

This engine is a conservative, code-only reading of the major U.S. copyright-duration rules,
written so a team of first-time builders can screen hundreds of books without hand-checking each
one against a lawyer. It is deliberately biased toward `uncertain` (or, where the term definitely
hasn't run out yet, `not_confirmed`) over a guessed `confirmed`. **Because these books are being
considered for active film projects, get a human with real copyright-law expertise to
independently verify every `confirmed` verdict before anyone relies on it** — especially anything
foreign-published, anonymous/corporate-authored, or published 1923–1988. See the "What this
doesn't model" section below for the specific gaps.

## What fields this agent needs, and why

The rule engine only asks for a field when the specific book's legal path actually needs it —
it never blanket-demands everything up front. Full explanation (also printed when you run the
agent interactively):

| Field | When it's needed |
|---|---|
| `title`, `author`, `publication_year` | Always. If a book has no publication year on file (or is unpublished), the verdict is always `uncertain` — unpublished works follow a separate rule (17 U.S.C. § 303) this engine doesn't evaluate. |
| `author_death_year` (+ `author_death_year_disputed`) | Needed whenever the life-of-author-plus-70 rule controls — i.e. anything first published 1978+, or an older foreign/unknown-country work where the 95-year publication rule alone can't rule out a restored copyright. A **disputed** death year is treated the same as an unknown one — it never resolves in either direction. |
| `country_of_first_publication` | Anything other than a confirmed U.S. first publication carries URAA restoration risk (see below) — the single biggest trap in this whole analysis. |
| `simultaneous_us_publication` | Was the book also published in the U.S. within 30 days of a foreign first publication? That makes it a "United States work" for restoration purposes even though first published abroad. |
| `had_copyright_notice_at_publication` | Only matters for pre-March-1989 U.S. publications — a work published without notice fell into the public domain immediately, no cure period existed before 1978's cure rules and even those only applied 1978–1989. |
| `renewal_filed` | Only matters for U.S. works first published 1923–1963 — these needed an affirmative renewal in their 28th year or they lapsed into the public domain. (1964–1977 U.S. works were **automatically** renewed by the Copyright Renewal Act of 1992 — no lookup needed for those; the engine returns a definite `not_confirmed` without asking.) |
| `is_anonymous_pseudonymous_or_corporate` | Defaults to "no" (identified individual author) unless set `true`, or the `author` field is literally `Anonymous`/`Unknown`. This category gets a fixed 95-year-from-publication term instead of life+70, with no country-of-publication wrinkle at all. |

## Why foreign publication is its own hazard (URAA)

A foreign work that looks public domain under the ordinary U.S. renewal/publication-year rules
can still be under U.S. copyright today because of **restoration** (17 U.S.C. § 104A). Works that
fell out of U.S. protection *only* for failing to comply with U.S. formalities (no notice, no
renewal) — not because their term had genuinely run out — had their U.S. copyright restored,
running for the same term the work would have had if it had never lost protection. For a foreign,
pre-1978, named-author book, that restored term is life-of-the-author-plus-70 — which can still be
running today even for a book published back in the 1920s or 1930s, if the author lived into the
late 20th century.

**This engine will never return `confirmed` for a foreign-published (or country-unknown) work
unless *both* the 95-years-from-publication ceiling *and* the life+70 ceiling have independently
expired** — so it doesn't matter which theory actually controls. Anything short of that comes back
`uncertain` with a `uraa_restoration_risk` flag and the specific missing fact named.

## How to run it

**Interactive** — check one book at a time, with Project Gutenberg lookup:

```bash
python -m pd_verification.agent
```

Opens with the field explanation above, lets you look a book up by Gutenberg ID, search
Gutenberg by title, or enter it manually, then asks — one round at a time — for whatever
additional fields that specific book's legal path still needs. You can always leave a field
blank; the verdict just stays `uncertain` and says what's missing.

**Batch** — run the whole corpus non-interactively (used for the actual pipeline into
`data/pd_verification.csv`):

```bash
python -m pd_verification.agent --batch data/book_corpus.csv \
    --supplementary data/pd_verification_inputs.csv \
    --out data/pd_verification.csv
```

No external dependencies — everything here is Python standard library plus a plain HTTPS call to
the free [Gutendex](https://gutendex.com) API for Gutenberg metadata (no key needed).

```bash
python -m pytest pd_verification/tests/ -v
```

## Input

- `data/book_corpus.csv` (produced by Package 3) — `title`, `author`, `author_death_year`,
  `author_death_year_disputed`, `publication_year`.
- `data/pd_verification_inputs.csv` — supplementary legal fields **this package owns and
  produces itself** (country of first publication, renewal status, etc. — see
  [`../docs/data-contracts.md`](../docs/data-contracts.md)). Interactive mode offers to save
  what you enter here so batch mode doesn't have to ask again.

## Output

- `data/pd_verification.csv` — exact schema in [`../docs/data-contracts.md`](../docs/data-contracts.md).
  `pd_status` is always exactly one of `confirmed` / `not_confirmed` / `uncertain`.

## What this doesn't model (always routes to `uncertain` instead of guessing)

- **Unpublished works.** Governed by a separate rule (§ 303) this engine doesn't attempt.
- **Whether a specific foreign source country's own copyright had already expired** as of that
  country's URAA restoration date. This is genuinely country- and date-specific research; the
  engine's fallback (requiring *both* U.S. theories to have expired) is deliberately more
  conservative than the real legal floor, so some genuinely-PD foreign books will come back
  `uncertain` rather than `confirmed` — that's an intentional false-negative bias, not a bug.
- **Government works, CC0/public-domain-dedicated works, or anything under a specific license.**
  Not a "term expired" question at all — needs a different check.
- **The precise 120-years-from-creation prong** for anonymous/pseudonymous/corporate works. In
  practice the 95-years-from-publication prong is almost always the shorter (binding) one for
  anything actually published, so this engine only checks that prong.

## Ground rule

No book goes on the final shortlist without passing this check — no exceptions, even if it scores
well in Package 4. When unsure, the answer is `uncertain`, not a guess.
