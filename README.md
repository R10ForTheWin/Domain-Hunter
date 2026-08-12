# Domain Hunter

Public-domain book screening & adaptation-potential shortlisting.

Domain Hunter screens hundreds of candidate books, filters them down to ones we can legally use
(public domain), scores the survivors against a researched studio adaptation mandate, and produces
a shortlist of ten. A forward-looking piece also tracks what's about to become public domain.

| Stage | What happens | Folder |
|---|---|---|
| 1 | Forward-Looking PD Calendar | [`pd_calendar/`](pd_calendar/) |
| 2 | PD Verification Agent | [`pd_verification/`](pd_verification/) |
| 3 | Book Corpus & Data Pipeline | [`book_corpus/`](book_corpus/) |
| 4 | Studio Mandate Research & Scoring | [`studio_scoring/`](studio_scoring/) |
| 5 | Shortlist & Output | [`shortlist_output/`](shortlist_output/) |
| 6 | Infra, QA & Docs | DJ (point of contact) |

Full plan, role assignments, and ground rules: [`docs/project-plan.md`](docs/project-plan.md).
File formats shared between packages: [`docs/data-contracts.md`](docs/data-contracts.md).

## Getting set up

See [`docs/project-plan.md` §3](docs/project-plan.md#3-getting-set-up-everyone-do-this-first) for
the full walkthrough (GitHub account → collaborator invite → GitHub Desktop → clone → branch →
Claude). Short version:

1. Clone this repo.
2. Create your own branch: `yourname-packagename`.
3. Open your package's folder — each has a `README.md` with your exact task.
4. Open a PR into `dj-development` when you have something working; DJ reviews and merges to `main`.

See the root [`CLAUDE.md`](CLAUDE.md) for the shared project rules every Claude session should follow.
