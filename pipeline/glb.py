"""Minimal glTF 2.0 / GLB reader for the one model this project cares about.

The source model is Draco-compressed (``KHR_draco_mesh_compression`` is in
``extensionsRequired``), so every primitive's geometry lives in a Draco buffer
rather than in plain accessors. We decode with DracoPy and keep only what the
voxelizer needs: triangles, the material name, and the material base colour.

Deliberately not a general glTF loader. It asserts the shape of the file it
expects and fails loudly if a swapped asset does not match, which is half the
point of the source-pin test in ``tests/test_source_pin.py``.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import DracoPy
import numpy as np

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
DRACO_EXT = "KHR_draco_mesh_compression"


@dataclass(frozen=True)
class Primitive:
    """One material-delimited chunk of the mesh.

    The source GLB has no named component nodes, so a primitive is the smallest
    unit of geometry we can name. ``material`` is the semantic handle the whole
    component mapping hangs off.
    """

    index: int
    material: str
    base_color: tuple[float, float, float, float]
    positions: np.ndarray  # (V, 3) float32, world space
    triangles: np.ndarray  # (T, 3) uint32, indices into positions

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])


@dataclass(frozen=True)
class Model:
    """The parsed source model plus the provenance the bundle header carries."""

    path: Path
    sha256: str
    byte_length: int
    generator: str
    primitives: tuple[Primitive, ...]

    @property
    def triangle_count(self) -> int:
        return sum(p.triangle_count for p in self.primitives)

    @property
    def material_names(self) -> tuple[str, ...]:
        return tuple(p.material for p in self.primitives)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lo = np.min([p.positions.min(axis=0) for p in self.primitives], axis=0)
        hi = np.max([p.positions.max(axis=0) for p in self.primitives], axis=0)
        return lo.astype(np.float64), hi.astype(np.float64)


def _chunks(data: bytes) -> dict[int, bytes]:
    magic, version, declared = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("not a GLB file (bad magic)")
    if version != 2:
        raise ValueError(f"unsupported GLB version {version}")
    if declared != len(data):
        raise ValueError(f"GLB length header {declared} != file size {len(data)}")

    out: dict[int, bytes] = {}
    offset = 12
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        out[kind] = data[offset + 8 : offset + 8 + length]
        offset += 8 + length
    return out


def _node_transforms(gltf: dict) -> np.ndarray:
    """Resolve the scene graph to a single world matrix for the mesh node.

    The source model is a mesh node under an identity pivot, but resolving it
    properly means a re-exported source with a baked transform still lands in
    the same world grid.
    """

    nodes = gltf["nodes"]

    def local(node: dict) -> np.ndarray:
        if "matrix" in node:
            # glTF matrices are column-major.
            return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
        m = np.eye(4)
        if "scale" in node:
            m = np.diag([*node["scale"], 1.0]) @ m
        if "rotation" in node:
            x, y, z, w = node["rotation"]
            rot = np.array(
                [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
                    [0, 0, 0, 1],
                ],
                dtype=np.float64,
            )
            m = rot @ m
        if "translation" in node:
            t = np.eye(4)
            t[:3, 3] = node["translation"]
            m = t @ m
        return m

    world = {}

    def walk(idx: int, parent: np.ndarray) -> None:
        here = parent @ local(nodes[idx])
        world[idx] = here
        for child in nodes[idx].get("children", []):
            walk(child, here)

    roots = gltf["scenes"][gltf.get("scene", 0)]["nodes"]
    for root in roots:
        walk(root, np.eye(4))

    for idx, node in enumerate(nodes):
        if "mesh" in node:
            return world[idx]
    raise ValueError("no node references a mesh")


def _base_color(material: dict) -> tuple[float, float, float, float]:
    pbr = material.get("pbrMetallicRoughness", {})
    factor = pbr.get("baseColorFactor")
    if factor is None:
        # glTF default is opaque white; the source relies on it for solarback.
        factor = [1.0, 1.0, 1.0, 1.0]
    r, g, b, a = (float(v) for v in factor)
    return (r, g, b, a)


def load(path: str | Path) -> Model:
    """Parse the GLB at ``path`` into world-space triangle soup per material."""

    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    chunks = _chunks(raw)
    gltf = json.loads(chunks[CHUNK_JSON].decode("utf-8"))
    binary = chunks.get(CHUNK_BIN, b"")

    required = set(gltf.get("extensionsRequired", []))
    unsupported = required - {DRACO_EXT}
    if unsupported:
        raise ValueError(f"GLB requires unsupported extensions: {sorted(unsupported)}")

    meshes = gltf["meshes"]
    if len(meshes) != 1:
        raise ValueError(f"expected exactly 1 mesh, found {len(meshes)}")

    matrix = _node_transforms(gltf)
    linear = matrix[:3, :3]
    offset = matrix[:3, 3]
    views = gltf["bufferViews"]
    materials = gltf["materials"]

    primitives: list[Primitive] = []
    for i, prim in enumerate(meshes[0]["primitives"]):
        draco = prim.get("extensions", {}).get(DRACO_EXT)
        if draco is None:
            raise ValueError(f"primitive {i} is not Draco-compressed; unsupported here")
        view = views[draco["bufferView"]]
        start = view.get("byteOffset", 0)
        mesh = DracoPy.decode(binary[start : start + view["byteLength"]])

        points = np.asarray(mesh.points, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.uint32).reshape(-1, 3)
        world = (points @ linear.T) + offset

        material = materials[prim["material"]]
        primitives.append(
            Primitive(
                index=i,
                material=material.get("name", f"material-{prim['material']}"),
                base_color=_base_color(material),
                positions=world.astype(np.float32),
                triangles=faces,
            )
        )

    # Sort by material name so downstream ordering never depends on file order.
    primitives.sort(key=lambda p: (p.material, p.index))

    return Model(
        path=path,
        sha256=digest,
        byte_length=len(raw),
        generator=gltf.get("asset", {}).get("generator", ""),
        primitives=tuple(primitives),
    )
