"""The share card: one 1200x630 PNG that has to explain the site on its own.

A link posted into Slack, Mastodon or a group chat is unfurled by a crawler
that shows a picture, a title and a sentence. The picture is the part that
travels furthest, and it often travels alone: people screenshot it, quote it,
repost it without the link. So the card is not just a pretty render of the
telescope. It carries the name and the one-line description as pixels, and it
carries the honesty caption too, because "this is a diagram, not a photograph"
is exactly the claim that gets lost when an image is separated from its page.

Everything visual here is built out of the same parts as the site: the same
offline raycaster as the no-WebGL fallback frames, the same palette, the same
starfield, and Silkscreen for the type. The card should look like a screenshot
of somewhere real.

Copy is not written here. It arrives as a ``CardSpec`` that ``web/build.py``
fills from ``data/facts.json``, so the sourcing rule survives the trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import render as render_mod
from .palette import Palette
from .voxelize import VoxelModel, occupancy

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

# The size every unfurler crops to. 1.91:1, and the template hard-codes it in
# og:image:width / og:image:height, so a test pins the two together.
WIDTH, HEIGHT = 1200, 630

# The card is drawn at a quarter scale and blown up with nearest neighbour, so
# every voxel edge lands on a 4 px block. 630 is not divisible by 4; rendering
# one row tall and trimming it is cheaper than special-casing the last row.
PIXEL = 4
LOW_W, LOW_H = WIDTH // PIXEL, 158

# Tokens from web/static/styles.css :root. Copied rather than parsed: there are
# five of them, and a CSS parser in the pipeline would be the larger surprise.
BG = (10, 13, 19)
INK = (207, 216, 227)
DIM = (135, 145, 158)
ACCENT = (224, 168, 62)

# Left column holds the type, right side holds the telescope. The split is off
# centre because the model reads better with room around it than the words do.
MARGIN = 72
COLUMN_RIGHT = 600
RULE_HEIGHT = 6

TITLE_SIZE = 56
TAGLINE_SIZE = 20
CAPTION_SIZE = 16


@dataclass(frozen=True)
class CardSpec:
    """What the card says. No knowledge of where the words came from."""

    title: str
    tagline: str
    caption: str


@lru_cache(maxsize=8)
def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "Silkscreen-Bold.ttf" if bold else "Silkscreen-Regular.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=font))


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, limit: int
) -> list[str]:
    """Greedy word wrap. A word wider than the column gets its own line rather
    than being broken: Silkscreen has no hyphen small enough to hide."""

    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and _text_w(draw, candidate, font) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit(
    draw: ImageDraw.ImageDraw, text: str, bold: bool, size: int, limit: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """The largest size at which every wrapped line clears the column.

    Wrapping alone is not enough: a single word can be wider than the column,
    and "Observatory" at the full title size is exactly that. Silkscreen is
    drawn on an eight pixel grid, so only multiples of eight land on whole
    pixels; anything between them is a blurred pixel font, which is worse than
    a smaller one.
    """

    while True:
        font = _font(bold, size)
        lines = _wrap(draw, text, font, limit)
        if size <= 8 or all(_text_w(draw, line, font) <= limit for line in lines):
            return font, lines
        size -= 8


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    """Draw a line of type, clearing the starfield out from behind it first.

    The stars are scattered without any knowledge of the layout, and one landing
    against a letter does not read as a star. It reads as punctuation: the first
    draft put one immediately after "STYLISED", which turned an honesty note
    into `STYLISED", NOT PHOTOGRAPHIC`. Painting the background colour back over
    the line's own box is invisible, because that is the colour already there.
    """

    box = draw.textbbox(xy, text, font=font)
    draw.rectangle((box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), fill=BG)
    draw.text(xy, text, font=font, fill=fill)


def _silhouette(primitive: np.ndarray) -> np.ndarray:
    """The model's pixels plus the one-pixel outline the renderer drew around
    them. ``render`` paints that rim onto background pixels, so a mask of
    ``primitive >= 0`` alone would composite the model and leave its outline
    behind."""

    solid = primitive >= 0
    mask = solid.copy()
    mask[1:, :] |= solid[:-1, :]
    mask[:-1, :] |= solid[1:, :]
    mask[:, 1:] |= solid[:, :-1]
    mask[:, :-1] |= solid[:, 1:]
    return mask


def _backdrop(
    voxels: VoxelModel,
    palette: Palette,
    color_index: np.ndarray,
    volume: np.ndarray | None = None,
) -> np.ndarray:
    """Starfield across the whole card, telescope composited into the right of
    it, then blown up to full size."""

    low = np.zeros((LOW_H, LOW_W, 3), dtype=np.uint8)
    low[:] = render_mod.BACKGROUND
    low = render_mod.starfield(low)

    tile_w, tile_h = 150, 150
    frame = render_mod.render(
        voxels,
        palette,
        render_mod.THREE_QUARTER,
        tile_w,
        tile_h,
        volume=volume if volume is not None else occupancy(voxels),
        color_index=color_index,
        stars=False,
    )

    # Right of the type column, vertically centred in the low-res canvas.
    x0 = LOW_W - tile_w - 4
    y0 = (LOW_H - tile_h) // 2
    mask = _silhouette(frame.primitive)
    region = low[y0 : y0 + tile_h, x0 : x0 + tile_w]
    region[mask] = frame.color[mask]

    full = render_mod.upscale(low, PIXEL)
    # LOW_H * PIXEL is 632. Trim a row off each end rather than the bottom two,
    # so the model stays centred.
    return full[1 : 1 + HEIGHT]


def render_card(
    voxels: VoxelModel,
    palette: Palette,
    color_index: np.ndarray,
    spec: CardSpec,
    volume: np.ndarray | None = None,
) -> Image.Image:
    """Draw the finished card."""

    image = Image.fromarray(_backdrop(voxels, palette, color_index, volume))
    draw = ImageDraw.Draw(image)

    # A rule along the top, the way every panel on the site is topped.
    draw.rectangle((0, 0, WIDTH, RULE_HEIGHT - 1), fill=ACCENT)

    column = COLUMN_RIGHT - MARGIN
    title_font, title_lines = _fit(draw, spec.title, True, TITLE_SIZE, column)
    tagline_font, tagline_lines = _fit(draw, spec.tagline, False, TAGLINE_SIZE, column)
    caption_font, caption_lines = _fit(draw, spec.caption, False, CAPTION_SIZE, column)

    title_step = title_font.size + 14
    tagline_step = tagline_font.size + 12
    block = (
        len(title_lines) * title_step + 28 + RULE_HEIGHT + 28 + len(tagline_lines) * tagline_step
    )
    y = (HEIGHT - block) // 2

    for line in title_lines:
        _text(draw, (MARGIN, y), line, title_font, INK)
        y += title_step

    y += 28
    draw.rectangle((MARGIN, y, MARGIN + 160, y + RULE_HEIGHT - 1), fill=ACCENT)
    y += RULE_HEIGHT + 28

    for line in tagline_lines:
        _text(draw, (MARGIN, y), line, tagline_font, DIM)
        y += tagline_step

    # The honesty line sits apart from the pitch, at the foot of the column.
    caption_step = caption_font.size + 8
    for i, line in enumerate(reversed(caption_lines)):
        _text(
            draw,
            (MARGIN, HEIGHT - MARGIN - (i + 1) * caption_step),
            line,
            caption_font,
            DIM,
        )

    return image


def write_card(path: Path, image: Image.Image, colours: int = 64) -> Path:
    """Save the card, quantized.

    The card is flat colour on a flat background, so an adaptive palette costs
    it nothing visible and takes the file from roughly 90 KB to 20 KB. Some
    unfurlers give up on slow images, and this one is fetched by a crawler that
    nobody is waiting on but everybody notices when it times out.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").quantize(colors=colours, method=Image.MEDIANCUT).save(
        path, format="PNG", optimize=True
    )
    return path
