#!/usr/bin/env python3
"""Simulate an AX12 1.1.22 -> owner-signed 1.5.0 NOR migration in a file.

NO device access, MTD writes, flash utilities, or bootloader execution.
This model uses the target manifest's physical partitions; it does NOT emulate
the proprietary nvrammanager updater's actual write order or flash ioctl code.
"""
import argparse
import hashlib
import re
import struct
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from self_sign_lab import cloud_decrypt

FLASH_SIZE = 0x1000000
MANIFEST_OFFSET = 0x1014
PTABLE_OFFSET = 0xF40000
ENTRY = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
PARTITION = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def partitions(table):
    return {
        m[1].decode(): (int(m[2], 16), int(m[3], 16))
        for m in PARTITION.finditer(table)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_flash", type=Path)
    parser.add_argument("signed_cloud", type=Path)
    parser.add_argument("owner_public_pem", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    before = args.original_flash.read_bytes()
    if len(before) != FLASH_SIZE:
        raise ValueError("Expected an exact 16 MiB original SPI NOR backup")

    old_table = partitions(before[PTABLE_OFFSET + 4:PTABLE_OFFSET + 0x800])
    if old_table["file-system"][0] != 0x440000:
        raise ValueError("This backup is not the expected AX12 RU 1.1.22 layout")

    public = serialization.load_pem_public_key(args.owner_public_pem.read_bytes())
    cloud = cloud_decrypt(args.signed_cloud.read_bytes(), public)
    new_table = partitions(cloud[0x1818:0x2014])
    if new_table["file-system"] != (0x400000, 0xB08000):
        raise ValueError("Unexpected target firmware partition layout")

    data = bytearray(before)
    changes = []
    for m in ENTRY.finditer(cloud[MANIFEST_OFFSET:0x1814]):
        name = m[1].decode()
        if name == "fs-uboot":
            continue  # Our *hypothetical* preserve-old-bootloader variant
        if name not in new_table:
            raise ValueError(f"Unmapped firmware payload: {name}")
        relative, size = int(m[2], 16), int(m[3], 16)
        flash_offset, capacity = new_table[name]
        source = cloud[MANIFEST_OFFSET + relative:MANIFEST_OFFSET + relative + size]
        if len(source) != size or size > capacity:
            raise ValueError(f"Invalid source or partition size for {name}")
        data[flash_offset:flash_offset + capacity] = bytes([0xFF]) * capacity
        data[flash_offset:flash_offset + size] = source
        changes.append((name, flash_offset, capacity))

    preserved = ["fs-uboot", "user-config", "ap-config", "router-config",
                 "product-info", "default-mac", "pin", "device-id", "radio"]
    for name in preserved:
        offset, size = old_table[name]
        if data[offset:offset + size] != before[offset:offset + size]:
            raise AssertionError(f"Preserved device partition changed: {name}")
    if data[0x40000:0x40004] != b"cr6c":
        raise AssertionError("Kernel marker is not at the target Flash offset")
    if data[0x400000:0x400004] != b"hsqs":
        raise AssertionError("RootFS marker is not at the target Flash offset")
    if partitions(data[PTABLE_OFFSET + 4:PTABLE_OFFSET + 0x800]) != new_table:
        raise AssertionError("Target partition table does not match new Cloud")

    args.output.write_bytes(data)
    print(f"PASS: {len(changes)} target partitions modeled, old bootloader preserved")
    print("New kernel header at 0x40000 and RootFS magic at 0x400000: PASS")
    print("User config, product identity, MAC and radio calibration retained: PASS")
    print("Virtual image size:", len(data))
    print("Virtual image SHA256:", hashlib.sha256(data).hexdigest())
    print("NOT VERIFIED: bootloader runtime compatibility, actual nvrammanager "
          "write ordering or recovery. NEVER flash this virtual image wholesale.")


if __name__ == "__main__":
    main()
