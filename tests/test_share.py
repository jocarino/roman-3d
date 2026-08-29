"""The share identity: what a crawler gets when somebody pastes the link.

This is the one part of the site nobody sees while building it. A broken
``og:image`` looks perfectly fine locally and only shows up as a grey box in
somebody else's group chat, days later, which is why it gets its own suite
rather than a line in the build. The bug these tests exist to prevent is the
original one: ``<meta property="og:image" content="og.png">``, a relative URL
that no unfurler resolves.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from pipeline import card as card_mod
from pipeline import palette as palette_mod
from web import build as build_mod
from web import meta as meta_mod

BASE = "https://example.test"

# Small enough to keep two full builds quick; the share plumbing does not care
# how many voxels the telescope is made of.
BUILD_GRID = 96


@pytest.fixture(scope="session")
def spec(facts) -> card_mod.CardSpec:
    return build_mod.card_spec(facts)


@pytest.fixture(scope="session")
def card(voxels, spec) -> Image.Image:
    pal = palette_mod.build()
    colour_index = palette_mod.material_indices(voxels.materials)
    return card_mod.render_card(voxels, pal, colour_index, spec)


@pytest.fixture(scope="session")
def built(tmp_path_factory, repo_root):
    """A real build with an origin set, which is how the deploy runs."""

    out = tmp_path_factory.mktemp("with-base") / "site"
    build_mod.build(
        out,
        BUILD_GRID,
        repo_root / "assets" / "source" / "roman-glb-a.glb",
        base_url=BASE + "/",  # trailing slash on purpose; it must be stripped
    )
    return out


@pytest.fixture(scope="session")
def built_without_origin(tmp_path_factory, repo_root):
    """An origin explicitly emptied, which is not the same as one left unsaid."""

    out = tmp_path_factory.mktemp("no-base") / "site"
    build_mod.build(
        out, BUILD_GRID, repo_root / "assets" / "source" / "roman-glb-a.glb", base_url=""
    )
    return out


@pytest.fixture(scope="session")
def built_plain(tmp_path_factory, repo_root):
    """A build with nothing configured at all, which is how the deploy runs."""

    out = tmp_path_factory.mktemp("default") / "site"
    build_mod.build(out, BUILD_GRID, repo_root / "assets" / "source" / "roman-glb-a.glb")
    return out


def head(out) -> str:
    text = (out / "index.html").read_text()
    return text[: text.index("</head>")]


def tag(html: str, attr: str, name: str) -> str | None:
    """The content of one meta tag, as a crawler would read it: the build
    escapes attribute values, so unescape before comparing to the source copy.
    """

    match = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', html)
    return html_mod.unescape(match.group(1)) if match else None


# --- the card ---------------------------------------------------------------


def test_card_is_the_size_every_unfurler_crops_to(card):
    assert card.size == (1200, 630)


def test_the_template_and_the_renderer_agree_on_the_size(built):
    """og:image:width is written into the page as a literal. If the renderer
    ever changes shape and this does not, crawlers letterbox the card."""

    html = head(built)
    assert tag(html, "property", "og:image:width") == str(card_mod.WIDTH)
    assert tag(html, "property", "og:image:height") == str(card_mod.HEIGHT)
    assert (card_mod.WIDTH, card_mod.HEIGHT) == (meta_mod.CARD_WIDTH, meta_mod.CARD_HEIGHT)


def test_card_says_what_the_site_is_rather_than_only_showing_it(card, spec):
    """The picture travels without the link often enough that the name has to
    be in the pixels. Assert the type column is actually inked."""

    left = np.asarray(card.convert("RGB"))[:, : card_mod.COLUMN_RIGHT]
    lit = (left.astype(int).sum(axis=2) > 300).sum()
    assert lit > 4000, "the type column is empty, so the card is unlabelled"
    assert spec.title and spec.tagline and spec.caption


def test_card_carries_the_honesty_line(spec):
    """SPEC 9 and CLAUDE.md: never let this read as a photograph. The caption
    is the only part of that wording which travels with a shared image."""

    caption = spec.caption.lower()
    assert "not photographic" in caption
    assert "not affiliated" in caption


def test_card_shows_the_telescope_on_the_right(card):
    """The model is composited beside the type, not behind it."""

    pixels = np.asarray(card.convert("RGB")).astype(int)
    right = pixels[:, card_mod.COLUMN_RIGHT :]
    # Plenty of mid-tone spacecraft, not just a starfield of single pixels.
    assert (right.sum(axis=2) > 200).sum() > 40_000


def test_card_type_stays_inside_its_column(card, spec):
    """A long word must shrink the type rather than run under the telescope.
    Wrapping alone does not save you: "Observatory" at the full title size is
    wider than the column all by itself."""

    from PIL import ImageDraw

    draw = ImageDraw.Draw(card)
    column = card_mod.COLUMN_RIGHT - card_mod.MARGIN
    for text, bold, size in (
        (spec.title, True, card_mod.TITLE_SIZE),
        (spec.tagline, False, card_mod.TAGLINE_SIZE),
        (spec.caption, False, card_mod.CAPTION_SIZE),
    ):
        font, lines = card_mod._fit(draw, text, bold, size, column)
        for line in lines:
            assert card_mod._text_w(draw, line, font) <= column, line


def test_a_very_long_title_shrinks_instead_of_overflowing(card):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(card)
    column = card_mod.COLUMN_RIGHT - card_mod.MARGIN
    font, lines = card_mod._fit(
        draw, "Extraordinarily Overlong Observatory", True, card_mod.TITLE_SIZE, column
    )
    assert font.size < card_mod.TITLE_SIZE
    for line in lines:
        assert card_mod._text_w(draw, line, font) <= column


def test_card_png_is_small_enough_that_a_crawler_waits_for_it(built):
    path = built / "og.png"
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(path).size == (1200, 630)
    assert len(data) < 60_000, f"{len(data)} bytes is slow for an unfurl"


# --- the default build ------------------------------------------------------
#
# This block is the regression guard for the bug that actually shipped. The
# share tags were correct and the card was fine; the deploy simply never set
# the build argument they depended on, so the live site served
# `og:image content="/og.png"` and the first link pasted into WhatsApp arrived
# without its picture. Nothing here may depend on configuration.


def test_a_build_with_nothing_configured_still_shares_absolutely(built_plain, facts):
    html = head(built_plain)
    expected = facts["site"]["origin"].rstrip("/")
    for attr, name in (
        ("property", "og:image"),
        ("property", "og:url"),
        ("name", "twitter:image"),
    ):
        value = tag(html, attr, name)
        assert value.startswith(f"{expected}/"), f"{name} is {value!r}, not absolute"


def test_a_build_with_nothing_configured_writes_a_sitemap(built_plain):
    assert (built_plain / "sitemap.xml").exists()
    assert "Sitemap:" in (built_plain / "robots.txt").read_text()


def test_the_origin_in_the_data_is_a_real_absolute_https_url(facts):
    origin = facts["site"]["origin"]
    assert origin.startswith("https://")
    assert not origin.endswith("/")
    assert "://" in origin and " " not in origin


def test_saying_nothing_and_saying_empty_are_different(facts):
    """The distinction the Dockerfile got wrong: interpolating an unset build
    argument passes an empty string, which reads as "home unknown"."""

    assert meta_mod.origin(facts, None) == facts["site"]["origin"]
    assert meta_mod.origin(facts, "") == ""
    assert meta_mod.origin(facts, "https://other.test/") == "https://other.test"


# --- absolute URLs ----------------------------------------------------------


def test_absolute_needs_an_origin_and_tolerates_a_missing_slash():
    site = meta_mod.Site(base_url=BASE)
    assert site.absolute("/og.png") == f"{BASE}/og.png"
    assert site.absolute("og.png") == f"{BASE}/og.png"


def test_without_an_origin_paths_stay_root_relative():
    """Root-relative, never bare. `content="og.png"` was the original bug: it
    resolves against the page URL, and unfurlers reject it outright."""

    site = meta_mod.Site()
    assert site.absolute("/og.png") == "/og.png"
    assert site.absolute("og.png") == "/og.png"


def test_a_trailing_slash_on_the_origin_does_not_double_up(built):
    assert tag(head(built), "property", "og:url") == f"{BASE}/"
    assert tag(head(built), "property", "og:image") == f"{BASE}/og.png"


@pytest.mark.parametrize(
    "attr,name",
    [
        ("property", "og:type"),
        ("property", "og:site_name"),
        ("property", "og:locale"),
        ("property", "og:title"),
        ("property", "og:description"),
        ("property", "og:url"),
        ("property", "og:image"),
        ("property", "og:image:width"),
        ("property", "og:image:height"),
        ("property", "og:image:alt"),
        ("name", "twitter:card"),
        ("name", "twitter:title"),
        ("name", "twitter:description"),
        ("name", "twitter:image"),
        ("name", "twitter:image:alt"),
        ("name", "description"),
    ],
)
def test_every_share_tag_is_present_and_filled(built, attr, name):
    value = tag(head(built), attr, name)
    assert value, f"missing {name}"


def test_the_picture_url_is_absolute_in_every_place_it_appears(built):
    html = head(built)
    for attr, name in (("property", "og:image"), ("name", "twitter:image")):
        value = tag(html, attr, name)
        assert value.startswith(f"{BASE}/"), f"{name} is not absolute: {value}"


def test_canonical_and_og_url_agree(built):
    html = head(built)
    canonical = re.search(r'<link rel="canonical" href="([^"]*)"', html).group(1)
    assert canonical == f"{BASE}/"
    assert tag(html, "property", "og:url") == canonical


def test_the_title_is_written_once_and_og_title_cannot_drift(built):
    html = (built / "index.html").read_text()
    titles = re.findall(r"<title>(.*?)</title>", html)
    assert len(titles) == 1
    assert titles[0] == tag(head(built), "property", "og:title")


def test_the_description_is_a_sentence_not_the_page_title(built, facts):
    description = tag(head(built), "name", "description")
    assert description == facts["site"]["share"]["description"]["text"]
    assert len(description.split()) >= 8
    assert tag(head(built), "property", "og:description") == description


def test_twitter_falls_back_to_the_large_card(built):
    assert tag(head(built), "name", "twitter:card") == "summary_large_image"


def test_the_alt_text_describes_the_picture(built, facts):
    alt = tag(head(built), "property", "og:image:alt")
    assert alt == facts["site"]["share"]["image_alt"]["text"]
    assert alt != facts["site"]["title"], "alt text is the title, so it says nothing"


# --- structured data --------------------------------------------------------


def test_jsonld_parses_and_agrees_with_the_tags(built):
    html = head(built)
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    node = json.loads(block)
    assert node["@type"] == "WebSite"
    assert node["url"] == tag(html, "property", "og:url")
    assert node["image"] == tag(html, "property", "og:image")
    assert node["name"] == tag(html, "property", "og:title")


def test_jsonld_cannot_close_its_own_script_element():
    site = meta_mod.Site(base_url=BASE)
    page = meta_mod.PageMeta(path="/", title="x", description="</script><b>ha</b>")
    assert "<" not in meta_mod.jsonld(site, page)


# --- robots and sitemap -----------------------------------------------------


def test_robots_always_ships_and_invites_everyone(built, built_without_origin):
    for out in (built, built_without_origin):
        text = (out / "robots.txt").read_text()
        assert "User-agent: *" in text
        assert "Allow: /" in text
        assert "Disallow: /\n" not in text


def test_robots_points_at_the_sitemap_only_when_there_is_one(built, built_without_origin):
    assert f"Sitemap: {BASE}/sitemap.xml" in (built / "robots.txt").read_text()
    assert "Sitemap:" not in (built_without_origin / "robots.txt").read_text()


def test_sitemap_is_well_formed_and_absolute(built):
    root = ET.fromstring((built / "sitemap.xml").read_text())
    ns = {
        "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "image": "http://www.google.com/schemas/sitemap-image/1.1",
    }
    locs = [element.text for element in root.findall("s:url/s:loc", ns)]
    assert locs == [f"{BASE}/"]
    images = [element.text for element in root.findall("s:url/image:image/image:loc", ns)]
    assert images == [f"{BASE}/og.png"]


def test_sitemap_lastmod_is_a_date_not_a_timestamp(built):
    root = ET.fromstring((built / "sitemap.xml").read_text())
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for element in root.findall("s:url/s:lastmod", ns):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", element.text), element.text


def test_no_sitemap_is_written_without_an_origin(built_without_origin):
    """A sitemap of relative locations is invalid, so none is better than one."""

    assert not (built_without_origin / "sitemap.xml").exists()
    assert (built_without_origin / "robots.txt").exists()


def test_building_a_sitemap_without_an_origin_is_an_error_not_a_bad_file():
    with pytest.raises(ValueError):
        meta_mod.sitemap_xml(meta_mod.Site())


def test_sitemap_escapes_urls():
    site = meta_mod.Site(
        base_url=BASE, pages=[meta_mod.PageMeta(path="/a&b", title="t", description="d")]
    )
    assert "/a&amp;b" in meta_mod.sitemap_xml(site)


def test_without_an_origin_the_page_still_names_its_card(built_without_origin):
    """Degraded, but not broken: the picture is still findable by a reader and
    by the more forgiving unfurlers."""

    html = head(built_without_origin)
    assert tag(html, "property", "og:image") == "/og.png"
    assert (built_without_origin / "og.png").exists()
