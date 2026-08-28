"""The model palette: sixteen curated base colours plus a fixed shading ramp.

The source materials are physically plausible and visually mushy: almost
everything is a slightly different grey. Quantizing to a small deliberate ramp
is what makes the render read as intentional pixel art rather than as a
compressed photograph, and it is the honest move too, since these colours are
ours and the site says so.

Shading never invents colours. A base colour plus a shade step indexes a
precomputed table that the browser and the offline renderer both consume, so
the two renderers cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Sixteen base colours. Families are contiguous so a ramp reads left to right.
BASE_COLORS: tuple[tuple[str, str], ...] = (
    ("void", "#0b0e13"),  # 0  lens glass, deepest shadow
    ("matte", "#14181f"),  # 1  blackout coatings
    ("charcoal", "#232a34"),  # 2  structure, darkest
    ("grey-dark", "#39424f"),  # 3
    ("grey-mid", "#5a6675"),  # 4
    ("grey-light", "#8794a3"),  # 5
    ("grey-pale", "#c3cdd8"),  # 6
    ("white", "#eef3f8"),  # 7  high-gain dish, reflector
    ("cell-deep", "#1b1f3d"),  # 8  solar cells, in shadow
    ("cell", "#34407e"),  # 9
    ("cell-lit", "#5b6fc4"),  # 10
    ("gold-deep", "#6b4a18"),  # 11 thermal blanket
    ("gold", "#b8862c"),  # 12
    ("gold-lit", "#e0a83e"),  # 13 the site accent
    ("bronze", "#4a3f2c"),  # 14 truss underside
    ("silver", "#9aa7b4"),  # 15 instrument housings
)

# Four luminance steps. Index 0 is unlit, 3 is fully keyed.
SHADE_STEPS: tuple[float, ...] = (0.42, 0.62, 0.82, 1.06)

# Added in linear light before the ramp is encoded, so an unlit face never falls
# all the way to the background. Without it the darkest materials rendered at
# 1.02 contrast against the sky, which is to say invisible: whole components
# disappeared when they turned away from the key light. Kept small on purpose,
# because a large floor flattens the dark end into one grey.
AMBIENT_FLOOR = 0.010

# The one-pixel rim. Mid-tone rather than near-black on purpose: it is lighter
# than the dark materials and darker than the pale ones, so it separates a part
# from the sky and from its neighbours whichever way that part is facing. Lives
# here rather than in each renderer so the two cannot drift apart.
OUTLINE = "#3a424e"

# Material name -> base colour index. Curated against the M1 contact sheet;
# every material in the source model appears here exactly once.
MATERIAL_COLORS: dict[str, int] = {
    "Afta-black-sm": 2,
    "Afta-blackout": 1,
    "Afta-blackout2": 1,
    "Afta-bridgework-bronze": 14,
    "Afta-bridgework-silver": 3,
    "Afta-bridgework-underside": 14,
    "Afta-grey1-sm": 5,
    "Afta-grey2-sm": 3,
    "Afta-grey3-sm": 4,
    "Afta-hood": 6,
    "Afta-Instrument1-sm": 15,
    "Afta-lens": 0,
    "Afta-rear-dish white": 7,
    "Afta-rear-disk": 12,
    "Afta-rear-diskcenter": 3,
    "Afta-rear-side-panels": 6,
    "Afta-schnoozle-inside": 1,
    "Afta-schnoozle-out": 4,
    "Afta-schnoozle-rear-out": 3,
    "Afta-silver1-fl": 15,
    "Afta-solar1": 9,
    "Afta-solar22": 9,
    "Afta-solar33": 9,
    "Afta-solar44": 9,
    "Afta-solar55": 9,
    "Afta-solar66": 9,
    "Afta-solar77": 9,
    "Afta-solarback": 8,
    "Afta-solartop-base": 8,
    "Afta-white reflector": 6,
    "Default": 4,
    "MTL28": 4,
    "MTL29": 4,
    "MTL30": 4,
    "MTL4": 4,
    "MTL44": 4,
}


@dataclass(frozen=True)
class Palette:
    """Base colours plus the flattened (base, shade) lookup table."""

    names: tuple[str, ...]
    base: np.ndarray  # (16, 3) uint8
    ramp: np.ndarray  # (16, 4, 3) uint8
    outline: str

    @property
    def size(self) -> int:
        return int(self.base.shape[0])

    @property
    def shades(self) -> int:
        return int(self.ramp.shape[1])

    def hex_base(self) -> list[str]:
        return [f"#{int(c[0]):02x}{int(c[1]):02x}{int(c[2]):02x}" for c in self.base]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def build() -> Palette:
    """Materialize the palette and its shading ramp."""

    names = tuple(name for name, _ in BASE_COLORS)
    base = np.array([_hex_to_rgb(h) for _, h in BASE_COLORS], dtype=np.uint8)

    # Ramp in linear light so darkening a colour does not also desaturate it.
    lin = (base.astype(np.float64) / 255.0) ** 2.2
    scaled = lin[:, None, :] * np.array(SHADE_STEPS, dtype=np.float64)[None, :, None]
    scaled += AMBIENT_FLOOR
    srgb = np.clip(scaled, 0.0, 1.0) ** (1 / 2.2)
    ramp = np.round(srgb * 255.0).astype(np.uint8)

    return Palette(names=names, base=base, ramp=ramp, outline=OUTLINE)


def material_indices(materials: tuple[str, ...]) -> np.ndarray:
    """Map material names to base-colour indices, in the given order."""

    missing = [m for m in materials if m not in MATERIAL_COLORS]
    if missing:
        raise KeyError(f"materials missing from the palette map: {sorted(missing)}")
    return np.array([MATERIAL_COLORS[m] for m in materials], dtype=np.uint8)
