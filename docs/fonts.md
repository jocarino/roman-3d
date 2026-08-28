# Fonts

Both are self-hosted in `web/static/fonts/`, latin subset, woff2 only. Nothing
is fetched from a font CDN at runtime: the site has to build and serve the same
way offline as online, and a webfont request is a third party watching visitors.

| Face | Weights | Licence | Upstream |
|---|---|---|---|
| Silkscreen | 400, 700 | SIL Open Font License 1.1 | https://fonts.google.com/specimen/Silkscreen |
| IBM Plex Mono | 400, 600 | SIL Open Font License 1.1 | https://fonts.google.com/specimen/IBM+Plex+Mono |

Full licence text: [`OFL-1.1.txt`](OFL-1.1.txt).

Silkscreen is by Jason Kottke. IBM Plex Mono is by Mike Abbink and Bold Monday
for IBM. Both are used unmodified, which is what the OFL asks for when you are
not renaming anything.

Silkscreen carries the pixel-font role: titles, button labels, small caps
legends. IBM Plex Mono carries everything anybody actually reads. That split is
deliberate and is the same one the sibling site uses. A pixel font at body size
is a legibility problem, not a style.

## Refreshing them

`web/static/fonts/*.woff2` are committed. To pull them again:

```bash
python3 tools/fetch-fonts.py web/static/fonts
```

The four files total about 27 KB. Keep them subset to latin; the full ranges are
several times larger for glyphs this site never renders.
