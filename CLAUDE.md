# Pixel Observatory

NASA's Roman Space Telescope as an interactive 3D pixel-art explorer. Sibling
project to the Exoplanet Palette site; this one is about the telescope itself.

**Read `SPEC.md` first, fully, before writing any code.** It is the contract:
architecture, UX, budgets, tests, and milestone order all live there. This file
is the working rules that keep a build session honest.

## Ground rules

- **Milestones are sequential and gated.** M1 (voxelizer proof + contact
  sheet) ends with the owner eyeballing renders and hand-labelling the
  material→component mapping. Do not start web code before that gate passes.
  Do not guess the component mapping yourself.
- **Pinned facts are pinned.** SPEC §11 lists mission facts that were
  hard-won on the sibling project (Roman's three supported bands 575/730/825,
  the 660 nm installed-but-never-characterised filter, "best effort" being a
  contractual term, launch by May 2027). Copy them exactly; never re-derive
  them from memory or from random web pages. If a primary source appears to
  contradict them, stop and raise it instead of editing.
- **Every displayed claim has a source.** All copy lives in `data/facts.json`
  with a `source` URL per fact; tests enforce it. No prose hardcoded in
  JS/HTML/templates.
- **Unofficial, affectionate, never against NASA.** No NASA branding, no
  comparisons to NASA's own pages, an explicit not-affiliated disclaimer in
  the about overlay. Credit: 3D model NASA/Christopher R. Meaney, public
  domain.
- **Copy voice**: plain-English labels a newcomer understands (dual-audience
  rule); no em dashes or decorative middle dots in site prose; "schematic" /
  "stylised" honesty wording wherever our rendering could be mistaken for
  the real appearance.

## Conventions

- Python 3.11+, `uv` for deps, `ruff` for lint, type hints throughout.
  This machine has `python3` only (no bare `python`).
- Web: static, vanilla ES modules + Three.js **vendored at a pinned exact
  version** in `web/static/vendor/` (no CDN, no bundler, no framework).
- Pipeline is deterministic: same input ⇒ byte-identical bundle; the bundle
  carries a provenance header (source hash, git commit, date).
- `dist/` is build output, gitignored. `assets/source/roman-glb-a.glb` is the
  committed source model; never re-download it silently — the source pin test
  (36 primitives / 36 materials / 301,586 triangles) guards against swaps.
- Tests: `uv run pytest`. Keep the SPEC §13 suite green; add a test whenever
  a fact or budget becomes load-bearing.

## Git

- Identity must be **jocarino** (repo-local config already set). When a
  remote is added, use the `git@github-personal:` host alias so the
  `~/.gitconfig` includeIf keeps enforcing it.
- Small commits, imperative messages. Never force-push main.

## Owner interaction points

The build has three by-eye gates the agent cannot decide alone: the M1
contact sheet (grid size + component labelling + overall GO/NO-GO), the M2
look tuning (internal resolution, dither, outline pass), and SPEC §16's open
decisions (name/domain, hero planet). Prepare the materials, present them
inline (rendered images, not file paths), and wait.
