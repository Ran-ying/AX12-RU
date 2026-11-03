#!/usr/bin/env python3
"""Extract physical MTD partition definitions from AX12 Realtek Linux kernels.

Reads decrypted TP-Link Cloud firmware files only. Does not access the router.
"""
import argparse
import lzma
import re
import struct
from pathlib import Path

KERNEL_ENTRY = re.compile(rb"fwup-ptn os-image base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
PARTITIONS = ("uboot", "uImage", "rootfs", "ART")
RECORD_SIZE = 32


def linux_image(cloud):
    match = KERNEL_ENTRY.search(cloud[0x1014:0x1814])
    start = 0x1014 + int(match[1], 16)
    image = cloud[start:start + int(match[2], 16)]
    if image[:4] not in (b"cr6c", b"cs6c"):
        raise ValueError("Expected Realtek cr6c kernel")
    marker = image.index(b"\x5d\x00\x00\x80\x00")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    kernel = decoder.decompress(image[marker:])
    if not decoder.eof:
        raise ValueError("Incomplete kernel LZMA stream")
    return kernel


def partition_table(kernel):
    marker = kernel.index(b"uboot\x00")
    pointer = struct.pack("<I", 0x80000000 + marker)
    base = kernel.index(pointer)
    partitions = []
    for index, expected in enumerate(PARTITIONS):
        off = base + index * RECORD_SIZE
        name_ptr, _, size, size_hi, offset, offset_hi = struct.unpack_from("<6I", kernel, off)
        name = kernel[name_ptr - 0x80000000:].split(b"\x00", 1)[0].decode()
        if name != expected or size_hi or offset_hi:
            raise ValueError(f"Unexpected MTD record at {off:#x}: {name}")
        partitions.append((name, offset, size))
    return base, partitions


def inspect(path):
    kernel = linux_image(path.read_bytes())
    table_off, parts = partition_table(kernel)
    print(path.name)
    print(f"  Decompressed kernel: {len(kernel):,} B")
    print(f"  MTD definitions at kernel memory {0x80000000 + table_off:#010x}")
    for name, offset, size in parts:
        print(f"  {name:<7} offset={offset:#010x} size={size:#010x}")
    return {name: (offset, size) for name, offset, size in parts}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old_cloud", type=Path)
    p.add_argument("new_cloud", type=Path)
    args = p.parse_args()
    old = inspect(args.old_cloud)
    new = inspect(args.new_cloud)
    assert old["rootfs"][0] == 0x440000
    assert new["rootfs"][0] == 0x400000
    assert new["uImage"] == (0x40000, 0x3c0000)
    assert old["uboot"] == new["uboot"] == (0, 0x40000)
    print("PASS: new kernel MTD rootfs starts at 0x400000 and bootloader remains 0x000000")
    print("NOTE: runtime MTD partition trimming and successful boot are not simulated")


if __name__ == "__main__":
    main()
