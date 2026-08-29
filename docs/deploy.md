# Deploying

The site is static. Everything interesting happened at build time.

## Dokploy, same pattern as the sibling site

Point a Dokploy application at this repo and let it build the `Dockerfile`. The
build stage runs the Python pipeline (`web/build.py`) and the serve stage is
nginx over `dist/site`. No secrets and no runtime configuration. There is one
build argument, and it matters.

The image runs the pipeline rather than shipping a prebuilt `dist/`, so what
gets deployed is always what the committed source model and the committed data
files produce. `dist/` stays gitignored.

## `SITE_BASE_URL`, the one setting

**Set `SITE_BASE_URL` as a build argument on the Dokploy application**, to the
site's own origin with no trailing path, for example
`https://observatory.example.com`.

It is a build argument rather than a runtime variable because the origin is
baked into the HTML at build time; changing it means rebuilding, which is also
true of every other word on the page.

Without it the site still builds and still works, but it shares badly:

| | with it | without it |
|---|---|---|
| `og:image`, `og:url`, canonical | absolute | root relative |
| Link unfurls with the card | yes | usually not |
| `sitemap.xml` | written | not written |
| `robots.txt` | written, points at the sitemap | written, no sitemap line |

Open Graph asks for absolute URLs and most unfurlers enforce it, so a relative
`og:image` is dropped and a shared link arrives as a bare grey box. A guessed
origin would be worse than a relative one, so the build never invents it. It
prints which of the two happened on the last line of its output, and
`uv run pytest tests/test_share.py` covers both paths.

## Building it by hand

```bash
docker build --build-arg SITE_BASE_URL=https://observatory.example.com \
  -t pixel-observatory .
docker run --rm -p 8080:80 pixel-observatory
```

Or without Docker at all:

```bash
uv run python web/build.py --base-url https://observatory.example.com
python3 -m http.server 8000 --directory dist/site
```

`--base-url` defaults to `$SITE_BASE_URL`. Leave both off for local work; the
warning at the end of the build is expected there.

## Checking a share card after a deploy

The unfurlers cache aggressively, so check before announcing anything. Paste
the URL into a private Slack channel or a draft post, or use the crawler's own
inspector. If the picture is wrong, `og.png` is served with a one-week
`Cache-Control` rather than the year the other images get, precisely so a fix
does not take a year to reach anybody.

## What the server needs to get right

Very little, but two things matter.

**Do not re-encode `model/roman.pxob.gz`.** The page fetches the gzip and
unwraps it itself, so the wire size holds whatever the server is configured to
do. `bundle.js` sniffs the magic number rather than trusting the extension, so
a server that *does* set `Content-Encoding: gzip` still works; it just makes the
transfer size depend on the server instead of on the file. The bundled nginx
config serves it untouched.

**Cache the fingerprinted things, revalidate the rest.** The bundle, the fonts
and the frames never change without the build changing, so they are immutable
for a year. `index.html`, `facts.json` and `mission.json` change whenever the
copy does, and must revalidate.

## Budgets to check after a deploy

From SPEC 12:

| Thing | Budget | Where it stands |
|---|---|---|
| First load, total transfer | 3.0 MB | about 300 KB |
| Voxel bundle, gzipped | 1.5 MB | 47 KB at grid 192 |
| Interactive on desktop broadband | under 2 s | |
| Lighthouse accessibility | no violations | |

First load pulls the page, the stylesheet, the ES modules, the vendored
three.js (about 180 KB gzipped, the largest single item), four woff2 faces
totalling 27 KB, and the bundle. The 24 orbit frames are only fetched by
browsers that fall back, and the share card only by crawlers, so neither counts
against the first load.

## Analytics

None, per SPEC 16.4, unless the owner asks. If it is added later, copy the
sibling's pattern: gated on a build-time key so only the real deploy reports,
and add the third-party origin to the `connect-src` in `deploy/nginx.conf`,
which is currently `'self'` only.
