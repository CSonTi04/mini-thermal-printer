# Protocol reference

This document is a clean-room reference recovered from the official Android
app `com.printer.lidloffice` version `1.3.13` (version code 176). It describes
what the app is capable of sending. Commands are not considered verified on
firmware `V1.06LY` until captured or tested against the physical printer.

## Target profile

| Property | Result | Evidence |
| --- | --- | --- |
| Advertised/observed name | `Mini Pocket Printer_BLE` | Observed |
| SDK name prefix | `Mini Pocket Printer` | Recovered |
| SDK device class | `MiniPocketPrinter` | Recovered |
| Inheritance | `MiniPocketPrinter -> DP_D1 -> BaseNormalDevice` | Recovered |
| Transport enum | `BLE_DUAL` | Recovered |
| SDK per-device BLE gate | `false` | Recovered |
| Print width | 384 dots | Recovered |
| Dot density | 8 dots/mm, approximately 203 dpi | Recovered |
| Printable width | 48 mm (`384 / 8`) | Inferred |
| Physical roll | approximately 56 mm | Observed |
| Density range | 0 through 2; app default 1 | Recovered |
| Default trailing feed | 80 dots | Recovered |
| Grayscale support | disabled by default | Recovered |
| Label support | enabled | Recovered |

Device lookup is prefix-based. Therefore `Mini Pocket Printer_BLE` selects the
`MiniPocketPrinter` class even though its suffix is not part of the registered
name.

After connection, `MiniPocketPrinter.initAfterConnect()` issues a model query.
Compression is enabled only when the decoded response is exactly `A2Y`.

## Classic Bluetooth SPP

- UUID: `00001101-0000-1000-8000-00805F9B34FB`
- Output stream chunks: at most 16,384 bytes
- Input buffer: 8,192 bytes per read
- Ordinary request timeout: typically 3 seconds
- End-of-job timeout: 70 seconds

The official-app selection logic strongly indicates classic SPP for this model:
BLE use requires both a global SDK gate and a per-device gate, and both are
statically `false`. No app caller of `setEnableBle(true)` and no matching custom
printer override were found. This is an **inference about this app build**, not
a claim that the printer lacks BLE.

## BLE GATT transport

The bundled SDK also implements the following BLE transport:

| Role | Selection rule |
| --- | --- |
| Service | UUID string starts with `0000ff00` |
| Write | characteristic in that service with property bit `0x04` (`WRITE_NO_RESPONSE`) |
| Response notify | notify characteristic whose UUID starts with `0000ff01` |
| Flow-control notify | notify characteristic whose UUID starts with `0000ff03` |

The write characteristic UUID is selected by properties, not by a hard-coded
UUID. A common FF02 layout is plausible but remains **unknown** until live GATT
enumeration.

FastBle is initialized with a 20-byte split-write size, a 10-second connection
timeout, and a 5-second operation timeout. The printer transport layers its own
waits and negotiated packet size on top of those defaults.

Connection setup:

1. Connect by MAC address, with a 12-second wait.
2. Discover the FF00 service and all three required characteristics.
3. Enable FF01 notifications, with a 5-second wait.
4. Enable FF03 notifications.
5. Wait up to 15 seconds for both initial credit and MTU setup.

FF03 flow-control messages:

- `01 credit` adds an unsigned number of transmission credits.
- `02 mtu_lo mtu_hi` supplies a little-endian desired ATT payload size.

The SDK requests GATT MTU `payload + 3`, clamps a successful value to 512, and
uses `MTU - 3` as its packet payload. It retries MTU negotiation up to three
times while reducing the requested value by 20 bytes per attempt. Before
negotiation, packet payload defaults to 20 bytes.

Write flow control:

1. Wait while credits are zero, aborting after 30 seconds.
2. If at least three credits are available, reserve one.
3. Send up to `min(ceil(remaining / packet_size), usable_credits)` packets in
   the next FastBle split-write batch.
4. Wait up to 10 seconds for the batch callbacks.
5. Decrement credits by the packet count.

FF01 carries ordinary command responses and asynchronous device data. FF03 is
reserved for credit and MTU events.

## Mini Pocket Printer label-print lifecycle

`DP_D1` overrides the generic label path. One page is sent as:

```text
10 FF F1 03                 enable/start print job (default mode 3)
00 00 00 00 00 00          wake-up prefix
00 00 00 00 00 00          (12 zero bytes total)
1F 80 01 20                 paper type 1, value 0x20
<raster command and data>
1D 0C                       position to label boundary
10 FF F1 45                 stop/end print job
```

The stop response is accepted when its first byte is `AA` or its decoded text
starts with `OK`.

The generic continuous-paper path differs after the raster: it feeds
`endLineDot` using `1B 4A n` and then stops the job. For a 384-dot device,
`endLineDot` defaults to 80.

