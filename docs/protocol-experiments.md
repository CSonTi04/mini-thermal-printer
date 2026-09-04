# Optional protocol experiments

These experiments cover statically recovered SDK commands that are not needed
for ordinary A2Y printing. They are separated by effect and require explicit
consent at each hardware tier.

## Tier 1: read-only information

The first tier sends only the following five queries. It does not change a
setting, start a print job, activate the print head, or move paper.

| Value | Request | Recovered response rule |
| --- | --- | --- |
| Serial number | `10 FF 20 F2` | ASCII string |
| Boot information | `10 FF 20 EF` | ASCII string |
| Shutdown time | `10 FF 13` | byte 1 for a two-byte reply; otherwise byte 0 |
| Speed | `10 FF 20 A0` | first unsigned byte |
| Time format | `10 FF B0` | exactly one unsigned byte |

Run all five over the verified classic-SPP path:

```powershell
.venv\Scripts\tronic-printer.exe probe-info --port COM6 --live
```

The equivalent `ble-probe-info <address> --live` command exists for later BLE
regression and native BlueZ testing. Do not put a real serial number or full
Bluetooth address in tracked captures.

### A2Y/SPP result: 2026-09-04

The COM6 probe reached firmware `V1.06LY` and produced these results:

| Value | Result |
| --- | --- |
| Serial number | supported; non-empty ASCII value withheld from Git |
| Boot information | `V3.02` (`56 33 2E 30 32`) |
| Shutdown time | `20` minutes (`14`) |
| Speed | no response within the recovered five-second operation timeout |
| Time format | no response within three seconds |

A standard model/firmware/battery/density/status query immediately afterward
returned clean status `00`, confirming the unsupported queries did not leave
the printer busy or in an error state. No paper moved and no print-head dots
were activated. See the [sanitized capture note](captures/pc-spp-optional-queries-2026-09-04.md).

## Tier 2: reversible settings

Before sending any write, first query and record the current value. Change only
one setting, query it again, then restore the original value and verify the
restoration. The official app exposes shutdown choices of 5, 10, 20, 30, and
60 minutes. The prepared HIL experiment changes the current value to another
official choice and restores it in a `finally` block. It remains skipped unless
both `--live` and `--allow-settings` are present. No generic setting CLI is
exposed by this research stage.

For the observed 20-to-30-minute test, the only setting frames would be:

```text
10 FF 12 00 1E    set 30 minutes temporarily
10 FF 12 00 14    restore 20 minutes
```

Both writes require an `OK` response, and `10 FF 13` verifies the value after
each write. Each operation uses a fresh SPP connection because the live test
showed that Windows may drop a reused link immediately after a successful
setting write. Speed and time-format writes are excluded because their matching
queries received no response. Heating level is excluded because there is no
read-back command with which to restore a known original value.

### Shutdown round-trip result: 2026-09-04

The printer accepted the temporary 30-minute setting. Windows then dropped the
original SPP link before the same-session verification, and the same-session
cleanup write timed out. A fresh connection read back 30, proving the first
write had persisted. Another fresh connection restored 20 and a final fresh
connection read back 20. The printer therefore ended with its original setting.

This verifies the shutdown query, big-endian setting frame, `OK` response, and
persistence. It also establishes fresh-connection verification and restoration
as the safer Windows SPP procedure. The revised gated HIL scenario then passed
end to end in 1.54 seconds and left the printer at 20 minutes.

## Tier 3: paper and mode behavior

Print width, printer mode, paper type, label positioning, and recovery/reset
can affect output, paper movement, or persistent device state. Test them only
with separate printing approval, deterministic calibration pages, and suitable
media. Recovery/reset is excluded until its persistence and side effects are
understood.

## Out of scope until evidence changes

The grayscale and secondary framed protocols occur in the generic SDK but are
not enabled for the A2Y profile. They should not be transmitted merely to test
whether the firmware accepts them.
