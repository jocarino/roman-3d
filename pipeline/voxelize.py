"""Surface voxelization onto a grid shared by every primitive.

One grid for the whole model is the point: components voxelized independently
still interlock exactly, so the exploded view can pull them apart and the pieces
fit back together with no seams.

Method is barycentric supersampling. Each triangle is subdivided finely enough
that consecutive samples land at most half a voxel apart, which makes the
resulting shell 6-connected for any triangle the source contains. It is slower
than a scanline rasterizer and much harder to get wrong.

Where two primitives claim the same voxel, the one whose surface passes closest
to the voxel centre wins. Counting samples instead would simply hand every
contested cell to whichever primitive happened to be finely tessellated, which
in this model silently erased two materials entirely. Ties break on material
name, so the result never depends on iteration order.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .glb import Model

# Samples land at most this fraction of a voxel apart along any triangle edge.
SAMPLE_SPACING = 0.5

# Cap on samples generated in one vectorized batch, to bound peak memory.
_BATCH_SAMPLES = 4_000_000

# How many near-miss cells to remember per primitive for the rescue pass.
RESCUE_CANDIDATES = 8


@dataclass(frozen=True)
class Grid:
    """The shared world grid. Everything downstream is expressed in its units."""

    origin: np.ndarray  # (3,) float64 world position of voxel (0,0,0)'s min corner
    size: float  # edge length of one voxel, world units
    dims: tuple[int, int, int]

    @property
    def count(self) -> int:
        return self.dims[0] * self.dims[1] * self.dims[2]

    def world_to_voxel(self, points: np.ndarray) -> np.ndarray:
        return np.floor((points - self.origin) / self.size).astype(np.int64)

    def linear(self, idx: np.ndarray) -> np.ndarray:
        nx, ny, nz = self.dims
        return (idx[:, 0] * ny + idx[:, 1]) * nz + idx[:, 2]

    def unlinear(self, flat: np.ndarray) -> np.ndarray:
        nx, ny, nz = self.dims
        z = flat % nz
        y = (flat // nz) % ny
        x = flat // (nz * ny)
        return np.stack([x, y, z], axis=1)


@dataclass(frozen=True)
class VoxelModel:
    """The voxelized observatory: one entry per occupied cell, sorted."""

    grid: Grid
    coords: np.ndarray  # (N, 3) uint16
    primitive: np.ndarray  # (N,) uint8 index into materials
    materials: tuple[str, ...]

    @property
    def count(self) -> int:
        return int(self.coords.shape[0])


def make_grid(model: Model, long_axis_voxels: int) -> Grid:
    """Build the shared grid so the model's longest axis spans N voxels."""

    lo, hi = model.bounds()
    extent = hi - lo
    size = float(extent.max()) / long_axis_voxels
    dims = np.maximum(np.ceil(extent / size).astype(int), 1) + 1
    # Centre the model in the grid so nothing clips at the far edge.
    origin = lo - 0.5 * (dims * size - extent)
    return Grid(origin=origin, size=size, dims=(int(dims[0]), int(dims[1]), int(dims[2])))


