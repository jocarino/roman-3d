"""SPEC 13.3. The bundle has to stay small, and has to read back as it wrote."""

from __future__ import annotations

import numpy as np

from pipeline import pack

BUDGET_BYTES = 1_500_000  # SPEC 12: 1.5 MB gzipped

# Regression window rather than an exact figure: the voxel count should only
# move when the grid, the sampling or the merge rule changes on purpose.
VOXEL_WINDOW = (118_000, 128_000)


def test_gzipped_size_is_within_budget(bundle):
    size = len(bundle.gzipped)
    assert size <= BUDGET_BYTES, f"bundle is {size:,} bytes gzipped"


def test_voxel_count_is_in_the_expected_window(voxels):
    low, high = VOXEL_WINDOW
    assert low <= voxels.count <= high, f"voxel count {voxels.count:,} left its window"


def test_header_round_trips(bundle):
    header, arrays = pack.unpack(bundle.payload)
    assert header["format"] == "pxob"
    assert header["version"] == pack.FORMAT_VERSION
    assert set(arrays) == {"x", "y", "z", "group", "color"}
    assert all(array.shape[0] == header["counts"]["voxels"] for array in arrays.values())


def test_arrays_match_the_model(bundle, voxels, groups):
    _, arrays = pack.unpack(bundle.payload)
    assert np.array_equal(arrays["x"], voxels.coords[:, 0])
    assert np.array_equal(arrays["y"], voxels.coords[:, 1])
    assert np.array_equal(arrays["z"], voxels.coords[:, 2])
    assert np.array_equal(arrays["group"], groups.astype(np.uint8))


def test_coordinates_are_sorted(bundle):
    """Sorted coordinates are what make the payload compress, and what make
    two runs of the pipeline produce the same bytes."""

    _, arrays = pack.unpack(bundle.payload)
    keys = (
        arrays["x"].astype(np.int64) * 1_000_000
        + arrays["y"].astype(np.int64) * 1_000
        + arrays["z"].astype(np.int64)
    )
    assert np.all(np.diff(keys) > 0), "coordinates are not strictly sorted"


def test_provenance_is_present(bundle, model):
    provenance = bundle.header["provenance"]
    assert provenance["source_sha256"] == model.sha256
    assert provenance["source_bytes"] == model.byte_length
    assert provenance["triangles"] == model.triangle_count
    assert provenance["source_origin"].startswith("https://")
    assert "NASA" in provenance["source_credit"]


def test_palette_ramp_is_complete(bundle):
    palette = bundle.header["palette"]
    assert len(palette["base"]) == 16
    assert len(palette["ramp"]) == 16 * len(palette["shades"])
    assert all(len(entry) == 3 for entry in palette["ramp"])


def test_groups_in_header_match_the_arrays(bundle):
    header, arrays = pack.unpack(bundle.payload)
    assert arrays["group"].max() < len(header["groups"])
    for group in header["groups"]:
        assert header["counts"]["groups"][group["id"]] > 0
