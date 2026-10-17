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
| `--poll` | Sets USB polling to 1 ms (stock 3 ms for the pen). Removes the 333 Hz host-side ceiling. It does not speed up the scan. |
| `--settle N` | Experimental. Wait between the end of the drive burst and the first ADC reading, in microseconds (stock 15). Only 12 to 15 is accepted, because 8 stopped pen detection on a real G640 V2. |
| `--flash-fast` | Experimental, untested, riskier than the others. Sets flash wait states and prefetch at startup (see below). |

Examples:

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
| `--flash-fast` | `0x1D007038` (16 bytes) | See below. |

### `--flash-fast`

The loader enters the app at `0x1D007000`, which falls into the startup code. Nothing in the boot flash, loader or app writes the flash control register (CHECON, `0xBF884000`), and the startup code only calls empty functions where the usual compiler startup configures it. For this chip family the reset state is prefetch off and 7 flash wait states, so code runs slowly.

The option replaces an empty function call at `0x1D007038` with four instructions that write CHECON = `0x33`: 3 wait states and prefetch on. The scan timers are unchanged.

This is inferred from the chip family's documented reset state and has not been confirmed on a tablet. If it caused a hang at startup, `xppen-tools dfu` would not work, because it needs the app running, and there is no known way back into the bootloader from that state.

## USB

Full speed (12 Mb/s) allows a minimum polling interval of 1 ms, so the host can read a pen endpoint at most 1000 times a second. The stock 3 ms interval caps it at about 333 reports a second. `--poll` removes that cap. The pen itself produces fewer reports than that, so the scan rate is what limits you.

## Known limits

- **Tested on hardware:** the no-smoothing base with `--square` (default size 8): a still pen held its position and passed no movement under about 8 counts. `--burst 15 --adc-fast --poll` ran at about 330 Hz.
- **Failed on hardware:** `--settle 8` stopped pen detection (the tablet still enumerated and was recovered by reflashing).
- **Not tested on hardware:** other dead-zone sizes, `--pressure`, `--settle 12` to `15`, `--flash-fast`, and `--burst` values other than 15. The dead-zone table values and their order are assumptions.
- **Scan rate:** the scan stopped getting faster once burst and ADC time were reduced (about 315 to 330 Hz across several settings). The remaining limit is not confirmed. `--flash-fast` is the untested attempt to find out whether the CPU is it.
- **Weak signal:** a low `--burst` weakens the pen signal. Watch for jitter at rest, dropouts near the edges or at hover height, and the pen cutting out on light touches.
- **Pressure** may still be smoothed. Only the X/Y position path was changed.
- **Out-of-area samples:** two or more bad readings in a row can still cause a short dropout.
- **IC check:** the IC number was not read from the tablet in normal mode. `xppen-tools info` in the bootloader confirms it.
