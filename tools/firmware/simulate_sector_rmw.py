#!/usr/bin/env python3
"""Model ordered AX12 Cloud writes with 64 KiB read-modify-erase-rewrite sectors.

This is a local file-only model, NOT an emulation of the complete Realtek driver
or nvrammanager and NEVER accesses a router or writes a firmware image.
"""
import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from self_sign_lab import cloud_decrypt

FLASH_BYTES = 0x1000000
SECTOR_BYTES = 0x10000
PARTITION = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
UPDATE = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def parse_entries(blob, pattern):
    return [(m[1].decode(), int(m[2], 16), int(m[3], 16))
            for m in pattern.finditer(blob)]


def simulate(old_flash, cloud):
    before = old_flash
    after = bytearray(before)
    old_table = {name: (base, size) for name, base, size in
                 parse_entries(before[0xF40004:0xF40800], PARTITION)}
    new_table = {name: (base, size) for name, base, size in
                 parse_entries(cloud[0x1818:0x2014], PARTITION)}
    updates = parse_entries(cloud[0x1014:0x1814], UPDATE)

    assert len(before) == FLASH_BYTES
    assert len(new_table) == 28
    assert "fs-uboot" not in {name for name, _, _ in updates}
    assert old_table["fs-uboot"] == new_table["fs-uboot"]

    touched = Counter()
    for name, relative, size in updates:
        base, capacity = new_table[name]
        source = cloud[0x1014 + relative:0x1014 + relative + size]
        if len(source) != size or size > capacity:
            raise ValueError(f"Invalid {name} update payload")

        cursor = 0
        while cursor < size:
            absolute = base + cursor
            sector_start = absolute & ~(SECTOR_BYTES - 1)
            in_sector = absolute - sector_start
            length = min(size - cursor, SECTOR_BYTES - in_sector)
            sector = bytearray(after[sector_start:sector_start + SECTOR_BYTES])
            sector[in_sector:in_sector + length] = source[cursor:cursor + length]

            # Model the effective end state of read -> modify -> erase -> rewrite.
            after[sector_start:sector_start + SECTOR_BYTES] = b"\xff" * SECTOR_BYTES
            after[sector_start:sector_start + SECTOR_BYTES] = sector
            touched[sector_start] += 1
            cursor += length

        assert after[base:base + size] == source
        print(f"APPLY {name:<16} physical={base:#08x} bytes={size:#x}")

    updated = {name for name, _, _ in updates}
    unchanged = []
    for name, (base, size) in old_table.items():
        if name not in updated and name in new_table and new_table[name][0] == base:
            if before[base:base + size] != after[base:base + size]:
                raise AssertionError(f"Unexpected change in {name}")
            unchanged.append(name)

    if after[0x40000:0x40004] != b"cr6c" or after[0x400000:0x400004] != b"hsqs":
        raise AssertionError("New Linux or RootFS marker missing")
    if len(after) != FLASH_BYTES:
        raise AssertionError("Image size changed")

    print("PASS: all", len(updates), "Cloud updates applied in declared order")
    print("PASS:", len(unchanged), "same-base legacy partitions unchanged, including fs-uboot and radio")
    print("Touched sectors:", len(touched), "of", FLASH_BYTES // SECTOR_BYTES)
    print("Multiply-updated sectors:",
          [(hex(addr), count) for addr, count in sorted(touched.items()) if count > 1])
    print("Virtual RMW SHA256:", hashlib.sha256(after).hexdigest())
    print("LIMIT: cannot prove driver error handling, actual erase sequencing, or boot compatibility")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("old_flash", type=Path)
    p.add_argument("signed_cloud", type=Path)
    p.add_argument("owner_public_pem", type=Path)
    args = p.parse_args()
    public = serialization.load_pem_public_key(args.owner_public_pem.read_bytes())
    cloud = cloud_decrypt(args.signed_cloud.read_bytes(), public)
    simulate(args.old_flash.read_bytes(), cloud)


if __name__ == "__main__":
    main()
