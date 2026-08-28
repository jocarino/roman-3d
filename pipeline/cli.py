"""Command line entry point for the offline pipeline.

uv run observatory info      what is in the source model
uv run observatory m1        contact sheet plus hero frames at each grid
uv run observatory bundle    the packed voxel bundle
uv run observatory frames    the no-WebGL orbit and the social card
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import components as components_mod
from . import contact, glb, pack
from . import palette as palette_mod
from . import render as render_mod
from .voxelize import VoxelModel, occupancy, voxelize

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "assets" / "source" / "roman-glb-a.glb"
DEFAULT_GRID = 192
ORBIT_FRAMES = 24


def load_model(path: Path) -> glb.Model:
    if not path.exists():
        raise SystemExit(f"source model not found: {path}")
    return glb.load(path)


def prepare(model: glb.Model, grid: int, dilate: bool = False):
    """Voxelize and apply the component mapping. Shared by every subcommand."""

    voxels = voxelize(model, grid, dilate=dilate)
    mapping = components_mod.load()
    groups = components_mod.assign(voxels, mapping)
    return voxels, mapping, groups


def cmd_info(args: argparse.Namespace) -> int:
    model = load_model(args.source)
    lo, hi = model.bounds()
    print(f"file        {model.path.name}  ({model.byte_length:,} bytes)")
    print(f"sha256      {model.sha256}")
    print(f"generator   {model.generator}")
    print(f"primitives  {len(model.primitives)}   materials {len(set(model.material_names))}")
    print(f"triangles   {model.triangle_count:,}")
    print(f"bounds      {np.round(lo, 2).tolist()} .. {np.round(hi, 2).tolist()}")

    voxels, mapping, groups = prepare(model, args.grid)
    print(f"\ngrid {args.grid}: dims {voxels.grid.dims}  voxel {voxels.grid.size:.4f}")
    print(f"occupied    {voxels.count:,}")
    counts = np.bincount(groups.astype(np.int64), minlength=len(mapping.groups))
    for i, group in enumerate(mapping.groups):
        share = 100 * counts[i] / max(voxels.count, 1)
        print(f"  {group.id:20s} {counts[i]:7,}  {share:5.1f}%  {group.label}")
    return 0


def cmd_m1(args: argparse.Namespace) -> int:
    model = load_model(args.source)
    out = args.out
    written = contact.build_all(model, out)
    for name, path in sorted(written.items()):
        print(f"{name:24s} {path}")

    # A component map alongside the material sheet: the same renders, coloured
    # by the grouping in data/components.json rather than by material.
    voxels, mapping, groups = prepare(model, DEFAULT_GRID)
    pal = palette_mod.build()
    swatches = np.array([9, 6, 13, 15, 7, 4], dtype=np.uint8)[: len(mapping.groups)]
    volume = np.full(voxels.grid.dims, -1, dtype=np.int16)
    coords = voxels.coords.astype(np.int64)
    volume[coords[:, 0], coords[:, 1], coords[:, 2]] = groups

    tiles = []
    for view in ("front", "left", "right"):
        frame = render_mod.render(
            voxels,
            pal,
            render_mod.SNAP_VIEWS[view],
            300,
            225,
            volume=volume,
            color_index=swatches,
            stars=False,
        )
        tiles.append(render_mod.upscale(frame.color, 2))
    path = out / "component-map.png"
    Image.fromarray(np.concatenate(tiles, axis=1)).save(path)
    print(f"{'component-map':24s} {path}")
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    model = load_model(args.source)
    voxels, mapping, groups = prepare(model, args.grid)
    pal = palette_mod.build()
    bundle = pack.build(model, voxels, mapping, groups, pal)
    written = pack.write(bundle, args.out)
    raw = written["raw"].stat().st_size
    packed = written["gz"].stat().st_size
    print(f"voxels {voxels.count:,}   raw {raw / 1024:.1f} KB   gzip {packed / 1024:.1f} KB")
    for name, path in written.items():
        print(f"  {name:4s} {path}")
    return 0


def orbit_frames(
    voxels: VoxelModel,
    pal: palette_mod.Palette,
    color_index: np.ndarray,
    out: Path,
    *,
    width: int = 320,
    height: int = 240,
    scale: int = 2,
    count: int = ORBIT_FRAMES,
) -> list[Path]:
    """One full turn, rendered offline for browsers without WebGL."""

    out.mkdir(parents=True, exist_ok=True)
    volume = occupancy(voxels)
    written = []
    for i in range(count):
        camera = render_mod.Camera(azimuth=360.0 * i / count, elevation=16.0)
        frame = render_mod.render(
            voxels, pal, camera, width, height, volume=volume, color_index=color_index
        )
        path = out / f"orbit-{i:02d}.png"
        Image.fromarray(render_mod.upscale(frame.color, scale)).save(path)
        written.append(path)
    return written


def cmd_frames(args: argparse.Namespace) -> int:
    model = load_model(args.source)
    voxels, _, _ = prepare(model, args.grid)
    pal = palette_mod.build()
    color_index = palette_mod.material_indices(voxels.materials)

    paths = orbit_frames(voxels, pal, color_index, args.out / "frames")
    print(f"{len(paths)} orbit frames -> {args.out / 'frames'}")

    # Social card, at the 1200x630 the crawlers expect.
    card = render_mod.render(
        voxels,
        pal,
        render_mod.THREE_QUARTER,
        300,
        158,
        volume=occupancy(voxels),
        color_index=color_index,
    )
    image = Image.fromarray(render_mod.upscale(card.color, 4)).resize((1200, 632), Image.NEAREST)
    card_path = args.out / "og.png"
    image.crop((0, 1, 1200, 631)).save(card_path)
    print(f"social card -> {card_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="observatory", description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--grid", type=int, default=DEFAULT_GRID)
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="report what the source model contains")
    info.set_defaults(func=cmd_info)

    m1 = sub.add_parser("m1", help="contact sheet and hero frames for the M1 gate")
    m1.add_argument("--out", type=Path, default=ROOT / "dist" / "m1")
    m1.set_defaults(func=cmd_m1)

    bundle = sub.add_parser("bundle", help="pack the voxel bundle")
    bundle.add_argument("--out", type=Path, default=ROOT / "dist" / "site" / "model")
    bundle.set_defaults(func=cmd_bundle)

    frames = sub.add_parser("frames", help="no-WebGL orbit frames and the social card")
    frames.add_argument("--out", type=Path, default=ROOT / "dist" / "site")
    frames.set_defaults(func=cmd_frames)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