def _lattice(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Barycentric sample lattice for a triangle subdivided ``n`` times."""

    i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    keep = (i + j) <= n
    return (i[keep] / n).astype(np.float64), (j[keep] / n).astype(np.float64)


def _sample_triangles(verts: np.ndarray, tris: np.ndarray, spacing: float) -> Iterator[np.ndarray]:
    """Yield batches of world-space points covering every triangle's surface."""

    v0 = verts[tris[:, 0]].astype(np.float64)
    e1 = verts[tris[:, 1]].astype(np.float64) - v0
    e2 = verts[tris[:, 2]].astype(np.float64) - v0
    e3 = e2 - e1

    longest = np.maximum(
        np.linalg.norm(e1, axis=1),
        np.maximum(np.linalg.norm(e2, axis=1), np.linalg.norm(e3, axis=1)),
    )
    steps = np.maximum(np.ceil(longest / spacing).astype(np.int64), 1)

    for n in np.unique(steps):
        rows = np.flatnonzero(steps == n)
        u, v = _lattice(int(n))
        per_tri = u.shape[0]
        chunk = max(1, _BATCH_SAMPLES // per_tri)
        for start in range(0, rows.shape[0], chunk):
            block = rows[start : start + chunk]
            pts = (
                v0[block, None, :]
                + u[None, :, None] * e1[block, None, :]
                + v[None, :, None] * e2[block, None, :]
            )
            yield pts.reshape(-1, 3)


def _rescue(best_prim: np.ndarray, fallback: dict[int, np.ndarray], total: int) -> None:
    """Give every primitive that lost all its cells one of its closest few back.

    The obvious version of this, taking each loser's single nearest cell, is
    wrong: that cell already belongs to someone, and if it was their only one
    the rescue erases them instead. On the real model at grid 192 that is not
    hypothetical, it happens between two materials. So walk each loser's
    candidates in distance order and take the first cell whose current holder
    can spare it, keeping the counts up to date as we go.
    """

    counts = np.bincount(best_prim[best_prim >= 0].astype(np.int64), minlength=total)
    for pindex in sorted(fallback):
        if counts[pindex] > 0:
            continue
        for flat in fallback[pindex].tolist():
            holder = int(best_prim[flat])
            if holder == pindex:
                break
            if holder >= 0 and counts[holder] <= 1:
                continue  # their last cell; leave it and try the next candidate
            if holder >= 0:
                counts[holder] -= 1
            best_prim[flat] = pindex
            counts[pindex] += 1
            break


def _reduce_min(keys: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Group ``values`` by ``keys`` and keep the minimum of each group."""

    order = np.argsort(keys, kind="stable")
    keys, values = keys[order], values[order]
    starts = np.flatnonzero(np.concatenate(([True], keys[1:] != keys[:-1])))
    return keys[starts], np.minimum.reduceat(values, starts)


def voxelize(model: Model, long_axis_voxels: int, dilate: bool = False) -> VoxelModel:
    """Voxelize every primitive onto one shared grid.

    ``dilate`` grows the shell by one voxel in the six axis directions. Thin
    plate geometry (the solar wings) can otherwise read as a sparkling
    single-voxel sheet when the camera orbits past it edge-on.
    """

    grid = make_grid(model, long_axis_voxels)
    nx, ny, nz = grid.dims
    spacing = grid.size * SAMPLE_SPACING

    best_dist = np.full(grid.count, np.inf, dtype=np.float32)
    best_prim = np.full(grid.count, -1, dtype=np.int16)
    # Each primitive's closest few cells, so nothing can be voted out entirely.
    # More than one, because the closest may belong to a primitive that has no
    # cell to spare, and taking it would just move the problem.
    fallback: dict[int, np.ndarray] = {}

    upper = np.array([nx - 1, ny - 1, nz - 1])
    for pindex, prim in enumerate(model.primitives):
        parts: list[tuple[np.ndarray, np.ndarray]] = []
        for points in _sample_triangles(prim.positions, prim.triangles, spacing):
            local = (points - grid.origin) / grid.size
            idx = np.floor(local).astype(np.int64)
            np.clip(idx, 0, upper, out=idx)
            offset = local - (idx + 0.5)
            parts.append(_reduce_min(grid.linear(idx), np.einsum("ij,ij->i", offset, offset)))

        if not parts:
            continue
        flats = np.concatenate([p[0] for p in parts])
        dists = np.concatenate([p[1] for p in parts])
        flats, dists = _reduce_min(flats, dists)

        # Nearest surface wins the cell. Sample counts would just hand every
        # contested voxel to whichever primitive happens to be finely tessellated.
        # Strict '<' means an earlier (alphabetically first) material keeps ties.
        win = dists < best_dist[flats]
        best_dist[flats[win]] = dists[win].astype(np.float32)
        best_prim[flats[win]] = pindex

        order = np.argsort(dists, kind="stable")[:RESCUE_CANDIDATES]
        fallback[pindex] = flats[order]

    _rescue(best_prim, fallback, len(model.primitives))

    if dilate:
        best_prim = _dilate(best_prim, grid)

    occupied = np.flatnonzero(best_prim >= 0)
    coords = grid.unlinear(occupied)
    prims = best_prim[occupied].astype(np.uint8)

    # Sort by (x, y, z) so the packed bundle is byte-identical run to run.
    order = np.lexsort((coords[:, 2], coords[:, 1], coords[:, 0]))
    return VoxelModel(
        grid=grid,
        coords=coords[order].astype(np.uint16),
        primitive=prims[order],
        materials=model.material_names,
    )


def _dilate(best_prim: np.ndarray, grid: Grid) -> np.ndarray:
    """Grow the shell one voxel along each axis, filling only empty cells."""

    nx, ny, nz = grid.dims
    vol = best_prim.reshape(nx, ny, nz)
    out = vol.copy()
    for axis in (0, 1, 2):
        for shift in (1, -1):
            moved = np.roll(vol, shift, axis=axis)
            # np.roll wraps; blank the wrapped face so nothing teleports.
            sl: list[slice | int] = [slice(None)] * 3
            sl[axis] = 0 if shift == 1 else -1
            moved[tuple(sl)] = -1
            gap = (out < 0) & (moved >= 0)
            out[gap] = moved[gap]
    return out.reshape(-1)


def occupancy(voxels: VoxelModel) -> np.ndarray:
    """Dense (nx, ny, nz) int16 volume of primitive indices, -1 for empty."""

    nx, ny, nz = voxels.grid.dims
    vol = np.full((nx, ny, nz), -1, dtype=np.int16)
    c = voxels.coords.astype(np.int64)
    vol[c[:, 0], c[:, 1], c[:, 2]] = voxels.primitive.astype(np.int16)
    return vol
