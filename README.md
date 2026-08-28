# Pixel Observatory

NASA's Roman Space Telescope, rebuilt voxel by voxel: an interactive 3D
pixel-art explorer of the observatory. Orbit it, pull it apart, and follow a
beam of starlight through the coronagraph to the three filters that could
measure the first true colour of an exoplanet.

Unofficial and not affiliated with or endorsed by NASA. The 3D geometry is
NASA's own public-domain model (NASA/Christopher R. Meaney, via
[NASA 3D resources](https://science.nasa.gov/3d-resources/nancy-grace-roman-space-telescope-a/));
the pixels are ours. Sibling project to the Exoplanet Palette site, which this
site's finale links into.

**Status: spec phase.** The build contract is [`SPEC.md`](SPEC.md); working
rules for build sessions are in [`CLAUDE.md`](CLAUDE.md). No code yet — the
first milestone is an offline voxelizer proof with a GO/NO-GO gate.

## Layout (per spec)

```
assets/source/   the committed NASA GLB (source of all geometry)
pipeline/        Python: GLB → voxel bundle + offline renders   (M1+)
web/             static site: renderer, UI                       (M2+)
data/            components.json, facts.json, mission.json       (M1+)
tests/           source pin, budgets, facts honesty              (M1+)
docs/            model format, font licences
```
