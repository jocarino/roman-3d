# Build-time fonts

`web/static/fonts/` ships WOFF2 for the browser. These are the same faces as
TrueType, for the offline renderer that draws the share card
(`pipeline/card.py`): build-time only, never copied into `dist/`, so they cost
a visitor nothing.

Pillow can read WOFF2 wherever FreeType was built with Brotli, and on this
machine it can. The deploy image is a different build of FreeType, and a share
card that silently falls back to a stand-in font is the kind of breakage nobody
notices until a link is already out in the world. TrueType removes the
question.

Keep the two copies the same face; the card is meant to look like the page.

Silkscreen, designed by Jason Kottke. Upstream copyright line, verbatim:

> Copyright 2001 The Silkscreen Project Authors
> (https://github.com/googlefonts/silkscreen)

Licensed under the SIL Open Font License 1.1. OFL section 2 requires the
licence to travel with every redistributed copy, so `OFL.txt` sits beside the
fonts here as well as at `docs/OFL-1.1.txt`, which covers the WOFF2 the site
actually serves. Source: <https://fonts.google.com/specimen/Silkscreen>.
