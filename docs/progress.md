# Progress and approval log

Last updated: 2026-09-04

## Project decisions

The following constraints and preferences were supplied by the device owner:

- Official Android package: `com.printer.lidloffice`
- Phone remains unrooted.
- Hybrid investigation: static analysis plus controlled hardware tests.
- Python is acceptable.
- Windows and Debian/Linux are target hosts.
- Current consumables are approximately 56 mm paper rolls.
- Ask for approval at phase boundaries and before installing additional tools.
- Document and showcase progress.
- Current priority: complete APK analysis.

The original clean-room code and documentation are licensed under Apache
License 2.0. The separately documented image test resource is public domain and
is not relicensed under Apache License 2.0.

## Completed

### Repository hygiene

- Added ignore rules for `private/`, ADB dumps, decompiler output, and analysis
  work directories.
- Confirmed the proprietary APK splits and local analysis artifacts are
  ignored.
- Committed the static-analysis and official-app capture milestones separately.

### Device/app acquisition

- Installed Android Platform Tools with WinGet.
- Authorized the unrooted Android phone over ADB.
- Pulled the installed Play-delivered base APK and its ABI and density splits.
- Recorded sizes and SHA-256 hashes in the static-analysis report.

### Analysis tools

- Used JDK 21 from `H:\DevTools\java\jdk-21.0.2`.
- Installed JADX 1.5.5 and verified the separately downloaded official CLI
  archive against its published SHA-256.
- Downloaded Apktool 3.0.3 and verified its JAR against its published SHA-256.
- Used the already-installed WSL toolchain for read-only ELF inspection; no
  native-analysis package was installed.

### Static APK analysis

- Decoded the base and both split APKs with Apktool.
- Decompiled all three DEX files with JADX and retained smali as the
  authoritative fallback.
- Audited manifest, components, permissions, resources, bundled manuals,
  dependencies, network configuration, WebViews, signing certificate, and
  ARM64 native libraries.
- Traced device selection, classic SPP, BLE GATT setup, credit/MTU flow
  control, print commands, print lifecycle, raster packing, optional
  compression, and the production image preprocessing path.
- Recovered the JADX-failed `PrinterHelper.initDevice` method from smali.
- Published the results in `docs/apk-analysis-v1.3.13.md` and
  `docs/protocol.md`.

### Non-root official-app capture

- Enabled full Bluetooth HCI snoop logging on an unrooted Samsung SM-S926B.
- Captured an official-app connection, device-information queries, density
  change, and two identical print jobs.
- Collected the report with `adb bugreport` and extracted the standard
  `btsnoop_hci.log`.
- Correlated the printer with classic HCI handle `0x0009`, RFCOMM DLCI 2, and
  SPP UUID `00001101-0000-1000-8000-00805F9B34FB`.
- Verified model `A2Y`, firmware `V1.06LY`, 384-dot width, compressed raster
  framing, 80-dot trailing feed, and `AA 0D 0A` print completion.
- Kept the bug report, snoop log, MAC address, serial number, and extracted
  streams under ignored `private/captures/`.
- Published the sanitized findings in
  `docs/captures/official-app-print-2026-07-24.md`.

### Local Python implementation and test rigs

- Created a Python 3.11+ package with a transport-independent domain and CQRS
  command/query buses.
- Added verified protocol encoders/decoders, 384-dot one-bit raster packing,
  image conversion, classic SPP serial transport, and read-only BLE discovery.
- Added a CLI designed as a thin adapter so future GUI and web interfaces can
  reuse the same application core.
- Added scripted and stateful mock transports, sanitized captured-session test
  data, unit tests, an integration workflow, and separately gated HIL tests.
- Enforced `--live` for physical access and `--allow-printing` in addition for
  print-head or paper-moving tests.
- Created the approved local `.venv` and installed the project dependencies.
- Verified 54 non-HIL tests with 87% aggregate package coverage and clean Ruff
  checks. Verified that all five HIL tests skip without consent flags.

### PC BLE discovery and read-only HIL

