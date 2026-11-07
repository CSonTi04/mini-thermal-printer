# Halftone QR Codes

Halftone QR codes blend a background photograph or illustration into a standard
QR code so that the image is visible through the data modules while the code
remains machine-readable.

## Technique

The rendering follows the approach described in:

> Chu, H.-K., Chang, C.-S., Lee, R.-R., & Mitra, N. J. (2013).
> **Halftone QR Codes.**
> *ACM Transactions on Graphics*, 32(6), 217:1–217:8.
> <https://dl.acm.org/doi/10.1145/2508363.2508408>

Inspiration and reference implementation:
[Halftone QR by Jorge C. Lucero](https://lucerojc.github.io/halftone-qr/)
(after Erik and Martin Demaine's QR art prints).

### Algorithm overview

1. **Generate a standard QR code** with [Segno](https://segno.readthedocs.io/)
   at the chosen error-correction level and optional mask.
2. **Subdivide** each QR module into an *N × N* grid of subpixels.
3. **Core subpixels** – the centred *C × C* block within each cell – always
   carry the true QR module colour (black or white).
4. **Background subpixels** – the remaining *N² − C²* positions – come from
   the user's image, which is:
   - converted to greyscale;
   - scaled to cover the full QR code area (cover-fit crop);
   - optionally adjusted for contrast, brightness, and inversion;
   - dithered to 1-bit.
5. **Reference marks** (finder patterns, timing, alignment patterns) can
   optionally be forced solid to improve scan reliability.
6. A solid white **quiet zone** (border) surrounds the code.

## Options

| Flag / parameter | Type | Default | Description |
|---|---|---|---|
| `--grid N` | int 2–10 | `6` | Subpixels per module side |
| `--core C` | int 1–N-1 | `2` | Solid core size (C × C inside the N × N cell) |
| `--preset` | 3/1, 5/1, 5/3, 6/2 | – | Named grid/core pair; overrides `--grid`/`--core` |
| `--dither` | str | `floyd-steinberg` | Background dither algorithm |
| `--error-level` | l/m/q/h | `h` | QR error correction level |
| `--marks` | all/finders/none | `all` | Which structural modules to render solid |
| `--contrast` | float ≥ 0 | `1.0` | Contrast factor for the background |
| `--brightness` | float ≥ 0 | `1.0` | Brightness factor for the background |
| `--invert` | flag | off | Invert background tones |
| `--border` | int ≥ 0 | `4` | Quiet zone in modules |
| `--mask` | int 0–7 | auto | QR mask pattern (auto if omitted) |

### Named presets

| Preset | Grid | Core | Character |
|---|---|---|---|
| `3/1` | 3 | 1 | Fine — small but dense image |
| `5/1` | 5 | 1 | Thin core, prominent image |
| `5/3` | 5 | 3 | Balanced |
| `6/2` | 6 | 2 | **Default** – good readability and image quality |

### Dither algorithms

| Value | Description |
|---|---|
| `floyd-steinberg` | Error-diffusion (default); smooth, natural look |
| `atkinson` | Bill Atkinson's pattern; higher contrast, retro feel |
| `ordered` | Bayer 4×4 ordered dither; regular pattern |
| `threshold` | Simple threshold; maximum sharpness |

### Marks modes

| Value | Solid region |
|---|---|
| `all` | Finder patterns + separators + timing + alignment (default) |
| `finders` | Finder patterns + separators only |
| `none` | Only the C×C core subpixels |

## Printing tips

- **Error level `h`** (30 % recovery) is strongly recommended. The image
  pixels in non-core positions degrade the QR signal; high redundancy
  compensates.
- **Grid 6, core 2** (the default) gives each module 36 subpixels with a
  4-subpixel solid core. Every subpixel becomes an exact integer square of
  printer dots (nearest-neighbour, never re-dithered), so the printed size is
  `(modules + 2 × border) × grid × dots_per_subpixel`. With the default
  border of 4, a version-1 code (21 modules) at 6/2 is 174 subpixels → 2 dots
  per subpixel (348 dots, 12 dots per module); a version-2 code (25 modules)
  is 198 subpixels → only 1 dot per subpixel (198 dots, 6 dots per module).
  The `3/1` preset fits version 1 at 4 and versions 2–4 at 3 dots per
  subpixel.
- **Large QR versions** (high version number) reduce the dots-per-subpixel.
  Shorter data, a smaller `--grid`, a smaller `--border`, or a lower error
  level produce codes that scale better. The JSON summary reports
  `dots_per_subpixel`, `module_dots` and `code_width`.
- The printed raster is always 384 dots wide with the code centred.
- **Contrast boost** (`--contrast 1.5`) sharpens the dithered image; combined
  with `--error-level h` and `--marks all` this gives the best balance of
  image quality and scan reliability.
- **Invert** (`--invert`) works well for light subjects on a dark background
  when you want the background to feel integrated with the QR whites.

## CLI usage

### Preview (no hardware)

```
tronic-printer prepare-halftone-qr \
    --data "https://example.com" \
    --image photo.jpg \
    --grid 6 --core 2 \
    --error-level h \
    --output preview.png
```

### Print over BLE

```
tronic-printer ble-print-halftone-qr AA:BB:CC:DD:EE:FF \
    --live --allow-printing \
    --data "https://example.com" \
    --image photo.jpg \
    --preview preview.png
```

## HTML template helper

Add a halftone QR to any Jinja receipt template:

```jinja
<img class="machine-code" alt="" src="{{ halftone_qr_code(
       "https://example.com",
       "photo.jpg",
       width=352,
       grid=6,
       core=2,
       error_level="h",
       marks="all",
       contrast=1.3
   ) }}">
```

The helper returns a `data:image/png;base64,…` URI for an `<img>` tag. The
image path must be relative to the template directory. Set `width` to the
content-box width that will hold the image (352 inside a 16 px padded
receipt, 384 for a full-bleed body): the PNG is integer-scaled to fit it, so
the browser displays it at its natural size and never resamples the one-bit
halftone. The `machine-code` class adds `image-rendering: pixelated` and
centres the image.

## Library usage

```python
from PIL import Image
from tronic_printer.halftone_qr import HalftoneOptions, prepare_halftone_qr

with Image.open("photo.jpg") as photo:
    prepared = prepare_halftone_qr("https://example.com", photo, HalftoneOptions())
prepared.save_preview("preview.png")   # exact one-bit print preview
raster = prepared.raster               # RasterImage for PrintRaster
```

`render_halftone_qr()` returns the unscaled one-bit image at subpixel
resolution if you need to place it yourself.

## Attribution

- Chu, H.-K. *et al.* (2013). "Halftone QR Codes." *ACM TOG* 32(6).
- Reference web tool by [Jorge C. Lucero](https://lucerojc.github.io/halftone-qr/)
  inspired by [Erik and Martin Demaine](http://erikdemaine.org/qr/).
