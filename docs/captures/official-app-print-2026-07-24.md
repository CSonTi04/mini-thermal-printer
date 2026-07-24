# Official-app Bluetooth capture: 2026-07-24

## Result

The official Lidl Office app version 1.3.13 communicates with this Mini Pocket
Printer over classic Bluetooth RFCOMM/SPP, not BLE. The capture also verifies
the static model-gated compression path:

- model: `A2Y`;
- firmware: `V1.06LY`;
- print width: 384 dots / 48 bytes per row;
- compressed envelope: `1F 10`;
- trailing feed: 80 dots; and
- successful print completion: `AA 0D 0A`.

This changes the transport conclusion from strong static inference to verified
behavior on the physical printer.

## Capture provenance

| Property | Value |
| --- | --- |
| Phone | Samsung SM-S926B |
| Android | 16 / API 36 |
| Security patch | 2026-06-05 |
| Root | No |
| HCI snoop setting | `FULL` |
| Capture interval | 2026-07-24 23:16:45–23:20:57 UTC |
| Printer address | redacted; suffix `55:40` |
| Bug report SHA-256 | `25C3BE28734B3DDFF53B13E37289FE17F2CE54D94039FEC2459F6C860DDC4EA8` |
| `btsnoop_hci.log` SHA-256 | `52A024B1A5EE1185C0CDEB1B07B9BDD5DAF2EE7F6E71856B12E9C460235468FB` |

The original bug report, snoop log, full MAC address, device serial number, and
extracted RFCOMM streams remain under ignored `private/captures/`.

## Transport correlation

Android's Bluetooth state recorded:

- app process: `com.printer.lidloffice`;
- remote name: `Mini Pocket Printer`;
- service: `00001101-0000-1000-8000-00805F9B34FB`;
- transport: classic BR/EDR;
- HCI connection handle: `0x0009`;
- RFCOMM DLCI: 2;
- phone-to-printer L2CAP CID: `0x0051`; and
- printer-to-phone L2CAP CID: `0x0049`.

The same physical address appeared separately in discovery as
`Mini Pocket Printer_BLE`, confirming a dual-interface device. No LE connection
to that address occurred during the official-app print.

RFCOMM UIH frames with the P/F bit carried a one-byte RFCOMM credit field
outside the application payload length. Those credit octets are Android stack
flow control, not printer commands.

## Identification and status traffic

| Request | Captured response | Interpretation |
| --- | --- | --- |
| `10 FF 20 F0` | ASCII `A2Y` | Model; enables compressed path |
| `10 FF 20 F1` | ASCII `V1.06LY` | Firmware |
| `10 FF 20 F2` | 12-byte ASCII identifier | Device serial; redacted |
| `10 FF 50 F1` | `00 5A` or `00 5C` | Battery 90% or 92% |
| `10 FF 13` | `14` | Shutdown setting value 20 |
| `10 FF 40` | `00` | No status/error bits set |
| `10 FF 10 00 02` | ASCII `OK` | Density set to level 2 |
| `10 FF 11` | `01 0C 10`, later `02 0C 10` | First byte tracks density |

Battery polling occurred approximately every 25 seconds while the app remained
connected.

## Captured print sequence

Two identical jobs were present:

```text
10 FF 40
  -> 00

10 FF F1 03
00 00 00 00 00 00 00 00 00 00 00 00
1F 10 00 30 00 25 00 00 00 D9 <217 compressed bytes>
1B 4A 50
10 FF F1 45
  -> AA 0D 0A
```

Decoded raster metadata:

| Field | Value |
| --- | ---: |
| Row width | 48 bytes |
| Pixel width | 384 dots |
| Height | 37 dots |
| Raw one-bit payload | 1,776 bytes |
| Compressed payload | 217 bytes |
| Complete compressed frame | 227 bytes |

Reproducibility hashes:

- complete frame:
  `91FFAE2FAD7FA057660BEE9D62CE69D88DF65FFF66ED2CE2F0399A9943037CD4`
- compressed data only:
  `8E72234F7B247B067D2E4F08A0023B42190D6436BEE4DD23F32146B9267586F6`

The normal print path did not send `1F 80 01 20` or `1D 0C`. It used the generic
continuous-roll sequence with `1B 4A 50`. The `DP_D1` paper-type/position path
therefore applies to indexed-label printing, not this normal roll print.

## Confirmed and still unknown

Confirmed:

- official app uses classic SPP;
- static command parsing is accurate;
- this firmware returns `A2Y`;
- `A2Y` activates the `1F 10` compressed path;
- compressed dimensions and length use big-endian fields;
- the continuous-roll path feeds 80 dots; and
- print completion begins with `AA`.

Still unknown:

- `codeESC` compression algorithm;
- whether the printer also accepts uncompressed `GS v 0`;
- live BLE GATT characteristic layout;
- exact physical margins; and
- indexed-label behavior.
