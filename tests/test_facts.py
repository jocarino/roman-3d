"""SPEC 13.4. Every displayed claim carries a source, and no copy escapes the
data file.

The second half is the one that actually decays. Copy has a way of creeping
into a template "just for now", where nobody ever finds it again to check it
against a source. So this walks the JavaScript and the HTML template looking for
sentences, and fails on anything that reads like prose written for a visitor.
"""

from __future__ import annotations

import json
import re

WEB = "web"
PROSE_WORDS = 4  # a string literal this long is a sentence, not an identifier

# Prose looks like words and punctuation. A CSS selector or an SVG viewBox has
# brackets, colons and digits in it, and is not something anybody reads.
PROSE_SHAPE = re.compile(r"^[A-Za-z][A-Za-z ,.'-]+$")


def walk_claims(facts: dict):
    """Yield (path, node) for every object that makes a claim on screen."""

    def visit(node, path):
        if isinstance(node, dict):
            if "text" in node and isinstance(node["text"], str):
                yield path, node
            for key, value in node.items():
                yield from visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from visit(value, f"{path}[{i}]")

    yield from visit(facts, "facts")


def test_every_claim_has_a_source(facts):
    missing = []
    for path, node in walk_claims(facts):
        source = node.get("source")
        if not source:
            missing.append(path)
            continue
        if source not in facts["sources"]:
            missing.append(f"{path} (unknown source id {source!r})")
    assert not missing, f"claims without a usable source: {missing}"


def test_every_source_has_a_url_and_label(facts):
    for key, entry in facts["sources"].items():
        assert entry.get("url", "").startswith("https://"), key
        assert entry.get("label"), key


def test_every_component_has_a_panel(facts, mapping):
    documented = {component["id"] for component in facts["components"]}
    promised = {component["id"] for component in mapping.components}
    assert promised == documented, "components.json and facts.json disagree"


def test_component_blurbs_are_short_enough(facts):
    """SPEC 8.3 caps a blurb at ninety words. Longer than that and nobody
    reads it standing in front of a spinning telescope."""

    for component in facts["components"]:
        words = len(component["blurb"]["text"].split())
        assert words <= 90, f"{component['id']} blurb is {words} words"


def test_components_have_facts_with_sources(facts):
    for component in facts["components"]:
        assert 1 <= len(component["facts"]) <= 4, component["id"]
        for fact in component["facts"]:
            assert fact["text"].strip()
            assert fact["source"] in facts["sources"]
        assert component["official"] in facts["sources"]


def test_lightpath_has_seven_steps(facts):
    steps = facts["lightpath"]["steps"]
    assert len(steps) == 7
    for step in steps:
        assert step["source"] in facts["sources"]


def test_house_style(facts):
    """No em dashes and no decorative middle dots in site prose (SPEC 9)."""

    offenders = []
    for path, node in walk_claims(facts):
        text = node["text"]
        if "—" in text or "·" in text:
            offenders.append(path)
    for key, value in facts["ui"].items():
        if "—" in value or "·" in value:
            offenders.append(f"facts.ui.{key}")
    assert not offenders, f"em dash or middle dot in: {offenders}"


def _string_literals(source: str) -> list[str]:
    """Every single or double quoted literal, with comments stripped first."""

    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    source = re.sub(r"(?m)\s//\s.*$", "", source)
    return re.findall(r"'([^'\\\n]{4,})'|\"([^\"\\\n]{4,})\"", source)


def test_no_visitor_copy_lives_in_javascript(repo_root, facts):
    """Developer-facing strings are fine. Sentences aimed at a visitor are not."""

    blob = json.dumps(facts, ensure_ascii=False)
    offenders = []
    for path in sorted((repo_root / WEB / "static" / "js").glob("*.js")):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            # Thrown errors and console output are for us, not for visitors.
            if stripped.startswith("//") or "throw " in line or "console." in line:
                continue
            for pair in _string_literals(line):
                literal = pair[0] or pair[1]
                if len(literal.split()) < PROSE_WORDS:
                    continue
                if not PROSE_SHAPE.match(literal):
                    continue
                if literal in blob:
                    continue
                offenders.append(f"{path.name}: {literal!r}")
    assert not offenders, "copy found outside facts.json:\n" + "\n".join(offenders)


def test_template_only_carries_placeholders(repo_root):
    """The template is structure. Anything a visitor reads arrives as a token."""

    template = (repo_root / WEB / "templates" / "index.html").read_text()
    body = re.sub(r"<!--.*?-->", "", template, flags=re.S)
    body = re.sub(r"<[^>]+>", "\n", body)
    body = re.sub(r"\{\{[A-Z_]+\}\}", "", body)
    leftovers = [line.strip() for line in body.splitlines() if len(line.split()) >= PROSE_WORDS]
    assert not leftovers, f"prose hardcoded in the template: {leftovers}"


def test_mission_countdown_is_sourced(mission):
    launch = mission["launch"]
    assert launch["source"].startswith("https://")
    assert launch["basis"].strip()
    assert launch["retrieved"]
    assert mission["no_js"].strip()


def test_about_carries_the_disclaimer(facts):
    disclaimer = facts["about"]["disclaimer"]["text"].lower()
    assert "not affiliated" in disclaimer
    assert "nasa" in disclaimer
    credit = facts["about"]["model_credit"]["text"]
    assert "Christopher R. Meaney" in credit
    assert "public domain" in credit.lower()
