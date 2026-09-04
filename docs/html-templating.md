# HTML receipt templates

HTML templates provide a file-based design surface now and a browser-rendered
foundation for a future WYSIWYG editor. A template is rendered with sandboxed
Jinja, captured by headless Chromium at one CSS pixel per printer dot, and then
passed through the same one-bit preprocessing pipeline as every other image.

## Installation

Jinja is a small core dependency. Chromium integration is optional so normal
driver installs remain lightweight:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev,html]"
```

Chromium starts only while an HTML receipt is being prepared. It is not used by
image, text, protocol, or transport operations. The renderer first looks for an
installed Microsoft Edge or Google Chrome, keeping the setup small on ordinary
desktop systems. If neither is available, install Playwright's isolated browser:

```powershell
.venv\Scripts\playwright.exe install chromium
```

## Template contract

Every template must contain exactly one `.receipt` element. It renders at
exactly 384 CSS pixels, mapping one CSS pixel to one print-head dot. Height is
content-driven and unlimited by the template API.

The built-in stylesheet defines these variables:

- `--printer-width: 384px`
- `--page-padding: 16px`
- `--spacing-unit: 4px`
- `--font-family` and `--font-size`

It also provides the following basic classes:

- `.receipt` and `.receipt--padded`
- `.full-width`, `.photo`, `.machine-code`, `.qr-code`, `.barcode`, and `.no-break`
- `.text-left`, `.text-center`, and `.text-right`
- `.row`, `.column`, and `.space-between`
- `.p-0` through `.p-4`, `.px-1`, `.px-2`, `.py-1`, and `.py-2`
- `.m-0`, `.mt-1`, `.mt-2`, `.mb-1`, and `.mb-2`

Override the CSS variables in the template's own `<style>` block to establish a
design system. All elements use `border-box` sizing. The standard padded content
width is 352 dots: 384 minus 16 dots on each side.

The [template gallery](../examples/README.md) includes a receipt, compact
shipping label, international postcard address, parcel drop-in form, checklist,
kitchen ticket, inventory label, event ticket, and photo note. Together they
demonstrate loops, conditionals, local assets, machine-readable codes, flex and
grid layout, spacing, and dithering.

The gallery is included in both wheel and source distributions. Installed users
can list its templates and copy one into a new editable directory:

```powershell
tronic-printer templates
tronic-printer copy-template checklist my-checklist
```

The copy contains the HTML template, sample `data.json`, and any local assets.

## Data and automation

Template data is a JSON object. Missing variables are errors instead of silently
printing blank content, and values are HTML-escaped by default.

```powershell
.venv\Scripts\tronic-printer.exe prepare-html `
  examples\receipt\receipt.html `
  --data examples\receipt\data.json `
  --output analysis-work\receipt.png
```

Use repeatable `--set NAME=VALUE` arguments to override top-level values. Values
use JSON syntax when valid and otherwise remain strings. `--data -` reads JSON
from standard input, making the command suitable for scripts and pipelines.

```powershell
.venv\Scripts\tronic-printer.exe prepare-html template.html `
  --data order.json --set 'currency="HUF"' --set total=4200 `
  -o preview.png
```

Jinja expressions, loops, conditionals, filters, macros, and includes are
available. Includes are rooted at the template directory.

## Pictures and dithering

There are two useful image paths:

1. A normal local image such as `<img class="photo" src="product.jpg">` is
   rendered with the rest of the page. The command's `--dither` and
   `--threshold` settings are applied once to the complete receipt. This is
   convenient for image-heavy layouts.
2. `printer_image(...)` prepares and embeds one local picture as a one-bit PNG.
   This allows a photograph to use Floyd–Steinberg or ordered dithering while
   the final receipt uses threshold mode for crisp text.

```html
<img class="photo"
     src="{{ printer_image('photo.jpg', width=352,
                           dither='floyd-steinberg',
                           effects=['autocontrast:cutoff=2']) }}">
```

The helper's width is explicit because it should match the CSS display width.
Use 384 for full bleed or 352 inside the default padded receipt. Supported
dither values are `threshold`, `floyd-steinberg`, and `ordered-4x4`. The helper
also accepts `threshold=` and the same ordered `effects=` strings as the image
CLI. The `.photo` class uses pixelated scaling so pre-dithered dots remain hard.

For mixed text and photographs, keep the final page in its default threshold
mode and pre-dither each photograph with `printer_image`. For a page that is
primarily artwork, a single final `--dither floyd-steinberg` pass is simpler.

## QR codes and barcodes

The optional HTML dependencies include pure-Python QR and barcode generators.
Both helpers return local data URIs, so they do not relax the browser's network
or filesystem restrictions.

```html
<img class="machine-code qr-code"
     src="{{ qr_code(ticket_url, scale=4, border=4, error='q') }}">

<img class="machine-code barcode"
     src="{{ barcode(tracking_number,
                     symbology='code128',
                     module_width=0.25,
                     module_height=12,
                     quiet_zone=2,
                     include_text=true) }}">
```

`qr_code` supports error levels `l`, `m`, `q`, and `h`, integer scale values
from 1 through 16, and quiet-zone borders from 0 through 16 modules. It emits a
pixel-aligned black-and-white PNG. `barcode` supports Code 128 and Code 39 and
emits an SVG. Its dimensions are expressed in millimetres before the browser
fits the SVG into the CSS layout.

Keep a QR image at its generated intrinsic size; non-integer CSS resizing can
turn square modules into uneven printer dots. Choose `scale` to control its
size instead. The `.qr-code` class deliberately leaves width automatic.

The helpers generate structurally valid symbols but cannot guarantee that a
physical print will scan. Thermal density, paper, module size, CSS scaling, and
the scanner all matter. Preserve the quiet zone and verify important codes on
the target hardware.

## Printing

Preview creation performs no hardware access. Printing keeps the existing two
consent gates and can save the exact raster before connecting:

```powershell
.venv\Scripts\tronic-printer.exe ble-print-html <address> template.html `
  --data data.json --preview preview.png --live --allow-printing

.venv\Scripts\tronic-printer.exe print-html --port COM7 template.html `
  --data data.json --preview preview.png --live --allow-printing
```

Both routes send the same `PrintRaster` command used by image and text printing.

On 2026-09-04, all nine gallery templates were printed over the paired Windows
classic Bluetooth SPP channel. Every job returned completion `AA 0D 0A`, and
physical inspection confirmed complete, clean output. This validates the HTML
capture, one-bit conversion, compressed raster, and serial transport path
together. Machine-readable codes still require a separate scanner check.

## Security and reproducibility

JavaScript is disabled. HTTP, HTTPS, and all other remote requests are blocked.
File requests must remain inside the template directory after resolving path
traversal and symlinks. `printer_image` applies the same rule. This covers local
images, stylesheets, fonts, SVGs, and included Jinja files.

Templates themselves should still be treated as trusted input: very large or
pathological HTML can consume browser memory even when script and network access
are disabled.
