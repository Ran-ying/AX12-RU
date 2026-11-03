#!/usr/bin/env python3
"""Read-only audit: pre-SSH AX12 Flash versus historical SSH reconstruction."""
import argparse
import hashlib
import re
from pathlib import Path

FLASH_SIZE = 0x1000000
ROOTFS_BASE = 0x440000
SSH_END = 0xDE6000
NEW_ROOTFS_BASE = 0x400000
NEW_ROOTFS_END = 0xEE4003  # Audited cs6c target payload end
ORIGINAL_SHA256 = "22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1"
RECONSTRUCTED_SHA256 = "c8976dfe2afc9a7d6c98e6d57b6246f74e23bdcaac365c51d29297cf7bcb3957"
PARTITION_RE = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checksum_rootfs(flash):
    """Realtek check_rootfs BE32 length plus 640 bytes and a BE16 checksum."""
    base = ROOTFS_BASE
    if flash[base:base + 4] != b"hsqs":
        raise ValueError("RootFS magic missing")
    length = int.from_bytes(flash[base + 8:base + 12], "big") + 642
    if length & 1 or not (642 < length <= 0xAC8000):
        raise ValueError(f"Invalid Realtek RootFS checksum length: {length:#x}")
    data = flash[base:base + length]
    total = sum(int.from_bytes(data[i:i + 2], "big") for i in range(0, length, 2))
    return length, total & 0xFFFF


def audit(original, reconstructed):
    for label, data, expected in (
        ("Original", original, ORIGINAL_SHA256),
        ("Reconstructed", reconstructed, RECONSTRUCTED_SHA256),
    ):
        if len(data) != FLASH_SIZE or sha256(data) != expected:
            raise ValueError(f"{label} length or SHA-256 differs from recorded snapshot")

    table = original[0xF40000:0xF41000]
    if table[:8] != bytes.fromhex("0000048000000000"):
        raise ValueError("Unexpected original partition-table header")
    partitions = {m[1].decode(): (int(m[2], 16), int(m[3], 16))
                  for m in PARTITION_RE.finditer(table[8:])}
    if len(partitions) != 24 or partitions["fs-uboot"] != (0, 0x40000) or \
            partitions["file-system"][0] != ROOTFS_BASE or \
            partitions["radio"] != (0xFF0000, 0x10000):
        raise ValueError("Unexpected old partition mapping")

    if original[:ROOTFS_BASE] != reconstructed[:ROOTFS_BASE] or \
            original[SSH_END:] != reconstructed[SSH_END:]:
        raise ValueError("Bytes outside SSH write interval changed")
    if original[ROOTFS_BASE:SSH_END] == reconstructed[ROOTFS_BASE:SSH_END]:
        raise ValueError("RootFS did not change")

    for label, image in (("Original", original), ("Reconstructed", reconstructed)):
        length, total = checksum_rootfs(image)
        print(f"{label}: Realtek check {length:#x} bytes, sum {total:#06x}")
        if total:
            raise ValueError(f"{label} RootFS checksum mismatch")

    if not (NEW_ROOTFS_BASE <= ROOTFS_BASE and SSH_END <= NEW_ROOTFS_END):
        raise ValueError("Target file-system does not fully overwrite SSH patch")

    changed = sum(a != b for a, b in zip(original[ROOTFS_BASE:SSH_END],
                                          reconstructed[ROOTFS_BASE:SSH_END]))
    print(f"PASS: {changed:,} changed bytes, all within {ROOTFS_BASE:#x}..{SSH_END:#x}")
    print(f"PASS: cs6c target RootFS covers {NEW_ROOTFS_BASE:#x}..{NEW_ROOTFS_END:#x}")
    print("MODEL: both baselines converge if the complete target RootFS payload is written.")
    print("LIMIT: no real -u execution, boot, or recovery test.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("reconstructed", type=Path)
    args = parser.parse_args()
    audit(args.original.read_bytes(), args.reconstructed.read_bytes())


if __name__ == "__main__":
    main()
