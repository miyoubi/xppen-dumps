# XP-Pen G640 (Variant 2): No-Smoothing Firmware

Removes the position smoothing from the XP-Pen G640 **Variant 2** firmware (IC 901, PIC32 / MIPS32 LE).

## Compatibility

| Item | Value |
| --- | --- |
| Tablet | XP-Pen G640 **Variant 2** only (not Rev A, Rev B, or any other model) |
| USB ID | `28BD:0914` |
| Firmware | `UG901_BPU0601` (20-05-25_Release02) |
| Image | `ic901-code.bin`, 102,400 bytes at `0x1D006000` |

`make_patch.py` checks the original bytes at every edit address and refuses to run on any other image.

## Files

| File | Description |
| --- | --- |
| `g640v2-nosmooth.hex` | **Default.** No averaging and no dead-zone. The cursor will shake at rest. |
| `g640v2-normal.hex` | Same, plus a small dead-zone while the pen is still, to stop the shake. |
| `make_patch.py` | Builds either image from the stock `ic901-code.bin`. |

## Build

```sh
python3 make_patch.py ic901-code.bin out            # out/g640v2-nosmooth.{bin,hex}
python3 make_patch.py ic901-code.bin out --normal   # out/g640v2-normal.{bin,hex}
```

The stock `ic901-code.bin` is in the dumps repo under `stock/G640 (Variant 2)/`.

## Flash

Uses [`xppen-tools`](https://github.com/NiceAesth) by NiceAesth.

1. `sudo ./xppen-tools info`: if the bootloader PID is **FFF3**, stop. It has no exit-DFU command and the tablet can get stuck.
2. `sudo ./xppen-tools dump backup`: makes a verified backup.
3. `sudo ./xppen-tools dfu`: reboots into DFU mode.
4. `sudo ./xppen-tools update g640v2-nosmooth.hex`: do not unplug while it writes.

`sudo ./xppen-tools exit-dfu` leaves DFU mode without flashing.

**Roll back:** flash `stock/G640 (Variant 2)/ic901-stock.hex` from the dumps repo, or your backup.

### Linux udev rules

`/etc/udev/rules.d/99-xppen.rules`:

```udev
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="0914", MODE="0666"
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="0914", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="1227", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff1", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff2", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="28bd", ATTRS{idProduct}=="fff3", MODE="0666"
```

```sh
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## What changes

37 bytes in total. Stock pipeline: raw position, moving average, area check, dead-zone, report.

| Edit | Address | Stock | Patched | Effect |
| --- | --- | --- | --- | --- |
| Window | `0x1D0099D4` | `e884868f` | `01000624` | Averaging window forced to 1 sample (stock: 5 to 40, chosen by pen speed). This is the main smoothing. |
| Hold | `0x1D018770` (16 B) | `80,70,50,50,50,45,45,45,45,45,45,35,30,25,20,15` | nosmooth: all `0`<br>normal: `32,28,20,14,10,8,6,4,3,2,0,0,0,0,0,0` | Dead-zone table. |
| Move flag | `0x1D009740` | `3200432c` | `0000432c` | "Pen moving" threshold 50 to 0. |
| No-edge | `0x1D007FB8`, `7FE4`, `8024`, `8050` | `dd8482a3` | `00000000` | One raw sample outside the active area no longer sets pen state 3, which produced single `X=0 Y=0` reports. |

Position path: antenna geometry (`0x9ADC`) → fine X/Y (`0xA0000DA0/DA4`) → window average (`0x99D4`) → scale → hold (`0x76F8`) → report bytes `0xA00004B7`..`BA`. A separate coarse position, smoothed by IIR filters, only selects which antenna group to scan and never reaches the report.

## USB

| Interface | Endpoint | Report | Purpose |
| --- | --- | --- | --- |
| 0 | EP81 IN, 8 B | ID 9 (abs. mouse), 1, 6 | Mouse-mode fallback |
| 1 | EP82 IN, 64 B | ID 7 (10 B) | **Pen**: flags, 16-bit X/Y/pressure, tilt |
| 2 | EP83 IN / EP03 OUT, 12 B | ID 2 | Vendor config. Not pen data. |

The 3 ms bInterval on EP82 is a polling ceiling (about 333 Hz), not a report rate. The real rate is set by the tablet's pen scan. Forcing 1 ms (bInterval bytes at `0x1D018D45`, `0x1D018D5E`, `0x1D018D77`: `04/03/03` to `01`) is not included in the script. Run `xppen-tools monitor` to see the measured rate.

## Known limits

- The dead-zone table's slow-to-fast order is assumed, not confirmed.
- Move flag and no-edge are not confirmed to fix any specific dropout.
- Only the X/Y path was patched. Pressure may still be smoothed.
- With filtering removed, raw sensor noise reaches the cursor (a few counts, 100 counts is about 1 mm).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Cursor shakes at rest | Flash `normal`. If it still shakes, raise the dead-zone values at `0x1D018770`. |
| Pen stops working | Flash the stock hex or your backup. |
| `X=0 Y=0` lines in `xppen-tools monitor` while hovering | Expected to be fixed by the no-edge edit. If not, it is a separate cause. |
