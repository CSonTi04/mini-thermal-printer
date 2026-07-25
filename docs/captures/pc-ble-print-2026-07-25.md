# PC BLE uncompressed print: 2026-07-25

## Result

The physical printer acknowledged an uncompressed ESC/POS `GS v 0` raster over
the new BLE transport and returned `AA 0D 0A`, but it rendered only one thin
horizontal line from the expected multi-row pattern. A later 20 mm feed proved
that the remaining pattern was not hidden under the cover or tear bar.

Uncompressed multi-row raster support is therefore **not verified** on firmware
`V1.06LY`. The observed line is consistent with only the first all-black raster
row being processed. Successful job completion alone is insufficient evidence
that the full raster was rendered.

## Test job

| Property | Value |
| --- | ---: |
| Raster width | 384 dots / 48 bytes |
| Raster height | 32 dots / 4 mm |
| Raster payload | 1,536 bytes |
| Raster frame | 1,544 bytes including header |
| Effective BLE packet size | 20 bytes |
| Trailing feed | 80 dots / 10 mm |
| Completion | `AA 0D 0A` |

The CQRS print handler first queried status and received clean status `00`, then
sent one continuous-roll job: start, 12-byte wake prefix, uncompressed raster,
80-dot feed, and stop.

## Physical observation

- One very fine horizontal line appeared; the remaining expected pattern did
  not.
- Its left edge aligned with the previous official-app `HelloWorld` sample.
- The lower thin line sat just above the paper's tear position.
- The official-app sample appeared to leave more blank space at the bottom.

The test raster intentionally begins at horizontal dot 0 and uses one-dot
lines, so the observed line's left alignment is expected. The protocol does
not appear to add an implicit left margin.

The captured official app also sent an 80-dot trailing feed. Its apparent
extra bottom space was therefore likely produced by blank rows inside its
raster or by the layout of the source content.

## Feed experiments

Three feed variants established the required lifecycle:

1. A bare `1B 4A A0` command produced no movement.
2. Start, wake, feed, and stop without a raster produced no movement, never
   returned completion, and required a printer restart before queries worked.
3. Start, wake, one 384×1 all-white `GS v 0` row, 160-dot feed, and stop moved
   the paper approximately 20 mm and returned `AA 0D 0A`.

The driver therefore implements standalone feed using the third sequence. The
all-white raster contains no active print-head dots.
