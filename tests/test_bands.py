"""SPEC 13.5. The coronagraph band facts, pinned.

These were wrong once, in public, on the sibling project. The numbers below are
copied from SPEC 11 rather than re-derived, and this file exists so that they
cannot quietly drift back to the wrong set.
"""

from __future__ import annotations

import json
import re

SUPPORTED = {
    575: "10 percent",
    730: "15 percent",
    825: "10 percent",
}
INSTALLED_BUT_UNTESTED = {660: "15 percent"}

# The set that appears in no primary source and must never come back.
FORBIDDEN_PATTERNS = [
    r"\b835\b",
    r"660[^.]{0,40}\b6 percent",
    r"730[^.]{0,40}\b6 percent",
]


def band_table(facts) -> dict[int, dict]:
    return {band["nm"]: band for band in facts["lightpath"]["bands"]}


def test_exactly_four_filters_are_described(facts):
    bands = band_table(facts)
    assert set(bands) == set(SUPPORTED) | set(INSTALLED_BUT_UNTESTED)


def test_supported_bands_and_widths(facts):
    bands = band_table(facts)
    for nm, width in SUPPORTED.items():
        assert bands[nm]["supported"] is True, nm
        assert bands[nm]["width"] == width, nm


def test_660_is_installed_but_not_supported(facts):
    band = band_table(facts)[660]
    assert band["supported"] is False
    assert band["width"] == INSTALLED_BUT_UNTESTED[660]
    assert "never characterised" in band["role"].lower()


def test_only_band_one_is_a_requirement(facts):
    bands = band_table(facts)
    required = [nm for nm, band in bands.items() if band.get("requirement")]
    assert required == [575]


def test_the_cgi_panel_states_the_pinned_facts(facts):
    cgi = next(c for c in facts["components"] if c["id"] == "cgi")
    joined = " ".join(fact["text"] for fact in cgi["facts"])

    assert "575 nm" in joined and "730 nm" in joined and "825 nm" in joined
    assert "660 nm" in joined
    assert "never characterised on the ground" in joined
    assert "not a supported observing mode" in joined
    # "best effort" is a contractual term, and the copy has to say so.
    assert "best effort" in joined
    assert "contractual term" in joined
    assert "technology demonstration" in joined.lower()


def test_installed_not_absent(facts):
    """SPEC 11 is specific about the wording: installed, never tested."""

    blob = json.dumps(facts).lower()
    assert "installed, never tested" in blob
    assert "660 nm filter is absent" not in blob


def test_the_wrong_band_set_appears_nowhere(facts):
    blob = json.dumps(facts)
    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, blob), f"forbidden band spec matched {pattern!r}"


def test_no_observing_schedule_is_promised(facts):
    cgi = next(c for c in facts["components"] if c["id"] == "cgi")
    joined = " ".join(fact["text"] for fact in cgi["facts"]).lower()
    assert "not a published schedule" in joined


def test_launch_wording(mission):
    """SPEC 11 pinned 'by May 2027'. NASA moved the launch up nine months, and
    the mission page the site cites now gives a date and a time, so this pins
    the new one. The old commitment stays in the basis text as history."""

    assert mission["launch"]["target_utc"] == "2026-08-30T11:26:00Z"
    assert "30 August 2026" in mission["launch"]["display"]
    basis = mission["launch"]["basis"].lower()
    assert "no earlier than" in basis
    assert "may 2027" in basis, "the superseded commitment should still be explained"
    assert mission["launch"]["retrieved"] == "2026-08-28"
