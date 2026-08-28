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

The build contract is [`SPEC.md`](SPEC.md); working rules for build sessions are
in [`CLAUDE.md`](CLAUDE.md).

## Quick start

```bash
uv venv && uv pip install -e ".[dev]"

uv run observatory info          # what is in the source model
uv run observatory m1            # contact sheet + hero frames for the M1 gate
uv run python web/build.py       # the whole site into dist/site
uv run pytest                    # the SPEC 13 suite
uv run ruff check . && uv run ruff format --check .
```

To look at it:

```bash
python3 -m http.server 8000 --directory dist/site
```

Add `?debug=1` to the URL to get a `window.observatory` handle for poking at
the renderer from the console.

## How it fits together

Heavy work offline, baked artifacts to the browser.

```
assets/source/roman-glb-a.glb          committed NASA GLB, Draco compressed
        |
        |  pipeline/glb.py             decode Draco, world-space triangles per material
        |  pipeline/voxelize.py        surface voxelization onto one shared grid
        |  pipeline/components.py      apply data/components.json
        |  pipeline/palette.py         16 base colours, 4 shade steps
        |  pipeline/pack.py            -> model/roman.pxob.gz   (about 47 KB)
        |  pipeline/render.py          -> 24 orbit frames, contact sheet, social card
        v
dist/site/                             static, no server logic
        web/static/js/scene.js         three.js, low-res target, posterize, dither, outline
        web/static/js/voxelmesh.js     visible cube faces -> one BufferGeometry
        data/facts.json                every displayed word, every source URL
```

The offline renderer in `pipeline/render.py` and the browser renderer in
`web/static/js/scene.js` are two implementations on purpose: one raycasts the
voxel grid headless, one rasterizes it with WebGL. They read the same palette
ramp out of the same bundle, so the no-WebGL fallback looks like the live site
rather than like a different project.

## Where things live

```
assets/source/   the committed NASA GLB, treated as immutable input
pipeline/        Python 3.11+, uv, ruff, typed. GLB in, bundle and renders out
web/             static site: template, vanilla ES modules, vendored three.js
data/            components.json (the mapping), facts.json (all copy), mission.json
tests/           source pin, mapping completeness, budgets, facts honesty, determinism
docs/            model-format.md, fonts.md
tools/           fetch-fonts.py
dist/            build output, gitignored
```

Three files carry the decisions:

- **`data/components.json`** maps the model's 36 materials to the seven
  components the UI talks about. Curated against renders, not against material
  names, which lie. Editing it needs no code change.
- **`data/facts.json`** holds every string a visitor reads, each claim beside
  its source URL. Tests fail if copy appears anywhere else.
- **`pipeline/palette.py`** holds the sixteen colours and the four shade steps.

## Notes worth knowing before you touch it

- The source GLB is **Draco-compressed**, so `DracoPy` is a hard dependency of
  parsing it at all.
- The model has **no named parts**. Its 36 primitives are split by material, and
  the material names are only loosely descriptive: `Afta-rear-disk` is the aft
  bulkhead, not the antenna. The mapping came from looking at renders.
- Three materials genuinely run the whole length of the observatory, so
  `components.json` supports splitting one by position along an axis.
- The pipeline is deterministic: same GLB and same config give byte-identical
  output. The build stamp is the git commit date, never the clock.
- `three.js` is vendored at an exact version in `web/static/vendor/three/`. No
  CDN, no bundler, no framework.

## Credits

3D model: NASA / Christopher R. Meaney, "Nancy Grace Roman Space Telescope (A)".
NASA 3D resources are public domain; credit NASA.

Fonts: Silkscreen and IBM Plex Mono, both SIL OFL 1.1. See
[`docs/fonts.md`](docs/fonts.md).

This site is not affiliated with, endorsed by, or produced by NASA, and uses no
NASA branding. NASA's own interactive tour of the observatory is at
<https://roman.gsfc.nasa.gov/interactive/>.
