# Image preprocessing and effect plugins

Image preparation is deliberately independent of Bluetooth, serial I/O, and
the CQRS print command. A CLI, GUI, web service, or third-party application can
prepare a `RasterImage`, inspect or save its exact preview, and only then decide
whether to submit `PrintRaster`.

## Pipeline

The built-in pipeline performs these stages in order:

1. apply EXIF orientation;
2. composite transparent pixels onto white;
3. convert to grayscale;
4. resize to the selected width, preserving aspect ratio;
5. apply zero or more registered effects in CLI order;
6. convert to black and white with threshold, Floyd–Steinberg, or ordered 4×4
   dithering;
7. pack black pixels into the printer's one-bit `RasterImage` format.

Effects must preserve image dimensions. This keeps physical size and paper
usage predictable even when effects come from separately installed packages.
Every print-time preview is the exact final one-bit raster, not an approximate
rendering.

## Preview without hardware

List all built-in and installed effects:

```powershell
.venv\Scripts\tronic-printer.exe image-effects
```

Prepare a preview and print metrics without opening Bluetooth:

```powershell
.venv\Scripts\tronic-printer.exe prepare-image photo.jpg `
  --output preview.png --width 384 --dither floyd-steinberg `
  --effect autocontrast:cutoff=2 `
  --effect contrast:factor=1.4
```

The JSON result includes source and raster dimensions, estimated printed
height, black-pixel coverage, raw raster size, and compressed `codeESC` frame
size. Effect flags are repeatable and their order is significant.

Generate the four built-in comparison pages with their exact printed headers:

```powershell
.venv\Scripts\tronic-printer.exe prepare-showcase `
  "tests\resources\Lenna_(test_image).png" `
  --output-dir analysis-work\image-showcase
```

Each page header contains the recipe name, dither, threshold, ordered effect
chain, raster dimensions, and black-pixel coverage. This command has no
transport dependency and never accesses Bluetooth.

## Example vibe recipes

These are starting points rather than hardware-calibrated artistic defaults:

```text
Crisp text/logo
  --dither threshold --threshold 150 --effect sharpen:factor=2

Newsprint photo
  --dither ordered-4x4 --effect autocontrast:cutoff=2

Gritty noir
  --dither threshold --threshold 145 --effect autocontrast:cutoff=2
  --effect contrast:factor=1.8 --effect gamma:value=1.15

Soft photograph
  --dither floyd-steinberg --effect blur:radius=0.5
  --effect contrast:factor=0.9

Outline sketch
  --dither threshold --threshold 180 --effect edge
```

Raising the threshold generally makes more pixels black. Gamma values above
one darken midtones; values below one lighten them.

## Printing the prepared style

The print command accepts the same pipeline options and can save the exact
preview before it connects:

```powershell
.venv\Scripts\tronic-printer.exe ble-print-image <printer-address> photo.jpg `
  --preview preview.png --dither ordered-4x4 `
  --effect autocontrast:cutoff=2 `
  --feed-dots 160 --live --allow-printing
```

## Writing a plugin

The public plugin contract is `ImageEffect` in
`tronic_printer.preprocessing`. An effect has a name, description, and `apply`
method. Options remain strings at the boundary so the same contract works for
CLI, GUI, and HTTP inputs.

```python
from collections.abc import Mapping

from PIL import Image, ImageEnhance


class PunchyEffect:
    name = "punchy"
    description = "strong local-project contrast"

    def apply(
        self,
        image: Image.Image,
        options: Mapping[str, str],
    ) -> Image.Image:
        factor = float(options.get("factor", "1.7"))
        return ImageEnhance.Contrast(image).enhance(factor)
```

Publish the class from another Python package using this entry-point group:

```toml
[project.entry-points."tronic_printer.image_effects"]
punchy = "my_printer_effects:PunchyEffect"
```

After installing that package in the same environment, `image-effects`,
`prepare-image`, and both image-printing commands discover it automatically.
Entry-point plugins execute Python code during discovery and should therefore
only be installed from trusted sources. The current plugin API version is 1.

Programmatic callers can also avoid package discovery and register an object
directly:

```python
from tronic_printer.preprocessing import (
    EffectSpec,
    ImageEffectRegistry,
    ImagePreparationConfig,
    prepare_image,
)

registry = ImageEffectRegistry([PunchyEffect()])
prepared = prepare_image(
    pillow_image,
    ImagePreparationConfig(
        effects=(EffectSpec.parse("punchy:factor=2"),),
    ),
    registry=registry,
)
```

The resulting `prepared.raster` is passed unchanged to the existing
`PrintRaster` CQRS command. `prepared.preview` and `prepared.summary()` are
available to GUI and web presentation layers.

## Four-page hardware showcase

The HIL rig contains a separately gated scenario that prints the four labeled
Lenna pages as individual compressed BLE jobs. The pages contain about 255 mm
of image and header content. Four 160-dot trailing feeds add another 80 mm, for
an expected total near 335 mm. The scenario pauses 20 seconds between jobs by
default and checks printer status before every page.

It requires all three explicit consent flags:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\hil\test_live_ble_image_showcase.py `
  --live --allow-printing --allow-four-image-showcase `
  --printer-address <printer-address> -s -v
```

The pause can be increased with `--showcase-pause-seconds`. The test must be
attended, and it has not yet been run against the printer.
