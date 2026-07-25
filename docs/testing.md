# Test rigs

The project has two deliberately separate test rigs. The default rig is fully
mocked and never accesses Bluetooth. The hardware-in-the-loop (HIL) rig uses a
paired printer through its operating-system serial port and is opt-in.

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

The print test is more strongly gated because it activates the print head and
moves paper. It will skip unless both consent flags are present:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_print.py `
  --live --allow-printing --printer-port COM7 -v
```

BLE printing has the same separate consent requirement:

```powershell
.venv\Scripts\python.exe -m pytest tests\hil\test_live_ble_print.py `
  --live --allow-printing --printer-address <printer-address> -v
```

The live print currently probes the unverified uncompressed `GS v 0` path. It
must not be run unattended. A failed print may establish that firmware
`V1.06LY` requires the proprietary compressed envelope.

## CLI safety gates

The CLI mirrors the test safety model:

```text
tronic-printer info --port COM7 --live
tronic-printer print-test --port COM7 --live --allow-printing
tronic-printer ble-info <printer-address> --live
tronic-printer ble-print-test <printer-address> --live --allow-printing
```

Omitting either required flag stops before the corresponding hardware action.
BLE scanning is passive. GATT enumeration connects but does not read or write
characteristic values and therefore requires `--live`.
