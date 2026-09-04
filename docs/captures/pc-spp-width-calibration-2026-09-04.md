# PC SPP printable-width calibration: 2026-09-04

## Scope

A deterministic 384×96-dot calibration strip was printed over the verified
Windows classic-Bluetooth SPP endpoint. The compressed page used three-dot
outer and centre lines, 2 mm ruler ticks, and a 160-dot / 20 mm trailing feed.

The printer returned completion `AA 0D 0A`. The operator supplied a photograph
and measured the flat output. The photograph remains outside the repository.

## Measurements

| Property | Result |
| --- | ---: |
| Paper width | approximately 56 mm |
| Printed border width | approximately 48 mm / 384 dots |
| Left paper edge to outer border | approximately 3 mm |
| Outer border to right paper edge | approximately 5 mm |
| Logical dot density | 8 dots/mm |

The dimensions close exactly at the reported precision: `3 + 48 + 5 = 56 mm`.
The printable area's centre is approximately 27 mm from the left paper edge,
while the paper centre is approximately 28 mm. The head is therefore positioned
about 1 mm, or 8 dots, left of the paper centre for this roll loading.

## Physical inspection

- both outer vertical border lines were complete and continuous;
- the top and bottom horizontal borders were complete;
- the centre lines and all visible ruler ticks were complete; and
- no left/right clipping or missing raster bands were visible.

This verifies the full 384-dot / approximately 48 mm width as reliably printable
with compressed `codeESC` output on firmware `V1.06LY`. For content that should
look centred on the physical roll, an equal-width safe area can be formed by
using 24 dots of left padding and 8 dots of right padding. That preserves the
standard 352-dot content width and yields approximately 6 mm physical whitespace
on both sides.
