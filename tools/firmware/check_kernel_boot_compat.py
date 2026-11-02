#!/usr/bin/env python3
"""Compare AX12 Realtek kernel boot headers from two *plaintext* Cloud images.

Read-only: checks loader ABI fields and the Realtek kernel checksum.
Passing these checks does not establish bootloader/rootfs compatibility.
"""
import argparse
import re
import struct
from pathlib import Path

START, END = 0x1014, 0x1814
ENTRY = re.compile(rb"fwup-ptn os-image base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def inspect(path):
    cloud = path.read_bytes()
    match = ENTRY.search(cloud[START:END])
    if match is None:
        raise ValueError(f"{path}: os-image not in Cloud manifest")
    offset = START + int(match[1], 16)
    size = int(match[2], 16)
    image = cloud[offset:offset + size]
    if len(image) != size:
        raise ValueError(f"{path}: truncated os-image")
    magic, entry, burn, length = struct.unpack_from(">4sIII", image)
    if magic != b"cr6c" or len(image) != 16 + length + 1:
        raise ValueError(f"{path}: unexpected Realtek boot image")
    body = image[16:16 + length]
    checksum = sum(int.from_bytes(body[i:i + 2], "big")
                   for i in range(0, len(body), 2)) & 0xFFFF
    if checksum:
        raise ValueError(f"{path}: invalid Realtek 16-bit checksum")
    return entry, burn, length, size


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("old_cloud", type=Path)
parser.add_argument("new_cloud_decrypted", type=Path)
args = parser.parse_args()
old = inspect(args.old_cloud)
new = inspect(args.new_cloud_decrypted)
for label, (entry, burn, length, size) in [("1.1.22", old), ("1.5.0", new)]:
    print(f"{label}: cr6c load={entry:#010x}, burn={burn:#x}, "
          f"data={length:#x}, package={size:#x}, checksum=PASS")
if old[:2] != new[:2]:
    raise ValueError("Kernel load or Flash destination changed")
print("PASS: kernel load address and Flash destination are unchanged")
print("NOT PROVEN: existing bootloader supports new kernel/rootfs,"
      " and new Linux MTD table boots correctly.")
