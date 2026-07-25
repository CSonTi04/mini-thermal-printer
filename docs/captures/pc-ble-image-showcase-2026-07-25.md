# PC BLE four-style image showcase: 2026-07-25

## Result

The clean-room preprocessing pipeline and compressed BLE driver successfully
printed four independently labeled 384×384 Lenna variants. The HIL scenario
passed in 90.74 seconds, and four user-supplied photographs physically
confirmed complete headers and images.

The photographs remain outside the repository. This note records observations
without copying those temporary files into Git.

## Connection sequence

The first invocation stopped before connecting because the printer was powered
off and could not be discovered. No paper or raster data was sent. After the
printer was turned on, a passive scan found `Mini Pocket Printer_BLE` at
approximately −78 dBm. The approved retry completed all four jobs.

## Printed pages

| Page | Dither | Threshold | Effects | Image black | Page height |
| --- | --- | ---: | --- | ---: | ---: |
| Floyd photo | Floyd–Steinberg | 128 | autocontrast cutoff 2 | 51.64% | 494 dots / 61.75 mm |
| Ordered newsprint | ordered 4×4 | 128 | autocontrast cutoff 2; contrast 1.2 | 51.60% | 516 dots / 64.50 mm |
| Gritty noir | threshold | 145 | autocontrast cutoff 2; contrast 1.8; gamma 1.15 | 56.39% | 538 dots / 67.25 mm |
| Outline sketch | threshold | 180 | edge | 5.80% | 494 dots / 61.75 mm |

Each page was a separate `codeESC` job followed by 160 feed dots (20 mm).
The scenario waited 20 seconds between jobs. Approximate paper use was 255 mm
of labeled page content plus 80 mm of trailing feed, or 335 mm total.

## Physical observations

- All four names and processing-setting headers are present and readable.
- All four 384×384 images are complete with stable left/right alignment.
- No missing raster bands, premature termination, or visible heat-related
  fading appears in the photographs.
- Floyd–Steinberg produces the smoothest photographic tonal transitions and
  preserves fine facial and hair detail.
- Ordered 4×4 produces a strong, regular halftone texture consistent with its
  intended newsprint appearance.
- The threshold/noir page preserves large, dense black regions without visible
  dropout, despite having the highest measured black coverage.
- The edge page produces a sparse, legible line drawing with fine details and
  the lowest ink coverage.

The small pixel header font renders punctuation compactly, but the settings
remain interpretable. This is a presentation characteristic rather than a
transport defect.

## Conclusions

The following are now verified end to end on Windows BLE and firmware
`V1.06LY`:

- RGB normalization and grayscale preparation;
- ordered effect chains;
- all three implemented rasterization modes;
- labeled page composition;
- `codeESC` compression of realistic, high-entropy image data;
- four sequential jobs on one BLE connection with cooling pauses; and
- compressed raster heights through at least 538 rows.

The absolute maximum reliable height remains unknown. The successful 538-row
page establishes a new verified lower bound rather than a protocol maximum.
