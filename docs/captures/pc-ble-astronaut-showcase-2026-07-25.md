# PC BLE astronaut four-style image showcase: 2026-07-25

## Result

The clean-room preprocessing pipeline and compressed BLE driver successfully
printed four independently labeled 384×384 variants of the public-domain
scikit-image astronaut test resource. The separately gated HIL scenario passed
in 89.77 seconds, including 20-second cooling pauses between pages.

The run used the pinned `tests/resources/astronaut.png` resource with SHA-256
`88431CD9653CCD539741B555FB0A46B61558B301D4110412B5BC28B5E3EA6CB5`.

## Printed pages

| Page | Dither | Threshold | Effects | Image black | Page height |
| --- | --- | ---: | --- | ---: | ---: |
| Floyd photo | Floyd–Steinberg | 128 | autocontrast cutoff 2 | 50.986% | 494 dots / 61.75 mm |
| Ordered newsprint | ordered 4×4 | 128 | autocontrast cutoff 2; contrast 1.2 | 50.007% | 516 dots / 64.50 mm |
| Gritty noir | threshold | 145 | autocontrast cutoff 2; contrast 1.8; gamma 1.15 | 51.103% | 538 dots / 67.25 mm |
| Outline sketch | threshold | 180 | edge | 7.319% | 494 dots / 61.75 mm |

Each page was a separate compressed `codeESC` job followed by 160 feed dots.
All four jobs returned an accepted completion response. Approximate paper use
was 255 mm of labeled page content plus 80 mm of trailing feed, or 335 mm total.

## Physical inspection

Physical rendering observations are pending confirmation from the attended
operator. In particular, compare facial detail, suit texture, background
separation, dense-region consistency, page completeness, and header legibility
across the four styles.
