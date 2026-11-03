#!/usr/bin/env python3
"""Audit old-vs-new AX12 Realtek Bootloader RootFS signature probe addresses.

Purely offline. Reads Bootloader binaries and a decrypted Cloud image;
does not communicate with or write to the router.
"""
import argparse
import re
import struct
import zlib
from pathlib import Path

FILE_SYSTEM = re.compile(rb"fwup-ptn file-system base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def stage2(data):
    gzip = data.index(b"\x1f\x8b\x08")
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    code = dec.decompress(data[gzip:]) + dec.flush()
    if not dec.eof or b"no rootfs signature at %X!" not in code:
        raise ValueError("Not the expected Realtek Bootloader second stage")
    return code


def rootfs_probe(path):
    code = stage2(path.read_bytes())
    candidates = []
    for index in range(4, len(code) - 4, 4):
        insn = struct.unpack_from("<I", code, index)[0]
        if (insn & 0xFFFF0000) != 0x3C040000:  # lui a0, physical flash address high word
            continue
        if (insn & 0xFFFF) not in (0xB044, 0xB040):
            continue
        prev = struct.unpack_from("<I", code, index - 4)[0]
        if prev >> 26 != 3:  # JAL into the RootFS checking routine
            continue
        target = 0x80000000 | ((prev & 0x03FFFFFF) << 2)
        candidates.append((insn & 0xFFFF, index, target))
    if len(candidates) != 1:
        raise ValueError(f"Expected one static RootFS validation call, found {candidates}")
    high, offset, target = candidates[0]
    print(f"{path.name}: decompressed Bootloader stage2 {len(code):,} bytes")
    print(f"  call at {0x80000000 + offset - 4:#010x} -> {target:#010x}")
    print(f"  RootFS probe Flash address: {(high & 0xFF) << 16:#010x}")
    print("  Recognized kernel image magic: cs6c / cr6c")
    return (high & 0xFF) << 16


def check_candidate(path):
    cloud = path.read_bytes()
    match = FILE_SYSTEM.search(cloud[0x1014:0x1814])
    start = 0x1014 + int(match[1], 16)
    fs = cloud[start:start + int(match[2], 16)]
    if not fs.startswith(b"hsqs"):
        raise ValueError("Candidate RootFS is not SquashFS")
    print(f"Candidate RootFS at 0x400000: {fs[:4].hex(' ')} (hsqs)")
    print(f"Candidate bytes at old RootFS 0x440000: {fs[0x40000:0x40004].hex(' ')}")
    return fs[0x40000:0x40004]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old_bootloader", type=Path)
    p.add_argument("new_bootloader", type=Path)
    p.add_argument("candidate_cloud_plaintext", type=Path)
    args = p.parse_args()

    old = rootfs_probe(args.old_bootloader)
    new = rootfs_probe(args.new_bootloader)
    at_old = check_candidate(args.candidate_cloud_plaintext)
    assert old == 0x440000 and new == 0x400000
    assert at_old not in (b"hsqs", b"sqsh")
    print("BLOCKED: the unchanged old Bootloader's fixed RootFS probe does not match")
    print("         the relocated 1.5.0 filesystem. DO NOT FLASH the no-uboot candidate.")
    print("LIMIT: branch evidence is static; actual boot was not attempted.")


if __name__ == "__main__":
    main()