- Paired the printer's BLE identity with Windows; the idle Settings label `Not
  connected` was confirmed to be normal rather than a pairing failure.
- Enumerated the live GATT database and verified FF01 notify, FF02 write without
  response, and FF03 credit/packet-size notify roles under service FF00.
- Implemented a credit-aware BLE transport with a private asyncio loop behind
  the same synchronous transport port used by the CQRS application.
- Observed the printer request a 100-byte packet payload, capped it to Windows'
  20-byte write-without-response limit, and completed model, firmware, battery,
  density, and status queries over BLE.
- Verified `A2Y`, `V1.06LY`, 86% battery, density 1, and clean status `00`.
- Passed the dedicated read-only BLE HIL test. No print, feed, or setting change
  was transmitted.

### PC BLE uncompressed print HIL

- Received separate approval for one minimal paper-moving test.
- Sent a 384×32 one-bit border/crosshair through the uncompressed `GS v 0`
  envelope, followed by the captured 80-dot feed.
- Received completion `AA 0D 0A`; the gated BLE transport-level HIL assertion
  passed.
- Physically observed only one fine horizontal line rather than the expected
  multi-row border/crosshair. A later 20 mm feed confirmed no additional output
  was hidden by the cover.
- Classified uncompressed multi-row support as unverified despite the success
  response; native compression remains the reliable target.
- Verified that bare feed is ignored and a job without raster times out. A
  one-row all-white raster followed by 160 feed dots moved paper and completed
  successfully, establishing a safe standalone-feed workaround.

### Native codeESC recovery

- Installed the user-approved AArch64 cross-binutils package in WSL.
- Disassembled all four JNI compression wrappers and their shared encoder in
  the stripped ARM64 `libPrinterNative.so`.
- Identified `codeESC` as zlib-wrapped DEFLATE using default compression,
  method 8, window bits 10, memory level 8, default strategy, and `Z_FINISH`.
- Decompressed the captured 217-byte payload to the expected 1,776 raster bytes
  and reproduced the native payload byte-for-byte with Python's standard zlib.
- Added a privacy-safe captured regression vector and made `codeESC` the
  driver's default raster encoding while retaining uncompressed mode for
  diagnostics.
- Verified 59 non-HIL tests and six HIL tests that skip without consent flags.

### Compressed print HIL

- Received separate approval for one deterministic compressed calibration job.
- Sent a 384×96 raster with three-dot border/crosshair lines, 2 mm ruler ticks,
  and a 160-dot trailing feed.
- Compressed 4,608 raster bytes to a 65-byte `codeESC` payload in a 75-byte
  frame.
- Received `AA 0D 0A`; the compressed BLE HIL test passed.
- Visually confirmed the complete pattern, consistent line weight, side
  margins, and useful blank tear margin from the user's photograph.

### Practical image CLI

- Added serial and BLE image-printing commands over the shared `PrintRaster`
  CQRS command.
- Added proportional resizing, adjustable one-bit thresholding, and output
  dimension reporting through the existing Pillow adapter.
- Kept both `--live` and `--allow-printing` gates for every physical image job.
- Verified that missing or invalid images fail before a BLE connection opens.
- Passed 65 non-HIL tests with all six hardware tests excluded.

### Debian-family userspace validation

- Installed the project from `pyproject.toml` into an isolated Python 3.12
  environment on Ubuntu 24.04/WSL2.
- Passed the same 65 non-HIL tests, Ruff checks, and installed CLI smoke test.
- Confirmed that this WSL environment has system D-Bus but no exposed Bluetooth
  controller or `bluetoothctl`; no Linux BLE hardware claim is made from it.
- Selected WSL as the current Linux development environment and a Raspberry Pi
  as the next native Debian/BlueZ HIL target.
- Added a staged Raspberry Pi checklist that preserves separate discovery,
  query, calibration-print, and image-print approval gates.

### Extensible image preprocessing

- Added image-effect plugin API version 1 with programmatic registration and
  automatic discovery through `tronic_printer.image_effects` package entry
  points.
- Added eight composable built-in effects: autocontrast, brightness, contrast,
  edge, gamma, invert, blur, and sharpen.
- Added threshold, Floyd–Steinberg, and ordered 4×4 rasterization modes.
- Added EXIF orientation, transparent-to-white compositing, high-quality
  proportional resizing, exact one-bit PNG previews, and print-size/ink/frame
  metrics.
- Added `image-effects` and hardware-free `prepare-image` commands. Both serial
  and BLE image commands accept the identical ordered effect pipeline and can
  save the final preview before opening their transport.
- Generated four ignored real-image previews through the production CLI to
  compare diffusion, newsprint, noir, and outline treatments. The untracked
  source image was not modified or added to Git.
- Added a deterministic low-ink preprocessing-to-BLE HIL test behind both
  consent flags. It has not been run against hardware.
- Passed 94 non-HIL tests on Windows and WSL; all eight HIL tests skip by
  default. Ruff and Windows coverage checks passed with 89% total coverage.

### Four-style labeled image showcase

- Added a tracked 512×512 RGB reference image with a pinned SHA-256 and explicit
  provenance. The initial Lenna resource was later replaced by scikit-image's
  public-domain astronaut image so the repository can be redistributed safely.
- Added reusable showcase recipes and exact one-bit labeled page generation for
  Floyd photo, ordered newsprint, gritty noir, and outline sketch variants.
- Added a hardware-free `prepare-showcase` command and generated all four pages
  locally for visual inspection.
- Added a BLE HIL scenario that prints four independent compressed jobs with
  name/settings headers, 160-dot feeds, and configurable cooling pauses.
- Added a dedicated `--allow-four-image-showcase` gate because the scenario is
  approximately 335 mm long and includes two images above 50% black coverage.
- Ran the separately approved four-page scenario. The first attempt stopped
  before connecting while the printer was off; the retry passed in 90.74
  seconds after passive discovery confirmed advertising.
- Four user photographs confirmed complete readable headers, complete images,
  stable alignment, distinct style output, and no visible heat dropout.
- Repeated the four-page scenario after replacing Lenna with the public-domain
  scikit-image astronaut resource. All four compressed BLE jobs completed in
  89.77 seconds with 20-second cooling pauses; physical rendering inspection is
  pending operator confirmation. See
  [the astronaut showcase capture](captures/pc-ble-astronaut-showcase-2026-07-25.md).
- Raised the verified compressed page-height lower bound from 96 to 538 rows.

### Unicode text and font support

- Added a transport-independent Unicode text renderer with measured wrapping,
  long-word splitting, margins, line spacing, and left/center/right alignment.
- Added explicit TTF/OTF/TTC loading and installed-family discovery for Windows,
  Debian/Linux, and macOS, including bold/italic face selection.
- Added hardware-free `fonts` and `prepare-text` CLI commands plus gated
  `ble-print-text` and classic-SPP `print-text` commands.
- Kept font rendering above the CQRS boundary: GUI and web adapters can prepare
  the same raster and submit the existing `PrintRaster` command.
- Added Unicode, font discovery, layout, validation, preview, consent-gate, and
  mocked BLE print coverage.

### HTML templating and gallery validation

- Added sandboxed Jinja HTML templates captured at one CSS pixel per printer
  dot through an installed Chromium-family browser.
- Added reusable layout classes, JSON data and overrides, confined local
  assets, per-picture dithering, and local QR/Code 128 generation.
- Added nine example templates: receipt, shipping label, postcard address,
  parcel drop-in form, checklist, kitchen ticket, inventory label, event
  ticket, and photo note.
- Bundled the gallery in wheel and source distributions and added lightweight
  `templates` and `copy-template` commands for installed users.
- Added a dedicated Ubuntu/Chromium CI smoke job that renders a complete
  machine-code template without adding Playwright to the full test matrix.
- Paired the printer through Windows and obtained the outgoing classic SPP
  endpoint on `COM6`.
- Printed every gallery example through `print-html`; all nine jobs returned
  completion `AA 0D 0A`, and the operator confirmed perfect physical output.
- A same-day BLE retest with Bleak 1.1.1 discovered the printer but failed to
  create a Windows GATT handle. Bluetooth LE Explorer still connected, and the
  classic SPP path remained fully functional.

### Optional protocol experiments

- Added typed, read-only queries for serial number, boot information, shutdown
  time, speed, and time format using the exact statically recovered frames.
- Added separately live-gated `probe-info` and `ble-probe-info` commands,
  emulator behavior, unit coverage, and SPP/BLE HIL cases. No setting-write
  command was exposed.
- Verified the hardware-free suite with 151 passing tests. The first COM6 live
  attempt stopped while Windows opened the Bluetooth serial endpoint with OS
  error 121, before any query bytes were transmitted; the standard `info`
  command reproduced the same transport-level failure.
- Retried after the printer was brought online. Serial number, boot information
  `V3.02`, and the 20-minute shutdown setting responded; the generic speed and
  time-format queries did not. Standard telemetry immediately afterward showed
  clean status `00`, so the printer remained healthy. The serial number stays
  outside tracked documentation.
- Prepared a separately gated shutdown-time round trip using only official app
  values: query 20 minutes, temporarily set 30, verify, restore 20 in a
  `finally` block, and verify restoration.
- Ran the approved shutdown experiment. The 30-minute write returned `OK` but
  Windows dropped the reused SPP session before verification; a fresh session
  read back 30. Separate fresh connections then restored and verified the
  original 20-minute setting. The HIL procedure now isolates each operation in
  its own connection; the revised scenario passed in 1.54 seconds and again
  left the printer at 20 minutes. No paper moved and the print head was not
  activated.

## Current checkpoint

The official app's classic SPP sequence, recovered `codeESC` codec, image and
text pipelines, and HTML template renderer are implemented and physically
verified. Windows now exposes the paired printer through outgoing SPP port
`COM6`; all nine gallery templates printed successfully through that path.
The earlier Windows BLE validation remains documented, but direct BLE
connection currently fails on this host with Bleak 1.1.1 despite successful
discovery and a working Bluetooth LE Explorer connection. Debian-family
packaging and mocked behavior are validated in WSL; native Linux BLE remains
deferred to the Raspberry Pi stage.

Remaining unknowns:

- the current Windows/Bleak direct-GATT connection regression;
- live BLE behavior on a native Debian/BlueZ host;
- maximum reliable compressed image height beyond the verified 538-row lower
  bound and the need for long-image segmentation;
- preferred physically calibrated preprocessing defaults for different media
  and artistic styles;
- exact physical margins and maximum reliable printable width; and
- behavior on indexed/label media rather than the current continuous roll.

## Agreed next phase: PC discovery and Python driver

The official app uses classic Bluetooth RFCOMM/SPP, so that is the primary
driver path. BLE discovery remains a secondary, read-only investigation until
its live GATT layout is understood.

1. Disconnect the phone from the printer while leaving the printer powered on.
2. Add a Python project skeleton with protocol encoding, serial transport, a
   command-line interface, raster packing, and unit tests.
3. Create a repository-local `.venv` and install `pyserial`, `bleak`, and
   `pytest` only after explicit approval.
4. Enumerate the PC's Bluetooth devices and inspect the printer's BLE
   advertisement and GATT layout without writes.
5. Pair the printer over classic Bluetooth and identify its outgoing Windows
   COM port.
6. After explicit approval, send only read-only model, firmware, battery,
   density, and status queries.
7. Implement uncompressed 384-dot raster printing first, using the already
   understood `GS v 0` format.
8. After a separate print approval, print a small deterministic test pattern,
   photograph or inspect the physical result, and refine width, margins, feed,
   and timing.
9. Recover the native compressed raster algorithm, validate it against the
   captured vector, and make it the default after verification. **Completed.**
10. Exercise the same driver on Debian, document host setup and known
    limitations, and commit each verified milestone so progress remains
    reviewable and reversible.

### Approval gates

- **Dependency gate:** approval is required before creating the environment and
  downloading `pyserial`, `bleak`, and `pytest`.
- **Query gate:** approval is required before the PC transmits even read-only
  commands to the printer.
- **Print gate:** separate approval is required before sending raster data,
  feeding paper, or replaying any captured job.
