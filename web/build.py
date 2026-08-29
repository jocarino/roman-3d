"""Build the static site into ``dist/site``.

Renders ``web/templates/index.html`` against ``data/facts.json`` and
``data/mission.json``, then copies the static tree and asks the pipeline for the
voxel bundle and the offline frames.

The template is filled by plain string substitution rather than by a templating
library, because the only thing being substituted is copy that already lives in
a JSON file. Every user-visible string on the finished page can be traced back
to ``data/facts.json``; there is no prose in here or in the template.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import card as card_mod  # noqa: E402
from pipeline import cli as pipeline_cli  # noqa: E402
from pipeline import components as components_mod  # noqa: E402
from pipeline import pack  # noqa: E402
from pipeline import palette as palette_mod  # noqa: E402
from web import meta as meta_mod  # noqa: E402

DATA = ROOT / "data"
STATIC = ROOT / "web" / "static"
TEMPLATE = ROOT / "web" / "templates" / "index.html"

FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">'
    '<rect width="16" height="16" fill="#0a0d13"/>'
    '<rect x="2" y="6" width="12" height="5" fill="#8794a3"/>'
    '<rect x="3" y="3" width="10" height="3" fill="#34407e"/>'
    '<rect x="11" y="7" width="3" height="3" fill="#e0a83e"/>'
    "</svg>"
)


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def source_url(facts: dict, key: str) -> str:
    entry = facts["sources"].get(key)
    return entry["url"] if entry else "#"


def source_label(facts: dict, key: str) -> str:
    entry = facts["sources"].get(key)
    return entry["label"] if entry else key


def cite(facts: dict, key: str, note: str | None = None) -> str:
    """The small superscript link that follows every claim."""

    label = source_label(facts, key)
    title = f"{label}. {note}" if note else label
    return (
        f'<a class="source-link" href="{esc(source_url(facts, key))}" target="_blank"'
        f' rel="noopener" title="{esc(title)}" aria-label="Source: {esc(title)}">?</a>'
    )


def view_buttons(facts: dict) -> str:
    order = ["front", "right", "back", "left", "top"]
    buttons = [
        f'<button type="button" class="view-button" data-view="{name}"'
        f' aria-pressed="false" accesskey="{i + 1}">{esc(facts["ui"][f"view_{name}"])}</button>'
        for i, name in enumerate(order)
    ]
    # The row wrapper lives in the template, so Reset can sit inside it.
    return "".join(buttons)


def parts_static(facts: dict, mapping) -> str:
    """The whole component library as plain HTML, for readers without JS."""

    shared_groups = {}
    for entry in mapping.raw["components"]:
        shared_groups.setdefault(entry["group"], []).append(entry["id"])

    chunks = []
    for component in facts["components"]:
        blurb = component["blurb"]
        facts_html = "".join(
            f"<li>{esc(fact['text'])}{cite(facts, fact['source'], fact.get('source_note'))}</li>"
            for fact in component["facts"]
        )
        official = facts["sources"].get(component["official"])
        official_html = (
            f'<p><a href="{esc(official["url"])}" target="_blank" rel="noopener">'
            f"{esc(facts['ui']['panel_official'])}</a></p>"
            if official
            else ""
        )
        shared_html = ""
        for ids in shared_groups.values():
            if len(ids) > 1 and component["id"] == ids[-1]:
                shared = facts["shared_geometry"]
                shared_html = (
                    f'<p class="shared-note">{esc(shared["text"])}'
                    f"{cite(facts, shared['source'])}</p>"
                )
        chunks.append(
            f'<article class="component">'
            f'<h3 class="component-name">{esc(component["name"])}</h3>'
            f'<p class="component-short">{esc(component["short"])}</p>'
            f'<p class="component-blurb">{esc(blurb["text"])}{cite(facts, blurb["source"])}</p>'
            f'<ul class="fact-list">{facts_html}</ul>'
            f"{shared_html}{official_html}"
            f"</article>"
        )
    return "".join(chunks)


def lightpath_static(facts: dict) -> str:
    data = facts["lightpath"]
    steps = "".join(
        f"<li><strong>{esc(step['title'])}</strong> {esc(step['text'])}"
        f"{cite(facts, step['source'], step.get('source_note'))}</li>"
        for step in data["steps"]
    )
    bands = "".join(
        f"<li>{band['nm']} nm, {esc(band['width'])}. {esc(band['role'])}"
        f"{'' if band['supported'] else ' Not a supported observing mode.'}</li>"
        for band in data["bands"]
    )
    return (
        f'<p class="overlay-body">{esc(data["intro"]["text"])}'
        f"{cite(facts, data['intro']['source'])}</p>"
        f'<ol class="fact-list">{steps}</ol>'
        f'<ul class="fact-list">{bands}</ul>'
    )


def about_body(facts: dict) -> str:
    order = ["what", "rendering", "model_credit", "disclaimer", "nasa_own"]
    return "".join(
        f'<p class="overlay-body">{esc(facts["about"][key]["text"])}'
        f"{cite(facts, facts['about'][key]['source'])}</p>"
        for key in order
        if key in facts["about"]
    )


def sources_list(facts: dict) -> str:
    items = "".join(
        f'<li><a href="{esc(entry["url"])}" target="_blank" rel="noopener">'
        f"{esc(entry['label'])}</a></li>"
        for entry in facts["sources"].values()
    )
    extra = []
    for link in facts.get("links", {}).values():
        if link.get("url"):
            extra.append(
                f'<li><a href="{esc(link["url"])}" target="_blank" rel="noopener">'
                f"{esc(link['label'])}</a></li>"
            )
    return f'<ul class="source-list">{items}{"".join(extra)}</ul>'


def finale_link(facts: dict) -> str:
    sibling = facts.get("links", {}).get("sibling", {})
    if not sibling.get("url"):
        return ""
    url = sibling["url"].rstrip("/") + sibling.get("path", "")
    return (
        f'<a class="action action-primary finale-link" href="{esc(url)}"'
        f' target="_blank" rel="noopener">{esc(facts["ui"]["lightpath_finale"])}</a>'
    )


def card_spec(facts: dict) -> card_mod.CardSpec:
    """Map the copy onto what the card renderer wants. The adapter lives here
    rather than in the pipeline so the renderer stays ignorant of the data
    file's shape, and so the copy keeps arriving from exactly one place."""

    share = facts["site"]["share"]
    return card_mod.CardSpec(
        title=facts["site"]["title"],
        tagline=facts["site"]["tagline"]["text"],
        caption=share["caption"]["text"],
    )


