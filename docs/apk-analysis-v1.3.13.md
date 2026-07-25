# Static APK analysis: Lidl Office 1.3.13

Analysis date: 2026-07-24

> Subsequent non-root HCI capture verified that the official app uses classic
> RFCOMM/SPP, that this printer reports model `A2Y`, and that its normal print
> path uses the recovered compressed envelope. See
> `docs/captures/official-app-print-2026-07-24.md`.

## Executive result

The official app's complete printing path for the Lidl TRONIC Mini Pocket
Printer has been recovered statically.

The app maps `Mini Pocket Printer_BLE` by prefix to a 384-dot,
approximately-203-dpi normal/label device. Its print path uses a short command
sequence around an ESC/POS-compatible one-bit raster. The app preprocesses
images at 384 pixels wide using either an adaptive-gamma, custom
Sierra-like error diffusion ("Image" mode) or a fixed threshold of 128
("Text" mode).

The SDK contains both classic SPP and BLE transports. However, this app build
registers the Mini Pocket Printer's per-device BLE gate as `false`, while the
global BLE gate also defaults to `false` and has no app-side caller. The
official app is therefore strongly inferred to choose classic SPP for this
model. That conclusion needs a non-root HCI capture because the physical
printer independently advertises BLE.

No proprietary code or assets are included in this repository.

## Scope and evidence rules

This report covers:

- installed-package provenance and integrity;
- manifest and application attack surface;
- bundled SDKs, resources, native code, and network surfaces;
- device identification and capabilities;
- classic and BLE transport implementations;
- command and response handling;
- raster packing and native compression boundary; and
- the production image-to-raster pipeline.

The report is a static analysis of the installed Play-delivered APK set. It
does not claim that every generic SDK command is supported by firmware
`V1.06LY`.

## APK set and integrity

The unrooted phone reported:

| Property | Value |
| --- | --- |
| Package | `com.printer.lidloffice` |
| Version name | `1.3.13` |
| Version code | `176` |
| Minimum SDK | 23 |
| Target SDK | 35 |
| Compile SDK | 35 |
| ABI | `arm64-v8a` |
| Installer | Google Play |

Pulled split set:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `base.apk` | 142,248,580 | `CED08999DC8B4AC40E22957CE93E67CEE43905AAAF4F363F8D72DD2BBD0C0812` |
| `split_config.arm64_v8a.apk` | 25,399,878 | `D11562281342A833D8206619D8948930CB30CA45D2FCAACF248499F0006F895D` |
| `split_config.xxhdpi.apk` | 119,996 | `BD90DAEFC7B16FB9B088F5BBEBC95B342D04CD93C6F73E9BD4E0C85F5561AAB6` |

The base APK's JAR signature verifies. Signer certificate:

| Field | Value |
| --- | --- |
| Subject/issuer | `CN=Android, OU=Android, O=Google Inc., L=Mountain View, ST=California, C=US` |
| Serial | `c837ec8c09a2dde6c33682630d88b4f65f20fb6a` |
| Validity | 2022-11-15 through 2052-11-15 |
| Key | RSA 4096 |
| Signature | SHA256withRSA |
| SHA-1 | `53:6C:DB:6A:DE:C3:B1:E2:E3:0A:06:DA:7C:FE:3D:DE:AA:4B:7C:80` |
| SHA-256 | `5B:0D:2D:72:53:98:9F:49:A6:97:F2:A0:5C:4D:C3:F4:7B:29:71:D4:4D:91:89:A3:12:A4:E6:56:FD:91:E1:81` |

`META-INF/BNDLTOOL.SF` and `BNDLTOOL.RSA` are present. Android's package dump
also reports modern APK signing. The exact v2/v3 scheme matrix was not
independently printed because Android Build Tools/apksigner was not installed;
this does not affect the recovered printing behavior.

## Toolchain and coverage

