# XP-Pen G640 (Variant 2): no-smoothing firmware builder

`make_patch.py` builds patched firmware for the **XP-Pen G640 Variant 2** (IC 901, PIC32 / MIPS32 little-endian). It removes the pen position smoothing and can optionally raise the report rate. It writes a `.hex` file you flash with [xppen-tools](https://github.com/NiceAesth/xppen-dumps).

**Use at your own risk.** A wrong or interrupted flash can brick the tablet. Back up first.

## Compatibility

| | |
| --- | --- |
| Tablet | XP-Pen G640 (Variant 2) only |
| USB ID | `28BD:0914` |
| Firmware string | `UG901_BPU0601` (20-05-25_Release02) |
| Input file | stock `ic901-code.bin`, 102,400 bytes, from the dumps repo under `stock/G640 (Variant 2)/` |

Every edit checks the original bytes first and the script refuses to run on any other image. Do not flash this on any other model or revision. Check the bootloader PID with `xppen-tools info` after `xppen-tools dfu`: it must be `1227`, `FFF1` or `FFF2`. `FFF3` has no exit-DFU command and can leave the tablet stuck.

## Build

```sh
python3 make_patch.py ic901-code.bin [options]
```

Run it with no arguments (or `-h`) to print the built-in help. Options combine freely.

| Option | What it does |
| --- | --- |
| *(none)* | Raw. Every position goes straight to the cursor. It may shake a few counts when the pen is held still. |
| `--deadzone N` | Ignore tiny movements while the pen is nearly still. `N` is 0 to 255 counts (100 counts is about 1 mm). Uses the stock diamond shape (X move plus Y move). |
| `--square` | Same, but the shape is a square: X and Y are checked separately. Default size 8, set another with `--deadzone N`. |
| `--pressure` | **Experimental, untested.** Stops the firmware cutting pressure to 66% for a few frames at touch-down. 2 bytes. |
| `--burst N` | **Experimental.** Carrier cycles the antenna is driven per scan step. Live stock is 35. Lower scans faster but gives a weaker signal. 2 bytes. |
| `--adc-fast` | **Experimental.** Runs the ADC conversion clock twice as fast. Raises the scan rate without weakening the signal. 1 byte. |
| `--settle N` | **Experimental.** Wait between the end of the burst and the first ADC reading, in microseconds. Allowed 12 to 15, stock 15. 2 bytes. |
| `--poll` | Sets USB polling to 1 ms on all three endpoints (stock 4/3/3 ms). 3 bytes. |

Examples:

```sh
python3 make_patch.py ic901-code.bin --square                                   # g640v2-nosmooth-square.hex
python3 make_patch.py ic901-code.bin --square --deadzone 12                     # g640v2-nosmooth-square-12.hex
python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll      # g640v2-nosmooth-square-burst-15-adc-poll.hex
```

File names are built from the options, so different builds never overwrite each other. `--sampc` was removed: the ADC sample-time field is not used by this firmware, so it did nothing.

## Flash

```sh
sudo ./xppen-tools dump backup                 # verified backup, wait for "verified"
sudo ./xppen-tools dfu                         # reboot into the bootloader
sudo ./xppen-tools info                        # check IC 901 and the bootloader PID
sudo ./xppen-tools update <build>.hex          # do not unplug while it writes
sudo ./xppen-tools info                        # after replugging: check the endpoints
sudo ./xppen-tools monitor                     # live pen state and measured report rate
```

**Rollback:** run `dfu` again and `update` with the stock `ic901-stock.hex` from the dumps repo, or with your own backup. `xppen-tools exit-dfu` leaves the bootloader without flashing.

On Linux you may need udev rules for USB and hidraw access. Create `/etc/udev/rules.d/99-xppen.rules`:

```udev
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", MODE="0666"
```

then run `sudo udevadm control --reload-rules && sudo udevadm trigger`.

## What changes

All edits are in the application (`code`) section only.

| Edit | Address | Stock | Patched |
| --- | --- | --- | --- |
| Averaging window (the main smoothing) | `0x1D0099D4` | `lw a2` (window 5 to 40) | `addiu a2,zero,1` |
| Dead-zone table (16 bytes) | `0x1D018770` | 80,70,50,50,50,45,... | all zero, or the `--deadzone` table |
| "Moving" flag threshold | `0x1D009740` | 50 | 0 |
| Out-of-area sample no longer sets pen state 3 | `0x1D007FB8`, `0x1D007FE4`, `0x1D008024`, `0x1D008050` | `sb` | `nop` |
| Square hold (`--square`) | `0x1D0076F8` | `\|dX\|+\|dY\|` | `max(\|dX\|,\|dY\|)` |
| Pressure factor (`--pressure`) | `0x1D018660`, `0x1D019D84` | 66 | 100 |
| Burst (`--burst`) | `0x1D018654`, `0x1D019D60` | 28 (boot image), 35 (startup, live) | `N` |
| ADC clock (`--adc-fast`) | `0x1D00CDD4` | `ADCS=1` | `ADCS=0` |
| Post-burst wait (`--settle`) | `0x1D01866C`, `0x1D019D98` | 10 (boot image), 15 (startup, live) | `N` |
| USB polling (`--poll`) | `0x1D018D45`, `0x1D018D5E`, `0x1D018D77` | 4, 3, 3 ms | 1 ms |

The pen position reaches the report through a window average, a scale step and a hold (dead-zone) step. A separate coarse position, which only selects the antenna group, never reaches the report and is left alone.

## Report rate

One report is 14 scan steps (7 on X, 7 on Y). Each step is a drive burst, a wait, then about 50 ADC readings. The chip runs at about 60 MHz.

- `--burst` shortens the drive. `--adc-fast` shortens each reading. `--settle` shortens the wait.
- At full speed USB the shortest polling interval is 1 ms, so `--poll` already removes the host as a limit.
- On a G640 V2, burst 15 with `--adc-fast` and `--poll` reached about 330 Hz. Burst 12 with a faster ADC gave about 315 Hz, and burst about 5 gave about 330 Hz, so shortening the burst further no longer helps. Something else, which I could not identify, limits the rate near 330 Hz.

## Known limits

- **Tested on hardware (G640 V2):** raw and `--square` (size 8) builds held the pen still and passed no movement under about 8 counts. Burst 15 with `--adc-fast` and `--poll` ran at about 330 Hz.
- **Not tested on hardware:** `--pressure`, other `--deadzone` sizes, and burst values other than 15.
- **`--settle 8` stopped pen detection** (the tablet saw the pen light but did not respond), so values below 12 are refused. `--settle 12` is untested.
- **`--adc-fast` is out of spec.** At 60 MHz it puts the ADC clock at about 33 ns, below the roughly 65 ns it is rated for. It works on the tested unit. If the pen gets noisy, drop it.
- Two or more bad readings in a row can still cause a short dropout. Only a single out-of-area sample is ignored.
- The direction of the dead-zone table (slow to fast) and the exact dropout mechanism are inferred from the code, not confirmed.
