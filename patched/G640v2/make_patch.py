#!/usr/bin/env python3
"""No-smoothing firmware builder for XP-Pen G640 (Variant 2), IC 901 (PIC32 / MIPS32 LE).

Run with no arguments, or with -h / --help, to print the instructions.
Options: --deadzone N (dead-zone size), --square (square shape), --pressure, --burst N, --adc-fast, --settle N, --flash-fast, --smooth N, --hover-hold N, --adaptive N, --poll. See HELP.
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
      pen on each scan step, in carrier cycles. Stock is 35: the boot
      image says 28, but the startup code overwrites it with 35 before
      the pen is ever scanned. Lower scans faster but gives a weaker signal. Try 20 and compare the rate in
      xppen-tools monitor. Changes 2 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 20
      -> g640v2-nosmooth-square-burst-20.hex

  --adc-fast
      Add-on. Runs the ADC conversion clock twice as fast. The scan takes
      about 50 ADC readings per step, so this raises the rate WITHOUT
      weakening the signal like a low --burst. Changes 1 byte.
      NOTE: the chip runs at about 60 MHz, so this puts the ADC clock at
      about 33 ns, which is under the ~65 ns the ADC is rated for. It has
      worked on a real G640 V2, but if the pen gets noisy, drop it.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast
      -> g640v2-nosmooth-square-burst-15-adc.hex

  --poll
      Add-on. Sets the USB polling interval to 1 ms (stock 3 ms for the
      pen). Stock polling caps the host at about 333 reports a second,
      so use this once the scan rate gets close to that. It does not
      speed up the scan. Changes 3 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll
      -> g640v2-nosmooth-square-burst-15-adc-poll.hex

  --settle N
      Add-on, EXPERIMENTAL. The wait between the end of the pen drive burst
      and the first ADC reading, in microseconds (stock is 15). Allowed
      range is 12 to 15. Every scan step pays this wait, 14 steps per
      report, so each microsecond saved is only about 0.5% more rate
      (15 -> 12 is roughly +4 Hz). A value of 8 was tried on a real G640 V2
      and the tablet stopped detecting the pen at all (the antenna is
      probably still ringing when the reading starts), which is why values
      below 12 are refused. Changes 2 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll --settle 12
      -> g640v2-nosmooth-square-burst-15-adc-settle-12-poll.hex

  --flash-fast
      Add-on, EXPERIMENTAL. Flashed on a real G640 V2: no noticeable difference
      (no rate measurement was taken). Not recommended: see README. The stock firmware never sets the
      chip's flash wait states or prefetch (CHECON register), so after reset
      every instruction is fetched from flash at 7 wait states with no
      prefetch. This sets 3 wait states and turns prefetch on, so all code
      (scan loop, math, interrupts) runs faster. It replaces 4 instructions
      at the start of the startup code (an empty function call) with one
      register write, 16 bytes. The scan timers do not change, but the ADC
      read loop gets much faster, so pen signal levels may change a little.
      RISK: this is the first option that touches hardware setup at boot. If
      it were to hang, the tablet might not start, and I do not know a way
      back into the bootloader from that state. Flash it only after a backup
      and be ready to accept that risk.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll --flash-fast
      -> g640v2-nosmooth-square-burst-15-adc-flash-poll.hex

  --smooth N
      Add-on, OPTIONAL, off by default (the builds above have no smoothing).
      Light smoothing against chatter, N = 2 to 8. The base build forces the
      stock moving average to a window of 1. The stock firmware used about 11
      samples while the pen touches (roughly 30 ms of lag). This sets a small
      fixed window instead, using the firmware's own averaging code. Changes 4
      bytes (the same instruction the base build already changes). Emulator
      results (6 counts of noise, 30 counts per sample of pen speed):
        N=2: rest noise -44%, lag 1 sample  (~3 ms at 330 Hz)
        N=3: rest noise -57%, lag 2 samples (~6 ms)
        N=4: rest noise -63%, lag 3 samples (~9 ms)
      Not tested on a real tablet.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll --smooth 3
      -> g640v2-nosmooth-square-burst-15-adc-smooth-3-poll.hex

  --hover-hold N
      Add-on, EXPERIMENTAL. Calms the cursor while the pen hovers (pressure 0)
      and does not touch pen-down behaviour. N = 1 to 255 counts (100 = about
      1 mm). The stock firmware held the hover cursor for up to 80 counts and
      averaged 25 samples. The no-smoothing build holds only 8, but hover noise
      measured on a real G640 V2 is about 15 to 25 counts, so the cursor moved
      on almost every report. This sets the hover hold to a fixed N instead.
      The hold only skips a report while the pen is within N counts (in both X
      and Y) of the last reported point, so there is no averaging and no lag;
      a move bigger than N goes through at once. Simulation of the real hold
      routine with 16 counts of noise, pen still: the reported position changed
      on 89% of reports at hold 8, 43% at 20, 16% at 30, 4% at 40. Slowly
      hovering moves are reported in steps of about N counts. Changes 12 bytes.
        python3 make_patch.py ic901-code.bin --square --burst 15 --adc-fast --poll --hover-hold 40
      -> g640v2-nosmooth-square-burst-15-adc-hover-40-poll.hex

  --adaptive N
      Add-on, EXPERIMENTAL (checked in an emulator running the real firmware
      code, not yet on a tablet). Steadier cursor with almost no lag: light
      smoothing that switches itself off when the pen moves. N = 2 to 8 is
      the averaging window used while the pen is nearly still (4 is a good
      start). Instead of the base build's fixed window of 1, it keeps the
      firmware's own moving average and rewrites its speed tables: the
      stock ones start at a window of 13 (pen down) / 10 (hover) and only
      reach 1 at a very high speed, which is the heavy lag of the stock
      firmware. With --adaptive the window is N at rest, drops to 1 by about
      2 to 3 mm of lag distance, and is 1 for fast strokes. The speed measure
      is the distance between the new reading and the last output, so it
      reacts at once to a real move (a 3 mm jump goes through with no lag).
      Emulator numbers for N=4 (sensor noise sigma 7 raw, about 14 in the
      report units that xppen-tools monitor shows): sideways jitter on a
      line 0.39x at rest, 0.5x at 36 mm/s, 0.56x at 70 mm/s, 0.67x at
      140 mm/s. Lag 0.1 to 0.3 mm at handwriting speed (stock: about 1 mm).
      A circle of 3 mm radius at 95 mm/s keeps its size and its radius
      ripple halves. N=3 is lighter, N=6 steadier (jitter 0.29x at rest,
      about 10 ms of lag when crawling). Hover gets N+2 at rest. It works
      with a dead-zone of 0, so no sticky hold is needed. Replaces the
      averaging-window edit, so it cannot be combined with --smooth.
      It changes only table data (26 init values) and turns 26 startup
      stores into nops. No new code is added.
        python3 make_patch.py ic901-code.bin --burst 15 --adc-fast --poll --adaptive 4
      -> g640v2-nosmooth-burst-15-adc-adaptive-4-poll.hex

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

# --burst N (experimental): number of carrier cycles the antenna is driven per scan step (28 in the boot image, but the
# startup routine overwrites it with 35, so 35 is the live stock value). Fewer cycles = shorter steps, possibly a faster scan, but a weaker signal.
def burst_edits(n):
    return [(0x1D018654, "1c", f"{n:02x}", "burst cycles 28 -> N (init image)"),
            (0x1D019D60, "23000324", f"{n:02x}000324", "burst cycles 35 -> N (reset code)")]

# --adc-fast: AD1CON3 is written once, at 0x1D00CDD4, as 0x0701 (SAMC=7, ADCS=1). ADCS=1 makes TAD = 4 peripheral-clock
# periods; each of the ~50 conversions per scan step takes 12*TAD. ADCS=0 halves TAD. The chip runs at 60 MHz (DEVCFG:
# 12 MHz /3 x15, FPBDIV /1; the 100 us timer reload of 6000 agrees), so TAD goes from 66.7 ns (at the ~65 ns minimum) to
# 33 ns, which is out of spec but has worked on hardware. The SAMC field is NOT used: AD1CON1 = 0xA000 has SSRC = 0
# (manual conversion), and the scan sets/clears SAMP itself with a 2-tick software wait, so SAMC was never doing anything.
ADC_FAST = [(0x1D00CDD4, "01070924", "00070924", "AD1CON3 ADCS 1 -> 0: conversion clock twice as fast")]

# --settle N: post-burst wait. The routine at 0x1D01B1A8 waits (a052a + a0060) * 60 timer ticks (60 ticks = 1 us) before
# the first reading. a052a is the adaptive ring-down count (0 when the signal is weak) and a0060 is the fixed part.
# Boot image has a0060 = 10 (0x1D01866C) but the startup routine at 0x1D019D04 overwrites it with 15 (0x1D019D98).
def settle_edits(n):
    return [(0x1D01866C, "0a", f"{n:02x}", "post-burst wait 10 -> N us (init image, overwritten at boot)"),
            (0x1D019D98, "0f000624", f"{n:02x}000624", "post-burst wait 15 -> N us (startup defaults: the live value)")]

# --flash-fast: the loader enters the app at 0x1D007000 and falls into the startup code at 0x1D007030. At 0x1D007038 the
# startup calls an EMPTY function (0x1D01C97C: jr ra; nop), the slot where the usual compiler startup configures flash.
# Nothing in the boot flash, loader or app writes CHECON (0xBF884000), so the chip stays at its reset state: prefetch off,
# KSEG0 uncached, 7 flash wait states. Replace the 4-word call with: lui t0,0xbf88 / addiu t1,zero,0x33 / sw t1,0x4000(t0) / nop.
# CHECON 0x33 = PFMWS 3 wait states (bits 2:0; 60 MHz needs 2, one extra for margin) + PREFEN 3 (bits 5:4, prefetch for cacheable
# and non-cacheable). No cache (DCSZ 0) and CP0 Config.K0 is untouched, so no flash-write coherency issues.
FLASH_FAST = [(0x1D007038, "029d083c7cc9082509f8000100000000", "88bf083c33000924004009ad00000000",
               "startup: empty call -> CHECON = 0x33 (3 flash wait states, prefetch on)")]

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

# --smooth N: the base build forces the averaging window to 1 by replacing "lw a2,-0x7b18(gp)" at 0x1D0099D4 with
# "addiu a2,zero,1". "addiu a2,zero,N" gives a fixed N-sample window through the stock averaging code (exponential-style,
# alpha = 1/N, lag N-1 samples). Optional, off by default.
def smooth_edit(n):
    return (0x1D0099D4, "e884868f", f"{n:02x}000624", f"averaging window = {n} samples (light smoothing)")

# --hover-hold N: the hold function at 0x1D0076F8 takes its threshold in a0. Six call sites load it from the speed table
# result (lbu a0,-0x7b2c(gp) in the delay slot of each jal): 0x1D0079B4, 0x1D007A80, 0x1D007B4C are in the pen-down branch,
# 0x1D007C20, 0x1D007CEC, 0x1D007DB8 are in the hover branch (the code at 0x1D0078E4 branches to 0x1D007B58 when the
# pressure at 0xA0000DA8 is 0). Replacing the three hover loads with "addiu a0,zero,N" gives hover a fixed hold of N counts.
HOVER_SITES = (0x1D007C20, 0x1D007CEC, 0x1D007DB8)
def hover_edits(n):
    return [(a, "d4848493", f"{n:02x}000424", f"hover hold threshold = {n} counts") for a in HOVER_SITES]

# --adaptive N: the stock averaging at 0x1D0099D4 is a moving average whose window N is picked at 0x1D009790..0x1D0099D0 from the
# distance d = |dX|+|dY| between the new raw fine position and the previous averaged output (computed at 0x1D0096D8, raw units
# 0..15999 for X, 100 per mm; the HID report is 0..32767, i.e. 2.05x). Pen down (pressure != 0): ten ascending thresholds T0..T9 at
# RAM 0xA00000DE..F0 pick one of eleven windows (0xA00000FC, FE..110); hover: thresholds T0, T5, T6, T9 pick one of five windows
# (F2 d<=T0, F4 d<=T5, F8 d<=T6, F6 d<=T9, FA above). The tables live in the RAM init image (flash 0x1D0186EA..) and the startup
# routine at 0x1D019E70..0x1D019F24 stores the stock values over them (live stock: T = 100..4000, pen windows 13,12,11,10,9,7,7,6,
# 5,4,3, hover 10,5,3,1,1), so both are edited: init values replaced, those 26 stores turned into nops.
# The stock thresholds start at 100 (1 mm) while pen noise gives d of about 10 to 30, so the selector could never tell noise from motion.
ADA_THR = [20, 30, 40, 60, 80, 120, 180, 280, 440, 700]
ADA_LADDER = [1, .8, .62, .5, .38, .25, .12, 0, 0, 0, 0]
ADA_THR_ADDR = [0xA00000DE + 2 * i for i in range(10)]
ADA_PEN_ADDR = [0xA00000FC] + [0xA00000FE + 2 * i for i in range(10)]
ADA_HOV_ADDR = [0xA00000F2, 0xA00000F4, 0xA00000F8, 0xA00000F6, 0xA00000FA]
ADA_STOCK_INIT = {0xA00000DE: 100, 0xA00000E0: 150, 0xA00000E2: 200, 0xA00000E4: 250, 0xA00000E6: 300, 0xA00000E8: 400,
                  0xA00000EA: 600, 0xA00000EC: 1000, 0xA00000EE: 1500, 0xA00000F0: 2000,
                  0xA00000F2: 25, 0xA00000F4: 15, 0xA00000F6: 8, 0xA00000F8: 7, 0xA00000FA: 5, 0xA00000FC: 40,
                  0xA00000FE: 30, 0xA0000100: 30, 0xA0000102: 20, 0xA0000104: 15, 0xA0000106: 15, 0xA0000108: 12,
                  0xA000010A: 8, 0xA000010C: 5, 0xA000010E: 3, 0xA0000110: 1}

def adaptive_tables(n):
    pen = [max(1, round(1 + (n - 1) * f)) for f in ADA_LADDER]
    nh = n + 2
    return ADA_THR, pen, [nh, max(1, round(nh * .5)), 2, 1, 1]

def init_image_locations(data):
    """flash address of every RAM byte in the init image (records of dest, length, copy-flag, data at 0x1D0183CC)"""
    import struct
    p, where = 0x1D0183CC - BASE, {}
    while True:
        dest, ln, flag = struct.unpack("<III", data[p:p + 12])
        if dest == 0: break
        p += 12
        if flag:
            for i in range(ln): where[dest + i] = BASE + p + i
            p += ln
        p = (p + 3) & ~3
    return where

def adaptive_edits(data, n):
    import struct
    thr, pen, hov = adaptive_tables(n)
    vals = dict(zip(ADA_THR_ADDR, thr)); vals.update(zip(ADA_PEN_ADDR, pen)); vals.update(zip(ADA_HOV_ADDR, hov))
    where, edits = init_image_locations(data), []
    for a, v in sorted(vals.items()):
        f = where[a]
        assert struct.unpack("<H", data[f - BASE:f - BASE + 2])[0] == ADA_STOCK_INIT[a], f"init image value differs at {a:#x}"
        edits.append((f, data[f - BASE:f - BASE + 2].hex(), struct.pack("<H", v).hex(), f"init image {a:#x} = {v}"))
    nops = 0
    for pc in range(0x1D019E70, 0x1D019F2C, 4):          # sh rX,off(gp) to a table address -> nop
        w = struct.unpack("<I", data[pc - BASE:pc - BASE + 4])[0]
        if (w >> 26) == 41 and ((w >> 21) & 31) == 28:
            a = (0xA0007FF0 + ((w & 0xFFFF) - (0x10000 if w & 0x8000 else 0))) & 0xFFFFFFFF
            if a in vals:
                edits.append((pc, data[pc - BASE:pc - BASE + 4].hex(), "00000000", f"startup store to {a:#x} removed")); nops += 1
    assert nops == len(vals) == 26, (nops, len(vals))
    return edits

SAMPLE_WAIT = None

def build(data, deadzone=None, square=False, pressure=False, burst=None, adc_fast=False, poll=False, settle=None, flash_fast=False, smooth=None, hover_hold=None, adaptive=None):
    edits = list(EDITS)
    if hover_hold is not None: edits += hover_edits(hover_hold)
    if smooth is not None: edits[0] = smooth_edit(smooth)
    if poll: edits += POLL
    if adc_fast: edits += ADC_FAST
    if flash_fast: edits += FLASH_FAST
    if settle is not None: edits += settle_edits(settle)
    if burst is not None: edits += burst_edits(burst)
    if pressure: edits += PRESSURE
    if SAMPLE_WAIT is not None: edits.append((0x1D0182FC, "0200422c", f"{SAMPLE_WAIT:02x}00422c", f"ADC sample wait = {SAMPLE_WAIT} ticks (stock 2 = 33 ns)"))
    if deadzone is not None:
        edits[1] = (edits[1][0], edits[1][1], square_table(deadzone).hex(), "dead-zone table")
    if square:
        edits.append((0x1D0076F8, SQUARE_HOLD_OLD, SQUARE_HOLD_NEW, "hold check: |dX|+|dY| -> max(|dX|,|dY|)"))
    if adaptive is not None:
        edits = [e for e in edits if e[0] != 0x1D0099D4] + adaptive_edits(data, adaptive)   # keep the stock averaging, change its tables
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
    argv, deadzone, square, pressure, burst, adc_fast, poll, settle, flash_fast, smooth, hover_hold, adaptive, args, i = sys.argv[1:], None, False, False, None, False, False, None, False, None, None, None, [], 0
    while i < len(argv):
        if argv[i] == "--square":
            square = True
        elif argv[i] == "--pressure":
            pressure = True
        elif argv[i] == "--adc-fast":
            adc_fast = True
        elif argv[i] == "--flash-fast":
            flash_fast = True
        elif argv[i] == "--hover-hold":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 1 <= int(argv[i + 1]) <= 255:
                sys.exit("--hover-hold needs a whole number from 1 to 255 (counts, 100 is about 1 mm)")
            hover_hold = int(argv[i + 1]); i += 1
        elif argv[i] == "--adaptive":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 2 <= int(argv[i + 1]) <= 8:
                sys.exit("--adaptive needs a whole number from 2 to 8 (averaging window at rest; 4 is a good start)")
            adaptive = int(argv[i + 1]); i += 1
        elif argv[i] == "--smooth":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 2 <= int(argv[i + 1]) <= 8:
                sys.exit("--smooth needs a whole number from 2 to 8 (averaging window in samples; the default build uses 1)")
            smooth = int(argv[i + 1]); i += 1
        elif argv[i] == "--sampc":
            sys.exit("--sampc was removed: the ADC sample time field is not used by this firmware (manual conversion), so it did nothing")
        elif argv[i] == "--settle":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 12 <= int(argv[i + 1]) <= 15:
                sys.exit("--settle needs a whole number from 12 to 15 (microseconds, stock is 15). 8 stopped pen detection on a real G640 V2, so lower values are refused")
            settle = int(argv[i + 1]); i += 1
        elif argv[i] == "--poll":
            poll = True
        elif argv[i] == "--sample-wait":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 1 <= int(argv[i + 1]) <= 30:
                sys.exit("--sample-wait needs a whole number from 1 to 30 (timer ticks, 60 = 1 us, stock 2)")
            SAMPLE_WAIT = int(argv[i + 1]); i += 1
        elif argv[i] == "--burst":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or not 1 <= int(argv[i + 1]) <= 255:
                sys.exit("--burst needs a whole number from 1 to 255 (stock is 35)")
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
    if adaptive is not None and smooth is not None:
        sys.exit("--adaptive and --smooth both set the averaging window: use one of them")
    d = open(args[0], "rb").read()
    assert len(d) == SIZE, "wrong size - this is not the G640 Variant 2 IC901 application image"
    b = build(d, deadzone, square, pressure, burst, adc_fast, poll, settle, flash_fast, smooth, hover_hold, adaptive)
    if deadzone is None: name = "g640v2-nosmooth"
    elif square and deadzone == DEFAULT_DEADZONE: name = "g640v2-nosmooth-square"
    elif square: name = f"g640v2-nosmooth-square-{deadzone}"
    else: name = f"g640v2-nosmooth-deadzone-{deadzone}"
    name += ("-pressure" if pressure else "") + (f"-burst-{burst}" if burst is not None else "") + ("-adc" if adc_fast else "") + (f"-settle-{settle}" if settle is not None else "") + ("-flash" if flash_fast else "") + (f"-smooth-{smooth}" if smooth is not None else "") + (f"-adaptive-{adaptive}" if adaptive is not None else "") + (f"-hover-{hover_hold}" if hover_hold is not None else "") + (f"-sw-{SAMPLE_WAIT}" if SAMPLE_WAIT is not None else "") + ("-poll" if poll else "")
    open(f"{name}.hex", "w").write(to_ihex(b))
    print(f"wrote {name}.hex  sha256 {hashlib.sha256(b).hexdigest()[:16]}  {sum(x != y for x, y in zip(d, b))} bytes changed")
