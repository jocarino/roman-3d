"""Shared fixtures. The GLB parse and the voxelization are slow enough that
every test wanting them should share one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import components as components_mod
from pipeline import glb, pack
from pipeline import palette as palette_mod
from pipeline.voxelize import voxelize

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "source" / "roman-glb-a.glb"
DATA = ROOT / "data"
GRID = 192


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def model():
    return glb.load(SOURCE)


@pytest.fixture(scope="session")
def voxels(model):
    return voxelize(model, GRID)


@pytest.fixture(scope="session")
def mapping():
    return components_mod.load()


@pytest.fixture(scope="session")
def groups(voxels, mapping):
    return components_mod.assign(voxels, mapping)


@pytest.fixture(scope="session")
def bundle(model, voxels, mapping, groups):
    return pack.build(model, voxels, mapping, groups, palette_mod.build())


@pytest.fixture(scope="session")
def facts() -> dict:
    return json.loads((DATA / "facts.json").read_text())


@pytest.fixture(scope="session")
def mission() -> dict:
    return json.loads((DATA / "mission.json").read_text())
