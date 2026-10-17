#!/usr/bin/env python3
"""No-smoothing firmware builder for XP-Pen G640 (Variant 2), IC 901 (PIC32 / MIPS32 LE).

Run with no arguments, or with -h / --help, to print the instructions.
Options: --deadzone N (dead-zone size), --square (square shape), --pressure, --burst N, --adc-fast, --poll. See HELP.
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

  --burst N
      Add-on, EXPERIMENTAL and untested. How long the tablet drives the
      pen on each scan step, in cycles (stock is 28). Lower may scan
      faster but gives a weaker signal. Try 20 and compare the rate in
      xppen-tools monitor. Changes 2 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 20
      -> g640v2-nosmooth-square-burst-20.hex

  --adc-fast
      Add-on, EXPERIMENTAL and untested. Runs the ADC conversion clock
      twice as fast. The scan does about 50 ADC readings per step, so this
      can raise the rate WITHOUT weakening the signal like a low --burst.
      It only works if the chip clock is slow enough (about 30 MHz). If
      the pen gets noisy or loses signal, the clock is too fast for this
      and you should not use it. Changes 1 byte.
        python3 make_patch.py ic901-code.bin --square --burst 20 --adc-fast
      -> g640v2-nosmooth-square-burst-20-adc.hex

  --poll
      Add-on. Sets the USB polling interval to 1 ms (stock 3 ms for the
      pen). Stock polling caps the host at about 333 reports a second,
      so use this once the scan rate gets close to that. It does not
      speed up the scan. Changes 3 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll
      -> g640v2-nosmooth-square-burst-15-adc-poll.hex

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

# --burst N (experimental): number of carrier cycles the antenna is driven per scan step (stock 28 in the boot
# image, 35 in the reset code). Fewer cycles = shorter steps, possibly a faster scan, but a weaker signal.
def burst_edits(n):
    return [(0x1D018654, "1c", f"{n:02x}", "burst cycles 28 -> N (init image)"),
            (0x1D019D60, "23000324", f"{n:02x}000324", "burst cycles 35 -> N (reset code)")]

# --adc-fast (experimental): AD1CON3 is written once, at 0x1D00CDD4, as 0x0701 (SAMC=7, ADCS=1). ADCS=1 makes the
# ADC clock TAD = 4 peripheral-clock periods, so each of the ~50 conversions per scan step takes 12*TAD. ADCS=0
# halves TAD (2 periods) and so halves the conversion time. The signal scale and the sample count do not change,
# so no threshold needs rescaling. It only works if TAD stays above the ADC's minimum (about 65 ns).
ADC_FAST = [(0x1D00CDD4, "01070924", "00070924", "AD1CON3 ADCS 1 -> 0: conversion clock twice as fast")]

# --poll: USB endpoint polling intervals (full speed, bInterval in ms). Stock EP81 = 4, EP82 (pen) = 3, EP83 = 3.
# 1 ms removes the 333 Hz ceiling on how often the host reads the pen. It does not make the scan faster.
POLL = [(0x1D018D45, "04", "01", "EP81 IN bInterval 4 -> 1 ms"),
        (0x1D018D5E, "03", "01", "EP82 IN (pen) bInterval 3 -> 1 ms"),
        (0x1D018D77, "03", "01", "EP83 IN bInterval 3 -> 1 ms")]

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

def build(data, deadzone=None, square=False, pressure=False, burst=None, adc_fast=False, poll=False):
    edits = list(EDITS)
    if poll: edits += POLL
    if adc_fast: edits += ADC_FAST
    if burst is not None: edits += burst_edits(burst)
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
    argv, deadzone, square, pressure, burst, adc_fast, poll, args, i = sys.argv[1:], None, False, False, None, False, False, [], 0
    while i < len(argv):
        if argv[i] == "--square":
            square = True
        elif argv[i] == "--pressure":
            pressure = True
        elif argv[i] == "--adc-fast":
            adc_fast = True
        elif argv[i] == "--poll":
            poll = True
        elif argv[i] == "--burst":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 1 <= int(argv[i + 1]) <= 255:
                sys.exit("--burst needs a whole number from 1 to 255 (stock is 28)")
            burst = int(argv[i + 1]); i += 1
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
    b = build(d, deadzone, square, pressure, burst, adc_fast, poll)
    if deadzone is None: name = "g640v2-nosmooth"
    elif square and deadzone == DEFAULT_DEADZONE: name = "g640v2-nosmooth-square"
    elif square: name = f"g640v2-nosmooth-square-{deadzone}"
    else: name = f"g640v2-nosmooth-deadzone-{deadzone}"
    name += ("-pressure" if pressure else "") + (f"-burst-{burst}" if burst is not None else "") + ("-adc" if adc_fast else "") + ("-poll" if poll else "")
    open(f"{name}.hex", "w").write(to_ihex(b))
    print(f"wrote {name}.hex  sha256 {hashlib.sha256(b).hexdigest()[:16]}  {sum(x != y for x, y in zip(d, b))} bytes changed")
