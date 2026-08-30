# Unicode text and font support

Text rendering is transport-independent. It resolves a font, lays out Unicode
text at the printer's dot width, wraps it by measured glyph width, and returns
the same exact one-bit `RasterImage` used by image, CLI, GUI, and future web
adapters.

## Font sources

The renderer supports:

- an explicit `.ttf`, `.otf`, or `.ttc` file;
- an installed font family discovered on Windows, Debian/Linux, or macOS; or
- DejaVu Sans as the portable default, with Pillow's embedded font as a final
  fallback.

List installed faces and their concrete files:

```powershell
.venv\Scripts\tronic-printer.exe fonts
.venv\Scripts\tronic-printer.exe fonts --family Arial
```

Family requests use `--bold` and `--italic` to choose the closest installed
face. An explicit font file already identifies one face, so those style flags
do not synthesize a different weight or slant.

The project does not bundle or relicense third-party fonts. Anyone distributing
output, a web editor, or a packaged application must follow the license of the
selected font.

## Preview without hardware

Render inline Unicode text and save the exact one-bit output:

```powershell
.venv\Scripts\tronic-printer.exe prepare-text "Szia, Dávid!" `
  --font-family Arial --font-size 32 --bold --align center `
  --output analysis-work\text-preview.png
```

For multiline content, UTF-8 files avoid shell-specific newline escaping:

```powershell
.venv\Scripts\tronic-printer.exe prepare-text `
  --text-file message.txt --font-file C:\Windows\Fonts\arial.ttf `
  --font-size 26 --margin 12 --line-spacing 5 `
  --output analysis-work\message-preview.png
```

Use `--text-file -` to read UTF-8 text from standard input. Text is wrapped by
actual glyph measurements, including individual splitting of a word that is
wider than the printable area. `--align` accepts `left`, `center`, or `right`.

## BLE printing

The text is fully rendered and validated before Bluetooth is opened. Printing
retains the same two explicit consent gates as every other physical job:

```powershell
.venv\Scripts\tronic-printer.exe ble-print-text <printer-address> `
  "Szia, Dávid!" --font-family Arial --font-size 32 --bold `
  --preview analysis-work\text-preview.png --feed-dots 160 `
  --live --allow-printing
```

Classic SPP uses the equivalent `print-text --port COM7 ...` command.

## Reusing the core

Presentation adapters call the renderer directly and pass its raster to the
existing CQRS command:

```python
from tronic_printer.messages import PrintRaster
from tronic_printer.text import FontSpec, TextAlign, TextLayoutConfig, prepare_text

document = prepare_text(
    "Szia, Dávid!",
    FontSpec(family="DejaVu Sans", size=32, bold=True),
    TextLayoutConfig(width=384, margin=12, align=TextAlign.CENTER),
)
result = app.commands.execute(PrintRaster(document.prepared.raster, feed_dots=160))
```

`RenderedText.image` remains available for richer composition with borders,
logos, QR codes, or independently styled blocks before the final rasterization
step. This keeps layout policy outside the printer protocol and transport.
