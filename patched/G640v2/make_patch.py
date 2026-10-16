#!/usr/bin/env python3
"""No-smoothing firmware builder for XP-Pen G640 (Variant 2), IC 901 (PIC32 / MIPS32 LE).

Run with no arguments, or with -h / --help, to print the instructions.
Options: --square  add a small square dead-zone (see HELP).
Tested on a G640 Variant 2: works. Back up first anyway. Every edit verifies the original bytes
and refuses to run on any other image.
"""
import sys, hashlib

BASE, SIZE = 0x1D006000, 102400

HELP = """\
XP-Pen G640 (Variant 2) no-smoothing firmware builder
For the G640 Variant 2 ONLY (USB ID 28BD:0914). Tested and working on hardware. Use at your own risk.

HOW TO USE IT, STEP BY STEP

 1. Get the files
      - xppen-dumps-main.zip (stock firmware dumps) and the xppen-tools build for your OS.
      - unzip xppen-dumps-main.zip

 2. Copy the stock firmware next to this script
      cp "xppen-dumps-main/stock/G640 (Variant 2)/ic901-code.bin" .

 3. Build the patched firmware
      python3 make_patch.py ic901-code.bin            fully raw, no dead-zone (cursor shakes at rest)
      python3 make_patch.py ic901-code.bin --square   same, plus a small SQUARE dead-zone while the pen is still
    This writes g640v2-nosmooth.hex (or g640v2-nosmooth-square.hex) in the current directory.
    It refuses to run on any file that is not the stock Variant 2 image.

 4. Check the tablet is connected and what it is
      sudo ./xppen-tools info
    It should show 28BD:0914 and an IC 901 firmware (UG901_...).
    If the bootloader PID is FFF3, STOP: that bootloader has no exit-DFU command.

 5. Back up the current firmware (do not skip)
      sudo ./xppen-tools dump backup

 6. Put the tablet in DFU mode
      sudo ./xppen-tools dfu

 7. Flash. Do NOT unplug the tablet while it writes.
      sudo ./xppen-tools update g640v2-nosmooth.hex      (or g640v2-nosmooth-square.hex)

 8. Check the result
      sudo ./xppen-tools monitor
    Draw on the tablet and watch the pen state and report rate.

IF SOMETHING GOES WRONG
  - Leave DFU mode without flashing:   sudo ./xppen-tools exit-dfu
  - Restore stock firmware:            sudo ./xppen-tools update "xppen-dumps-main/stock/G640 (Variant 2)/ic901-stock.hex"
    (or flash your backup)

OPTIONS
  (none)     Fully raw. Every position the tablet measures goes straight to the cursor.
             Nothing is averaged and nothing is held back, so the cursor wobbles a few counts
             at rest (100 counts = about 1 mm). 37 bytes changed.

  --square   Same as above, plus a small dead-zone while the pen is nearly still. 82 bytes changed.
             How it works:
               - A dead-zone ignores tiny pen movements so the cursor sits still instead of shaking.
                 Once the pen moves further than the dead-zone, the real position is used
                 immediately, with no delay or blending.
               - The size of the dead-zone depends on pen speed and comes from a 16-entry table
                 (SQUARE_TABLE in this script): 8,7,6,5,4,3,2,1,0,0,... Slow pen = about 8 counts
                 (0.08 mm), fast pen = none. The slow-to-fast order is assumed.
               - The shape: stock firmware adds the X change and the Y change (a diamond).
                 --square instead takes the larger of the two (a square). A move is ignored only if
                 BOTH the X change and the Y change are smaller than the dead-zone size.
               - To change the size, edit the numbers in SQUARE_TABLE and run again.
"""

# (address, expected original bytes, new bytes, description)
EDITS = [
    (0x1D0099D4, "e884868f", "01000624", "averaging window = 1 sample (the main smoothing)"),
    (0x1D018770, bytes([80,70,50,50,50,45,45,45,45,45,45,35,30,25,20,15]).hex(),
                 bytes(16).hex(), "dead-zone table all zero"),
    (0x1D009740, "3200432c", "0000432c", "'moving' flag threshold 50 -> 0"),
] + [(a, "dd8482a3", "00000000", "out-of-area sample no longer sets pen state 3")
     for a in (0x1D007FB8, 0x1D007FE4, 0x1D008024, 0x1D008050)]

# --square: small dead-zone table + hold check rewritten from |dX|+|dY| (diamond) to max(|dX|,|dY|) (square).
SQUARE_TABLE = bytes([8,7,6,5,4,3,2,1,0,0,0,0,0,0,0,0])
SQUARE_HOLD_OLD = (  # stock 0x1D0076F8..0x1D007733, 15 instructions
    "ff008430fc84838fac858a8fd885828fac84898f23404900"
    "c33f08002640e8002338070123306a00c32f06002630a600"
    "2328c5002128e5002a28a400")
SQUARE_HOLD_NEW = (  # lw x4, |dY| -> a3, |dX| -> a1, a1 = max(a3,a1) < a0
    "fc84838fac858a8fd885828fac84898f23404900c33f0800"
    "2640e8002338070123306a00c32f06002630a6002328c500"
    "2a30e5000b38a6002a28e400")

def build(data, square=False):
    edits = list(EDITS)
    if square:
        edits[1] = (edits[1][0], edits[1][1], SQUARE_TABLE.hex(), "small dead-zone table")
        edits.append((0x1D0076F8, SQUARE_HOLD_OLD, SQUARE_HOLD_NEW, "hold check: |dX|+|dY| -> max(|dX|,|dY|)"))
    out, seen = bytearray(data), set()
    for addr, old, new, why in edits:
        o, n = addr - BASE, len(old) // 2
        assert not (set(range(o, o + n)) & seen), f"overlap at {addr:#x}"
        seen |= set(range(o, o + n))
        assert bytes(out[o:o+n]) == bytes.fromhex(old), f"unexpected bytes at {addr:#x}: {out[o:o+n].hex()} (wanted {old})"
        out[o:o+n] = bytes.fromhex(new)
    return bytes(out)

def to_ihex(code, base=BASE):
    """Absolute-address Intel HEX, same layout as `xppen-tools ihex --ic 901`."""
    def rec(addr, typ, data):
        b = bytes([len(data), (addr >> 8) & 0xff, addr & 0xff, typ]) + data
        return ":" + (b + bytes([(-sum(b)) & 0xff])).hex().upper() + "\n"
    out, upper = [], None
    for i in range(0, len(code), 16):
        a = base + i
        if (a >> 16) != upper:
            upper = a >> 16
            out.append(rec(0, 4, bytes([upper >> 8, upper & 0xff])))
        out.append(rec(a & 0xffff, 0, code[i:i+16]))
    return "".join(out) + ":00000001FF\n"

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--square"]
    if len(args) != 1 or args[0] in ("-h", "--help", "help"):
        print(HELP)
        sys.exit(0 if len(sys.argv) == 1 or args[:1] in (["-h"], ["--help"], ["help"]) else 1)
    square = "--square" in sys.argv
    d = open(args[0], "rb").read()
    assert len(d) == SIZE, "wrong size - this is not the G640 Variant 2 IC901 application image"
    b = build(d, square)
    name = "g640v2-nosmooth-square" if square else "g640v2-nosmooth"
    open(f"{name}.hex", "w").write(to_ihex(b))
    print(f"wrote {name}.hex  sha256 {hashlib.sha256(b).hexdigest()[:16]}  {sum(x != y for x, y in zip(d, b))} bytes changed")
