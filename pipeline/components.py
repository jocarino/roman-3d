"""Apply the curated material to component mapping from ``data/components.json``.

The source model names materials, not parts, so this file is where a human's
reading of the M1 contact sheet turns into something the site can highlight.
Rules are evaluated in declaration order and the first match wins, which lets a
catch-all structure material be split by position: ``Afta-grey3-sm`` genuinely
runs the whole length of the observatory, so the barrel claims its forward end
before the bus claims the rest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .voxelize import VoxelModel

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "components.json"

_BOUNDS = {
    "x_min": (0, "min"),
    "x_max": (0, "max"),
    "y_min": (1, "min"),
    "y_max": (1, "max"),
    "z_min": (2, "min"),
    "z_max": (2, "max"),
}


@dataclass(frozen=True)
class Group:
    """A geometry group: the thing that highlights when you hover."""

    id: str
    label: str
    explode: tuple[float, float, float]
    rules: tuple[dict, ...]


@dataclass(frozen=True)
class Mapping:
    groups: tuple[Group, ...]
    components: tuple[dict, ...]
    raw: dict

    @property
    def group_ids(self) -> tuple[str, ...]:
        return tuple(g.id for g in self.groups)


def load(path: Path | str = DEFAULT_PATH) -> Mapping:
    raw = json.loads(Path(path).read_text())
    groups = tuple(
        Group(
            id=g["id"],
            label=g["label"],
            explode=tuple(float(v) for v in g["explode"]),
            rules=tuple(g["rules"]),
        )
        for g in raw["groups"]
    )
    ids = [g.id for g in groups]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate group id in components.json")
    for component in raw["components"]:
        if component["group"] not in ids:
            raise ValueError(f"component {component['id']} points at unknown group")
    return Mapping(groups=groups, components=tuple(raw["components"]), raw=raw)


def assign(voxels: VoxelModel, mapping: Mapping) -> np.ndarray:
    """Return a per-voxel group index. Raises if any voxel goes unclaimed."""

    world = voxels.grid.origin + (voxels.coords.astype(np.float64) + 0.5) * voxels.grid.size
    material_of = np.array(voxels.materials, dtype=object)[voxels.primitive.astype(np.int64)]

    out = np.full(voxels.count, -1, dtype=np.int16)
    for index, group in enumerate(mapping.groups):
        for rule in group.rules:
            match = (material_of == rule["material"]) & (out < 0)
            for key, (axis, kind) in _BOUNDS.items():
                if key in rule:
                    limit = float(rule[key])
                    match &= world[:, axis] <= limit if kind == "max" else world[:, axis] >= limit
            out[match] = index

    if (out < 0).any():
        orphans = sorted(set(material_of[out < 0].tolist()))
        raise ValueError(f"voxels with no component: materials {orphans}")
    return out


def coverage(voxels: VoxelModel, mapping: Mapping) -> dict[str, int]:
    """Voxel count per group. Used by the mapping-completeness test."""

    groups = assign(voxels, mapping)
    counts = np.bincount(groups.astype(np.int64), minlength=len(mapping.groups))
    return {g.id: int(counts[i]) for i, g in enumerate(mapping.groups)}
