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

## Current checkpoint

Static APK analysis of the printing path is complete. The following claims
still require the physical printer and are deliberately marked as inferred or
unknown:

- whether this official app build actually connects to this model over classic
  SPP, as its static gates indicate;
- the live FF00 service characteristic UUIDs and negotiated MTU/credits;
- actual responses to model, version, battery, and status commands;
- whether firmware `V1.06LY` reports model string `A2Y`;
- the proprietary compressed raster algorithm; and
- the exact physical margins and maximum reliable printable width.

## Proposed next phase: non-root transport capture

This phase requires explicit approval before work starts.

1. Add a Python project skeleton and a discovery-only CLI.
2. Enumerate BLE advertisements, GATT services, characteristic properties,
   MTU, and notifications without sending print data.
3. Enable Android's Bluetooth HCI snoop-log developer option and collect an
   `adb bugreport`; this does not require root.
4. Capture one official-app status query and one tiny known-pattern print.
5. Compare the official traffic with the existing Web Bluetooth
   implementation.
6. Present the capture and proposed protocol API before enabling writes in the
   clean-room driver.

If Android does not include the snoop log in a bug report on this device, the
fallback is host-side BLE capture plus a narrowly scoped classic-SPP proxy or
external Bluetooth sniffer. That fallback will be discussed before installing
anything.
