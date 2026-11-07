"""Halftone QR code rendering (Chu, Chang, Lee & Mitra, ACM TOG 2013).

Each QR module is subdivided into an N×N grid of subpixels.  The centred C×C
*core* always carries the true QR module colour.  The surrounding subpixels
are filled from a user-supplied background image, dithered to 1-bit.
Reference-mark modules (finder patterns, timing, alignment) can optionally be
kept fully solid to improve scan reliability.

Public API
----------
HalftoneDither  – dither algorithm for the background image
MarksMode       – which structural modules to render solid
HalftoneOptions – frozen, validated configuration dataclass
render_halftone_qr(data, image, options) → PIL.Image  (mode "1")
prepare_halftone_qr(data, image, options, width=384) → PreparedHalftoneQr
    (RasterImage + exact preview, integer nearest-neighbour scaled, centred)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from PIL import Image, ImageEnhance, ImageOps

from tronic_printer.domain import RasterImage
from tronic_printer.preprocessing import _normalize_source
from tronic_printer.protocol import MAX_PRINT_WIDTH

# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------

class HalftoneDither(StrEnum):
    THRESHOLD = "threshold"
    FLOYD_STEINBERG = "floyd-steinberg"
    ATKINSON = "atkinson"
    ORDERED = "ordered"


class MarksMode(StrEnum):
    ALL = "all"
    FINDERS = "finders"
    NONE = "none"


# ---------------------------------------------------------------------------
# Named presets (N, C)
# ---------------------------------------------------------------------------

PRESETS: Final[dict[str, tuple[int, int]]] = {
    "3/1": (3, 1),
    "5/1": (5, 1),
    "5/3": (5, 3),
    "6/2": (6, 2),
}

# ---------------------------------------------------------------------------
# Options dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HalftoneOptions:
    """Frozen, validated halftone QR rendering configuration."""

    grid: int = 6
    core: int = 2
    dither: HalftoneDither = HalftoneDither.FLOYD_STEINBERG
    error_level: str = "h"
    marks: MarksMode = MarksMode.ALL
    border: int = 4
    mask: int | None = None
    contrast: float = 1.0
    brightness: float = 1.0
    invert: bool = False

    def __post_init__(self) -> None:
        if not 2 <= self.grid <= 10:
            raise ValueError("grid must be between 2 and 10")
        if not 1 <= self.core <= self.grid - 1:
            raise ValueError("core must be between 1 and grid-1")
        if self.error_level not in {"l", "m", "q", "h"}:
            raise ValueError("error_level must be l, m, q, or h")
        if self.mask is not None and not 0 <= self.mask <= 7:
            raise ValueError("mask must be between 0 and 7, or None for auto")
        if self.border < 0:
            raise ValueError("border must be non-negative")
        if self.contrast < 0:
            raise ValueError("contrast must be non-negative")
        if self.brightness < 0:
            raise ValueError("brightness must be non-negative")


# ---------------------------------------------------------------------------
# QR alignment-pattern position table (ISO 18004 Annex E)
# ---------------------------------------------------------------------------

_ALIGN_POSITIONS: Final[dict[int, list[int]]] = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
    11: [6, 30, 54],
    12: [6, 32, 58],
    13: [6, 34, 62],
    14: [6, 26, 46, 66],
    15: [6, 26, 48, 70],
    16: [6, 26, 50, 74],
    17: [6, 30, 54, 78],
    18: [6, 30, 56, 82],
    19: [6, 30, 58, 86],
    20: [6, 34, 62, 90],
    21: [6, 28, 50, 72, 94],
    22: [6, 26, 50, 74, 98],
    23: [6, 30, 54, 78, 102],
    24: [6, 28, 54, 80, 106],
    25: [6, 32, 58, 84, 110],
    26: [6, 30, 58, 86, 114],
    27: [6, 34, 62, 90, 118],
    28: [6, 26, 50, 74, 98, 122],
    29: [6, 30, 54, 78, 102, 126],
    30: [6, 26, 52, 78, 104, 130],
    31: [6, 30, 56, 82, 108, 134],
    32: [6, 34, 60, 86, 112, 138],
    33: [6, 30, 58, 86, 114, 142],
    34: [6, 34, 62, 90, 118, 146],
    35: [6, 30, 54, 78, 102, 126, 150],
    36: [6, 24, 50, 76, 102, 128, 154],
    37: [6, 28, 54, 80, 106, 132, 158],
    38: [6, 32, 58, 84, 110, 136, 162],
    39: [6, 26, 54, 82, 110, 138, 166],
    40: [6, 30, 58, 86, 114, 142, 170],
}


def _alignment_centers(version: int) -> list[tuple[int, int]]:
    """Return (row, col) centres of alignment patterns, excluding finder areas."""
    positions = _ALIGN_POSITIONS.get(version, [])
    if not positions:
        return []
    size = 4 * version + 17
    centres: list[tuple[int, int]] = []
    for r in positions:
        for c in positions:
            # Exclude centres whose 5×5 block overlaps a finder+separator area
            in_tl = r < 8 and c < 8
            in_tr = r < 8 and c >= size - 8
            in_bl = r >= size - 8 and c < 8
            if not (in_tl or in_tr or in_bl):
                centres.append((r, c))
    return centres


# ---------------------------------------------------------------------------
# Functional-module mask
# ---------------------------------------------------------------------------

def _build_functional_mask(
    qr_size: int,
    version: int,
    marks: MarksMode,
) -> list[list[bool]]:
    """Return a 2-D bool grid: True where the module must be rendered solid."""
    if marks is MarksMode.NONE:
        return [[False] * qr_size for _ in range(qr_size)]

    mask: list[list[bool]] = [[False] * qr_size for _ in range(qr_size)]

    # Finder patterns (7×7) + separators → 8×8 corner blocks
    for r in range(min(8, qr_size)):
        for c in range(min(8, qr_size)):
            mask[r][c] = True
    for r in range(min(8, qr_size)):
        for c in range(max(0, qr_size - 8), qr_size):
            mask[r][c] = True
    for r in range(max(0, qr_size - 8), qr_size):
        for c in range(min(8, qr_size)):
            mask[r][c] = True

    if marks is MarksMode.ALL:
        # Timing patterns (row 6 and col 6 between finder areas)
        for i in range(8, qr_size - 8):
            mask[6][i] = True
            mask[i][6] = True
        # Alignment patterns (5×5 blocks)
        for cr, cc in _alignment_centers(version):
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    rr, rc = cr + dr, cc + dc
                    if 0 <= rr < qr_size and 0 <= rc < qr_size:
                        mask[rr][rc] = True

    return mask


# ---------------------------------------------------------------------------
# Background image dithering
# ---------------------------------------------------------------------------

def _safe_getdata(image: Image.Image) -> list[int]:
    getter = getattr(image, "get_flattened_data", None)
    if getter is not None:
        return list(getter())
    return list(image.getdata())  # type: ignore[arg-type]


def _dither_background(gray: Image.Image, dither: HalftoneDither) -> list[list[bool]]:
    """Convert a grayscale image to a 2-D bool grid (True = black)."""
    w, h = gray.size

    if dither is HalftoneDither.THRESHOLD:
        pixels = _safe_getdata(gray)
        return [[pixels[y * w + x] < 128 for x in range(w)] for y in range(h)]

    if dither is HalftoneDither.FLOYD_STEINBERG:
        mono = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        values = _safe_getdata(mono)
        return [[values[y * w + x] == 0 for x in range(w)] for y in range(h)]

    if dither is HalftoneDither.ORDERED:
        bayer = (
            (0, 8, 2, 10),
            (12, 4, 14, 6),
            (3, 11, 1, 9),
            (15, 7, 13, 5),
        )
        pixels = _safe_getdata(gray)
        return [
            [
                pixels[y * w + x]
                < max(0, min(255, round(128 + (bayer[y % 4][x % 4] - 7.5) * 16)))
                for x in range(w)
            ]
            for y in range(h)
        ]

    if dither is HalftoneDither.ATKINSON:
        # Float buffer: integer floor division would bias negative error
        # (dark pixels) and darken the background.  Atkinson deliberately
        # diffuses only 6/8 of the error, and the buffer is not clamped.
        buf = [float(value) for value in _safe_getdata(gray)]
        result = [[False] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                old = buf[y * w + x]
                new = 0.0 if old < 128 else 255.0
                result[y][x] = new == 0.0
                err = (old - new) / 8
                for dy, dx in ((0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        buf[ny * w + nx] += err
        return result

    raise ValueError(f"unsupported dither mode: {dither}")


def _prepare_background(
    image: Image.Image,
    size: int,
    options: HalftoneOptions,
) -> list[list[bool]]:
    """Grayscale + cover-crop to *size*×*size*, adjust, dither → bool grid."""
    # Shared normalisation: EXIF orientation first, transparency flattened
    # onto white (otherwise transparent pixels would turn black), greyscale.
    gray = _normalize_source(image)

    # Cover-fit crop: scale so smaller dimension fills *size*, then centre-crop
    w, h = gray.size
    scale = max(size / w, size / h)
    new_w = max(size, round(w * scale))
    new_h = max(size, round(h * scale))
    gray = gray.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - size) // 2
    top = (new_h - size) // 2
    gray = gray.crop((left, top, left + size, top + size))

    if options.contrast != 1.0:
        gray = ImageEnhance.Contrast(gray).enhance(options.contrast)
    if options.brightness != 1.0:
        gray = ImageEnhance.Brightness(gray).enhance(options.brightness)
    if options.invert:
        gray = ImageOps.invert(gray)

    return _dither_background(gray, options.dither)


# ---------------------------------------------------------------------------
# Main rendering function
# ---------------------------------------------------------------------------

def render_halftone_qr(
    data: object,
    image: Image.Image,
    options: HalftoneOptions | None = None,
) -> Image.Image:
    """Render a halftone QR code and return a 1-bit PIL Image.

    Parameters
    ----------
    data:
        Content to encode.  Converted to string.
    image:
        Background photo/illustration.  Any PIL-readable mode; colour is fine.
    options:
        Rendering options.  Defaults to HalftoneOptions() (grid=6, core=2,
        dither=floyd-steinberg, error=h, marks=all, border=4).

    Returns
    -------
    PIL.Image in mode "1" at subpixel resolution
    ``(qr_modules + 2*border) * grid`` pixels square.
    """
    try:
        import segno
    except ImportError as exc:
        raise ImportError(
            "halftone QR requires segno; install tronic-mini-printer[html] or segno"
        ) from exc

    options = options or HalftoneOptions()
    text = str(data)
    if not text:
        raise ValueError("QR data cannot be empty")

    # --- Generate QR code ---------------------------------------------------
    mask_param: int | None = options.mask
    code = segno.make_qr(text, error=options.error_level, mask=mask_param)
    version: int = code.version  # type: ignore[assignment]

    # is_dark[r][c] – True means black QR module (segno matrix, no border)
    is_dark: list[list[bool]] = [[bool(value) for value in row] for row in code.matrix]
    qr_size = len(is_dark)

    # --- Functional-module mask ---------------------------------------------
    functional = _build_functional_mask(qr_size, version, options.marks)

    # --- Dimension calculations ---------------------------------------------
    N = options.grid
    C = options.core
    border = options.border
    total_subpixels = (qr_size + 2 * border) * N

    # Warn if the caller intends to print and a module maps to < 3 dots
    # (This function doesn't know the target DPI; the caller is responsible
    #  for scaling.  We surface a warning so the CLI can relay it.)
    _warn_if_tiny(total_subpixels, N)

    # --- Prepare background image -------------------------------------------
    bg = _prepare_background(image, total_subpixels, options)

    # --- Core subpixel region within each module cell -----------------------
    core_start = (N - C) // 2
    core_end = core_start + C

    # --- Compose output -----------------------------------------------------
    out_pixels: list[int] = []

    for y in range(total_subpixels):
        module_row = y // N
        sy = y % N
        in_core_row = core_start <= sy < core_end

        for x in range(total_subpixels):
            module_col = x // N
            sx = x % N

            qr_row = module_row - border
            qr_col = module_col - border

            if qr_row < 0 or qr_row >= qr_size or qr_col < 0 or qr_col >= qr_size:
                # Quiet zone → white
                out_pixels.append(255)
                continue

            dark = is_dark[qr_row][qr_col]
            is_core_px = in_core_row and (core_start <= sx < core_end)
            is_ref = functional[qr_row][qr_col]

            if is_core_px or is_ref:
                out_pixels.append(0 if dark else 255)
            else:
                out_pixels.append(0 if bg[y][x] else 255)

    out_img = Image.new("L", (total_subpixels, total_subpixels))
    out_img.putdata(out_pixels)
    return out_img.convert("1")


def _warn_if_tiny(total_subpixels: int, grid: int) -> None:
    """Emit a warning when each module would be very small at 384-dot width."""
    dps = MAX_PRINT_WIDTH // total_subpixels  # dots per subpixel
    module_dots = dps * grid
    if dps < 1:
        warnings.warn(
            f"QR code is too large to fit in {MAX_PRINT_WIDTH} dots at this grid size; "
            "increase error level (fewer modules) or decrease grid size",
            stacklevel=4,
        )
    elif module_dots < 3:
        warnings.warn(
            f"each QR module will be only {module_dots} dot(s) wide at "
            f"{MAX_PRINT_WIDTH}-dot printer width; consider a smaller grid or "
            "lower error correction level",
            stacklevel=4,
        )


# ---------------------------------------------------------------------------
# Utility: convert a rendered image to RasterImage for the printer
# ---------------------------------------------------------------------------

def halftone_qr_to_raster(
    rendered: Image.Image,
    *,
    max_width: int = MAX_PRINT_WIDTH,
) -> tuple[Image.Image, int]:
    """Scale *rendered* to fit *max_width* (nearest-neighbour) and return
    ``(scaled_pil_image, dots_per_subpixel)``.

    Raises ValueError if even a single subpixel cannot fit.
    """
    total_subpixels = rendered.width  # square
    dps = max_width // total_subpixels
    if dps < 1:
        raise ValueError(
            f"QR code ({total_subpixels} subpixels wide) does not fit in "
            f"{max_width} dots; use a smaller grid or lower error correction"
        )
    side = total_subpixels * dps
    scaled = rendered.resize((side, side), Image.Resampling.NEAREST)
    return scaled, dps


# ---------------------------------------------------------------------------
# Printer preparation: the same "raster + exact preview" contract as images
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PreparedHalftoneQr:
    """A halftone QR code laid out on a full printer-width raster."""

    raster: RasterImage
    preview: Image.Image
    code_width: int
    dots_per_subpixel: int
    grid: int
    core: int

    @property
    def module_dots(self) -> int:
        return self.dots_per_subpixel * self.grid

    def save_preview(self, path: str | Path) -> None:
        self.preview.save(path)

    def summary(self) -> dict[str, object]:
        return {
            "width": self.raster.width,
            "height": self.raster.height,
            "code_width": self.code_width,
            "dots_per_subpixel": self.dots_per_subpixel,
            "module_dots": self.module_dots,
            "grid": self.grid,
            "core": self.core,
            "raster_bytes": len(self.raster.data),
        }


def prepare_halftone_qr(
    data: object,
    image: Image.Image,
    options: HalftoneOptions | None = None,
    *,
    width: int = MAX_PRINT_WIDTH,
) -> PreparedHalftoneQr:
    """Render, integer-scale (nearest neighbour) and centre a halftone QR code.

    The result is exactly *width* dots wide.  The one-bit halftone is never
    resampled with smoothing or dithered again: each subpixel becomes an
    exact ``dots_per_subpixel`` square of printer dots.
    """
    if not 1 <= width <= MAX_PRINT_WIDTH:
        raise ValueError(f"width must be between 1 and {MAX_PRINT_WIDTH} dots")
    options = options or HalftoneOptions()
    rendered = render_halftone_qr(data, image, options)
    scaled, dps = halftone_qr_to_raster(rendered, max_width=width)
    canvas = Image.new("1", (width, scaled.height), 1)
    canvas.paste(scaled, ((width - scaled.width) // 2, 0))
    values = _safe_getdata(canvas)
    rows = [
        [values[y * width + x] == 0 for x in range(width)]
        for y in range(canvas.height)
    ]
    return PreparedHalftoneQr(
        raster=RasterImage.from_rows(rows),
        preview=canvas.convert("L"),
        code_width=scaled.width,
        dots_per_subpixel=dps,
        grid=options.grid,
        core=options.core,
    )
