# Two stages: build the site with the Python pipeline, then serve the static
# output. Nothing from the build stage reaches the running image except dist/.

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /src
ENV UV_LINK_MODE=copy

# Dependencies first, so editing content does not reinstall numpy.
COPY pyproject.toml README.md ./
COPY pipeline ./pipeline
RUN uv pip install --system --no-cache .

COPY assets ./assets
COPY data ./data
COPY web ./web

# Optional override of the canonical origin, for a preview deploy on some other
# host. Leave it unset for the real one: the origin is in data/facts.json, so
# share URLs come out absolute without anything being configured here.
#
# Note the ${VAR:+...} form. Passing an empty --base-url is not the same as
# passing none: it means "this site's home is unknown", which turns every share
# URL relative and drops the sitemap. Interpolating the argument unconditionally
# would do exactly that on every default build, which is the bug this replaced.
ARG SITE_BASE_URL=""

RUN python web/build.py --out /out/site ${SITE_BASE_URL:+--base-url "$SITE_BASE_URL"}


FROM nginx:1.27-alpine AS serve

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out/site /usr/share/nginx/html

EXPOSE 80