| Tool | Version/use |
| --- | --- |
| Java | JDK 21.0.2 |
| Apktool | 3.0.3 |
| JADX | 1.5.5 |
| ELF inspection | WSL `file`, `readelf`, `nm`, `strings` |

Decoded output:

- 3 DEX files;
- 5,664 generated Java files;
- 12,460 smali files;
- 3,513 resource files; and
- 597 asset files.

Apktool decoded the base and both splits. The base decode emitted unresolved
resource-reference warnings where resources belong to the density split, so
split resources must be considered together.

JADX emitted decompilation errors and the generated tree contains 522
`Method not decompiled` placeholders across app code and bundled libraries.
Of those, 11 are under `com.printer`, 5 under `com.luckprinter`, and 2 are in
the obfuscated transport packages. Relevant gaps were checked against smali:

- `PrinterHelper.initDevice` was fully recovered from smali.
- Classic-SPP connection setup remains partially awkward in Java output, but
  its UUID, stream behavior, read loop, write chunking, and command path are
  visible in Java and smali.
- The Mini Pocket Printer print lifecycle, raster code, BLE transport, and
  production image pipeline decompiled successfully.

Smali is treated as authoritative whenever JADX output is incomplete.

## Application structure

The application class is `com.printer.lidloffice.base.App`; the launcher is
`com.printer.lidloffice.WelcomeActivity`.

Declared components:

| Type | Count |
| --- | ---: |
| Activities | 44 |
| Services | 2 |
| Receivers | 1 |
| Providers | 3 |
| Total | 50 |

The app contains two closely related product workflows:

- continuous/pocket printing; and
- sticker/thermal-label editing and printing.

There are dedicated sticker-label editor, template, size, print, and history
activities. This explains generic SDK support that is not necessarily
applicable to the pocket printer.

The 597 assets include 41 PDFs: 15 localized Pocket Printer IAN508705 manuals,
14 Label Printer IAN538612 manuals, and 12 older/localized Thermo Label Printer
manual files. Their size accounts for much of the unusually large base APK.

Notable bundled libraries include:

- LuckPrinter `sdk_new`;
- FastBle;
- OpenCV 4 native bindings;
- AndroidX, Room, and Material;
- Glide and Luck Picture Selector;
- ZXing;
- Retrofit, OkHttp, Okio, Gson, and Fastjson;
- RxJava and Kotlin coroutines;
- UCrop; and
- PDF.js assets.

No Firebase Analytics, Crashlytics, AppsFlyer, Adjust, Mixpanel, Amplitude,
Sentry, Flurry, or Tencent Bugly implementation was found by package/API
search. An empty `BuglyKey` class exists, but no Bugly SDK package or call was
found. This is a static absence finding, not proof that all network behavior is
inactive.

## Manifest and security surface

Requested permissions:

- legacy Bluetooth and Bluetooth admin;
- Android 12+ Bluetooth scan, connect, and advertise;
- coarse and fine location;
- camera;
- legacy read/write external storage;
- Internet, Wi-Fi state, and network state;
- vibration; and
- download without notification.

BLE hardware is optional. `allowBackup` is false and `extractNativeLibs` is
false.

Five app activities are exported without an app-defined permission:

- `HomeActivity`
- `WelcomeActivity`
- `DeviceListActivity`
- `DeviceInfoActivity`
- `PermissionListActivity`

Only `WelcomeActivity` has the launcher intent filter. The other exported
activities enlarge the external invocation surface, but static inspection
alone does not establish an exploitable issue.

All three providers are non-exported. Both file providers can grant URI
permissions; the Luck Picture provider declares broad external/root paths.
That is a broad grant surface, but callers still require an explicitly granted
URI because the provider itself is not exported.

The only exported receiver is AndroidX Profile Installer's receiver, protected
by `android.permission.DUMP`.

Network security globally disables cleartext traffic. One legacy search URL is
hard-coded as `http://www.google.com.hk/...`; it conflicts with the cleartext
policy unless WebView upgrades or redirects it.

## Web and network behavior

Static app endpoints:

