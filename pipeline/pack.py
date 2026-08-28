"""Pack the voxel model into the binary bundle the browser downloads.

Format is deliberately dull: a magic number, a JSON header, then five planar
arrays. Planar rather than interleaved because gzip finds far more to chew on in
a run of monotonically increasing x values than in the same numbers sprinkled
between colour bytes. See ``docs/model-format.md``.

Nothing here reads the clock. The build stamp comes from the git commit, so two
runs of the same pipeline over the same source produce byte-identical output,
which is what the determinism test checks.
"""

from __future__ import annotations

import gzip
import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import palette as palette_mod
from .components import Mapping
from .glb import Model
from .voxelize import VoxelModel

MAGIC = b"PXOB"
FORMAT_VERSION = 1

# Fixed gzip mtime; the header already carries real provenance.
_GZIP_MTIME = 0


@dataclass(frozen=True)
class Bundle:
    header: dict
    payload: bytes

    @property
    def gzipped(self) -> bytes:
        return gzip.compress(self.payload, compresslevel=9, mtime=_GZIP_MTIME)


def _git(*args: str) -> str:
    try:
        root = Path(__file__).resolve().parent.parent
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def provenance(model: Model) -> dict:
    """Where this bundle came from, in enough detail to reproduce it."""

    return {
        "source_file": model.path.name,
        "source_sha256": model.sha256,
        "source_bytes": model.byte_length,
        "source_generator": model.generator,
        "source_origin": "https://science.nasa.gov/3d-resources/nancy-grace-roman-space-telescope-a/",
        "source_credit": "NASA / Christopher R. Meaney. NASA 3D resources are public domain.",
        "pipeline_commit": _git("rev-parse", "HEAD") or "unversioned",
        # Commit date, not wall clock, so the bundle stays byte-identical.
        "generated": _git("log", "-1", "--format=%cI") or "unversioned",
        "triangles": model.triangle_count,
        "primitives": len(model.primitives),
    }


def build(
    model: Model,
    voxels: VoxelModel,
    mapping: Mapping,
    groups: np.ndarray,
    pal: palette_mod.Palette,
) -> Bundle:
    """Assemble the bundle. ``groups`` is the per-voxel group index."""

    color_index = palette_mod.material_indices(voxels.materials)[voxels.primitive.astype(np.int64)]
    counts = np.bincount(groups.astype(np.int64), minlength=len(mapping.groups))

    header = {
        "format": "pxob",
        "version": FORMAT_VERSION,
        "grid": {
            "dims": list(voxels.grid.dims),
            "voxel": voxels.grid.size,
            "origin": [float(v) for v in voxels.grid.origin],
        },
        "counts": {
            "voxels": voxels.count,
            "groups": {g.id: int(counts[i]) for i, g in enumerate(mapping.groups)},
        },
        "palette": {
            "base": pal.hex_base(),
            "shades": list(palette_mod.SHADE_STEPS),
            "ramp": [[int(v) for v in shade] for row in pal.ramp for shade in row],
            "outline": pal.outline,
        },
        "groups": [
            {"id": g.id, "label": g.label, "explode": list(g.explode)} for g in mapping.groups
        ],
        "components": [dict(c) for c in mapping.components],
        "arrays": [
            {"name": "x", "type": "uint16"},
            {"name": "y", "type": "uint16"},
            {"name": "z", "type": "uint16"},
            {"name": "group", "type": "uint8"},
            {"name": "color", "type": "uint8"},
        ],
        "provenance": provenance(model),
    }

    blob = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = b"".join(
        (
            np.ascontiguousarray(voxels.coords[:, 0], dtype="<u2").tobytes(),
            np.ascontiguousarray(voxels.coords[:, 1], dtype="<u2").tobytes(),
            np.ascontiguousarray(voxels.coords[:, 2], dtype="<u2").tobytes(),
            np.ascontiguousarray(groups, dtype="u1").tobytes(),
            np.ascontiguousarray(color_index, dtype="u1").tobytes(),
        )
    )
    payload = MAGIC + struct.pack("<HII", FORMAT_VERSION, len(blob), voxels.count) + blob + body
    return Bundle(header=header, payload=payload)


def unpack(payload: bytes) -> tuple[dict, dict[str, np.ndarray]]:
    """Read a bundle back. Used by the tests and by anyone poking at output."""

    if payload[:4] != MAGIC:
        raise ValueError("not a pxob bundle")
    version, header_len, count = struct.unpack_from("<HII", payload, 4)
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported bundle version {version}")
    start = 4 + 10
    header = json.loads(payload[start : start + header_len])
    body = payload[start + header_len :]

    arrays: dict[str, np.ndarray] = {}
    offset = 0
    for spec in header["arrays"]:
        width = 2 if spec["type"] == "uint16" else 1
        dtype = "<u2" if width == 2 else "u1"
        arrays[spec["name"]] = np.frombuffer(body, dtype=dtype, count=count, offset=offset).copy()
        offset += count * width
    return header, arrays


def write(bundle: Bundle, directory: Path, stem: str = "roman") -> dict[str, Path]:
    """Write both the raw bundle and its gzip, and report the sizes."""

    directory.mkdir(parents=True, exist_ok=True)
    raw = directory / f"{stem}.pxob"
    packed = directory / f"{stem}.pxob.gz"
    raw.write_bytes(bundle.payload)
    packed.write_bytes(bundle.gzipped)
    return {"raw": raw, "gz": packed}
