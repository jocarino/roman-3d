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

RUN python web/build.py --out /out/site


FROM nginx:1.27-alpine AS serve

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out/site /usr/share/nginx/html

EXPOSE 80
