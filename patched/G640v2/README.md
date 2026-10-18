# XP-Pen G640 (Variant 2): no-smoothing firmware builder

`make_patch.py` builds a modified firmware for the **XP-Pen G640 Variant 2** (IC 901, PIC32 / MIPS32 little-endian). It removes the pen position smoothing and can optionally raise the report rate. It writes a `.hex` file that you flash with [`xppen-tools`](https://github.com/NiceAesth/xppen-dumps).

**Use at your own risk.** A wrong or interrupted flash can brick the tablet. Nothing here comes from the vendor.

## Compatibility

Only for the G640 Variant 2.

| Item | Value |
| --- | --- |
| USB ID | `28BD:0914` ("6 inch PenTablet") |
| Firmware string | `UG901_BPU0601 (20-05-25_Release02)` |
| IC | 901 |
| Input image | `ic901-code.bin`, 102,400 bytes, base `0x1D006000` |

Every edit checks the original bytes first and the script refuses to run on any other image. Never flash firmware from a different tablet or revision.

## Build

You need Python 3 and the stock `ic901-code.bin` from the dumps repo, in `stock/G640 (Variant 2)/`.

```sh
python3 make_patch.py ic901-code.bin [options]
```

The script writes one `.hex` file, named after the options you chose. It does not write a modified `.bin`. Run it with no arguments to print the help.

### Options

| Option | What it does |
| --- | --- |
| *(none)* | Raw. The cursor goes exactly where the pen is. It may shake a few counts when the pen is held still. |
| `--deadzone N` | Ignore tiny movements while the pen is nearly still. `N` is 0 to 255 counts (100 counts is about 1 mm). Uses the stock diamond shape (X move + Y move added together). |
| `--square` | Same, with a square shape: X and Y are checked separately, and a move is ignored only while both are under the size. Default size 8. Combine with `--deadzone N` to change it. |
| `--pressure` | Experimental, untested. Stops the firmware cutting pressure to 66% for a few frames after touch-down. |
| `--burst N` | Experimental. Carrier cycles the antenna is driven per scan step (stock 35). Lower values scan a little faster but give a weaker signal. |
| `--adc-fast` | Runs the ADC conversion clock twice as fast. Raises the scan rate without weakening the signal. The ADC clock ends up faster than its rated minimum, but it worked on a real G640 V2. |
| `--smooth N` | Optional, off by default. Light smoothing, N = 2 to 8, instead of the base build's window of 1 (stock was about 11 samples while touching). Not tested on a tablet. |
| `--hover-hold N` | Experimental. Fixed hold of N counts (100 = about 1 mm) while the pen hovers, to stop the hover cursor twitching. No averaging, no lag, and pen-down behaviour is unchanged. Try 30 to 40. |
| `--sample-wait N` | Experimental, did not help. ADC sample-and-hold wait in timer ticks (60 = 1 us, stock 2). N = 1 to 30. Tested 6 and 12 on the square-12 base; both were worse. Not recommended. |
| `--adaptive N` | Experimental (emulator-checked, not yet on a tablet). Speed-adaptive light smoothing for a steadier cursor with almost no lag, N = 2 to 8 (start with 4). Works with a dead-zone of 0. See below. |
| `--poll` | Sets USB polling to 1 ms (stock 3 ms for the pen). Removes the 333 Hz host-side ceiling. It does not speed up the scan. |
| `--settle N` | Experimental. Wait between the end of the drive burst and the first ADC reading, in microseconds (stock 15). Only 12 to 15 is accepted, because 8 stopped pen detection on a real G640 V2. |
| `--flash-fast` | Experimental, riskier than the others, and **not recommended**: flashed on a real G640 V2 with no noticeable difference. Sets flash wait states and prefetch at startup (see below). |

Examples:

```sh
# Steadier cursor without a dead-zone (adaptive smoothing, window 4 at rest)
python3 make_patch.py ic901-code.bin --burst 15 --adc-fast --poll --adaptive 4
# -> g640v2-nosmooth-burst-15-adc-adaptive-4-poll.hex
```

```sh
# Square dead-zone of 8 counts (default size)
python3 make_patch.py ic901-code.bin --square
# -> g640v2-nosmooth-square.hex

# Different size
python3 make_patch.py ic901-code.bin --square --deadzone 12
# -> g640v2-nosmooth-square-12.hex

# Faster scan
python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll
# -> g640v2-nosmooth-square-burst-15-adc-poll.hex
```

If the cursor feels sticky, lower the dead-zone. If it shakes at rest, raise it.

## Flash

1. Back up first and wait for the "verified" message:
   ```sh
   sudo ./xppen-tools dump backup
   ```
2. Reboot the tablet into its bootloader and check it:
   ```sh
   sudo ./xppen-tools dfu
   sudo ./xppen-tools info
   ```
   The IC must be 901 and the bootloader PID must be `1227`, `FFF1` or `FFF2`. If it is `FFF3`, stop: that bootloader has no exit command and you can get stuck.
3. Flash. Do not unplug the tablet while it writes:
   ```sh
   sudo ./xppen-tools update g640v2-nosmooth-square.hex
   ```
4. Replug the tablet, run `sudo ./xppen-tools info`, then `sudo ./xppen-tools monitor` while drawing to see the report rate.

### Rollback

Run `dfu` again and flash the stock `ic901-stock.hex` from the dumps repo, or the hex from your own backup. Use `sudo ./xppen-tools update <file>`. `xppen-tools exit-dfu` leaves the bootloader without flashing.

### Linux udev rules

Create `/etc/udev/rules.d/99-xppen.rules`:

```udev
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="0914", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="0914", MODE="0666"

# Bootloaders
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="1227", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="1227", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff1", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff1", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff2", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff2", MODE="0666"
```

Then:

```sh
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## What changes

### Base edits (always applied)

| Edit | Address | Effect |
| --- | --- | --- |
| Averaging window | `0x1D0099D4` | The final position went through a moving average of 5 to 40 samples, chosen by pen speed. The window is forced to 1 sample. This is the main smoothing. |
| Dead-zone table | `0x1D018770` | The 16-entry hold table (stock 80 down to 15 counts) is replaced by zeros, or by the table from `--deadzone` / `--square`. |
| "Moving" flag | `0x1D009740` | Threshold 50 to 0, so the flag reads "moving". With the window at 1, the flag would otherwise flip on and off at normal drawing speed. |
| Out-of-area samples | `0x1D007FB8`, `0x1D007FE4`, `0x1D008024`, `0x1D008050` | A single out-of-area reading no longer sets pen state 3 (the out-of-range flicker). Two or more bad readings in a row can still cause a short dropout. |

### Option edits

| Option | Addresses | Bytes |
| --- | --- | --- |
| `--square` | `0x1D0076F8` (hold check, 15 instructions) | Rewritten from \|dX\|+\|dY\| to max(\|dX\|,\|dY\|). |
| `--pressure` | `0x1D018660`, `0x1D019D84` | 66 to 100. |
| `--burst N` | `0x1D018654`, `0x1D019D60` | The boot image says 28, but startup code overwrites it with 35, so both places are set. |
| `--adc-fast` | `0x1D00CDD4` | AD1CON3 ADCS 1 to 0 (1 byte). |
| `--settle N` | `0x1D01866C`, `0x1D019D98` | Boot image 10, startup overwrites with 15, so both places are set. |
| `--poll` | `0x1D018D45`, `0x1D018D5E`, `0x1D018D77` | USB `bInterval` for EP81, EP82 (pen) and EP83 set to 1 ms. |
| `--hover-hold N` | `0x1D007C20`, `0x1D007CEC`, `0x1D007DB8` | The three hover-branch threshold loads (`lbu a0`) become `addiu a0,zero,N`. |
| `--sample-wait N` | `0x1D0182FC` | The `sltiu v0,v0,2` in the ADC sample wait loop becomes `sltiu v0,v0,N`, so the wait goes from 2 ticks to N. |
| `--adaptive N` | init image `0x1D0186EA`..`0x1D018720` (26 values), startup stores `0x1D019E70`..`0x1D019F24` (26 nops) | Keeps the stock averaging and rewrites its speed tables. See below. |
| `--smooth N` | `0x1D0099D4` | `lw a2` becomes `addiu a2,zero,N` instead of `addiu a2,zero,1`. |
| `--flash-fast` | `0x1D007038` (16 bytes) | See below. |

### `--adaptive N`

The stock firmware averages the final position over a window that depends on how far the new reading is from the last output (`d` = |dX|+|dY|, in raw units where 100 = 1 mm; the HID report is 2.05x that). The window is chosen at `0x1D009790`..`0x1D0099D0`: pen down uses ten thresholds T0..T9 (RAM `0xA00000DE`..`F0`) to pick one of eleven windows, hover uses T0, T5, T6, T9 to pick one of five. The live stock values, set by the startup code, are thresholds 100, 150, 200, 250, 300, 400, 600, 1000, 2000, 4000 and pen-down windows 13, 12, 11, 10, 9, 7, 7, 6, 5, 4, 3 (hover 10, 5, 3, 1, 1). Pen noise gives `d` of about 10 to 30, so it always sat in the first bucket (window 13): heavy smoothing and about 1 mm of lag at slow speeds.

The base build forces the window to 1. `--adaptive N` restores the stock averaging code and writes new tables instead: thresholds 20, 30, 40, 60, 80, 120, 180, 280, 440, 700, pen-down windows N at rest stepping down to 1 above `d` = 180, hover N+2 at rest. Because `d` is measured against the lagging output, the window shrinks by itself as soon as the pen really moves.

The tables sit in the RAM init image and the startup code at `0x1D019E70` stores the stock values over them, so the option edits both: the 26 init values are replaced and the 26 stores to those addresses become nops. No code is added.

I ran the real firmware routine (`0x1D0096D8`, speed measure, window selection and average) in a Unicorn emulator on synthetic pen paths with white noise. Window 4, noise sigma 7 raw (about 14 report units, similar to what `xppen-tools monitor` showed):

| Pen speed | Sideways jitter vs raw | Lag (stock: about 1 mm at slow speeds) |
| --- | --- | --- |
| still | 0.39x | none |
| 18 mm/s | 0.46x | 0.10 mm (4.5 ms) |
| 36 mm/s | 0.50x | 0.16 mm (3.6 ms) |
| 71 mm/s | 0.56x | 0.23 mm (2.5 ms) |
| 143 mm/s | 0.67x | 0.32 mm (1.7 ms) |

Hover (sigma 10 raw): 0.40x at rest. A 3 mm jump goes through with no lag. A circle of 3 mm radius at 95 mm/s keeps its radius (299.6 against 300) and its radius ripple halves. The same tables gave 0.35x to 0.42x at rest for noise sigma 4 and 10, so the thresholds do not need tuning to the noise level. N = 3 is lighter, N = 6 is steadier (0.29x at rest, about 10 ms of lag when crawling). At very high speed the window can flip between 1 and 2, which makes the spacing of points along a stroke slightly uneven (the emulator shows 20 to 40 raw units) but does not bend the line.

These are emulator results on synthetic noise, not a tablet measurement. Real pen noise may not be white.

### `--hover-hold N`

The hold routine at `0x1D0076F8` skips a report while the pen is within a threshold of the last reported point. Its threshold comes from a 16-entry speed table, and the pen-down and hover branches share that table. The stock table held 80 counts at rest, and hover also had a 25-sample average. The no-smoothing build holds only 8, but `xppen-tools monitor` on a real G640 V2 showed hover noise of about 15 to 25 counts (peak-to-peak 55 to 80 in the quietest windows), so the cursor moved on almost every report.

The code at `0x1D0078E4` sends pressure 0 to the hover branch at `0x1D007B58`. That branch has three call sites of the hold routine, and each loads its threshold with `lbu a0,-0x7b2c(gp)` in the delay slot. This option replaces those three loads with a constant.

I ran the real hold routine in a Unicorn emulator with 16 counts of noise and the pen still:

| Hover hold | Reports where the position changes |
| --- | --- |
| 8 (base build) | 89% |
| 20 | 43% |
| 30 | 16% |
| 40 | 4% |

Slow hovering moves are reported in steps of about N counts, and a move bigger than N goes through at once. These are simulation results on synthetic noise, not a measurement of the pen-down behaviour or of a tablet.

### `--flash-fast`

The loader enters the app at `0x1D007000`, which falls into the startup code. Nothing in the boot flash, loader or app writes the flash control register (CHECON, `0xBF884000`), and the startup code only calls empty functions where the usual compiler startup configures it. For this chip family the reset state is prefetch off and 7 flash wait states, so code runs slowly.

**Status: flashed on a real G640 V2 with no noticeable difference. Not recommended.** No rate measurement was taken, so the effect, if any, is small. Two points argue that the CPU is not what limits the scan: the rate barely changed between `--burst` 5, 12 and 15 even though the carrier interrupt handler (about 90 instructions per carrier cycle) would dominate the burst at 7 wait states, and nothing in the app waits on CPU speed alone, because every timing wait is a busy-loop on a hardware timer. The register address and reset value for this exact chip were not confirmed.

The option replaces an empty function call at `0x1D007038` with four instructions that write CHECON = `0x33`: 3 wait states and prefetch on. The scan timers are unchanged.

This is inferred from the chip family's documented reset state and has not been confirmed on a tablet. If it caused a hang at startup, `xppen-tools dfu` would not work, because it needs the app running, and there is no known way back into the bootloader from that state.

## USB

Full speed (12 Mb/s) allows a minimum polling interval of 1 ms, so the host can read a pen endpoint at most 1000 times a second. The stock 3 ms interval caps it at about 333 reports a second. `--poll` removes that cap. The pen itself produces fewer reports than that, so the scan rate is what limits you.