- privacy and article pages under
  `https://api.pp.luckjingle.com/api/apis/public/webview/appArticles/`;
- a support-form file upload in bundled `DeviceReport.html` to
  `https://api.pp.luckjingle.com/api/apis/app/oss/upload`; and
- user-selected/public browsing destinations such as Google, Wikipedia,
  Reddit, Pinterest, and others.

`WebViewActivity` enables JavaScript, DOM storage, file/content access,
`allowFileAccessFromFileURLs`, and `allowUniversalAccessFromFileURLs`. It also
exposes an `Android.submitMail()` JavaScript bridge that parses supplied
support information and opens an email composer. URL navigation is not
restricted to an allowlist. The activity is not exported, which reduces direct
external reachability, but the permissive file/URL settings are still a
hardening concern when untrusted content is displayed.

The method named `StickerLabelEditActivity.uploadFile` is misleading: smali
shows that it writes PNG bytes to the app's local sticker-label image
directory and returns the local path. It does not perform a network upload.

## Device identification

The SDK registers:

```text
name prefix: Mini Pocket Printer
class:       MiniPocketPrinter
transport:   BLE_DUAL
BLE enabled: false
```

`PrinterEnum.getByStartWithName()` compares prefixes. The observed
`Mini Pocket Printer_BLE` therefore instantiates `MiniPocketPrinter`, records
the full device name and MAC, and uses the registered prefix as its model
identity.

Class hierarchy:

```text
BaseDevice
  -> BaseNormalDevice
    -> DP_D1
      -> MiniPocketPrinter
```

Recovered defaults:

- 384-dot print width;
- 8 dots/mm because it is not a 304-dpi profile;
- density minimum 0, maximum 2, default app selection 1;
- no speed selection;
- no grayscale support by default;
- label printing supported; and
- 80-dot trailing feed for continuous output.

The user's approximately 56 mm roll and the 384-dot head imply 48 mm of
printable width with about 8 mm left for combined physical margins. The margin
distribution remains unknown.

After connection, the class queries model string `10 FF 20 F0`. It enables
native compression only if the response is exactly `A2Y`.

## Transport conclusion

The SDK has complete classic SPP and BLE implementations. For BLE selection,
all of the following must be true:

1. Android reports BLE support.
2. SDK global flag `b.a.f43a` is true.
3. The matched printer's `isBleEnable` is true.
4. The transport enum/name rule permits BLE.

The global flag initializes to false. Its only setter is
`PrinterHelper.setEnableBle(boolean)`, and no caller was found across Java or
smali. The Mini Pocket Printer registration also sets its device flag to
false. No matching custom-property override was found.

**Inferred result:** the official version 1.3.13 app chooses classic SPP for
`Mini Pocket Printer_BLE`, even though the hardware offers a BLE interface and
the SDK contains a usable BLE transport.

This must be validated with an Android Bluetooth HCI snoop capture because
runtime injection, reflection, downloaded configuration, or vendor changes
outside the inspected APK set could theoretically alter the gates.

The recovered BLE protocol, including FF00 service selection, FF01/FF03
notifications, credit accounting, and MTU negotiation, is specified in
`docs/protocol.md`.

## Print-job lifecycle

The Mini Pocket Printer inherits `DP_D1`'s label override:

1. Start job with mode 3.
2. Send 12 zero wake-up bytes.
3. Select paper type 1/value `0x20`.
4. Send bitmap raster.
5. Issue label positioning.
6. Stop the job and wait for completion.

Exact bytes and generic query/configuration commands are in
`docs/protocol.md`.

The app's sticker-label workflow has a separate orientation branch for L12,
L13, and D11s devices. `MiniPocketPrinter` is not included in
`PrinterManager.isMiniLabelPrinter()`, so this device takes the normal,
non-rotated sticker-label branch.

## Production image pipeline

The user-facing print modes are:

| Value | UI mode | Processing |
| ---: | --- | --- |
| 0 | Image | adaptive gamma plus custom error diffusion |
| 1 | Text | fixed grayscale threshold at 128 |

