#!/usr/bin/env python3
"""Inspect embedded Linux/LZMA and Realtek MTD identifiers in decrypted AX12 Cloud firmware.

Read-only static evidence; cannot prove that the current bootloader boots new Linux.
"""
import argparse
import lzma
import re
from pathlib import Path

MANIFEST = re.compile(rb"fwup-ptn os-image base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
LZMA_HEADER = b"\x5d\x00\x00\x80\x00"
IDENTIFIERS = (
    b"RTL8197F",
    b"rtkxxpart",
    b"uImage",
    b"rootfs",
    b"console=ttyS0,115200 root=/dev/mtdblock2 init=/etc/preinit",
)


def inspect(path):
    cloud = path.read_bytes()
    match = MANIFEST.search(cloud[0x1014:0x1814])
    if match is None:
        raise ValueError(f"No os-image manifest entry in {path}")
    start = 0x1014 + int(match[1], 16)
    size = int(match[2], 16)
    image = cloud[start:start + size]
    if len(image) != size or image[:4] != b"cr6c":
        raise ValueError(f"Unexpected os-image payload in {path}")

    offset = image.find(LZMA_HEADER)
    if offset < 0:
        raise ValueError(f"No LZMA kernel in {path}")
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    linux = dec.decompress(image[offset:])
    if not dec.eof:
        raise ValueError(f"Incomplete LZMA kernel in {path}")

    version = re.search(rb"Linux version [^\x00\n]+", linux)
    if version is None:
        raise ValueError(f"No Linux version banner in {path}")
    present = {name.decode(): name in linux for name in IDENTIFIERS}
    print(f"{path.name}: os-image={size:#x}, LZMA at {offset:#x}, "
          f"decompressed={len(linux):,} bytes")
    print(" ", version.group().decode(errors="replace"))
    for name, found in present.items():
        print(f"  {name}: {'found' if found else 'MISSING'}")
    return present


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old_cloud_plaintext", type=Path)
    p.add_argument("new_cloud_plaintext", type=Path)
    args = p.parse_args()

    old = inspect(args.old_cloud_plaintext)
    new = inspect(args.new_cloud_plaintext)
    if not all(old.values()) or not all(new.values()):
        raise ValueError("Realtek MTD identifiers differ or are absent")
    print("PASS: both kernels retain Linux 4.4, RTL8197F, rtkxxpart, "
          "and root=/dev/mtdblock2 conventions")
    print("NOT PROVEN: future MTD offsets, old-Bootloader execution, "
          "or successful RootFS mount")


if __name__ == "__main__":
    main()
