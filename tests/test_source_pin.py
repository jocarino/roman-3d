"""SPEC 13.1. Pin the source model so an asset swap cannot pass unnoticed.

Every number here was measured from the committed GLB, not assumed. If one of
them changes, either the file was replaced or the parser broke, and both are
worth stopping the build over.
"""

from __future__ import annotations

import pytest

EXPECTED_PRIMITIVES = 36
EXPECTED_MATERIALS = 36
EXPECTED_TRIANGLES = 301_586
EXPECTED_BYTES = 2_672_000
EXPECTED_SHA256 = "f92b52b780eb0754a9ccefcec394194361fca59396b409e510beb7226326b471"
EXPECTED_GENERATOR = "Khronos glTF Blender I/O v4.2.57"

# From SPEC 4, rounded to a tenth of a model unit.
EXPECTED_BOUNDS = ((-177.8, -65.1, -103.5), (166.5, 65.4, 103.5))


def test_counts(model):
    assert len(model.primitives) == EXPECTED_PRIMITIVES
    assert len(set(model.material_names)) == EXPECTED_MATERIALS
    assert model.triangle_count == EXPECTED_TRIANGLES


def test_identity(model):
    assert model.byte_length == EXPECTED_BYTES
    assert model.sha256 == EXPECTED_SHA256
    assert model.generator == EXPECTED_GENERATOR


def test_bounds(model):
    low, high = model.bounds()
    for actual, expected in zip(low, EXPECTED_BOUNDS[0], strict=True):
        assert actual == pytest.approx(expected, abs=0.1)
    for actual, expected in zip(high, EXPECTED_BOUNDS[1], strict=True):
        assert actual == pytest.approx(expected, abs=0.1)


def test_every_material_has_geometry(model):
    for primitive in model.primitives:
        assert primitive.triangle_count > 0, primitive.material
        assert primitive.vertex_count > 0, primitive.material


def test_materials_are_sorted(model):
    """Primitive order must not depend on the order inside the file."""

    names = list(model.material_names)
    assert names == sorted(names)
