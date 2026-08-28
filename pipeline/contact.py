"""M1 artifacts: hero frames at each candidate grid size, and the contact sheet.

The contact sheet is the gate. The source GLB has no named parts, only 36
materials, so the only honest way to decide which material is which component is
to render each one highlighted and look at all 36 at once. Nothing downstream
guesses; ``data/components.json`` is filled in from these tiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import palette as palette_mod
from . import render as render_mod
from .glb import Model
from .voxelize import VoxelModel, occupancy, voxelize

GRID_SIZES = (128, 192, 256)

LABEL_HEIGHT = 26
LABEL_BG = (19, 24, 32)
LABEL_FG = (207, 216, 227)
LABEL_ACCENT = (224, 168, 62)
SHEET_BG = (10, 13, 17)


@dataclass(frozen=True)
class Tile:
    material: str
    triangles: int
    voxels: int
    image: np.ndarray


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def hero(
    voxels: VoxelModel,
    pal: palette_mod.Palette,
    color_index: np.ndarray,
    view: str = "front",
    width: int = 320,
    height: int = 240,
    scale: int = 3,
    **kwargs,
) -> Image.Image:
    """One full-model frame in approximately final style."""

    frame = render_mod.render(
        voxels,
        pal,
        render_mod.SNAP_VIEWS[view],
        width,
        height,
        volume=occupancy(voxels),
        color_index=color_index,
        **kwargs,
    )
    return Image.fromarray(render_mod.upscale(frame.color, scale))


def contact_sheet(
    model: Model,
    voxels: VoxelModel,
    pal: palette_mod.Palette,
    color_index: np.ndarray,
    *,
    view: str = "front",
    tile_width: int = 220,
    tile_height: int = 165,
    scale: int = 2,
    columns: int = 6,
) -> Image.Image:
    """One tile per material, that material lit and the rest dropped back."""

    volume = occupancy(voxels)
    counts = np.bincount(voxels.primitive.astype(np.int64), minlength=len(voxels.materials))

    tiles: list[Tile] = []
    for index, prim in enumerate(model.primitives):
        frame = render_mod.render(
            voxels,
            pal,
            render_mod.THREE_QUARTER if view == "three-quarter" else render_mod.SNAP_VIEWS[view],
            tile_width,
            tile_height,
            volume=volume,
            color_index=color_index,
            highlight=index,
            stars=False,
        )
        tiles.append(
            Tile(
                material=prim.material,
                triangles=prim.triangle_count,
                voxels=int(counts[index]),
                image=render_mod.upscale(frame.color, scale),
            )
        )

    cell_w = tile_width * scale
    cell_h = tile_height * scale + LABEL_HEIGHT
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    name_font = _font(15)
    meta_font = _font(12)

    for i, tile in enumerate(tiles):
        col, row = i % columns, i // columns
        x, y = col * cell_w, row * cell_h
        sheet.paste(Image.fromarray(tile.image), (x, y))
        draw.rectangle([x, y + tile_height * scale, x + cell_w, y + cell_h], fill=LABEL_BG)
        draw.text(
            (x + 7, y + tile_height * scale + 4), f"{i:02d}", font=meta_font, fill=LABEL_ACCENT
        )
        draw.text(
            (x + 30, y + tile_height * scale + 3), tile.material, font=name_font, fill=LABEL_FG
        )
        draw.text(
            (x + 30, y + tile_height * scale + 15),
            f"{tile.triangles:,} tri   {tile.voxels:,} vox",
            font=meta_font,
            fill=(135, 145, 158),
        )
    return sheet


def build_all(model: Model, out_dir: Path, *, dilate: bool = False) -> dict[str, Path]:
    """Emit every M1 artifact: hero frames at each grid size, plus the sheet."""

    out_dir.mkdir(parents=True, exist_ok=True)
    pal = palette_mod.build()
    color_index = palette_mod.material_indices(model.material_names)
    written: dict[str, Path] = {}

    reference: VoxelModel | None = None
    for size in GRID_SIZES:
        voxels = voxelize(model, size, dilate=dilate)
        if size == 192:
            reference = voxels
        for view in ("front", "right", "top"):
            path = out_dir / f"hero-{size}-{view}.png"
            hero(voxels, pal, color_index, view=view).save(path)
            written[f"hero-{size}-{view}"] = path

    assert reference is not None
    sheet_path = out_dir / "contact-sheet.png"
    contact_sheet(model, reference, pal, color_index).save(sheet_path)
    written["contact-sheet"] = sheet_path
    return written
