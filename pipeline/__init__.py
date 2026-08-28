"""Pixel Observatory offline pipeline.

Turns NASA's Roman Space Telescope GLB into a baked voxel bundle plus the
offline renders the site falls back to. Everything here runs at build time; the
browser only ever sees the artifacts this package emits.
"""

__all__ = ["glb", "voxelize", "palette", "components", "pack", "render", "cli"]
