# Progress and approval log

Last updated: 2026-07-24

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
- Nothing has been staged or committed.

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

## Current checkpoint

The official app's transport and normal print sequence are now verified.
Remaining unknowns:

- the live FF00 BLE characteristic layout and negotiated MTU/credits;
- the proprietary `codeESC` compressed-raster algorithm;
- whether this firmware also accepts the uncompressed `GS v 0` envelope;
- exact physical margins and maximum reliable printable width; and
- behavior on indexed/label media rather than the current continuous roll.

## Proposed next phase: PC discovery and minimal driver

This phase requires explicit approval before installing dependencies or
sending commands from the PC.

1. Disconnect the official app so the printer has no active client.
2. Add a Python project skeleton, protocol model, raster packer, and unit tests.
3. Install `pyserial` and `bleak` only after approval.
4. Enumerate the PC's Bluetooth devices and the printer's BLE GATT layout
   without writes.
5. Pair classic Bluetooth and identify the Windows COM port.
6. Send only model, firmware, battery, and status queries first.
7. Present those results before replaying a captured print or testing
   uncompressed raster output.
