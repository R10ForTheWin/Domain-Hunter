# Package 2 — PD Verification Agent

**Owner:** Jason Brown · Branch suggestion: `jason-pd-verification`

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

## Input

- `data/book_corpus.csv` (produced by Package 3)

## Output

- `data/pd_verification.csv` — exact schema in [`../docs/data-contracts.md`](../docs/data-contracts.md)

## Ground rule

No book goes on the final shortlist without passing this check — no exceptions, even if it scores
well in Package 4. When unsure, the answer is `uncertain`, not a guess.