### Common preparation

`PrintActivity` decodes the selected image and resizes it to the printer width
while preserving aspect ratio:

```text
new width  = 384
new height = floor(old_height * 384 / old_width)
```

OpenCV `Imgproc.resize` is called without an explicit interpolation argument,
so OpenCV's default linear interpolation applies. Preview generation uses the
same mode processing at preview width.

### Text mode

1. Convert bitmap to OpenCV Mat.
2. Convert color to grayscale with OpenCV conversion code 6.
3. Apply binary threshold 128, maximum 255, type 0.
4. Convert to an RGB_565 bitmap.
5. The SDK then packs black pixels using its independent `< 128` test.

### Image mode

1. Convert bitmap to Mat.
2. Convert BGRA to grayscale with OpenCV conversion code 10
   (`COLOR_BGRA2GRAY` in the bundled OpenCV constants).
3. Compute mean luminance.
4. Choose gamma from the following table.
5. Normalize to 0-1 and calculate `value^(1/gamma)`.
6. Rescale to 0-255.
7. Threshold each pixel at 127 and diffuse its quantization error.
8. Return an ARGB_8888 black/white bitmap.
9. The SDK packs the already-binary result.

Gamma selection:

| Mean luminance | Gamma |
| --- | ---: |
| `< 120` | 1.8 |
| `120-129` | 1.7 |
| `130-139` | 1.5 |
| `140-149` | 1.4 |
| `150-159` | 1.3 |
| `160-169` | 1.2 |
| `170-179` | 1.0 |
| `180-189` | 0.9 |
| `190-199` | 0.8 |
| `200-209` | 0.7 |
| `210-219` | 0.6 |
| `220-229` | 0.5 |
| `230-239` | 0.4 |
| `240-249` | 0.3 |
| `>= 250` | 0.2 |

Although the method is named `onFloydSteinbergNew`, its interior diffusion
kernel is not Floyd-Steinberg:

```text
                    current pixel   x+1: 5/32   x+2: 3/32
next row: x-2: 2/32  x-1: 4/32       x: 3/32   x+1: 4/32  x+2: 2/32
row + 2:              x-1: 2/32       x: 3/32   x+1: 2/32
```

The weights sum to 30/32, so a small portion of error is intentionally lost.
Boundary rows and columns use reduced/special-case distributions. The closest
description is a custom two-row, Sierra-like error diffusion.

The image editor also exposes optional grayscale, adaptive threshold,
lomo, sharpen, and sepia/vintage filters. Those are user-selected edits and
are not automatically inserted into the production print pipeline.

## Raster and compression

The default raster is ESC/POS `GS v 0`:

```text
1D 76 30 mode width_bytes_le height_le raster
```

Rows are top-to-bottom, horizontal bits are MSB-first, and arithmetic-mean RGB
below 128 is black. A 384-dot row occupies 48 bytes.

When model string `A2Y` is returned, the app uses native `codeESC` compression
and a `1F 10` compressed envelope. The full envelope is documented in
`docs/protocol.md`.

## Native libraries

ARM64 split:

| Library | Bytes | SHA-256 |
| --- | ---: | --- |
| `libc++_shared.so` | 1,292,904 | `4397241B4BD20A8E579BFB41D21107857E12985F6A01CA0C2A5F83380D1270B4` |
| `libopencv_java4.so` | 23,972,544 | `D331AAC20D0A76981EA652F7DF7978E3B82CCC46D5926DC7C394D33C813694AB` |
| `libPrinterNative.so` | 84,824 | `9A8E9B4470E9903D677A1D24D12F2ED868CE172FCBDB1F0EDB1FE8745CB8235F` |

`libPrinterNative.so` is a stripped, little-endian AArch64 shared object:

- Build ID: `560ecccd308dcb0c68d6be8f5013f499c86ad6d8`
- Android clang: 18.0.1

Relevant exports:

