# Forward-Looking Public Domain Calendar

Works entering the U.S. public domain on each of the next 5 January 1sts, as of 2026.

Copyright runs through December 31 of its final year, so works do not trickle into the public domain through the year — they all arrive on January 1. See `docs/project-plan.md` §1.

Generated from `data/book_corpus.csv` (2630 rows) by `pd_calendar/scripts/build_calendar.py`.

## Summary

| | count |
|---|---|
| Books read | 2630 |
| Already public domain as of 2026 | 2182 |
| No determinable date | 341 |
| Entering in 2027–2031 | 34 |
| Entering after 2031 | 73 |

## January 1, 2027

11 work(s), by author:

**Beckmann, Max**

- *Max Beckmann* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Fallada, Hans**

- *Bauern, Bonzen und Bomben* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Goldman, Emma**

- *Living my Life* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Iorga, Nicolae**

- *A history of Anglo-Roumanian relations* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Karlfeldt, Erik Axel**

- *Why Sinclair Lewis got the Nobel prize* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Saint-Exupéry, Antoine de**

- *Vol de nuit* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Spengler, Oswald**

- *Der Mensch und die Technik* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Tarrasch, Siegbert**

- *Das Schachspiel. Systematisches Lehrbuch für Anfänger und Geübte.* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Trotsky, Leon**

- *История русской революции* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Tucholsky, Kurt**

- *Schloss Gripsholm* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

**Werfel, Franz**

- *Die Geschwister von Neapel* — published 1931, rule `pub+95`, uncertain, flags: renewal_era

## January 1, 2028

7 work(s), by author:

**Chaliapin, Feodor**

- *Chaliapin, man and mask* — published 1932, rule `pub+95`, uncertain, flags: renewal_era
- *Maska i dusha* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

**Fallada, Hans**

- *Kleiner Mann, was nun?* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

**Marinetti, Filippo Tommaso**

- *Cocina Futurista, La - Una Comida Que Evito El Suicidio* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

**Ripley, H. A. (Harold Austin)**

- *Minute Mysteries [Detectograms]* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

**Roth, Joseph**

- *Radetzkymarsch* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

**Čapek, Josef**

- *Devatero pohádek* — published 1932, rule `pub+95`, uncertain, flags: renewal_era

## January 1, 2029

7 work(s), by author:

**Bunin, Ivan**

- *Short stories* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

**George, David Lloyd**

- *War Memoirs* — published 1933, rule `pub+95`, uncertain, flags: renewal_era
- *War memoirs of David Lloyd George* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

**Jensen, Johannes V.**

- *Kongens fald* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

**Spengler, Oswald**

- *Jahre der Entscheidung* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

**Stein, Gertrude**

- *The Autobiography of Alice B. Toklas* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

**Werfel, Franz**

- *Die vierzig Tage des Musa Dagh* — published 1933, rule `pub+95`, uncertain, flags: renewal_era

## January 1, 2030

2 work(s), by author:

**Dressler, Marie**

- *My own story* — published 1934, rule `pub+95`, uncertain, flags: renewal_era

**Einstein, Albert**

- *Mein Weltbild* — published 1934, rule `pub+95`, uncertain, flags: renewal_era

## January 1, 2031

7 work(s), by author:

**Bose, Subhas Chandra**

- *The Indian struggle, 1920-1934* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Dawes, Charles G.**

- *Notes As Vice President 1928 1929* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Giraudoux, Jean**

- *La guerre de Troie n'aura pas lieu* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Masaryk, Tomáš Garrigue**

- *Gespräche mit Masaryk* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Stapledon, Olaf**

- *Philosophy and living* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Yogananda, Paramahansa**

- *Whispers from Eternity* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

**Yosano, Akiko**

- *Midaregami* — published 1935, rule `pub+95`, uncertain, flags: renewal_era

## Reading the confidence column

34 of the 34 works above are marked `uncertain`. That is a required answer under `docs/project-plan.md` §5, not a hedge: a renewal-era work may already be public domain if its copyright was never renewed, and a foreign work may have been restored by the URAA. Neither can be settled from the columns `book_corpus.csv` currently carries.

Do not treat any date here as cleared for use. Package 2 (`pd_verification/`) is the agent that confirms a specific book's public-domain claim; this file only says when a term is scheduled to end.
