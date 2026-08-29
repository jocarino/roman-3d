"""Share identity: what a crawler sees when somebody pastes the link.

Three jobs, all of them string work:

* the ``<head>`` values that Slack, Mastodon, iMessage, WhatsApp and the search
  engines read (Open Graph, Twitter cards, canonical, JSON-LD);
* ``robots.txt``;
* ``sitemap.xml``.

The one rule that makes or breaks all of it is **absolute URLs**. Open Graph
wants a full URL with a scheme and a host, and WhatsApp's published rules say
so outright: "an absolute URL for an image". Relative ones are dropped, which
is how a site ends up sharing as a grey box with no picture.

The origin therefore lives in ``data/facts.json`` as ``site.origin``, and is
the default. It used to arrive only from outside, as ``$SITE_BASE_URL`` or
``--base-url``, on the reasoning that a build cannot know where it will be
served and a guessed origin is worse than a relative one. That reasoning was
sound and the conclusion was still wrong, because it made working share links
depend on somebody remembering a build argument. Nobody did, the site shipped
with ``content="/og.png"``, and the first link pasted into WhatsApp arrived
without its picture. A default that is checked into the repo cannot be
forgotten, and it is not a guess: it is where the site actually is.

``$SITE_BASE_URL`` and ``--base-url`` still override it, for a preview deploy
on another host. Passing an explicitly empty origin turns every share URL back
into a root-relative path and writes no sitemap, which is the honest output for
a build whose home really is unknown. The sitemap has no halfway house, because
``<loc>`` is required to be absolute. ``web/build.py`` says which of the three
happened on stdout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

# Hard-coded in the template as og:image:width / og:image:height, and pinned to
# the renderer by tests/test_share.py.
CARD_WIDTH, CARD_HEIGHT = 1200, 630
CARD_PATH = "/og.png"

LOCALE = "en_GB"
LANGUAGE = "en-GB"


@dataclass(frozen=True)
class PageMeta:
    """One addressable page. There is one today; the shape is here so that
    adding a second does not mean rewriting the sitemap."""

    path: str
    title: str
    description: str
    image: str | None = None
    image_alt: str | None = None
    changefreq: str = "monthly"
    priority: str = "1.0"


@dataclass(frozen=True)
class Site:
    base_url: str = ""
    pages: list[PageMeta] = field(default_factory=list)

    def absolute(self, path: str) -> str:
        """Origin plus path, or the path alone when no origin was given."""

        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}" if self.base_url else path


def share_values(site: Site, page: PageMeta) -> dict[str, str]:
    """The template tokens for the head. Plain strings; ``web/build.py``
    escapes them on the way in, like every other token."""

    image = site.absolute(page.image or CARD_PATH)
    url = site.absolute(page.path)
    return {
        "SHARE_URL": url,
        "SHARE_TITLE": page.title,
        "SHARE_DESCRIPTION": page.description,
        "SHARE_IMAGE": image,
        "SHARE_IMAGE_ALT": page.image_alt or page.title,
        "SHARE_IMAGE_WIDTH": str(CARD_WIDTH),
        "SHARE_IMAGE_HEIGHT": str(CARD_HEIGHT),
        "SHARE_LOCALE": LOCALE,
    }


def jsonld(site: Site, page: PageMeta) -> str:
    """A minimal WebSite node.

    Deliberately small. Everything in it is already in the Open Graph tags, and
    schema.org fields we cannot source honestly (an author, a rating, a date
    the content was "published") are left out rather than invented.
    """

    node = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": page.title,
        "url": site.absolute(page.path),
        "description": page.description,
        "image": site.absolute(page.image or CARD_PATH),
        "inLanguage": LANGUAGE,
    }
    # A literal "</script>" inside the block would end it early.
    return json.dumps(node, ensure_ascii=False).replace("<", "\\u003c")


def robots_txt(site: Site) -> str:
    """Everything here is meant to be found. The only line that varies is the
    pointer to the sitemap, which cannot exist without an origin."""

    lines = ["User-agent: *", "Allow: /", ""]
    if site.base_url:
        lines.append(f"Sitemap: {site.absolute('/sitemap.xml')}")
        lines.append("")
    return "\n".join(lines)


def sitemap_xml(site: Site, lastmod: str | None = None) -> str:
    """A urlset naming every page, with the share card attached as an image."""

    if not site.base_url:
        raise ValueError("sitemap.xml needs an absolute origin; pass --base-url")

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for page in site.pages:
        out.append("  <url>")
        out.append(f"    <loc>{escape(site.absolute(page.path))}</loc>")
        if lastmod:
            out.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        out.append(f"    <changefreq>{escape(page.changefreq)}</changefreq>")
        out.append(f"    <priority>{escape(page.priority)}</priority>")
        image = page.image or CARD_PATH
        out.append("    <image:image>")
        out.append(f"      <image:loc>{escape(site.absolute(image))}</image:loc>")
        out.append("    </image:image>")
        out.append("  </url>")
    out.append("</urlset>")
    out.append("")
    return "\n".join(out)


def origin(facts: dict, override: str | None = None) -> str:
    """Where the site lives.

    ``None`` means nobody asked for anything in particular, so use the origin
    in the data. An empty string is a deliberate request for relative URLs and
    is honoured: it is not the same as saying nothing.
    """

    chosen = facts["site"]["origin"] if override is None else override
    return chosen.rstrip("/")


def home(facts: dict) -> PageMeta:
    """The one page, described out of ``data/facts.json``."""

    share = facts["site"]["share"]
    return PageMeta(
        path="/",
        title=facts["site"]["title"],
        description=share["description"]["text"],
        image=CARD_PATH,
        image_alt=share["image_alt"]["text"],
        changefreq="monthly",
        priority="1.0",
    )
