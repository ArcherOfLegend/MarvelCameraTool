#!/usr/bin/env python3
"""Extract and inject single cameras in UMvC3 .lmcm files.

    m3c.py list       chara.lmcm
    m3c.py extract    chara.lmcm 0 -o hyper0.m3c
    m3c.py extractall chara.lmcm -o out/
    m3c.py inject     chara.lmcm hyper0.m3c 2 -o patched.lmcm
"""

import argparse
import os
import struct
import sys

LMCM_MAGIC = b"LMCM"
M3C_MAGIC = b"M3C1"
ENTRY_SIZE = 0x40
M3C_HEADER = 0x40
BYTES_PER_FRAME = 48


class Camera:
    def __init__(self, slot, frames, floats, eye, target, rot, fov, roll, source=""):
        self.slot = slot
        self.frames = frames
        self.floats = list(floats)
        self.eye = eye
        self.target = target
        self.rot = rot
        self.fov = fov
        self.roll = roll
        self.source = source

    @property
    def block_size(self):
        return BYTES_PER_FRAME * self.frames

    def pack(self):
        out = bytearray()
        for v in self.eye:
            out += struct.pack("<3f", *v)
        for v in self.target:
            out += struct.pack("<3f", *v)
        for v in self.rot:
            out += struct.pack("<4f", *v)
        for v in self.fov:
            out += struct.pack("<f", v)
        for v in self.roll:
            out += struct.pack("<f", v)
        return bytes(out)


def unpack_tracks(data, ptrs, n):
    eye = [struct.unpack_from("<3f", data, ptrs[0] + 12 * j) for j in range(n)]
    tgt = [struct.unpack_from("<3f", data, ptrs[1] + 12 * j) for j in range(n)]
    rot = [struct.unpack_from("<4f", data, ptrs[2] + 16 * j) for j in range(n)]
    fov = [struct.unpack_from("<f", data, ptrs[3] + 4 * j)[0] for j in range(n)]
    rol = [struct.unpack_from("<f", data, ptrs[4] + 4 * j)[0] for j in range(n)]
    return eye, tgt, rot, fov, rol


def read_lmcm(path):
    data = open(path, "rb").read()
    if data[:4] != LMCM_MAGIC:
        raise ValueError("%s is not an LMCM file" % path)
    version, slot_count = struct.unpack_from("<hh", data, 4)
    table = struct.unpack_from("<%dq" % slot_count, data, 8)
    stem = os.path.splitext(os.path.basename(path))[0]

    cams = []
    for slot, off in enumerate(table):
        if off <= 0:
            continue
        n = struct.unpack_from("<i", data, off)[0]
        floats = struct.unpack_from("<5f", data, off + 4)
        ptrs = struct.unpack_from("<5q", data, off + 24)
        cams.append(Camera(slot, n, floats, *unpack_tracks(data, ptrs, n),
                           source=stem))
    return version, slot_count, cams


def write_lmcm(path, version, slot_count, cams):
    # Rebuilds the LMCM file from a list of Camera objects.
    cams = sorted(cams, key=lambda c: c.slot)
    if len(cams) != len({c.slot for c in cams}):
        raise ValueError("two cameras claim the same slot")
    for c in cams:
        if not 0 <= c.slot < slot_count:
            raise ValueError("slot %d is outside the table capacity %d"
                             % (c.slot, slot_count))

    table_end = 8 + slot_count * 8
    heap = table_end + len(cams) * ENTRY_SIZE

    out = bytearray(heap)
    out[0:4] = LMCM_MAGIC
    struct.pack_into("<hh", out, 4, version, slot_count)

    cursor = heap
    for i, c in enumerate(cams):
        entry = table_end + i * ENTRY_SIZE
        struct.pack_into("<q", out, 8 + c.slot * 8, entry)
        struct.pack_into("<i", out, entry, c.frames)
        struct.pack_into("<5f", out, entry + 4, *c.floats)
        ptrs = []
        for size in (12 * c.frames, 12 * c.frames, 16 * c.frames,
                     4 * c.frames, 4 * c.frames):
            ptrs.append(cursor)
            cursor += size
        struct.pack_into("<5q", out, entry + 24, *ptrs)
        out += c.pack()

    expected = heap + sum(c.block_size for c in cams)
    if len(out) != expected:
        raise AssertionError("size came out %d, expected %d" % (len(out), expected))
    open(path, "wb").write(bytes(out))
    return len(out)


