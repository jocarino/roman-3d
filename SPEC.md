# Pixel Observatory — build spec

**Working title:** Pixel Observatory (provisional; owner may rename)
**One-liner:** NASA's Roman Space Telescope, rebuilt voxel by voxel. An interactive
3D pixel-art explorer of the observatory, ending where our sibling site begins:
the instrument that will measure the first true colour of an exoplanet.
**Status:** spec approved for build. Built by an agent (Opus 5) following this
document plus `CLAUDE.md`. Spec author: Fable 5, 2026-08-28, with the source
model already downloaded and inspected (numbers below are verified, not assumed).

---

## 1. What this is, and why

NASA's own interactive (https://roman.gsfc.nasa.gov/interactive/) is an
image-map from another era: five fixed camera angles, click a part, get a page.
We are building the version that page wants to be: a real-time 3D voxel model
you can orbit freely, pull apart, and interrogate — rendered in a deliberate
pixel-art style that matches the CRT/retro design language of the Exoplanet
Palette site (the sibling project this one links to and from).

Positioning rules (non-negotiable):

- **Affectionate, unofficial companion.** The site never mocks or compares
  itself to NASA's pages. No "better than", no snark. NASA built the telescope;
  we built a tribute in voxels.
- **Clearly not NASA.** No NASA logos or insignia. The footer and about text
  state: unofficial, not affiliated with or endorsed by NASA; 3D model courtesy
  NASA/Christopher R. Meaney (public domain). Never imitate NASA branding.
