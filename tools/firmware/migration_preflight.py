#!/usr/bin/env python3
"""Read-only structural preflight for a decrypted AX12 RU Cloud image.

Reports partition boundaries and bootloader changes; never flashes hardware.
"""
import argparse
import re
from pathlib import Path

FLASH_SIZE = 0x1000000
PREFIX = 0x1014

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("decrypted_cloud", type=Path)
parser.add_argument("--existing_uboot", type=Path, help="Optional original 0x40000-byte Flash dump")
parser.add_argument("--old_cloud", type=Path, help="Optional decrypted/plaintext 1.1.22 Cloud image")
args = parser.parse_args()

raw = args.decrypted_cloud.read_bytes()
manifest = raw[PREFIX:0x1814]
updates = {
    m[1].decode(): (int(m[2], 16), int(m[3], 16))
    for m in re.finditer(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)", manifest)
}
table = raw[0x1818:0x2014]
flash = {
    m[1].decode(): (int(m[2], 16), int(m[3], 16))
    for m in re.finditer(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)", table)
}

for name, (offset, size) in sorted(flash.items(), key=lambda p: p[1][0]):
    if offset + size > FLASH_SIZE:
        raise ValueError(f"{name}: exceeds 16 MiB Flash")

print(f"Target Flash partitions: {len(flash)} (old 1.1.22 parser has 28 slots)")
print("Firmware manifest payload order:", " -> ".join(updates))
print("Cloud partition payloads mapped against the image partition table:")
for name in ("fs-uboot", "os-image", "file-system", "partition-table"):
    if name not in updates:
        continue
    src, count = updates[name]
    target, capacity = flash[name]
    if PREFIX + src + count > len(raw) or count > capacity:
        raise ValueError(f"{name}: source truncated or larger than destination")
    print(f"  {name:16s} Flash {target:#08x}..{target+capacity:#08x}, "
          f"payload {count:#x}, spare {capacity-count:,} bytes")

if args.existing_uboot and "fs-uboot" in updates:
    start, size = updates["fs-uboot"]
    original = args.existing_uboot.read_bytes()
    candidate = raw[PREFIX + start:PREFIX + start + size]
    changed = sum(a != b for a, b in zip(original, candidate))
    print(f"Existing vs image fs-uboot: {changed:,} differing bytes "
          f"in {len(candidate):,}-byte payload; new bootloader is NOT identical")

if args.old_cloud:
    old = args.old_cloud.read_bytes()
    old_table = {
        m[1].decode(): (int(m[2], 16), int(m[3], 16))
        for m in re.finditer(
            rb"partition ([\\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)",
            old[0x1818:0x2014]
        )
    }
    print(f"Old Flash partitions: {len(old_table)}")
    for name in ("os-image", "file-system"):
        if old_table[name] != flash[name]:
            print(f"  {name}: old {old_table[name]} -> new {flash[name]}")
    added = sorted(set(flash) - set(old_table))
    print("New partition names:", ", ".join(added))
    print("Caution: 1.5.0 RootFS starts inside the old os-image partition; "
          "old/new partition map migration must be verified.")

print("NOTE: This validates sizes and presence only, not upgrade write order, "
      "power-loss safety, boot compatibility or preserved factory data.")
