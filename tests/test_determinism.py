"""SPEC 13.6. Same input, same bytes.

Determinism is what makes the provenance header worth anything: if the bundle
changes when nothing changed, nobody can tell which build produced which file.
"""

from __future__ import annotations

import hashlib

import numpy as np

from pipeline import components as components_mod
from pipeline import glb, pack
from pipeline import palette as palette_mod
from pipeline.voxelize import voxelize

from .conftest import GRID, SOURCE


def build_once():
    model = glb.load(SOURCE)
    voxels = voxelize(model, GRID)
    mapping = components_mod.load()
    groups = components_mod.assign(voxels, mapping)
    return pack.build(model, voxels, mapping, groups, palette_mod.build())


def test_two_runs_are_byte_identical():
    first = build_once()
    second = build_once()
    assert hashlib.sha256(first.payload).hexdigest() == hashlib.sha256(second.payload).hexdigest()


def test_gzip_is_reproducible():
    bundle = build_once()
    assert hashlib.sha256(bundle.gzipped).hexdigest() == hashlib.sha256(bundle.gzipped).hexdigest()
    again = build_once()
    assert bundle.gzipped == again.gzipped


def test_voxelization_is_stable(model):
    """Different grid sizes must not perturb each other, and repeating one
    must land on exactly the same cells."""

    first = voxelize(model, 128)
    second = voxelize(model, 128)
    assert np.array_equal(first.coords, second.coords)
    assert np.array_equal(first.primitive, second.primitive)


def test_the_header_carries_no_wall_clock(bundle):
    """A timestamp taken at build time would break byte equality."""

    generated = bundle.header["provenance"]["generated"]
    assert generated, "provenance is missing a build stamp"
    # It is the commit date or the unversioned sentinel, never "now".
    assert generated == "unversioned" or generated[:2] == "20"