- **Honest about what is real.** The geometry is NASA's real model. The colours
  and the light-path animation are ours: stylised, schematic, labelled as such.
  Honesty phrasing is a house rule inherited from the sibling site ("modelled,
  not photographed" is its whole thesis; ours is "NASA's geometry, our pixels").

## 2. Relationship to Exoplanet Palette

Two independent deploys, one family:

- Shared design language (see §9) so they read as siblings.
- This site's light-path finale (§8.5) ends on a real predicted planet colour
  from the palette catalogue and deep-links to the palette site's `/roman`
  target board ("the empty slot this instrument will fill").
- The palette site later adds one outbound link on `/roman` ("Explore the
  telescope itself →"). That change happens in the palette repo, not here;
  it is out of scope for this build.
- No shared code or data dependency at runtime. Anything taken from the palette
  project (a hex colour, a fact) is copied in at build time with provenance
  noted. Static means static.

## 3. Non-goals

- Not an encyclopedia. Seven component hotspots, not thirty. Short blurbs.
- No backend, no CMS, no accounts, no database. A static site.
- No replication of NASA's mission-science content (dark energy, WFI survey
  detail). One sentence and a link out is the ceiling.
- No photorealism. If a choice arises between "accurate render" and "great
  pixel art", pixel art wins; geometry stays true, surfaces are stylised.
- No interior coronagraph geometry. The source model is the observatory
  exterior only (verified, §4); the light path is a schematic overlay by
  design, and the UI says so.
- v1 ships desktop + mobile web only. No app, no WebXR.

## 4. Source model (verified 2026-08-28)

| Fact | Value |
|---|---|
| File | `Nancy Grace Roman Space Telescope (A).glb` |
| Committed at | `assets/source/roman-glb-a.glb` (2,672,000 bytes) |
| Origin | https://science.nasa.gov/3d-resources/nancy-grace-roman-space-telescope-a/ |
| Mirror | https://github.com/nasa/NASA-3D-Resources (3D Models/Nancy Grace Roman Space Telescope (A)) |
| Credit | NASA / Christopher R. Meaney; NASA 3D resources are public domain (credit NASA) |
| Generator | Khronos glTF Blender I/O v4.2.57 |
| Structure | 2 nodes, **1 mesh, 36 primitives, 36 materials**, 301,586 triangles |
| Bounding box | x −177.8..166.5, y −65.2..65.4, z −103.5..103.5 (long axis = x, solar array span) |

**The critical structural fact:** the GLB has no named component nodes. It is
one mesh whose 36 primitives are split **by material**, and the material names
are semantic. Component segmentation therefore works by grouping primitives by
material. Verified material names (prefix "Afta" = AFTA, the 2012 Astrophysics
Focused Telescope Assets program whose donated 2.4 m mirror became WFIRST, then
Roman — worth a hotspot fact):

```
Afta-black-sm, Afta-blackout, Afta-blackout2,
Afta-bridgework-bronze, Afta-bridgework-silver, Afta-bridgework-underside,
Afta-grey1-sm, Afta-grey2-sm, Afta-grey3-sm,
Afta-hood, Afta-Instrument1-sm, Afta-lens,
Afta-rear-dish white, Afta-rear-disk, Afta-rear-diskcenter, Afta-rear-side-panels,
Afta-schnoozle-inside, Afta-schnoozle-out, Afta-schnoozle-rear-out,
Afta-silver1-fl, Afta-solar1, Afta-solar22, Afta-solar33, Afta-solar44,
Afta-solar55, Afta-solar66, Afta-solar77, Afta-solarback, Afta-solartop-base,
Afta-white reflector, Default, MTL28, MTL29, MTL30, MTL4, MTL44
```

The material → logical-component mapping is **curated by a human against
renders** (M1 produces a contact sheet for exactly this; §14). Do not guess the
mapping blind and do not ship a mapping the owner has not eyeballed. Candidate
grouping to start from (to be confirmed visually):

- `solar1..77, solarback, solartop-base` → Solar Array Sun Shield
- `hood, schnoozle-*` → telescope barrel / aperture shade
- `lens` → telescope aperture
- `bridgework-*` → truss / Outer Barrel Assembly structure
- `rear-dish*, rear-disk*` → high-gain antenna
- `Instrument1-sm, rear-side-panels` → instrument carrier (WFI + CGI live here)
- `grey*, black*, Default, MTL*` → spacecraft bus / unassigned (inspect)

## 5. Architecture

Two-stage, mirroring the sibling project's philosophy — heavy work offline,
the browser gets baked artifacts:

```
pipeline/   Python 3.11+, uv, ruff, typed.
            parse GLB → voxelize per primitive → apply component mapping
            → quantize colours to palette → pack → emit web/static/model bundle
            + PNG contact sheets + no-WebGL fallback frames.
web/        Static site. index.html + vanilla JS modules + Three.js (vendored,
            exact version committed). No framework, no bundler required;
            plain ES modules. A tiny Python build step (Jinja2 optional) may
            stamp facts/countdown data into the page.
data/       components.json (curated mapping), facts.json (all copy + sources),
            mission.json (launch date etc., each field sourced).
tests/      pytest: pipeline regression + content honesty tests (§13).
```

## 6. Voxel data spec

- Voxelize each primitive separately on a **shared world grid** so components
  interlock exactly. Target grid: **long axis 192 voxels** (≈1.8 units/voxel);
  M1 also emits 128 and 256 for comparison and the owner picks by eye.
  Surface voxelization (shell), not solid fill, except thin parts must be
  watertight enough to not sparkle when orbiting (dilate one voxel if needed).
- Per voxel: `(x, y, z, component_id, color_index)`. Colour comes from the
  source material's base colour quantized to the site palette (§9); component_id
  from `data/components.json`.
- Pack as a binary buffer (e.g. z-slice RLE or sorted 16-bit coords), served
  gzipped. **Budget: ≤ 1.5 MB gzipped** for the 192 grid. JSON header with
  grid dims, palette, component table; binary body. Document the format in
  `docs/model-format.md`.
- Determinism: same GLB + same config ⇒ byte-identical output (sort before
  packing). The bundle carries a provenance header: source file hash, pipeline
  git commit, generation date (same convention as the sibling's planets.json).

## 7. Renderer spec

- Three.js, **vendored at an exact pinned version** in `web/static/vendor/`
  (no CDN: the site must work offline-built and deploys must be reproducible).
- Geometry: merge visible voxel faces into one BufferGeometry per component
  (greedy meshing optional if budgets need it; start naive, measure).
  301k source triangles become ~tens of thousands of quads; this must hit
  **60 fps on a mid-range phone**, and will.
- Camera: **orthographic**. Pixel-art reads orthographic.
- The pixel look (this is the identity of the whole site, get it right):
  1. Render to a low-res offscreen target — internal height ≈ **240 px**
     (tune 200–320) — then upscale to the viewport with **nearest-neighbour**.
  2. Flat shading, one key light + ambient, luminance **quantized to 3–4
     steps** per material colour (posterized), optional 4×4 ordered-Bayer
     dither on the step boundaries.
  3. Optional 1-px dark outline pass on silhouette edges (toggleable; decide
     by eye in M2).
  4. Subtle CRT scanline/vignette overlay consistent with the sibling site;
     must respect `prefers-reduced-motion` and never harm legibility.
- Background: near-black with a sparse starfield (single-rect stars, the
  sibling's technique). No nebula art.

## 8. UX spec

### 8.1 Landing state
Full-viewport canvas. The observatory slowly auto-orbits until first
interaction. Title, one-line tagline, and the **launch countdown** (from
`data/mission.json`; the only ticking element). A short "what am I looking
at" line with an `[i]` reveal. No scroll required to reach the model; all
secondary content lives in panels/overlays.

### 8.2 Camera controls
- Drag to orbit, wheel/pinch to zoom, double-tap to reset. Inertia, clamped
  zoom, no roll.
- **Five snap-view buttons: Front / Right / Back / Left / Top** — a deliberate,
  quiet homage to the NASA page's five thumbnails (never explained on-site).
  Buttons animate the camera; each has a keyboard shortcut (1–5).
- Full keyboard support: arrows orbit, +/- zoom, buttons focusable.
- `prefers-reduced-motion`: no auto-orbit, no inertia, snap transitions cut.

### 8.3 Component mode (default)
- Hover (desktop) / tap (mobile) highlights a component group: it lifts to
  full brightness, everything else drops one shade. Component name appears
  as a pixel-font label.
- Click/tap opens a side panel (desktop: right rail; mobile: bottom sheet):
  component name, plain-English blurb (≤ 90 words), 2–4 facts each with a
  visible source link, and one "official page" link out to NASA. Content
  entirely from `data/facts.json` — no copy hardcoded in JS or HTML.
- Exactly **7 components** in v1: Solar Array Sun Shield · Telescope barrel &
  aperture cover · Primary mirror story (the AFTA/donated-mirror history) ·
  Wide Field Instrument · **Coronagraph Instrument (CGI)** · High-gain antenna ·
  Spacecraft bus. (WFI and CGI share housing geometry in the model; their
  hotspots may attach to the same group with an explicit note.)

### 8.4 Exploded view
A slider (label: "Pull it apart") that translates each component group
outward along curated per-component vectors (stored in `components.json`).
Fully reversible, works during orbit, snaps back on double-tap. Reduced
motion: slider still works, transitions are instant.

### 8.5 Light-path mode — "Follow the light" (the signature)
A guided, step-through sequence (Next/Back buttons, not a timeline scrub;
each step is one idea):

1. Light from a star system enters the aperture — two beams drawn: the star's
   (bright) and the planet's (faint, 1 px).
2. Into the instrument bay. **Overlay switches to schematic**: a flat,
   oscilloscope-style diagram drawn over a dimmed cutaway view, explicitly
   labelled "schematic — the real instrument is inside; the 3D model shows
   only the outside".
3. The coronagraph masks eat the starlight; the planet's beam survives.
4. The filter wheel: **four filters drawn, one greyed out** — 575, 660
   (greyed, "installed, never characterised on the ground"), 730, 825 nm.
5. The detector counts photons through each supported filter → three numbers.
6. The three numbers become a colour: show a real planet's Roman-view swatch
   (hex + planet name from the palette catalogue, copied into `facts.json`
   with provenance at build time; owner picks the hero planet, see §16).
7. Finale card: "That colour is a prediction. Roman turns predictions into
   measurements." → deep link to the palette site's `/roman` board.

Every step's copy lives in `facts.json` with sources. The CGI facts in §11
are load-bearing here; do not paraphrase them loosely.

### 8.6 About / credits
One overlay (not a separate page): what the site is, NASA model credit +
public-domain note, unofficial disclaimer, sibling-site link, source-code
link, and the full source list rendered from `facts.json` (every fact's
source appears here too, palette-site `/credits` style).

## 9. Design language (port of the sibling site's retro spec)

- **Square corners everywhere.** No border-radius.
- **Hard offset shadows** (solid, no blur) on panels and buttons.
- **Pixel/mono typography**: pixel font for labels/headers (self-hosted,
  licence checked into `docs/`), monospace for body/data. No system sans.
- **One accent colour** carries all interactivity (hovers, active states,
  the `[i]` buttons, links). Base surfaces are dark greys/near-black.
- **Model palette**: quantize the GLB's material colours to a curated ramp
  (solar-panel blue-black, thermal-blanket gold/bronze, structure greys,
  white dish) of ~16 entries so the render reads as intentional pixel art,
  not compressed truth. The palette file is data (`pipeline/palette.py`),
  documented, and shared with the schematic overlay.
- **Dual audience** (hard requirement inherited from the sibling): every
  control labelled in plain words ("Pull it apart", "Follow the light",
  "Front"), never jargon-only; `[i]` reveals for anything subtle; technical
  terms get a plain-English gloss in the panel copy.
- **Copy voice**: no em dashes and no decorative middle dots in site prose
  (data rows exempt); never frame the site against other sites or artists;
  "modelled/schematic" honesty wording wherever a stylisation could be
  mistaken for fact.

## 10. Accessibility & fallbacks

- Full keyboard operation of every mode; visible focus states in the accent.
- All interactive elements have aria labels; panels are proper dialogs;
  countdown has `aria-live="off"` (matches sibling convention).
- **No-WebGL fallback**: the pipeline pre-renders a 24-frame orbit PNG
  sequence (at final pixel style); the page detects missing WebGL and swaps
  in a scrubbable/auto-playing frame viewer. Hotspot panels still work from
  a static front view with an image map. This also serves as the
  social/OG imagery source.
- `prefers-reduced-motion` honoured throughout (§7, §8.2, §8.4).
- Touch targets ≥ 44 px; the whole UI works at 390 px wide (test via the
  iframe harness technique, since desktop Chrome won't shrink that far).

## 11. Pinned facts (copy these exactly; do not re-derive, do not "fix")

These were hard-won in the sibling project; getting them wrong there produced
real published errors. A test pins them (§13).

- Roman CGI supports **three** visible bandpasses: **575 nm (10% width,
  imaging + polarimetry), 730 nm (15%, slit + R~50 prism spectroscopy),
  825 nm (10%, wide-field imaging)**. Source: Roman CGI Primer (CPP,
  8 Jan 2025) mode table.
- A **fourth filter at 660 nm (15%)** is physically installed on the CFAM
  filter wheel but was **never characterised on the ground**, so it is not a
  supported observing mode. Wording: "installed, never tested", not "absent".
- **Only Band 1 (575 nm) with the hybrid Lyot coronagraph is a formal
  requirement**; the other bands are "best effort" — a contractual term, not
  a forecast that they won't happen.
- Never use the old wrong band set (660/6%, 730/6%, 835/15%). It appears in
  no primary source.
- CGI is a **technology demonstration**, not a survey instrument. Which
  planets it observes, and when, is not a published schedule.
- Launch: **by May 2027** (NASA, as of 2026-08; store date + retrieval date +
  source URL in `mission.json`; the countdown must state its source in the
  `[i]` reveal, and the page must degrade gracefully to plain text without JS).
- The telescope's 2.4 m primary mirror came to NASA via the **AFTA** program
  (repurposed National Reconnaissance Office hardware); the mission was named
  **WFIRST** until being renamed for Nancy Grace Roman in 2020. (This is why
  the GLB's materials all say "Afta".)
- No exoplanet has ever had its visible-light colour measured; Roman's CGI
  could be the first instrument to do it. (The sibling site's `/roman` board
  is the running scoreboard for this.)

## 12. Performance budgets

- Total transfer on first load **≤ 3.0 MB** (voxel bundle ≤ 1.5 MB gz,
  Three.js ~150 KB gz, everything else lean).
- 60 fps orbit on a mid-range phone (throttled-CPU DevTools check in CI notes
  at minimum; manual device check before ship).
- Interactive < 2 s on desktop broadband; the canvas may show the fallback
  front-view PNG as a poster while the bundle streams.
- Lighthouse: no accessibility violations.

## 13. Testing

`pytest` in `tests/`, run in CI:

1. **Source pin**: parsing `assets/source/roman-glb-a.glb` yields exactly
   36 primitives / 36 materials / 301,586 triangles (guards silent asset swaps).
2. **Mapping completeness**: every primitive maps to a component in
   `components.json`; no component is empty; ids are stable.
3. **Bundle budget**: gzipped model bundle ≤ 1.5 MB; format header parses;
   voxel count within expected band (regression window, not exact).
4. **Facts honesty**: every fact and blurb in `facts.json` has a non-empty
   `source` URL; every component in §8.3 has a panel; no copy string lives
   outside `facts.json` (grep templates/JS for known blurb sentinels).
5. **Band-spec pin**: the 575/730/825 + 660-installed-untested facts appear
   verbatim (§11) and the wrong sets (575/660/730/825-as-supported, or the
   old 6%/6%/15% widths) appear nowhere.
6. **Determinism**: two pipeline runs produce byte-identical bundles.

## 14. Milestones

- **M1 — Voxelizer proof + contact sheet (GO/NO-GO gate).**
  CLI: GLB in → voxel grids at 128/192/256 → offline renders: one full-model
  hero frame per grid size in approximate final style, plus a **contact sheet
  of every material group rendered highlighted** (36 tiles, labelled).
  Owner eyeballs: picks grid size, labels the material→component mapping,
  and decides the project looks good enough to continue. **No web code before
  this gate passes.**
- **M2 — Browser renderer.** Voxel bundle + Three.js scene, pixel pipeline
  (low-res target, quantized shading, dither), orbit + snap views + keyboard,
  fps budget met, no-WebGL fallback wired.
- **M3 — Components.** Curated mapping in, hover/click highlighting, side
  panel with sourced facts, exploded view, about/credits overlay.
- **M4 — Follow the light.** The §8.5 sequence, countdown, hero-planet swatch,
  deep link to the palette `/roman`.
- **M5 — Ship.** Mobile polish at 390 px, a11y pass, OG cards from the
  fallback renders, deploy config, README, cross-link PR brief for the
  palette repo (brief only; that PR happens palette-side).

Each milestone ends with tests green and a short demo artifact (rendered
frames or a screen recording) for the owner.

## 15. Deploy

Static output in `dist/` (gitignored), built by `web/build.py`. Deploy target:
Dokploy, same pattern as the sibling site (static serve of `dist/`). Domain:
owner decision (§16). Analytics: none in v1 unless the owner asks; if added,
copy the sibling's pattern (PostHog gated on a build-time key so only the
real deploy reports).

## 16. Open decisions for the owner

1. **Name + domain.** "Pixel Observatory" is a placeholder.
2. **Hero planet** for the light-path finale (must be on the palette site's
   Roman target board; 47 UMa b-class targets are the natural pick).
3. **Grid size and outline pass** — decided by eye at the M1/M2 gates.
4. Whether v1 gets analytics at all.
