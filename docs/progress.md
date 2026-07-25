# Progress and approval log

Last updated: 2026-07-25

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

Apache License 2.0 is the recommended license for the future clean-room code.

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
- Verified 44 non-HIL tests with 88% aggregate package coverage and clean Ruff
  checks. Verified that both HIL tests skip without consent flags.

## Current checkpoint

The official app's transport and normal print sequence are verified, and the
mock-backed Python implementation is ready for PC-side discovery. Serial-port
enumeration currently returns no ports, so Windows pairing is the next live
checkpoint. No PC command has yet been sent to the physical printer.

Remaining unknowns:

- the live FF00 BLE characteristic layout and negotiated MTU/credits;
- the proprietary `codeESC` compressed-raster algorithm;
- whether this firmware also accepts the uncompressed `GS v 0` envelope;
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
9. Continue native-library analysis to recover the proprietary compressed
   raster algorithm, then add it as an optional encoding after it is verified.
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
