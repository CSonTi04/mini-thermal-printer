# PC SPP optional read-only queries: 2026-09-04

## Scope

Five statically recovered information commands were sent over the previously
verified Windows classic-Bluetooth SPP endpoint. None starts a print job,
changes a setting, activates the print head, or moves paper.

## Results

| Query | Request | Observed result |
| --- | --- | --- |
| Serial number | `10 FF 20 F2` | non-empty ASCII response; value withheld |
| Boot information | `10 FF 20 EF` | `V3.02`, raw `56 33 2E 30 32` |
| Shutdown time | `10 FF 13` | one byte `14`, decoded as 20 minutes |
| Speed | `10 FF 20 A0` | no response within 5 seconds |
| Time format | `10 FF B0` | no response within 3 seconds |

A repeated gated test again completed the first three supported queries. Its
speed probe was rejected by Windows with a serial write timeout rather than a
response timeout. Both observations are consistent with speed control being
unsupported by the A2Y profile; the probe reports either outcome without
mistaking it for a supported value.

The 20-minute interpretation is independently supported by the official app:
its settings UI labels the returned integer in minutes and offers values 5,
10, 20, 30, and 60.

## Post-probe state

The standard read-only query set immediately succeeded afterward with model
`A2Y`, firmware `V1.06LY`, density 1, status `00`, and 94% battery. This confirms
the two unsupported generic queries did not leave the printer busy or in an
error state.

No full serial number, Bluetooth address, or other device identifier is stored
in this tracked note.

## Reversible shutdown-setting experiment

With separate setting-change approval, the current 20-minute value was changed
to 30 using `10 FF 12 00 1E`; the printer returned `OK`. Windows dropped the
reused SPP connection before verification, and the cleanup attempt on that
connection timed out. Recovery then used independent fresh connections:

1. `10 FF 13` returned `1E`, confirming 30 minutes had persisted.
2. `10 FF 12 00 14` restored 20 minutes and returned `OK`.
3. `10 FF 13` returned `14`, confirming the original 20-minute value.

No print job was opened and no paper or print-head operation occurred. The HIL
procedure was revised so every read and write uses a fresh SPP connection. The
revised scenario passed in 1.54 seconds and again verified the final 20-minute
setting.
