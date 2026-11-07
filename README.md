# Lidl TRONIC Mini Pocket Printer

[![CI](https://github.com/CSonTi04/mini-thermal-printer/actions/workflows/ci.yml/badge.svg)](https://github.com/CSonTi04/mini-thermal-printer/actions/workflows/ci.yml)

Clean-room reverse engineering and an open Python implementation for the Lidl
TRONIC Mini Pocket Printer.

The target observed by this project is:

- Bluetooth name: `Mini Pocket Printer_BLE`
- Firmware shown by the official app: `V1.06LY`
- Paper: approximately 56 mm wide
- Print head: verified full-width 384 dots / approximately 48 mm at 8 dots/mm
- Measured continuous-roll margins: approximately 3 mm left and 5 mm right
- Host platforms: Windows and Debian/Linux

## Current status

The static analysis of the official Android app
`com.printer.lidloffice` version `1.3.13` is complete for the printing path,
and a non-root Android HCI capture has verified the main conclusions. The work
recovered and verified:

- device-name matching and model selection;
- official-app use of classic Bluetooth RFCOMM/SPP;
- the live `A2Y` model and `V1.06LY` firmware responses;
- BLE service/characteristic selection and credit-based flow control;
- print-job lifecycle and command bytes;
- a live 384×37-dot compressed print transaction;
- a live PC BLE connection and read-only query session;
- an acknowledged but incomplete uncompressed BLE raster probe;
- byte-exact recovery of the native `codeESC` zlib codec;
- a physically verified multi-row compressed BLE calibration print;
- the app's resize, threshold, gamma, and error-diffusion pipeline; and
- native-library exports, app permissions, network surfaces, and signing
  provenance; and
- physically verified HTML rendering for all nine gallery templates over the
  classic Bluetooth SPP transport.

The findings are documented in:

- [Static APK analysis](docs/apk-analysis-v1.3.13.md)
- [Official-app transport capture](docs/captures/official-app-print-2026-07-24.md)
- [PC BLE discovery and read-only queries](docs/captures/pc-ble-2026-07-25.md)
- [PC BLE uncompressed print](docs/captures/pc-ble-print-2026-07-25.md)
- [PC BLE compressed print](docs/captures/pc-ble-compressed-print-2026-07-25.md)
- [PC BLE four-style image showcase](docs/captures/pc-ble-image-showcase-2026-07-25.md)
- [Protocol reference](docs/protocol.md)
- [Progress and approval log](docs/progress.md)
- [Mock and hardware-in-the-loop test rigs](docs/testing.md)
- [Image preprocessing and effect plugins](docs/image-preprocessing.md)
- [Unicode text and font support](docs/text-printing.md)
- [HTML receipt templates](docs/html-templating.md)
- [Halftone QR codes](docs/halftone-qr.md)
- [Optional protocol experiments](docs/protocol-experiments.md)
- [Raspberry Pi native Linux HIL stage](docs/rpi-hil.md)
- [Driver architecture](docs/architecture.md)
- [Continuous integration and delivery](docs/ci-cd.md)

Remaining generic SDK behavior is not presented as live hardware validation.
The first Python implementation is structured around CQRS messages and a
transport-independent application core. A CLI is the initial presentation
adapter; GUI and web interfaces can reuse the same command/query buses without
depending on serial or Bluetooth details.

## Python development

Create an environment and install the package with its test dependencies:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the mocked test rig, which performs no hardware access:

```powershell
.venv\Scripts\python.exe -m pytest -m "not hil"
```

List serial ports without connecting to a device:

```powershell
.venv\Scripts\tronic-printer.exe ports
```

Live access is explicitly gated. Read [test-rig documentation](docs/testing.md)
before using `--live` or `--allow-printing`.

Compressed `codeESC` output is the default because the live uncompressed probe
rendered only its first expected row. The encoding remains explicitly
selectable for regression work.

Preview a styled image without accessing hardware:

```powershell
.venv\Scripts\tronic-printer.exe prepare-image image.jpg -o preview.png `
  --dither floyd-steinberg --effect autocontrast:cutoff=2
```

Build the four labeled comparison pages without accessing hardware:

```powershell
.venv\Scripts\tronic-printer.exe prepare-showcase image.jpg `
  --output-dir analysis-work\image-showcase
```

Preview Unicode text with an installed font without accessing hardware:

```powershell
.venv\Scripts\tronic-printer.exe prepare-text "Szia, Dávid!" `
  --font-family Arial --font-size 32 --bold --align center `
  --output analysis-work\text-preview.png
```

Render a sandboxed Jinja HTML receipt at one CSS pixel per printer dot:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[html]"
.venv\Scripts\tronic-printer.exe prepare-html `
  examples\receipt\receipt.html --data examples\receipt\data.json `
  --output analysis-work\receipt.png
```

The HTML path includes a 384-dot CSS layout contract, local-only assets,
automation-friendly JSON data and overrides, per-picture dithering, and local
QR/Code 128 generation. JavaScript and remote browser requests are disabled.
See the template guide and the shipping-label, checklist, kitchen-ticket,
inventory-label, event-ticket, postcard-address, parcel-drop-in, and photo-note
examples in the gallery.

Installed packages include the gallery. List it or copy a starter into a new
editable directory without cloning the repository:

```powershell
tronic-printer templates
tronic-printer copy-template shipping-label my-shipping-label
```

List discoverable system font faces with `tronic-printer fonts`. Text can also
come from a UTF-8 file, and explicit TTF, OTF, or TTC paths are supported.

Print a Pillow-readable image over the verified BLE path, optionally saving the
exact one-bit preview before connecting:

```powershell
.venv\Scripts\tronic-printer.exe ble-print-image <printer-address> image.png `
  --preview preview.png --width 384 --dither floyd-steinberg `
  --effect contrast:factor=1.4 --feed-dots 160 --live --allow-printing
```

The extensible pipeline applies ordered, repeatable effects and converts the
image before Bluetooth is opened. Built-in effects and separately installed
entry-point plugins feed the same `RasterImage` and `PrintRaster` CQRS command
available to future GUI and web adapters.

The transport-independent text renderer provides measured Unicode wrapping,
left/center/right alignment, margins, line spacing, family/style resolution,
and exact one-bit previews. Its output feeds that same CQRS command, so GUI and
web interfaces do not need to depend on BLE or serial details.

All four built-in showcase recipes and all nine HTML gallery templates have
been physically verified on the target printer. The longest successful
composed page was 538 raster rows.

The package, CLI, linter, and complete mocked test rig also pass under Python
3.12 on Ubuntu 24.04/WSL2. This validates Debian-family userspace portability;
live Linux BLE still requires a host where the Bluetooth controller is exposed
to BlueZ and D-Bus.

## Repository policy

This repository contains original documentation, clean-room implementation
code, tests, and one separately documented public-domain image test resource;
see [`tests/resources/README.md`](tests/resources/README.md). The repository
does not contain the proprietary APK, decompiled sources, phone dumps, signing
material, or extracted manuals. Those local artifacts are excluded by
`.gitignore`.

Evidence labels used in the documentation:

- **Observed**: directly present in an APK, device dump, or user observation.
- **Recovered**: reconstructed from bytecode or native-library metadata.
- **Inferred**: a conclusion supported by static evidence but awaiting a live
  capture.
- **Verified**: reproduced against the physical printer.
- **Unknown**: not yet established.

## License

Copyright 2026 CSonTi04.

The project's original source code and documentation are licensed under the
[Apache License 2.0](LICENSE). The separately documented public-domain image
test resource remains public domain and is not relicensed under Apache License
2.0. No proprietary app code or assets are included.
