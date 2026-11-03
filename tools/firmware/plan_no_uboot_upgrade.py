#!/usr/bin/env python3
"""Static AX12 RU upgrade-plan check. Never accesses or writes real Flash.

Mode labels inferred from the 1.1.22 nvrammanager MIPS disassembly:
  1: firmware payload, 2: relocate data from old Flash,
  3: same-base existing data (writer skips), 0: new unused partition.
This is NOT a substitute for tracing the full proprietary updater.
"""
import argparse
import re
from pathlib import Path

PREFIX = 0x1014
UPDATE = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
PARTITION = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def entries(data, pattern):
    return {m[1].decode(): (int(m[2], 16), int(m[3], 16))
            for m in pattern.finditer(data)}


def plan(old, new):
    before = entries(old[0x1818:0x2014], PARTITION)
    after = entries(new[0x1818:0x2014], PARTITION)
    updates = entries(new[PREFIX:0x1814], UPDATE)
    if len(after) > 28:
        raise ValueError("Target layout exceeds the 1.1.22 28-partition limit")
    if "fs-uboot" in updates:
        raise ValueError("Image still requests an explicit bootloader update")
    if before["fs-uboot"] != after["fs-uboot"]:
        raise ValueError("Bootloader Flash partition changed")

    print("Partition".ljust(18), "Mode", "Destination", "Capacity", "Source")
    modes = {}
    for name, (base, capacity) in after.items():
        if name in updates:
            src, size = updates[name]
            if size > capacity or PREFIX + src + size > len(new):
                raise ValueError(f"Invalid Cloud payload for {name}")
            mode, source = 1, "Cloud image"
        elif name in before and before[name][0] == base:
            mode, source = 3, "Existing Flash (skip write)"
        elif name in before:
            mode, source = 2, "Existing Flash (relocate)"
        else:
            mode, source = 0, "New, no update payload"
        modes[name] = mode
        print(f"{name:18} {mode:4} {base:#010x} {capacity:#010x} {source}")

    if modes["fs-uboot"] != 3:
        raise AssertionError("Bootloader not classified as same-base skip")
    relocated = [name for name, mode in modes.items() if mode == 2]
    print("\nPASS: fs-uboot classified as mode 3 (same-base skip)")
    print("Mode 1 explicit Cloud updates:", sum(v == 1 for v in modes.values()))
    print("Mode 2 legacy-data relocations:", len(relocated), relocated)
    print("Mode 3 same-base skips:", sum(v == 3 for v in modes.values()))
    print("Mode 0 new unpopulated:", sum(v == 0 for v in modes.values()))
    print("CAUTION: inferred modes; no live -u, MTD write trace, or boot test performed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_cloud_plaintext", type=Path)
    parser.add_argument("new_cloud_plaintext", type=Path)
    args = parser.parse_args()
    plan(args.old_cloud_plaintext.read_bytes(), args.new_cloud_plaintext.read_bytes())


if __name__ == "__main__":
    main()