def render_page(
    facts: dict,
    mission: dict,
    mapping,
    provenance: dict,
    site: meta_mod.Site,
    page: meta_mod.PageMeta,
) -> str:
    ui = facts["ui"]
    values = {
        "TITLE": facts["site"]["title"],
        "TAGLINE": facts["site"]["tagline"]["text"],
        "INTRO": facts["site"]["intro"]["text"],
        "HONESTY": facts["site"]["honesty"]["text"],
        "PIXELS": facts["site"]["pixels"]["text"],
        "CANVAS_LABEL": ui["canvas_label"],
        "NOSCRIPT_NOTE": ui["noscript"],
        "COUNTDOWN_LABEL": mission["launch"]["label"],
        "COUNTDOWN_STATIC": mission["no_js"],
        "COUNTDOWN_BASIS": mission["launch"]["basis"],
        "COUNTDOWN_SOURCE_URL": mission["launch"]["source"],
        "COUNTDOWN_SOURCE_LABEL": mission["launch"]["source_label"],
        "LIGHTPATH_TITLE": facts["lightpath"]["title"],
        "ABOUT_TITLE": facts["about"]["title"],
    }
    for key, value in ui.items():
        values[f"UI_{key.upper()}"] = value
    values.update(meta_mod.share_values(site, page))

    html_out = TEMPLATE.read_text()
    for key, value in values.items():
        html_out = html_out.replace("{{" + key + "}}", esc(str(value)))

    raw = {
        # Already escaped for the script element by ``jsonld`` itself; running
        # it through ``esc`` would turn the quotes into entities and break it.
        "JSONLD": meta_mod.jsonld(site, page),
        "VIEW_BUTTONS": view_buttons(facts),
        "PARTS_STATIC": parts_static(facts, mapping),
        "LIGHTPATH_STATIC": lightpath_static(facts),
        "LIGHTPATH_FINALE_LINK": finale_link(facts),
        "ABOUT_BODY": about_body(facts),
        "SOURCES_LIST": sources_list(facts),
        "PROVENANCE": json.dumps(provenance, indent=2, sort_keys=True),
    }
    for key, value in raw.items():
        html_out = html_out.replace("{{" + key + "}}", value)

    leftover = [token for token in ("{{",) if token in html_out]
    if leftover:
        start = html_out.index("{{")
        raise SystemExit(f"unfilled template token near: {html_out[start : start + 40]!r}")
    return html_out


