# Package 4 — Studio Mandate Research & Scoring Agent

**Owner:** Chantell Ferrell · Branch suggestion: `chantell-studio-scoring`

## Goal

Select the target studio, assess what that studio is actually looking for, turn that research into
an evidence-based adaptation mandate, and build the scoring system that ranks PD-confirmed books
against it.

- Select one target studio and clearly identify it as the studio the project is optimizing for
- Assess the studio's mandate using multiple forms of evidence: publicly observable
  purchasing/acquisition history, past adaptations and produced slate, genre and audience
  patterns, and the kinds of projects it's known for
- Use online sources: trade coverage, studio/executive interviews, podcasts, panels, press
  releases, other credible public materials
- Separate fact from inference. Concise mandate brief with source notes; label criteria we're
  inferring from that evidence
- Translate the mandate into a scoring rubric and weights (genre fit, name recognition,
  visual/story adaptability, franchise potential, budget/scale fit, audience fit)
- Make the mandate and weights **editable as a config**, not hardcoded; build the agent that
  takes a book + mandate criteria and produces a score with reasoning
- Output: studio mandate brief + source log + scoring config/agent

Full context: [`../docs/project-plan.md`](../docs/project-plan.md) §2, Package 4.

## Input

- `data/book_corpus.csv` (produced by Package 3)

## Output

- `studio_scoring/mandate_config.yaml` (or `.json`) — editable weights, shape in
  [`../docs/data-contracts.md`](../docs/data-contracts.md)
- `studio_scoring/mandate_brief.md` — the researched mandate + source notes, fact vs. inference labeled
- `data/studio_scores.csv` — one row per book, schema in
  [`../docs/data-contracts.md`](../docs/data-contracts.md)

## Notes

- Score every book in the corpus regardless of PD status — this package stays independent of
  Package 2's verification. Package 5 is what applies the PD gate at the end.
