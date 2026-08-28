"""SPEC 13.2. The material to component mapping has to be total and stable.

The failure this guards against is quiet: add a material, or rename one, and
some voxels stop belonging to any component. On the site that shows up as a
patch of the observatory that cannot be hovered, which nobody notices until
someone tries to click it.
"""

from __future__ import annotations

import numpy as np

from pipeline import components as components_mod
from pipeline import palette as palette_mod

# Every component the UI promises, from SPEC 8.3.
EXPECTED_COMPONENTS = {
    "sun-shield",
    "barrel",
    "optics",
    "wfi",
    "cgi",
    "antenna",
    "bus",
}


def test_every_material_is_claimed(model, mapping):
    claimed = {rule["material"] for group in mapping.groups for rule in group.rules}
    missing = set(model.material_names) - claimed
    assert not missing, f"materials with no component rule: {sorted(missing)}"

    unknown = claimed - set(model.material_names)
    assert not unknown, f"components.json names materials not in the model: {sorted(unknown)}"


def test_every_voxel_is_assigned(voxels, mapping):
    # components.assign raises if any voxel is unclaimed; this pins the count too.
    assigned = components_mod.assign(voxels, mapping)
    assert assigned.shape[0] == voxels.count
    assert (assigned >= 0).all()


def test_no_group_is_empty(voxels, mapping):
    coverage = components_mod.coverage(voxels, mapping)
    empty = [name for name, count in coverage.items() if count == 0]
    assert not empty, f"groups with no voxels: {empty}"


def test_components_match_the_spec(mapping):
    ids = {component["id"] for component in mapping.components}
    assert ids == EXPECTED_COMPONENTS


def test_every_component_points_at_a_real_group(mapping):
    group_ids = set(mapping.group_ids)
    for component in mapping.components:
        assert component["group"] in group_ids


def test_group_ids_are_stable(mapping):
    """Group order is the index baked into the bundle, so it must not drift."""

    assert mapping.group_ids == (
        "sun-shield",
        "barrel",
        "optics",
        "instrument-carrier",
        "antenna",
        "bus",
    )


def test_every_material_has_a_palette_colour(model):
    indices = palette_mod.material_indices(model.material_names)
    assert indices.shape[0] == len(model.primitives)
    assert indices.max() < len(palette_mod.BASE_COLORS)


def test_palette_map_has_no_strays():
    known = set(palette_mod.MATERIAL_COLORS)
    assert len(known) == len(palette_mod.MATERIAL_COLORS)


def test_explode_vectors_are_distinct(mapping):
    """Two groups sharing a direction would slide apart into each other."""

    vectors = [np.array(group.explode) for group in mapping.groups]
    for i, a in enumerate(vectors):
        for b in vectors[i + 1 :]:
            if np.allclose(a, 0) or np.allclose(b, 0):
                continue
            assert not np.allclose(a, b), "two groups explode along the same vector"
