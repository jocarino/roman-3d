# Deploying

The site is static. Everything interesting happened at build time.

## Dokploy, same pattern as the sibling site

Point a Dokploy application at this repo and let it build the `Dockerfile`. The
build stage runs the Python pipeline (`web/build.py`) and the serve stage is
nginx over `dist/site`. No environment variables, no secrets, no runtime
configuration.

The image runs the pipeline rather than shipping a prebuilt `dist/`, so what
gets deployed is always what the committed source model and the committed data
files produce. `dist/` stays gitignored.

## Building it by hand

```bash
docker build -t pixel-observatory .
docker run --rm -p 8080:80 pixel-observatory
```

Or without Docker at all:

```bash
uv run python web/build.py
python3 -m http.server 8000 --directory dist/site
```

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
totalling 27 KB, and the bundle. The 24 orbit frames and the social card are
only fetched by browsers that fall back, so they do not count against the first
load.

## Analytics

None, per SPEC 16.4, unless the owner asks. If it is added later, copy the
sibling's pattern: gated on a build-time key so only the real deploy reports,
and add the third-party origin to the `connect-src` in `deploy/nginx.conf`,
which is currently `'self'` only.
