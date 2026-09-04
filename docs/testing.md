# Test rigs

The project has two deliberately separate test rigs. The default rig is fully
mocked and never accesses Bluetooth. The hardware-in-the-loop (HIL) rig uses a
paired printer through its operating-system serial port and is opt-in.

On 2026-09-04, Windows pairing created an outgoing SPP channel on `COM6`, and
all nine HTML gallery templates printed successfully through `print-html`.
Each job returned `AA 0D 0A`; the printer remained ready after the batch.

## Mocked rig

`EmulatedPrinterTransport` models the verified `A2Y` responses and maintains
battery, density, status, and completed-job state in memory. It exercises the
same CQRS handlers used by the CLI and future GUI or web adapters.

Run all tests that do not touch hardware:

```powershell
.venv\Scripts\python.exe -m pytest -m "not hil"
```

Linux equivalent:

```bash
.venv/bin/python -m pytest -m "not hil"
```

### Linux validation status

On 2026-07-25, an editable install from `pyproject.toml`, all 94 non-HIL tests,
Ruff, and the installed CLI entry point passed under Python 3.12 on Ubuntu
24.04/WSL2. This is a Debian-family packaging and userspace compatibility test,
not a live Linux Bluetooth test. That WSL environment exposed system D-Bus but
had no `bluetoothctl` command and no controller in `/sys/class/bluetooth`.

Live Debian BLE HIL requires a physical or virtualized Debian host whose
Bluetooth adapter is visible to BlueZ. Use the same `--live` and
`--allow-printing` gates shown below; do not infer live BLE support from the WSL
result alone. The planned native target and staged procedure are documented in
[Raspberry Pi native Linux HIL stage](rpi-hil.md).

## Hardware-in-the-loop rig

Prerequisites:

1. Turn off Bluetooth on the phone or disconnect the official app.
2. Power on and pair the printer with the test host.
3. Identify the outgoing classic Bluetooth SPP serial port.
4. Obtain approval for the desired test tier.

Read-only identity and telemetry tests require both a port and `--live`:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_queries.py `
  --live --printer-port COM7 -v
```

The verified BLE equivalent takes the printer address instead of a COM port:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_ble_queries.py `
  --live --printer-address <printer-address> -v
```

The BLE path was originally verified on this printer, but a 2026-09-04 retest
with Bleak 1.1.1 could discover the advertisement while direct GATT connection
failed on Windows. Bluetooth LE Explorer could still connect. Use the outgoing
SPP port on Windows until this compatibility issue is resolved.

The print test is more strongly gated because it activates the print head and
moves paper. It will skip unless both consent flags are present:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_print.py `
  --live --allow-printing --printer-port COM7 -v
```

The production-path BLE calibration test uses recovered `codeESC` compression,
three-dot lines, a 96-row image, and 160 feed dots. It requires separate
consent:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_ble_compressed_print.py `
  --live --allow-printing --printer-address <printer-address> -v
```

A separate low-ink image-pipeline HIL test exercises normalization, two ordered
effects, ordered 4×4 dithering, compression, and BLE transport. It remains
skipped without both consent flags:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\hil\test_live_ble_preprocessed_image.py `
  --live --allow-printing --printer-address <printer-address> -v
```

The long four-style showcase prints four independent, labeled 384×384 image
jobs with approximately 335 mm total paper use. It adds a third consent gate
and 20-second cooling pauses between pages:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\hil\test_live_ble_image_showcase.py `
  --live --allow-printing --allow-four-image-showcase `
  --printer-address <printer-address> -s -v
```

Do not run this scenario unattended. Increase `--showcase-pause-seconds` if
physical output or status suggests heat accumulation.

The first approved run completed all four jobs in 90.74 seconds. Photographs
confirmed complete headers and images, including the 538-row noir page and its
large solid-black regions. The scenario is therefore hardware-verified on the
Windows BLE path; its explicit gates remain mandatory for future runs.

The separate uncompressed probe receives successful completion but renders only
its first expected horizontal row. It is retained as a regression probe:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_ble_print.py `
  --live --allow-printing --printer-address <printer-address> -v
```

Standalone BLE feed uses a verified one-row all-white raster workaround:

```powershell
.venv\Scripts\tronic-printer.exe ble-feed <printer-address> `
  --dots 160 --live --allow-printing
```

All live print tests must be attended so physical rendering can be compared
with transport-level completion.

## CLI safety gates

The CLI mirrors the test safety model:

```text
tronic-printer info --port COM7 --live
tronic-printer print-test --port COM7 --live --allow-printing
tronic-printer ble-info <printer-address> --live
tronic-printer ble-print-test <printer-address> --height 96 --line-width 3 `
  --feed-dots 160 --live --allow-printing
tronic-printer ble-print-test <printer-address> --encoding uncompressed `
  --live --allow-printing
tronic-printer ble-print-image <printer-address> image.png --width 384 `
  --threshold 128 --feed-dots 160 --live --allow-printing
tronic-printer ble-feed <printer-address> --dots 160 --live --allow-printing
```

Omitting either required flag stops before the corresponding hardware action.
BLE scanning is passive. GATT enumeration connects but does not read or write
characteristic values and therefore requires `--live`.