def read_m3c(path):
    d = open(path, "rb").read()
    if d[:4] != M3C_MAGIC:
        raise ValueError("%s is not an M3C file" % path)
    slot = struct.unpack_from("<H", d, 6)[0]
    frames = struct.unpack_from("<I", d, 8)[0]
    floats = struct.unpack_from("<5f", d, 0x10)
    source = d[0x24:0x40].split(b"\0")[0].decode("utf-8", "replace")
    if len(d) != M3C_HEADER + BYTES_PER_FRAME * frames:
        raise ValueError("%s: size does not match its frame count" % path)

    o = M3C_HEADER
    ptrs = (o, o + 12 * frames, o + 24 * frames,
            o + 40 * frames, o + 44 * frames)
    return Camera(slot, frames, floats, *unpack_tracks(d, ptrs, frames),
                  source=source)


def write_m3c(path, cam):
    hdr = bytearray(M3C_HEADER)
    hdr[0:4] = M3C_MAGIC
    struct.pack_into("<HH", hdr, 4, 1, cam.slot)
    struct.pack_into("<II", hdr, 8, cam.frames, 0)
    struct.pack_into("<5f", hdr, 0x10, *cam.floats)
    src = cam.source.encode("utf-8")[:27]
    hdr[0x24:0x24 + len(src)] = src
    open(path, "wb").write(bytes(hdr) + cam.pack())
    return M3C_HEADER + cam.block_size


def slot_label(i):
    if i < 10:
        return "hyper %d" % i
    if i < 20:
        return "thc %d" % (i - 10)
    if i < 30:
        return "win %d" % (i - 20)
    if i < 50:
        return "etc %d" % (i - 30)
    if i < 60:
        return "cine %d" % (i - 50)
    return "slot %d" % i


def cmd_list(a):
    version, slot_count, cams = read_lmcm(a.lmcm)
    print("%s  version %d  capacity %d  %d cameras  %d frames"
          % (os.path.basename(a.lmcm), version, slot_count, len(cams),
             sum(c.frames for c in cams)))
    print("%5s  %-10s %8s %10s" % ("slot", "guess", "frames", "bytes"))
    for c in cams:
        print("%5d  %-10s %8d %10d"
              % (c.slot, slot_label(c.slot), c.frames, c.block_size))


def cmd_extract(a):
    _, _, cams = read_lmcm(a.lmcm)
    hit = [c for c in cams if c.slot == a.slot]
    if not hit:
        sys.exit("slot %d is empty. populated: %s"
                 % (a.slot, ", ".join(str(c.slot) for c in cams)))
    out = a.out or "%s_slot%02d.m3c" % (
        os.path.splitext(os.path.basename(a.lmcm))[0], a.slot)
    print("wrote %s  (%d frames, %d bytes)"
          % (out, hit[0].frames, write_m3c(out, hit[0])))


def cmd_extractall(a):
    _, _, cams = read_lmcm(a.lmcm)
    base = os.path.splitext(os.path.basename(a.lmcm))[0]
    os.makedirs(a.out, exist_ok=True)
    for c in cams:
        p = os.path.join(a.out, "%s_slot%02d.m3c" % (base, c.slot))
        write_m3c(p, c)
        print("wrote %s  (%d frames)" % (p, c.frames))


def cmd_inject(a):
    version, slot_count, cams = read_lmcm(a.lmcm)
    cam = read_m3c(a.m3c)
    cam.slot = a.slot if a.slot is not None else cam.slot
    cams = [c for c in cams if c.slot != cam.slot] + [cam]
    out = a.out or a.lmcm.replace(".lmcm", "_patched.lmcm")
    size = write_lmcm(out, version, slot_count, cams)
    print("injected %d frames into slot %d" % (cam.frames, cam.slot))
    print("wrote %s  (%d bytes)" % (out, size))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("lmcm")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("extract")
    p.add_argument("lmcm")
    p.add_argument("slot", type=int)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("extractall")
    p.add_argument("lmcm")
    p.add_argument("-o", "--out", default=".")
    p.set_defaults(fn=cmd_extractall)

    p = sub.add_parser("inject")
    p.add_argument("lmcm")
    p.add_argument("m3c")
    p.add_argument("slot", type=int, nargs="?", default=None)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_inject)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()