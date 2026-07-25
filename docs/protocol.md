# Protocol reference

This document is a clean-room reference recovered from the official Android
app `com.printer.lidloffice` version `1.3.13` (version code 176). A non-root
Android HCI capture has verified the official transport, identification
queries, and normal compressed print sequence on firmware `V1.06LY`. Generic
SDK commands not seen in that capture remain unverified.

## Target profile

| Property | Result | Evidence |
| --- | --- | --- |
| Advertised/observed name | `Mini Pocket Printer_BLE` | Observed |
| SDK name prefix | `Mini Pocket Printer` | Recovered |
| SDK device class | `MiniPocketPrinter` | Recovered |
| Inheritance | `MiniPocketPrinter -> DP_D1 -> BaseNormalDevice` | Recovered |
| Transport enum | `BLE_DUAL` | Recovered |
| SDK per-device BLE gate | `false` | Recovered |
| Official-app transport | Classic RFCOMM/SPP | Verified |
| PC BLE transport | FF00 GATT service | Verified |
| Live model response | `A2Y` | Verified |
| Live firmware response | `V1.06LY` | Verified |
| Print width | 384 dots | Verified |
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

The official-app selection logic indicated classic SPP for this model: BLE use
requires both a global SDK gate and a per-device gate, and both are statically
`false`. A live HCI capture verified that `com.printer.lidloffice` opens the SPP
UUID over classic Bluetooth. The printer separately advertises a BLE identity,
so this is not a claim that the hardware lacks BLE.

The captured connection used RFCOMM DLCI 2. Android's stack handled RFCOMM
credit flow; application bytes begin after the RFCOMM credit octet and should
not include that octet when reproducing commands through an OS serial port.

## BLE GATT transport

A Windows live session on 2026-07-25 verified this service layout and used it
successfully for model, firmware, battery, density, and status queries. The
printer requested a 100-byte packet payload through FF03, but Windows exposed
a 20-byte write-without-response maximum, so the driver safely uses 20-byte
packets. Printing over BLE has not yet been attempted.

The bundled SDK also implements the following BLE transport:

| Role | Selection rule |
| --- | --- |
| Service | UUID string starts with `0000ff00` |
| Write | characteristic in that service with property bit `0x04` (`WRITE_NO_RESPONSE`) |
| Response notify | notify characteristic whose UUID starts with `0000ff01` |
| Flow-control notify | notify characteristic whose UUID starts with `0000ff03` |

The write characteristic UUID is selected by properties, not by a hard-coded
UUID. Live enumeration verified that this printer uses `FF02`, with both
`write` and `write without response` properties.

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

## Verified continuous-roll lifecycle

The official app's normal `PrintActivity` path produced:

```text
10 FF 40                    query status
10 FF F1 03                 enable/start print job
00 00 00 00 00 00          wake-up prefix
00 00 00 00 00 00          (12 zero bytes total)
1F 10 00 30 00 25          compressed raster: 48 bytes wide, 37 rows
00 00 00 D9 <217 bytes>     217-byte compressed payload
1B 4A 50                    feed 80 dots
10 FF F1 45                 stop/end print job
```

The printer returned `AA 0D 0A` after each completed job. Two captured jobs had
identical 227-byte compressed frames.

The normal path did not issue a paper-type command. It used the generic
continuous-paper feed rather than `DP_D1`'s indexed-label positioning command.

## Statically recovered label lifecycle

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
starts with `OK`; live completion was `AA 0D 0A`.

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

A live PC BLE test on firmware `V1.06LY` acknowledged this envelope for a
384×32 raster and returned `AA 0D 0A`, but physically rendered only one thin
horizontal line instead of the expected multi-row border/crosshair. A later
feed confirmed the rest was not hidden under the cover. Full uncompressed
raster support therefore remains unverified.

## codeESC compressed raster

When model query returns `A2Y`, the same one-bit raster payload is compressed
and wrapped as:

```text
1F 10 width_bytes_hi width_bytes_lo height_hi height_lo
      compressed_length_be32 <compressed_data>
```

Compression way 0 calls native `Compress.codeESC`; way 1 calls
`Compress.codeLihu`. The Mini Pocket Printer class enables compression but does
not change the default way, so its path is `codeESC`.

ARM64 disassembly and a captured input/output vector establish that `codeESC`
is a zlib-wrapped DEFLATE stream with these parameters:

| zlib setting | Value |
| --- | ---: |
| Compression level | `Z_DEFAULT_COMPRESSION` (`-1`) |
| Method | `Z_DEFLATED` (`8`) |
| Window bits | `10` |
| Memory level | `8` |
| Strategy | `Z_DEFAULT_STRATEGY` (`0`) |
| Flush | `Z_FINISH` (`4`) |

The JNI wrapper at `0x9184` calls a shared encoder at `0x994C`. Its allocation
helper at `0x9A30` computes zlib's `compressBound` expression
`n + (n >> 12) + (n >> 14) + 11`. The encoder initializes an embedded zlib
stream with `deflateInit2_`, finishes it, and returns the resulting bytes.
`codeLihu` and `codeCPCL` call the same encoder with window bits 10;
`codeTSPL` differs by using window bits 15.

The live printer returned `A2Y` and the official app sent:

```text
1F 10 00 30 00 25 00 00 00 D9 <217 compressed bytes>
```

This represents 384×37 one-bit pixels: 1,776 uncompressed raster bytes reduced
to 217 compressed bytes. The two captured frames were identical:

- complete 227-byte frame SHA-256:
  `91FFAE2FAD7FA057660BEE9D62CE69D88DF65FFF66ED2CE2F0399A9943037CD4`
- compressed-payload SHA-256:
  `8E72234F7B247B067D2E4F08A0023B42190D6436BEE4DD23F32146B9267586F6`

Decompressing the payload with window bits 10 produces exactly 1,776 bytes
with SHA-256
`72D4FED9D387831DC6F3BEC1750372BDE59AEEBC25D0F186F2A8A754D44FF400`.
Recompressing those bytes with the parameters above reproduces all 217 captured
bytes and the existing compressed-payload hash. The clean-room Python driver
uses this encoding by default.

A subsequent live BLE calibration used a 384×96 raster with three-dot lines.
Its 4,608 raw bytes compressed to 65 bytes in a 75-byte frame with SHA-256
`61406202BF27FA23264A61738E1D6DB7B217FC87656BC7F9E913F6AD934EAE4E`.
The printer returned `AA 0D 0A`, and physical inspection confirmed the complete
border, crosshair, and all 2 mm ruler ticks. Multi-row `codeESC` output is
therefore verified end to end.

The later four-style image showcase verified realistic high-entropy compressed
pages at heights of 494, 516, and 538 rows. All four jobs completed on one BLE
connection, and photographs showed complete rasters without missing horizontal
bands. The verified reliable-height lower bound is therefore 538 rows; this is
not evidence that 538 is the protocol or firmware maximum.

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
