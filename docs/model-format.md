# The `.pxob` bundle format

The one file the browser downloads to draw the observatory. Produced by
`pipeline/pack.py`, read by `web/static/js/bundle.js`, version 1.

Two rules shape it. It has to be small enough to arrive quickly on a phone, and
two runs of the pipeline over the same source have to produce the same bytes,
because otherwise the provenance header in it means nothing.

## Layout

```
offset  size          contents
0       4             magic, ASCII "PXOB"
4       2             format version, uint16 little endian
6       4             header length in bytes, uint32 little endian
10      4             voxel count, uint32 little endian
14      headerLength  header, UTF-8 JSON
...     count * 2     x, uint16 little endian
...     count * 2     y, uint16 little endian
...     count * 2     z, uint16 little endian
...     count * 1     group index, uint8
...     count * 1     palette base colour index, uint8
```

Arrays are planar, not interleaved, and that is the single largest thing making
the file small. Coordinates are sorted by `(x, y, z)`, so the `x` array is a
long run of slowly increasing numbers and gzip eats it: at grid 192 the raw
payload is about 962 KB and the gzip is about 47 KB, thirty times smaller. The
same numbers sprinkled between colour bytes compress far worse.

The array order and types are described in the header rather than assumed, so a
reader can walk them without hard-coding the layout above.

## Header

```jsonc
{
  "format": "pxob",
  "version": 1,
  "grid": {
    "dims": [193, 74, 117],       // voxels along x, y, z
    "voxel": 1.7932,              // edge length of one voxel, source model units
    "origin": [-178.7, -65.8, -104.4]  // world position of voxel (0,0,0)'s min corner
  },
  "counts": { "voxels": 122845, "groups": { "sun-shield": 10632, ... } },
  "palette": {
    "base":   ["#0b0e13", ...],   // 16 base colours
    "shades": [0.42, 0.62, 0.82, 1.06],
    "ramp":   [[11,14,19], ...]   // 16 * 4 RGB triples, index = base * 4 + shade
  },
  "groups":     [ { "id": "sun-shield", "label": "...", "explode": [0, 1, 0] }, ... ],
  "components": [ { "id": "wfi", "group": "instrument-carrier" }, ... ],
  "arrays":     [ { "name": "x", "type": "uint16" }, ... ],
  "provenance": { ... }
}
```

`ramp` is the whole reason the browser and the offline renderer agree on colour.
Both index the same table with the same `(base, shade)` pair, so neither one is
computing a colour of its own. The web renderer uploads it as a 4 by 16 texture:
x is the shade, y is the base colour.

`groups` is geometry. `components` is the UI. They are not the same list:
the Wide Field Instrument and the Coronagraph Instrument are two components
pointing at one group, because NASA's public model is of the outside of the
observatory and there is no separate shape to highlight for each.

Group indices in the `group` array are positions in the `groups` list, so
reordering that list changes the meaning of already-built bundles. A test pins
the order for exactly that reason.

## Provenance

```jsonc
"provenance": {
  "source_file": "roman-glb-a.glb",
  "source_sha256": "f92b52...",
  "source_bytes": 2672000,
  "source_generator": "Khronos glTF Blender I/O v4.2.57",
  "source_origin": "https://science.nasa.gov/3d-resources/...",
  "source_credit": "NASA / Christopher R. Meaney. NASA 3D resources are public domain.",
  "pipeline_commit": "<git rev>",
  "generated": "<git commit date>",
  "triangles": 301586,
  "primitives": 36
}
```

`generated` is the commit date, never the wall clock. A build timestamp would
make every rebuild produce different bytes and quietly break the determinism
test, and it would tell you less than the commit does anyway.

The same block is written into an HTML comment at the top of `index.html`, so
a published page can always be traced back to the source model and the commit
that shaped it.

## Serving it

The pipeline writes both `roman.pxob` and `roman.pxob.gz`. The page fetches the
gzip directly and decompresses it with `DecompressionStream`, rather than
relying on the server being configured to compress. `bundle.js` sniffs the
magic number instead of trusting the extension, so if the server *does* send
`Content-Encoding: gzip` and the browser has already unwrapped it, the file is
used as is. If `DecompressionStream` is missing, the uncompressed sibling is
fetched instead.

## Reading one

```bash
uv run python -c "
from pipeline import pack
header, arrays = pack.unpack(open('dist/site/model/roman.pxob','rb').read())
print(header['counts'], arrays['x'][:8])
"
```