- `Java_com_print_libnative_Compress_codeESC`
- `Java_com_print_libnative_Compress_codeLihu`
- `Java_com_print_libnative_Compress_codeCPCL`
- `Java_com_print_libnative_Compress_codeTSPL`
- `Java_com_print_libnative_Code941_code`
- `Java_com_print_libnative_DFunction_dataprocesser`
- `Java_com_print_libnative_F2Function_F2Data`
- `Java_com_print_libnative_PrintNative_analysisData`
- `decompressionString`
- `decompressionString2`
- `reverseBits`

Cross-disassembly performed after the initial static report resolved the
compression path. The `codeESC` wrapper at `0x9184` calls an embedded zlib
encoder at `0x994C` with default compression, DEFLATE method 8, window bits 10,
memory level 8, and default strategy. Its helper at `0x9A30` is zlib's
`compressBound` calculation. A captured 217-byte payload decompresses to the
expected 1,776 raster bytes and recompresses byte-for-byte with those settings.
This is a zlib-wrapped DEFLATE stream, not gzip and not a proprietary codec.

## Implementation consequences

A clean-room driver should initially:

1. treat the printer as 384 dots/48 bytes per row;
2. implement the recovered image and text preprocessing modes independently;
3. pack one-bit rows MSB-first;
4. use recovered `codeESC` zlib compression for reliable multi-row output;
5. implement both SPP and BLE as transport adapters;
6. discover BLE characteristics by service/property rules rather than assuming
   FF02;
7. keep BLE credit/MTU state separate from command framing; and
8. retain uncompressed `GS v 0` only as a diagnostic path because live firmware
   rendered only the first expected row.

Potentially state-changing commands such as time, shutdown, density, paper
mode, recovery, firmware update, or arbitrary raw command writes should not be
used during initial discovery.

## Evidence index

The following local paths are intentionally ignored by Git and are listed only
so the analysis can be reproduced:

| Finding | Primary local evidence |
| --- | --- |
| Manifest/components | `decompiled/apktool/base/AndroidManifest.xml` |
| Package/version | `decompiled/apktool/base/apktool.yml`, `dumpsys.txt` |
| Device registration | `decompiled/jadx/sources/com/luckprinter/sdk_new/device/PrinterEnum.java` |
| Smali device factory | `decompiled/apktool/base/smali/com/luckprinter/sdk_new/device/PrinterHelper.smali` |
| Model compression gate | `decompiled/jadx/sources/com/luckprinter/sdk_new/device/normal/MiniPocketPrinter.java` |
| Mini print lifecycle | `decompiled/jadx/sources/com/luckprinter/sdk_new/device/normal/DP_D1.java` |
| Commands/status | `decompiled/jadx/sources/com/luckprinter/sdk_new/device/normal/base/BaseNormalDevice.java` |
| Raster packing | `decompiled/jadx/sources/com/luckprinter/sdk_new/device/normal/base/PrinterImageProcessor.java` |
| BLE transport | `decompiled/jadx/sources/d/i.java`, `decompiled/jadx/sources/d/e.java` |
| Classic SPP | `decompiled/jadx/sources/e/b.java` |
| Print pipeline | `decompiled/jadx/sources/com/printer/lidloffice/print/PrintActivity.java` |
| Image algorithms | `decompiled/jadx/sources/org/opencv/algorithm/OpenCVUtils.java` |
| Sticker path | `decompiled/jadx/sources/com/printer/lidloffice/stickerlabel/StickerLabelPrintActivity.java` |
| WebView surface | `decompiled/jadx/sources/com/printer/lidloffice/web/WebViewActivity.java` |
| Support upload | `decompiled/apktool/base/assets/DeviceReport.html` |

## Remaining unknowns

Subsequent non-root capture and PC HIL work resolved the official transport,
live GATT layout, device responses, model, continuous-roll lifecycle, and
compressed raster algorithm. Remaining hardware questions are exact physical
margins, thermal/density behavior, and command differences between continuous
roll and indexed media.
