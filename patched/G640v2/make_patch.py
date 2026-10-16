#!/usr/bin/env python3
"""Firmware builder for XP-Pen G640 (Variant 2), IC 901 (PIC32 / MIPS32 LE).

usage: make_patch.py ic901-code.bin OUTDIR [--normal]
  default   -> OUTDIR/g640v2-nosmooth.{bin,hex}  everything off, fully raw (the cursor WILL shake at rest)
  --normal  -> OUTDIR/g640v2-normal.{bin,hex}    averaging off + small dead-zone while still (stops the shake)
  flash a .hex with `xppen-tools update`

Back up first: xppen-tools dump backup. Every edit verifies the original bytes
and refuses to run on any other image.
"""
import sys, os, hashlib
BASE, SIZE = 0x1D006000, 102400

STOCK_HOLD = bytes([80,70,50,50,50,45,45,45,45,45,45,35,30,25,20,15])
NORMAL_HOLD = bytes([32,28,20,14,10,8,6,4,3,2,0,0,0,0,0,0])   # small when still, none when moving (slow->fast order assumed)
RAW_HOLD = bytes(16)                                            # no dead-zone at all

def edits(hold):
    return [
        (0x1D0099D4, "e884868f", "01000624", "averaging window = 1 sample (main smoothing)"),
        (0x1D018770, STOCK_HOLD.hex(), hold.hex(), "hold dead-zone table"),
        (0x1D009740, "3200432c", "0000432c", "'moving' flag threshold 50 -> 0"),
    ] + [(a, "dd8482a3", "00000000", "out-of-area sample no longer sets state 3")
         for a in (0x1D007FB8, 0x1D007FE4, 0x1D008024, 0x1D008050)]

BUILDS = {"normal": edits(NORMAL_HOLD), "nosmooth": edits(RAW_HOLD)}

def build(data, edit_list):
    out, seen = bytearray(data), set()
    for addr, old, new, why in edit_list:
        o, n = addr - BASE, len(old) // 2
        assert len(new) == len(old), why
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
    args = [a for a in sys.argv[1:] if a != "--normal"]
    if len(args) != 2:
        sys.exit(__doc__)
    src, outdir = args
    name = "normal" if "--normal" in sys.argv else "nosmooth"
    d = open(src, "rb").read()
    assert len(d) == SIZE, "wrong size - this is not the G640 Variant 2 IC901 application image"
    os.makedirs(outdir, exist_ok=True)
    for name, e in [(name, BUILDS[name])]:
        b = build(d, e)
        open(f"{outdir}/g640v2-{name}.bin", "wb").write(b)
        open(f"{outdir}/g640v2-{name}.hex", "wb").write(to_ihex(b).encode())
        print(f"g640v2-{name}.hex  sha256 {hashlib.sha256(b).hexdigest()[:16]}  {sum(x != y for x, y in zip(d, b))} bytes changed")