## Command table

Multi-byte values are described in the byte order recovered from the app.

| Operation | Bytes | Response behavior |
| --- | --- | --- |
| Start/enable job | `10 FF F1 mode` | None required; default mode `03` |
| Wake printer | 12 zero bytes | None required |
| Stop job | `10 FF F1 45` | first byte `AA` or ASCII prefix `OK`; 70 s timeout |
| Feed dots | `1B 4A dots` | None required |
| Reverse/adjust dots | `1F 11 dots` | None required |
| Position label | `1D 0C` | None required |
| Set paper type | `1F 80 type value` | callback variant expects ASCII prefix `OK` |
| Query battery | `10 FF 50 F1` | battery value is response byte 1 |
| Query density | `10 FF 11` | first response byte |
| Set density | `10 FF 10 00 density` | success/failure callback |
| Query status | `10 FF 40` | one-byte bit field |
| Query model | `10 FF 20 F0` | response decoded as a string |
| Query firmware | `10 FF 20 F1` | response decoded as a string |
| Query serial number | `10 FF 20 F2` | response decoded as a string |
| Query boot info | `10 FF 20 EF` | response decoded as a string |
| Set print width | `10 FF 15 width_lo width_hi` | None required |
| Query shutdown time | `10 FF 13` | first response byte |
| Set shutdown time | `10 FF 12 value_hi value_lo` | success/failure callback |
| Query speed | `10 FF 20 A0` | first response byte |
| Set speed | `10 FF C0 speed` | success/failure callback |
| Query time format | `10 FF B0` | exactly one response byte |
| Set time | `10 FF 53 4A format` + 7 bytes | ASCII prefix `OK` |
| Heating level | `1F 70 01 level` | success/failure callback |
| Set printer mode | `10 FF 30 27 mode` | success/failure callback |
| Recovery/reset setting | `10 FF 04` | success/failure callback |
| Set platform | `FC FF 00 02 45 02 00 46` | None required |
| Mark first page | `1B BB CC` | None required |
| Mark last page | `1B BB BB` | None required |
| Mark not-last page | `1B BB AA` | None required |

The seven time bytes are `year_hi year_lo month day hour minute second`.

### Status byte

| Bit | Meaning when set |
| --- | --- |
| 0 | Printing |
| 1 | Cover open |
| 2 | Paper absent |
| 3 | Low battery |
| 4 | Overheat |
| 5 | Charging |
| 6 | Overheat |

The SDK treats either bit 4 or bit 6 as overheat. Bit 7 was not assigned in the
recovered parser.

The special eight-byte frame
`FC FF 00 02 45 FE 01 BB` is dispatched as a label-paper error.

## One-bit raster format

Default output uses the ESC/POS `GS v 0` envelope:

```text
1D 76 30 mode xL xH yL yH <raster>
```

- `mode` is constrained to 0 through 3; the app uses 0.
- `x = ceil(pixel_width / 8)`, little-endian.
- `y = pixel_height`, little-endian.
- Rows are emitted top to bottom.
- Within a byte, the leftmost pixel is bit 7.
- A pixel becomes black when `(red + green + blue) / 3 < 128`.
- Padding bits at the right edge remain white.

For a 384-dot row, `x = 48` bytes. A 384 by 100 image therefore has an 8-byte
header followed by 4,800 raster bytes.

## Optional compressed raster

When model query returns `A2Y`, the same one-bit raster payload is compressed
and wrapped as:

```text
1F 10 width_bytes_hi width_bytes_lo height_hi height_lo
      compressed_length_be32 <compressed_data>
```

Compression way 0 calls native `Compress.codeESC`; way 1 calls
`Compress.codeLihu`. The Mini Pocket Printer class enables compression but does
not change the default way, so its static path is `codeESC`.

The compression algorithm itself remains **unknown**. It lives in the stripped
ARM64 `libPrinterNative.so`. Uncompressed raster is consequently the first
clean-room implementation target.

## Grayscale extension

The SDK contains a grayscale raster extension:

```text
1D 47 59 levels width_bytes_lo width_bytes_hi height_lo height_hi <data>
```

It packs two four-bit pixels per byte. Level 4 uses direct quantization; other
supported level counts use a Floyd-Steinberg-style quantizer. The Mini Pocket
Printer profile does not enable grayscale support, so this is out of scope
until hardware evidence says otherwise.

## Secondary framed protocol

The SDK also contains generic framed transports that are not yet tied to this
printer:

- `FC FF length_be command_payload xor_checksum`
- `FB AA ... additive_checksum`

Response parsing for the FC/FF family reads a big-endian length at bytes 2-3
and data after the six-byte prefix. These formats must not be assumed for the
Mini Pocket Printer beyond commands independently listed above.