def build(out: Path, grid: int, source: Path, base_url: str = "") -> dict:
    facts = json.loads((DATA / "facts.json").read_text())
    mission = json.loads((DATA / "mission.json").read_text())
    mapping = components_mod.load()

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out)

    model = pipeline_cli.load_model(source)
    voxels, mapping_obj, groups = pipeline_cli.prepare(model, grid)
    pal = palette_mod.build()
    bundle = pack.build(model, voxels, mapping_obj, groups, pal)
    written = pack.write(bundle, out / "model")

    # The no-WebGL orbit comes from the same offline renderer as the card.
    pipeline_cli.cmd_frames(argparse.Namespace(source=source, grid=grid, out=out))

    colour_index = palette_mod.material_indices(voxels.materials)
    card = card_mod.render_card(voxels, pal, colour_index, card_spec(facts))
    card_path = card_mod.write_card(out / "og.png", card)

    for name in ("facts.json", "mission.json"):
        shutil.copyfile(DATA / name, out / name)
    (out / "favicon.svg").write_text(FAVICON)

    # The commit date, not the wall clock, so two builds of one commit agree.
    lastmod = bundle.header["provenance"]["generated"][:10]
    home = meta_mod.home(facts)
    site = meta_mod.Site(base_url=base_url.rstrip("/"), pages=[home])

    page = render_page(facts, mission, mapping, bundle.header["provenance"], site, home)
    (out / "index.html").write_text(page)

    (out / "robots.txt").write_text(meta_mod.robots_txt(site))
    if site.base_url:
        (out / "sitemap.xml").write_text(meta_mod.sitemap_xml(site, lastmod=lastmod))

    return {
        "index": out / "index.html",
        "bundle_raw": written["raw"],
        "bundle_gz": written["gz"],
        "voxels": voxels.count,
        "card": card_path,
        "base_url": site.base_url,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the static site.")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "site")
    parser.add_argument("--grid", type=int, default=pipeline_cli.DEFAULT_GRID)
    parser.add_argument("--source", type=Path, default=pipeline_cli.DEFAULT_SOURCE)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SITE_BASE_URL", ""),
        help="Canonical origin, for example https://example.com. Open Graph wants absolute "
        "URLs and most unfurlers drop a relative og:image, so a shared link with no origin "
        "set arrives without its picture. sitemap.xml is only written when this is given, "
        "because a sitemap of relative locations is invalid. Defaults to $SITE_BASE_URL.",
    )
    args = parser.parse_args(argv)

    result = build(args.out, args.grid, args.source, base_url=args.base_url)
    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"site      {args.out}")
    print(f"voxels    {result['voxels']:,}")
    print(f"bundle    {result['bundle_gz'].stat().st_size / 1024:.1f} KB gzipped")
    print(f"card      {result['card']} ({result['card'].stat().st_size / 1024:.1f} KB)")
    print(f"tree      {total / 1024 / 1024:.2f} MB on disk")
    if result["base_url"]:
        print(f"share     absolute at {result['base_url']}, sitemap.xml written")
    else:
        print(
            "share     no --base-url or $SITE_BASE_URL, so the share tags are relative\n"
            "          and no sitemap.xml was written. Most unfurlers will show the link\n"
            "          without its picture. Set it on the deploy."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
