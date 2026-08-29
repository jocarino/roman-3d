# Deploying

The site is static. Everything interesting happened at build time.

## Dokploy, same pattern as the sibling site

Point a Dokploy application at this repo and let it build the `Dockerfile`. The
build stage runs the Python pipeline (`web/build.py`) and the serve stage is
nginx over `dist/site`. No secrets, no runtime configuration, and nothing that
has to be set for the site to be correct.

The image runs the pipeline rather than shipping a prebuilt `dist/`, so what
gets deployed is always what the committed source model and the committed data
files produce. `dist/` stays gitignored.

## Where the site thinks it lives

The canonical origin is `site.origin` in `data/facts.json`, currently
`https://roman.joaogveloso.com`. Share URLs are built from it, so `og:image`,
`og:url`, the canonical link and `sitemap.xml` all come out absolute with
nothing configured on the host.

This used to be a required `SITE_BASE_URL` build argument, on the reasoning
that a build cannot know where it will be served. The reasoning was fine and
the conclusion was wrong: the argument was never set on the Dokploy
application, so the live site served `og:image content="/og.png"`, and the
first link pasted into WhatsApp arrived without its picture. WhatsApp's rules
say plainly that it wants "an absolute URL for an image". A default checked
into the repo cannot be forgotten, and it is not a guess: it is where the site
is. If the domain changes, change that one line.

`SITE_BASE_URL` still works as an **override**, for a preview deploy on another
host:

```bash
docker build --build-arg SITE_BASE_URL=https://preview.example.com \
  -t pixel-observatory .
```

Leave it unset for the real deploy. Note that unset and empty are different: an
empty origin means "this site's home is unknown", which turns every share URL
root relative and skips the sitemap. That is why the `Dockerfile` uses
`${SITE_BASE_URL:+--base-url ...}` rather than interpolating the argument
straight in, which would have forced the relative form on every build.

The build prints which of the three it did on its last line, and
`uv run pytest tests/test_share.py` covers all of them, including a plain
build with nothing configured.

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

## Checking a share card after a deploy

The unfurlers cache aggressively, so check before announcing anything. Paste
the URL into a private Slack channel or a draft post, or use the crawler's own
inspector. If the picture is wrong, `og.png` is served with a one-week
`Cache-Control` rather than the year the other images get, precisely so a fix
does not take a year to reach anybody.

WhatsApp caches per URL, and it caches the *failure* too: once it has decided a
link has no picture, it keeps saying so for about a week even after the deploy
is fixed. To see the current truth rather than the cached one, add a throwaway
query string, `https://roman.joaogveloso.com/?x=1`, which is a different cache
key. The real URL catches up on its own.

Two quick checks that need no phone:

```bash
curl -s https://roman.joaogveloso.com/ | grep -E 'og:(image|url)'   # absolute?
curl -sI https://roman.joaogveloso.com/sitemap.xml | head -1        # 200, not 404?
```

A 404 on `sitemap.xml` is the cheapest tell that a build came out with no
origin, because the two fail together.

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
