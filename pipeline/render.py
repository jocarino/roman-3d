"""Offline pixel-art renderer: an orthographic voxel raycaster in numpy.

This exists twice on purpose. The browser renders the same voxels with Three.js
for interactivity; this one renders them headless for the M1 contact sheet, the
no-WebGL fallback frames and the social cards. Both read the same palette ramp
and the same shading constants, so the fallback frames look like the live site
rather than like a different project.

Raycasting rather than meshing, because a voxel grid raycasts trivially
(Amanatides and Woo grid traversal), gives exact face normals for free, and has
no seams to debug. It is offline, so it can afford to be slow and obviously
correct.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .palette import Palette
from .voxelize import VoxelModel, occupancy

# Key light in world space. Slightly off-axis so the three visible cube faces
# of any voxel land on three different shade steps.
KEY_LIGHT = np.array([0.55, 0.72, 0.42], dtype=np.float64)
AMBIENT = 0.34

# 4x4 ordered Bayer matrix, normalized to (-0.5, 0.5).
BAYER4 = (
    np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        dtype=np.float64,
    )
    / 16.0
    - 0.5
)

BACKGROUND = np.array([10, 13, 19], dtype=np.uint8)


def _outline_rgb(palette: Palette) -> np.ndarray:
    value = palette.outline.lstrip("#")
    return np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.uint8)


@dataclass(frozen=True)
class Camera:
    """Orthographic camera described the way the UI describes it."""

    azimuth: float  # degrees, 0 = looking down -z at the front
    elevation: float  # degrees, positive looks down from above
    zoom: float = 1.0

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        forward = np.array(
            [
                -math.cos(el) * math.sin(az),
                -math.sin(el),
                -math.cos(el) * math.cos(az),
            ],
            dtype=np.float64,
        )
        forward /= np.linalg.norm(forward)
        world_up = np.array([0.0, 1.0, 0.0])
        if abs(forward[1]) > 0.999:
            world_up = np.array([0.0, 0.0, 1.0])
        right = np.cross(forward, world_up)
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        return forward, right, up


# The five snap views. Named the way the buttons are labelled, per the
# plain-words rule; the set is a quiet nod to the NASA page's five thumbnails.
SNAP_VIEWS: dict[str, Camera] = {
    "front": Camera(azimuth=0.0, elevation=14.0),
    "right": Camera(azimuth=90.0, elevation=14.0),
    "back": Camera(azimuth=180.0, elevation=14.0),
    "left": Camera(azimuth=270.0, elevation=14.0),
    "top": Camera(azimuth=0.0, elevation=88.0),
}

# A three-quarter angle used for the contact sheet and the landing pose, where
# reading a part's shape matters more than the tidiness of an axis-aligned view.
THREE_QUARTER = Camera(azimuth=36.0, elevation=24.0)


@dataclass
class Frame:
    """A rendered frame, still at internal resolution."""

    color: np.ndarray  # (h, w, 3) uint8
    primitive: np.ndarray  # (h, w) int16, -1 where background
    depth: np.ndarray  # (h, w) float32, +inf where background


def _fit(volume_dims: tuple[int, int, int], camera: Camera, margin: float) -> tuple[float, float]:
    """Half-extents, in voxels, that just contain the grid from this angle."""

    nx, ny, nz = volume_dims
    corners = np.array(
        [[x, y, z] for x in (0, nx) for y in (0, ny) for z in (0, nz)], dtype=np.float64
    )
    centre = np.array([nx, ny, nz], dtype=np.float64) / 2.0
    _, right, up = camera.basis()
    rel = corners - centre
    return (
        float(np.abs(rel @ right).max()) * margin,
        float(np.abs(rel @ up).max()) * margin,
    )


def _traverse(
    volume: np.ndarray, origins: np.ndarray, direction: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Amanatides-Woo grid traversal for a bundle of parallel rays.

    Returns per-ray (primitive index or -1, face axis, ray distance).
    """

    dims = np.array(volume.shape, dtype=np.float64)
    n_rays = origins.shape[0]

    hit = np.full(n_rays, -1, dtype=np.int16)
    axis_hit = np.zeros(n_rays, dtype=np.int8)
    dist = np.full(n_rays, np.inf, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / direction
    inv[~np.isfinite(inv)] = np.inf

    t_lo = (0.0 - origins) * inv
    t_hi = (dims - origins) * inv
    t_near = np.minimum(t_lo, t_hi)
    t_far = np.maximum(t_lo, t_hi)
    t_enter = np.nanmax(t_near, axis=1)
    t_exit = np.nanmin(t_far, axis=1)

    live = np.flatnonzero(t_exit > np.maximum(t_enter, 0.0))
    if live.size == 0:
        return hit, axis_hit, dist

    entry_axis = np.argmax(np.nan_to_num(t_near[live], nan=-np.inf), axis=1).astype(np.int8)
    start = np.maximum(t_enter[live], 0.0) + 1e-6
    pos = origins[live] + direction[None, :] * start[:, None]

    voxel = np.floor(pos).astype(np.int64)
    np.clip(voxel, 0, (dims - 1).astype(np.int64), out=voxel)

    step = np.where(direction > 0, 1, -1).astype(np.int64)
    t_delta = np.abs(inv)
    boundary = voxel + (direction > 0).astype(np.int64)
    t_next = (boundary - pos) * inv[None, :]
    t_next[:, direction == 0] = np.inf

    travelled = start
    last_axis = entry_axis
    max_steps = int(dims.sum()) + 8

    for _ in range(max_steps):
        if live.size == 0:
            break
        found = volume[voxel[:, 0], voxel[:, 1], voxel[:, 2]]
        struck = found >= 0
        if struck.any():
            rays = live[struck]
            hit[rays] = found[struck]
            axis_hit[rays] = last_axis[struck]
            dist[rays] = travelled[struck]
            keep = ~struck
            live = live[keep]
            voxel, t_next, travelled = voxel[keep], t_next[keep], travelled[keep]
            last_axis = last_axis[keep]
            if live.size == 0:
                break

        axis = np.argmin(t_next, axis=1)
        rows = np.arange(live.size)
        travelled = t_next[rows, axis]
        voxel[rows, axis] += step[axis]
        t_next[rows, axis] += t_delta[axis]
        last_axis = axis.astype(np.int8)

        inside = np.all((voxel >= 0) & (voxel < dims.astype(np.int64)), axis=1)
        if not inside.all():
            live = live[inside]
            voxel, t_next, travelled = voxel[inside], t_next[inside], travelled[inside]
            last_axis = last_axis[inside]

    return hit, axis_hit, dist


def render(
    voxels: VoxelModel,
    palette: Palette,
    camera: Camera,
    width: int,
    height: int,
    *,
    volume: np.ndarray | None = None,
    color_index: np.ndarray | None = None,
    highlight: int | None = None,
    dither: bool = True,
    outline: bool = True,
    stars: bool = True,
    margin: float = 1.06,
) -> Frame:
    """Render the voxel model to an internal-resolution frame.

    ``highlight`` dims every primitive except the given one, which is what the
    M1 contact sheet needs: one tile per material, that material lit.
    """

    if volume is None:
        volume = occupancy(voxels)
    if color_index is None:
        raise ValueError("color_index is required")

    forward, right, up = camera.basis()
    half_w, half_h = _fit(voxels.grid.dims, camera, margin)

    # Fit the model to whichever screen axis is tighter, then honour zoom.
    scale = max(half_w / (width / 2), half_h / (height / 2)) / camera.zoom
    centre = np.array(voxels.grid.dims, dtype=np.float64) / 2.0

    xs = (np.arange(width) - (width - 1) / 2.0) * scale
    ys = ((height - 1) / 2.0 - np.arange(height)) * scale
    gx, gy = np.meshgrid(xs, ys)

    span = float(np.linalg.norm(np.array(voxels.grid.dims, dtype=np.float64)))
    origins = (
        centre[None, None, :]
        + gx[..., None] * right[None, None, :]
        + gy[..., None] * up[None, None, :]
        - forward[None, None, :] * span
    ).reshape(-1, 3)

    hit, axis_hit, dist = _traverse(volume, origins, forward)
    hit = hit.reshape(height, width)
    axis_hit = axis_hit.reshape(height, width)
    depth = dist.reshape(height, width).astype(np.float32)

    image = _shade(
        hit, axis_hit, palette, color_index, forward, highlight, dither, stars, width, height
    )
    if outline:
        image = _outline(image, hit, _outline_rgb(palette))

    if highlight is not None:
        solo = np.where(volume == highlight, np.int16(0), np.int16(-1))
        solo_hit, solo_axis, solo_dist = _traverse(solo, origins, forward)
        solo_hit = solo_hit.reshape(height, width)
        solo_axis = solo_axis.reshape(height, width)
        visible = solo_dist.reshape(height, width) <= depth + 1e-6
        image = _paint_xray(image, solo_hit, solo_axis, forward, palette, visible)
        depth = np.minimum(depth, solo_dist.reshape(height, width).astype(np.float32))

    return Frame(color=image, primitive=hit.astype(np.int16), depth=depth)


def _paint_xray(
    image: np.ndarray,
    solo_hit: np.ndarray,
    solo_axis: np.ndarray,
    forward: np.ndarray,
    palette: Palette,
    visible: np.ndarray,
) -> np.ndarray:
    """Draw one material in accent gold, dimmer where the shell hides it."""

    struck = solo_hit >= 0
    if not struck.any():
        return image

    height, width = solo_hit.shape
    normals = np.zeros((height, width, 3), dtype=np.float64)
    for axis in range(3):
        mask = struck & (solo_axis == axis)
        normals[mask, axis] = -np.sign(forward[axis]) if forward[axis] != 0 else 1.0

    key = KEY_LIGHT / np.linalg.norm(KEY_LIGHT)
    lambert = np.clip((normals * key[None, None, :]).sum(axis=2), 0.0, 1.0)
    level = np.clip(np.round((AMBIENT + (1 - AMBIENT) * lambert) * (palette.shades - 1)), 0, 3)
    shade = level.astype(np.int64)

    out = image.copy()
    front = struck & visible
    behind = struck & ~visible
    out[front] = palette.ramp[13, shade[front]]  # gold-lit
    out[behind] = palette.ramp[11, np.maximum(shade[behind] - 1, 0)]  # gold-deep, ghosted
    return out


def _shade(
    hit: np.ndarray,
    axis_hit: np.ndarray,
    palette: Palette,
    color_index: np.ndarray,
    forward: np.ndarray,
    highlight: int | None,
    dither: bool,
    stars: bool,
    width: int,
    height: int,
) -> np.ndarray:
    image = np.broadcast_to(BACKGROUND, (height, width, 3)).copy()
    if stars:
        image = _starfield(image)

    solid = hit >= 0
    if not solid.any():
        return image

    # The struck face's normal points back along the axis the ray crossed.
    normals = np.zeros((height, width, 3), dtype=np.float64)
    for axis in range(3):
        mask = solid & (axis_hit == axis)
        normals[mask, axis] = -np.sign(forward[axis]) if forward[axis] != 0 else 1.0

    key = KEY_LIGHT / np.linalg.norm(KEY_LIGHT)
    lambert = np.clip((normals * key[None, None, :]).sum(axis=2), 0.0, 1.0)
    intensity = AMBIENT + (1.0 - AMBIENT) * lambert

    steps = palette.shades
    level = intensity * (steps - 1)
    if dither:
        tile = np.tile(BAYER4, (height // 4 + 1, width // 4 + 1))[:height, :width]
        level = level + tile * 0.5
    shade = np.clip(np.round(level), 0, steps - 1).astype(np.int64)

    base = color_index[np.clip(hit, 0, None)].astype(np.int64)

    if highlight is not None:
        # Contact-sheet mode: everything becomes a dark ghost here; the
        # highlighted group is composited on top by an x-ray pass in render(),
        # because most of the source materials sit inside the shell and would
        # otherwise never appear on their own tile.
        base[solid] = 2
        shade[solid] = 0

    rgb = palette.ramp[base, shade]
    image[solid] = rgb[solid]
    return image


def _starfield(image: np.ndarray) -> np.ndarray:
    """Sparse single-pixel stars. Seeded, so frames are reproducible."""

    height, width = image.shape[:2]
    rng = np.random.default_rng(20270501)
    count = max(12, (height * width) // 900)
    ys = rng.integers(0, height, count)
    xs = rng.integers(0, width, count)
    tone = rng.choice(np.array([46, 62, 88, 130], dtype=np.uint8), count)
    image[ys, xs] = np.stack([tone, tone, np.minimum(tone.astype(np.int16) + 14, 255)], axis=1)
    return image


def _outline(image: np.ndarray, hit: np.ndarray, colour: np.ndarray) -> np.ndarray:
    """One-pixel dark rim wherever the silhouette meets the background."""

    solid = hit >= 0
    edge = np.zeros_like(solid)
    edge[1:, :] |= solid[1:, :] & ~solid[:-1, :]
    edge[:-1, :] |= solid[:-1, :] & ~solid[1:, :]
    edge[:, 1:] |= solid[:, 1:] & ~solid[:, :-1]
    edge[:, :-1] |= solid[:, :-1] & ~solid[:, 1:]
    out = image.copy()
    out[edge] = colour
    return out


def upscale(image: np.ndarray, factor: int) -> np.ndarray:
    """Nearest-neighbour upscale. Never interpolate; that is the whole style."""

    return np.repeat(np.repeat(image, factor, axis=0), factor, axis=1)
