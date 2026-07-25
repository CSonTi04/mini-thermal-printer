# Lidl TRONIC Mini Pocket Printer

Clean-room reverse engineering and an open Python implementation for the Lidl
TRONIC Mini Pocket Printer.

The target observed by this project is:

- Bluetooth name: `Mini Pocket Printer_BLE`
- Firmware shown by the official app: `V1.06LY`
- Paper: approximately 56 mm wide
- Print head: 384 dots, inferred as 48 mm printable width at 8 dots/mm
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
- the app's resize, threshold, gamma, and error-diffusion pipeline; and
- native-library exports, app permissions, network surfaces, and signing
  provenance.

The findings are documented in:

- [Static APK analysis](docs/apk-analysis-v1.3.13.md)
- [Official-app transport capture](docs/captures/official-app-print-2026-07-24.md)
- [Protocol reference](docs/protocol.md)
- [Progress and approval log](docs/progress.md)
- [Mock and hardware-in-the-loop test rigs](docs/testing.md)
- [Driver architecture](docs/architecture.md)

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

## Repository policy

This repository contains only original documentation and, in later phases,
clean-room implementation code and tests. It does not contain the proprietary
APK, decompiled sources, phone dumps, signing material, or extracted manuals.
Those local artifacts are excluded by `.gitignore`.

Evidence labels used in the documentation:

- **Observed**: directly present in an APK, device dump, or user observation.
- **Recovered**: reconstructed from bytecode or native-library metadata.
- **Inferred**: a conclusion supported by static evidence but awaiting a live
  capture.
- **Verified**: reproduced against the physical printer.
- **Unknown**: not yet established.

## Licensing recommendation

Apache License 2.0 is recommended for the clean-room implementation. It is
permissive, includes an explicit patent grant, and works well for a small
hardware/protocol library. No proprietary app code or assets should be copied
into the implementation.
