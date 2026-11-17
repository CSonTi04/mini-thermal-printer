# NIIMBOT B1 support

The driver also speaks the NIIMBOT B1 protocol over any byte transport. The B1 uses
the same 384-dot head (203 dpi) as the TRONIC printer, so every image, text, HTML and
halftone-QR pipeline feeds it unchanged.

## Evidence

| Area | Status |
|---|---|
| USB CDC serial at 115200 baud, frame format, checksum | **Verified** (physical B1, 2026-11-16) |
| Info queries: device type, versions, serial, battery, density, paper type | **Verified** |
| Heartbeat (13-byte payload) | **Verified** reads; field meanings **Recovered** from [vkolarik/niimbot-b1](https://github.com/vkolarik/niimbot-b1) (hardware 6.01 / firmware 6.19, the same unit type) |
| Print-job lifecycle (density, paper type, start, page, rows, end, status poll) | **Verified**: the job completed with every acknowledgement on a physical B1 and matches that reference sequence; the paper result still needs a human check |
| Density ack is `0x31` (not `0x22`), paper-type ack is `0x33` | **Verified** (`0x31`); `0x33` matches the reference |
| `0xDB` packet = printer-reported command error | **Recovered** (reference), handled but not yet provoked on hardware |

Observed on a B1 reporting hardware **6.01** / firmware **6.19** (info bytes `06 01` and
`06 13`, i.e. `major, minor`; decoding them as one decimal number gives a wrong
"15.55"): device type `4096`, density `3`, paper type `3` (continuous), battery level
`4`.

The heartbeat reports `cover_closed` (byte 9 is `0`), the battery level (byte 10),
`paper_present` (byte 11 is `0`) and the RFID state (byte 12 is `1` for a tagged roll).
A roll without a tag reads `0` in byte 12; stock firmware rejects such rolls, firmware
that skips the tag check prints them. Library callers decide what to gate on; the
monitor in `qa-order-printer` treats an open cover or missing paper as a fault.

## Commands

```powershell
tronic-printer niimbot-info --port COM4 --live
tronic-printer niimbot-info --ble --live                       # Bluetooth LE, first "B1-*" found
tronic-printer niimbot-ble-scan                                # passive scan, no connection

tronic-printer niimbot-print-image image.png --port COM4 `
  --preview preview.png --live --allow-printing

tronic-printer niimbot-print-html template.html --data data.json --ble `
  --preview preview.png --live --allow-printing
```

Every connecting command takes exactly one of `--port COM4` (USB) or `--ble [ADDRESS]`.
The same two consent gates as the TRONIC commands apply: `--live` for any hardware
access and `--allow-printing` for anything that moves paper. `niimbot-info` only
sends info and heartbeat queries.

## Bluetooth LE

`tronic_printer.infrastructure.niimbot_ble.NiimbotBleTransport` carries the same packets
over BLE, behind the same transport port as USB, so `NiimbotClient` is unchanged. It
connects in its constructor and raises `OSError` when the printer is off, out of range or
already connected elsewhere.

| Fact | Status |
|---|---|
| Advertises as `B1-<serial>` (here `B1-I612120126`); the advertisement carries no service UUID, so discovery matches the name | **Verified** |
| Vendor service `e7810a71-73ae-499d-8c15-faa9aef0c3f2`, one characteristic with `notify` + `write-without-response`, 237-byte write limit | **Verified** (matches the reference) |
| Read-only queries (info and heartbeat) over BLE, repeated reconnects | **Verified** (connect 3–6 s including the scan, queries about 2 s) |
| Write pacing: 64-byte writes, 10 ms apart | **Recovered** from the reference client; **Unknown** under a full print until the first recorded BLE print |

Only one BLE connection exists at a time: close the phone app first. The B1 stays
reachable over USB and BLE at the same time. Printing is slower than USB because of the
write pacing. A connect costs several seconds, so an application that probes the printer
often should connect per operation and cache the address, as `qa-order-printer` does.

Options: `--density 1-5`, `--feed-rows N` (blank rows appended so the print clears the
tear bar, default 96), `--label-type N` (default: re-send whatever paper type the
printer reports, so continuous paper stays continuous) and
`--start-variant v3|legacy`.

## Job lifecycle

`NiimbotClient.print_raster` sends, waiting for an acknowledgement after each step:

1. `0x21` set density, `0x23` set paper type
2. `0x01` print start, `0x03` page start, `0x13` page size (rows, columns)
3. Row packets: identical neighbouring rows collapse into one packet with a repeat
   count (at most 255); blank rows use the empty-row command `0x84`; other rows use
   `0x85` with the black-pixel counts of the three 128-dot thirds of the row
4. `0xE3` page end, then `0xA3` status polls until the page reports 100%
5. `0xF3` print end

If anything fails after the job started, the client sends a best-effort `0xF3` so the
printer is left idle.

`--start-variant v3` sends the seven-byte print-start and six-byte page-size payloads
(`encode_print_start`, `encode_set_page_size`). `legacy` sends the one-byte start and
four-byte page size used by older firmware. If a B1 rejects the default, try the
other and record the result here.

## Tests

`EmulatedNiimbotTransport` in `tronic_printer.testing` answers queries like the
physical B1 and rebuilds the printed page from row packets, verifying each row's
black counts. It lets tests assert that a raster survives encoding byte for byte
without hardware.
