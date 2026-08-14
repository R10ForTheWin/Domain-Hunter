# A24 Studio Mandate — Research Brief

**Target studio:** A24
**Approach:** rather than a single fixed mandate, this package uses a live "mad-lib" mechanic —
audience members fill in blanks in a sentence template during the demo, generating a fresh mandate
each run. This brief documents the research that grounds the template's design (why these blanks,
why they map to these rubric categories) and the weights in `mandate_config.yaml`. It is not a
one-time fixed mandate the way a normal Package 4 brief would be — see `mandate_config.yaml` and
`madlib_template.yaml` for the live/editable parts.

## Why A24

Well-documented public acquisition and production history, wide genre range (useful for varied
mad-lib answers), strong brand recognition with the target demo. Selected per project-plan.md's
requirement to pick one studio and identify it clearly.

## Research findings

### Genre (fact)
Historically built on elevated horror and prestige, director-driven drama. As of 2023–2026,
industry reporting describes an active pivot toward "action and big IP projects" and broader genre
mixing. A24's reported 2026 slate (21 films) spans horror, action, romantic drama, mockumentary,
documentary, musical comedy, and video game adaptations.
Sources: [TheWrap](https://www.thewrap.com/a24-shifts-strategy-commercial-film/),
[ComicBook.com](https://comicbook.com/movies/news/a24-shifts-focus-indie-films-big-franchises-ips/),
[World of Reel](https://www.worldofreel.com/blog/2023/10/11/jeqrlgg6617lxx4jl4cykrsvq8adby)

### Budget / scale (fact)
Typical theatrical budget historically $15–20M, optimized for a short path to break-even. The
annual average climbed to $50M in 2024 — the highest on record — as the studio has taken on bigger,
more commercial films alongside its traditional low-budget slate.
Sources: [Statista](https://www.statista.com/statistics/1375638/average-budget-production-a24-movies-worldwide/),
[Parrot Analytics](https://www.parrotanalytics.com/press/a24s-dollar35b-valuation-pushes-the-indie-studio-toward-blockbusters/),
[IMDb](https://www.imdb.com/news/ni65065882/)

### Franchise / IP appetite (fact, with inference noted)
Reporting (via agents and distribution executives, not direct A24 statements) says A24 has been
seeking franchise and "big IP" projects, including reportedly chasing rights to the *Halloween*
franchise. This is widely linked to a $2.5–3.5B valuation following a $225M investment from Stripes
for under 10% of the company, which analysts say creates pressure to deliver more commercially
scalable output.
**Inference:** because no A24 executive has spoken on-record about this strategy, treat "franchise
appetite" as a real but softer signal than the genre/budget facts above — weighted accordingly
below.
Sources: [TheWrap](https://www.thewrap.com/a24-shifts-strategy-commercial-film/),
[032c](https://magazine.032c.com/magazine/the-billion-dollar-underdog-a24-and-the-business-of-cultural-capital)

### Audience (fact)
Core audience 18–34, skewing 25–34, slight female skew, concentrated in urban areas and college
towns, middle-to-upper-middle-class. Digitally native, social-media-driven, cinephile — audience
treats the A24 brand itself as a quality signal ("thoughtfully made, visually distinct,
intellectually challenging").
Sources: [CanvasBusinessModel](https://canvasbusinessmodel.com/blogs/target-market/a24-target-market),
[nogood.io](https://nogood.io/blog/a24-marketing-strategy)

### Visual / story style (fact, general pattern across all sources)
A24's brand identity is consistently described as director-driven and visually distinct filmmaking
— this recurs across nearly every source consulted, independent of the genre pivot discussed above.

### Name recognition (not covered by mad-lib — see below)
A24 titles frequently succeed without pre-existing IP name recognition; the brand itself substitutes
for it. Because the target audience for this project is scoring **public-domain books**, name
recognition should be assessed from the book's own metadata (well-known title/author vs. obscure)
rather than generated live by an audience mad-lib answer — see "Design decision" below.

## Mad-lib template design

> *"A [ADJECTIVE] [GENRE] where a [CHARACTER] [VERB] at/in a [SETTING]."*
>
> The VERB blank is collected already conjugated (present tense, e.g. "escapes," "survives" — matching the prompt's examples), so the template does not append an "s" itself.

| Blank | Part of speech | Rubric category | Rationale |
|---|---|---|---|
| GENRE | noun | `genre_fit` | scored against A24's demonstrated range: elevated horror → prestige drama → now action/IP |
| ADJECTIVE | adjective | `visual_story_adaptability` | scored against A24's director-driven, visually distinct brand identity |
| CHARACTER | noun | `audience_fit` | scored against the 18–34, cinephile, urban/college-town audience |
| VERB | verb | `franchise_potential` | scored on how much world-building/sequel potential the action implies, tied to A24's reported IP pivot |
| SETTING | noun/place | `budget_scale_fit` | scored on whether it implies contained/practical scale ($15–20M) vs. event scale ($50M+) |

Machine-readable version: [`madlib_template.yaml`](madlib_template.yaml).

### Design decision: `name_recognition` excluded from the mad-lib
An audience shout-out can't meaningfully generate a "how famous is this" signal. `name_recognition`
is instead scored directly from each book's own metadata in `book_corpus.csv` (well-known
title/author vs. obscure) rather than from a mad-lib blank. It keeps a nonzero weight in
`mandate_config.yaml` but is populated by the scoring agent from book data, not audience input.

## Weight rationale (see `mandate_config.yaml` for the actual numbers)

- `genre_fit` and `franchise_potential` weighted highest — the clearest, best-sourced signal is
  A24's active pivot toward IP/franchise and broader genre range.
- `budget_scale_fit` and `visual_story_adaptability` weighted moderately — well-documented, stable
  brand traits.
- `audience_fit` weighted moderately — well-sourced but less discriminating (most PD classics could
  plausibly appeal to a broad 18–34 cinephile audience).
- `name_recognition` weighted lowest — A24's own history shows it succeeds without pre-existing IP
  recognition, and per the design decision above, this category runs on book metadata rather than
  the live mandate.

## Design decision: scoring is grounded in a plot summary, not just the title string

`book_corpus.csv` has no summary/genre/plot field (see `docs/data-contracts.md`) — only title,
author, and publication metadata. `scoring_agent.py` requires the model to first state what it
actually knows about each book's plot, genre, and themes (`book_summary` in the output CSV) before
scoring any category, rather than pattern-matching on the bare title. If the model doesn't
confidently recognize a specific title/author, it says so explicitly instead of inventing a plot —
this matters because most of the corpus is genuinely obscure (not every public-domain book is a
famous classic like the small hand-picked sample set used for early testing).

This also interacts with a real data-quality bug found in the corpus: ~98 titles are attached to
the wrong author (e.g. multiple different real authors listed for the same well-known title). The
prompt tells the model the title is more reliable than the author field when they conflict, so it
scores the actual known book rather than a false pairing — Radoslav is fixing the underlying data,
but this makes scoring resilient to whatever attribution noise remains.
