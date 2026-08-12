# Visual style guide

The retro comic / pop-art style in this folder is the visual direction for Domain Huntress's
graphics going forward — logo, diagrams, and the final shortlist report presentation. This is a
first pass; treat it as a direction to react to, same as everything else in the plan.

## Reference images

- `comic-boom.png` — halftone comic-burst graphic (motif reference, not branded)
- `domain-huntress-archer.png` — early character art, no title text
- `domain-huntress-banner.png` — same character art with a placeholder title lockup
- [`../logo/domain-huntress-logo.png`](../logo/domain-huntress-logo.png) — **adopted primary logo**,
  combining the archer with the original book/magnifying-glass mark

## Palette

| Swatch | Use |
|---|---|
| Teal blue (background) | primary background |
| Golden yellow | starburst / energy-burst accents, secondary text |
| Red-orange | primary title text, impact lettering |
| Cream / off-white | comic "smoke puff" accents, outlines |
| Black | bold outlines on everything |

## Motifs

- Halftone dot texture (comic-print look) on backgrounds and shading
- Bold black outlines on all linework
- Star/energy-burst shape behind focal art
- Comic "impact" lettering style for titles (thick, angled, drop-shadowed)

## Naming — resolved

The project is renamed **Domain Huntress** (from "Domain Hunter"), settling the open question
floated in [`../../docs/project-plan.md` §6](../../docs/project-plan.md#6-general). The GitHub
repo, local folder, and branch names (`Domain-Hunter`, `dj-development`, etc.) are unchanged —
only the product name and branding.

## Logo — resolved

`../logo/domain-huntress-logo.png` is the adopted primary logo: the original navy/gold
book-and-magnifying-glass mark combined with the archer character and a "Domain Huntress /
Public-Domain Adaptation Scout" lockup. The earlier navy/gold-only logo
(`../logo/domain-hunter-logo.jpg`) is superseded but left in place for history.

## Logo animation

`../logo/Huntress Animation 1.mp4` — an animated version of the logo, used as the looping header
on the live demo site (`site/`). A web-ready copy lives at `site/static/logo-animation.mp4`; the
static PNG logo is used as its poster frame / fallback for browsers that don't autoplay video.

`../logo/Animation Textelss.mp4` — a second animation, textless (no "Domain Huntress" title
lockup). Saved as a brand asset for now; not wired into the site yet. Could work as a hover state,
a background element, or a lower-thirds/intro clip if we ever want the mark without the title
baked in — placement not decided.
