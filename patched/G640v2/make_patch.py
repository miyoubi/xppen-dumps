#!/usr/bin/env python3
"""No-smoothing firmware builder for XP-Pen G640 (Variant 2), IC 901 (PIC32 / MIPS32 LE).

Run with no arguments, or with -h / --help, to print the instructions.
Options: --deadzone N (dead-zone size), --square (square shape), --pressure. See HELP.
Tested on a G640 Variant 2: works. Back up first anyway. Every edit verifies the original bytes
and refuses to run on any other image.
"""
import sys, hashlib

BASE, SIZE = 0x1D006000, 102400

HELP = """\
XP-Pen G640 (Variant 2) no-smoothing firmware builder
Only for the G640 Variant 2 (USB ID 28BD:0914). Use at your own risk.

USAGE
  python3 make_patch.py ic901-code.bin [option]

  ic901-code.bin is the stock firmware, in the dumps repo under
  stock/G640 (Variant 2)/. The script writes a .hex file you can flash
  with xppen-tools.

OPTIONS

  (none)
      Raw. The cursor goes exactly where the pen is, with no smoothing.
      It may shake a little when the pen is held still.
        python3 make_patch.py ic901-code.bin
      -> g640v2-nosmooth.hex

  --deadzone N
      Ignore tiny movements while the pen is nearly still. N is the size,
      0 to 255 (100 = about 1 mm). Higher is steadier but stickier.
      Uses the stock shape: a diamond (X move + Y move added together).
        python3 make_patch.py ic901-code.bin --deadzone 12
      -> g640v2-nosmooth-deadzone-12.hex

  --square
      Same, but the shape is a square: X and Y are checked separately,
      so the pen is ignored only until it moves N in X or N in Y.
      Default size is 8. Add --deadzone N to pick a different size.
        python3 make_patch.py ic901-code.bin --square
        python3 make_patch.py ic901-code.bin --square --deadzone 12
      -> g640v2-nosmooth-square.hex
      -> g640v2-nosmooth-square-12.hex

  --pressure
      Add-on, EXPERIMENTAL and untested. Stops the firmware from cutting
      pressure to 66% for a few frames when the pen first touches down.
      Changes 2 bytes.
        python3 make_patch.py ic901-code.bin --square --pressure
      -> g640v2-nosmooth-square-pressure.hex

  -h, --help
      Show this message.
"""

# (address, expected original bytes, new bytes, description)
EDITS = [
    (0x1D0099D4, "e884868f", "01000624", "averaging window = 1 sample (the main smoothing)"),
    (0x1D018770, bytes([80,70,50,50,50,45,45,45,45,45,45,35,30,25,20,15]).hex(),
                 bytes(16).hex(), "dead-zone table all zero"),
    (0x1D009740, "3200432c", "0000432c", "'moving' flag threshold 50 -> 0"),
] + [(a, "dd8482a3", "00000000", "out-of-area sample no longer sets pen state 3")
     for a in (0x1D007FB8, 0x1D007FE4, 0x1D008024, 0x1D008050)]

# --pressure (experimental): in the light-touch zone the firmware reports 66% of the last pressure for a few
# frames. Set that factor to 100% (boot default in the init image, and the same value set by the reset code).
PRESSURE = [(0x1D018660, "42000000", "64000000", "pressure light-touch factor 66 -> 100 (init image)"),
            (0x1D019D84, "42000424", "64000424", "pressure light-touch factor 66 -> 100 (reset code)")]

# --square: small dead-zone table + hold check rewritten from |dX|+|dY| (diamond) to max(|dX|,|dY|) (square).
DEFAULT_DEADZONE = 8   # counts (100 counts = about 1 mm)

def square_table(size):
    """16-entry dead-zone table: `size` counts for a slow pen, shrinking linearly to 0 by entry 8.
    size=8 gives 8,7,6,5,4,3,2,1,0,0,0,0,0,0,0,0"""
    return bytes([max(0, round(size * (8 - i) / 8)) if i < 8 else 0 for i in range(16)])
SQUARE_HOLD_OLD = (  # stock 0x1D0076F8..0x1D007733, 15 instructions
    "ff008430fc84838fac858a8fd885828fac84898f23404900"
    "c33f08002640e8002338070123306a00c32f06002630a600"
    "2328c5002128e5002a28a400")
SQUARE_HOLD_NEW = (  # lw x4, |dY| -> a3, |dX| -> a1, a1 = max(a3,a1) < a0
    "fc84838fac858a8fd885828fac84898f23404900c33f0800"
    "2640e8002338070123306a00c32f06002630a6002328c500"
    "2a30e5000b38a6002a28e400")

def build(data, deadzone=None, square=False, pressure=False):
    edits = list(EDITS)
    if pressure: edits += PRESSURE
    if deadzone is not None:
        edits[1] = (edits[1][0], edits[1][1], square_table(deadzone).hex(), "dead-zone table")
    if square:
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
    argv, deadzone, square, pressure, args, i = sys.argv[1:], None, False, False, [], 0
    while i < len(argv):
        if argv[i] == "--square":
            square = True
        elif argv[i] == "--pressure":
            pressure = True
        elif argv[i] == "--deadzone":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 0 <= int(argv[i + 1]) <= 255:
                sys.exit("--deadzone needs a whole number from 0 to 255 (counts)")
            deadzone = int(argv[i + 1]); i += 1
        else:
            args.append(argv[i])
        i += 1
    if square and deadzone is None:
        deadzone = DEFAULT_DEADZONE
    if len(args) != 1 or args[0] in ("-h", "--help", "help"):
        print(HELP)
        sys.exit(0 if not argv or args[:1] in (["-h"], ["--help"], ["help"]) else 1)
    d = open(args[0], "rb").read()
    assert len(d) == SIZE, "wrong size - this is not the G640 Variant 2 IC901 application image"
    b = build(d, deadzone, square, pressure)
    if deadzone is None: name = "g640v2-nosmooth"
    elif square and deadzone == DEFAULT_DEADZONE: name = "g640v2-nosmooth-square"
    elif square: name = f"g640v2-nosmooth-square-{deadzone}"
    else: name = f"g640v2-nosmooth-deadzone-{deadzone}"
    name += "-pressure" if pressure else ""
    open(f"{name}.hex", "w").write(to_ihex(b))
    print(f"wrote {name}.hex  sha256 {hashlib.sha256(b).hexdigest()[:16]}  {sum(x != y for x, y in zip(d, b))} bytes changed")
