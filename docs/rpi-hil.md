# Raspberry Pi native Linux HIL stage

The Raspberry Pi is the planned first native Linux/BlueZ hardware target. WSL
remains useful for Debian-family packaging, linting, mocked tests, and CLI
development, but its current environment does not expose a Bluetooth
controller and therefore cannot validate live BLE behavior.

## Suggested host

- Raspberry Pi with onboard Bluetooth or a supported USB Bluetooth adapter;
- current 64-bit Raspberry Pi OS, which is Debian-based;
- Python 3.11 or newer; and
- the printer within a few metres of the adapter during initial tests.

## One-time prerequisites

Package installation requires separate approval on the Pi:

```bash
sudo apt update
sudo apt install bluetooth bluez python3-venv
```

Confirm that BlueZ sees an adapter before installing or running the driver:

```bash
systemctl is-active bluetooth
bluetoothctl show
```

Then create an isolated environment from the repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -m "not hil"
```

## Staged live validation

Keep Bluetooth disabled on the phone so the official app cannot take the
printer connection. Each tier remains independently gated.

1. Passive discovery, which does not connect or transmit to the printer:

   ```bash
   .venv/bin/tronic-printer ble-scan --timeout 10
   ```

2. After explicit read-only-query approval, inspect GATT and query the device:

   ```bash
   .venv/bin/tronic-printer ble-gatt <printer-address> --live
   .venv/bin/tronic-printer ble-info <printer-address> --live
   .venv/bin/python -m pytest tests/hil/test_live_ble_queries.py \
     --live --printer-address <printer-address> -v
   ```

3. Only after separate print approval, run one deterministic compressed job:

   ```bash
   .venv/bin/python -m pytest tests/hil/test_live_ble_compressed_print.py \
     --live --allow-printing --printer-address <printer-address> -v
   ```

4. After that calibration is physically confirmed, test a chosen image with
   a fresh approval:

   ```bash
   .venv/bin/tronic-printer ble-print-image <printer-address> image.png \
     --width 384 --threshold 128 --feed-dots 160 \
     --live --allow-printing
   ```

The first Pi session should capture the OS release, Python version, BlueZ
version, adapter identity, discovered device name, GATT layout, query results,
completion bytes, and physical print outcome. Full Bluetooth addresses and
adapter serials must stay out of tracked documentation.

