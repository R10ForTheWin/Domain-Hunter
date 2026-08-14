# Domain Huntress

## Project
Domain Huntress (formerly "Domain Hunter") is a group software project. This GitHub repository —
still named `Domain-Hunter` on GitHub, unchanged — is the single source of truth for the app.

Domain Huntress screens hundreds of candidate books, filters them to ones we can legally use (public
domain), scores the survivors against a researched studio adaptation mandate, and produces a
shortlist of ten. Full plan and role assignments: [`docs/project-plan.md`](docs/project-plan.md).
The exact file formats passed between packages are pinned in
[`docs/data-contracts.md`](docs/data-contracts.md) — read that before changing what your package
reads or writes.

## Package map
| Folder | Package | Owner |
|---|---|---|
| `pd_calendar/` | 1 — Forward-Looking PD Calendar | Ross |
| `pd_verification/` | 2 — PD Verification Agent | Jason Brown |
| `book_corpus/` | 3 — Book Corpus & Data Pipeline | Radoslav Raychev |
| `studio_scoring/` | 4 — Studio Mandate Research & Scoring | Chantell Ferrell |
| `shortlist_output/` | 5 — Shortlist & Output Formatting | Luis R. |
| `data/` | shared interchange files (see `docs/data-contracts.md`) | — |
| `assets/logo/` | project logo | Ross |
| `site/` | live class-demo site (deployed dashboard) | DJ (Package 6) |

Each package folder has its own `README.md` with that package's exact goal, bullets, inputs, and
outputs — start there.

## Development Rules
- Do not work directly on main.
- Each team member should work on their own branch.
- Pull the latest main before beginning significant new work.
- Do not delete or substantially rewrite another team member's work without approval.
- Keep changes focused on the task requested.
- Reuse existing components and code when practical.
- Do not change the overall architecture without discussing it first.
- Test changes before committing.
- Never commit passwords, API keys, secrets, or credentials.

## Testing
Run the **full** test suite from the repo root with:
```bash
pytest
```
This is the only supported way to run tests project-wide — it picks up every package's tests
regardless of whether they're written as plain pytest functions (e.g. `pd_verification/`) or as
`unittest.TestCase` classes (e.g. `pd_calendar/`). **Do not use `python -m unittest discover`** —
it silently reports 0 tests collected for anything pytest-style, and separately hard-crashes
entering `pd_calendar/scripts/` (`ImportError: Start directory is not importable`, since that
folder isn't a Python package). Fixing the latter means changing `pd_calendar/scripts/`'s import
style, which touches Ross's code — get his sign-off before doing that; in the meantime, `pytest`
sidesteps the issue entirely and is the supported command. `pyproject.toml` at the repo root pins
the configuration above —
don't remove it.

## Git Workflow
1. Start from the latest `main` branch.
2. Work on your own branch, named `yourname-packagename` (e.g. `luis-shortlist`).
3. Commit changes with a clear description.
4. Push the branch to GitHub.
5. Open a pull request **into `dj-development`**, not `main` — DJ reviews there and merges into
   `main` periodically once packages fit together.

## Claude Instructions
Before making significant changes:
- Review the existing codebase.
- Understand how the requested change fits into the existing app.
- Preserve existing working functionality.
- Explain any major architectural change before implementing it.
- Ask before making destructive or irreversible changes.