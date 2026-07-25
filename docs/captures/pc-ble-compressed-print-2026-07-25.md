# PC BLE codeESC compressed print: 2026-07-25

## Result

The clean-room Python `codeESC` implementation produced a complete multi-row
calibration image on firmware `V1.06LY`. The printer returned `AA 0D 0A`, the
HIL test passed, and a user-supplied photograph visually confirmed every
expected pattern element.

This verifies the full path from domain raster through Python zlib compression,
the `1F 10` envelope, BLE credit-based transport, and physical thermal output.

## Deterministic job

| Property | Value |
| --- | ---: |
| Raster width | 384 dots / 48 bytes / approximately 48 mm |
| Raster height | 96 dots / approximately 12 mm |
| Line thickness | 3 dots / approximately 0.375 mm |
| Tick spacing | 16 dots / 2 mm |
| Raw raster | 4,608 bytes |
| Compressed payload | 65 bytes |
| Complete compressed frame | 75 bytes |
| Frame SHA-256 | `61406202BF27FA23264A61738E1D6DB7B217FC87656BC7F9E913F6AD934EAE4E` |
| Trailing feed | 160 dots / 20 mm |
| Completion | `AA 0D 0A` |

## Physical confirmation

The photograph shows:

- complete top, middle, and bottom horizontal bands;
- complete left, center, and right vertical bands;
- all ruler ticks along the top edge;
- clear, consistent three-dot line weight;
- the full 384-dot pattern within the paper's physical side margins; and
- substantial blank paper between the lower border and the tear bar.

The image appears centered within the approximately 56 mm roll. Since the
verified printable width is 48 mm, the nominal unused paper width is about
8 mm total. Exact left/right millimeter margins still require a flat physical
measurement rather than estimation from a perspective photograph.

## Conclusion

`codeESC` is the reliable production encoding for this model. Uncompressed
`GS v 0` remains useful only for diagnostics because the corresponding live
probe rendered one expected raster row rather than the full image.
