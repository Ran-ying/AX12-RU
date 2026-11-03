#!/usr/bin/env python3
"""File-only model of AX12 RU 1.1.22 updater Flash writes.

Emulates the observed 64-KiB read/modify/erase/write result for ioctl mode 0
(raw payload) and ioctl mode 1 (BE32 length, zero word, then payload).
Without --old-flash this uses synthetic Flash patterns, not a router dump.
No networking, device access, signing, firmware output, or flashing.
"""
import argparse
import hashlib
import re
import struct
from collections import Counter
from pathlib import Path

FLASH_SIZE = 0x1000000
SECTOR_SIZE = 0x10000
UPDATE_RE = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
PART_RE = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def records(data, rx):
    return [(m[1].decode(), int(m[2], 16), int(m[3], 16))
            for m in rx.finditer(data)]


def load_layout(old_cloud, new_cloud):
    old = dict((n, (a, s)) for n, a, s in
               records(old_cloud[0x1818:0x2014], PART_RE))
    new = dict((n, (a, s)) for n, a, s in
               records(new_cloud[0x1818:0x2014], PART_RE))
    updates = records(new_cloud[0x1014:0x1814], UPDATE_RE)
    if len(old) != 24 or len(new) != 28 or len(updates) != 10:
        raise ValueError("Unexpected source/target partition counts")
    if old["fs-uboot"] != new["fs-uboot"] or "fs-uboot" in {n for n, _, _ in updates}:
        raise ValueError("Bootloader must remain untouched")
    if any(old[n][0] != a for n, (a, _) in new.items()
           if n in old and n not in {v[0] for v in updates}):
        raise ValueError("Relocation mode 2 is not supported by this model")
    if {n for n, _, _ in updates} != {
        "os-image", "file-system", "re-def-config", "partition-table",
        "soft-version", "extra-para", "support-list", "profile",
        "default-config", "ap-def-config"
    }:
        raise ValueError("Unexpected update selection")
    if [n for n, _, _ in updates] != [n for n in new if n in {u[0] for u in updates}]:
        raise ValueError("Manifest order differs from the updater's partition iteration")
    if old["file-system"][0] != 0x440000 or new["file-system"][0] != 0x400000:
        raise ValueError("Unexpected old or new RootFS address")
    if new["os-image"][0] != 0x40000 or new["partition-table"][0] != 0xF40000:
        raise ValueError("Unexpected kernel or partition-table address")
    return old, new, updates


def operations(new_cloud, new, updates):
    result = [("upgrade-flag-before", 0xF42000,
               struct.pack(">II", 2, 0) + b"\x01\x00")]
    for name, source_offset, length in updates:
        start, capacity = new[name]
        payload = new_cloud[0x1014 + source_offset:0x1014 + source_offset + length]
        if len(payload) != length:
            raise ValueError(f"Truncated payload: {name}")
        if name == "partition-table":
            # Actual 1.1.22 -u ioctl trace: 28 records x 48 bytes = 0x540.
            table = payload[:0x540]
            if len(records(table[4:], PART_RE)) != 28:
                raise ValueError("Unexpected target partition-table entries")
            write = struct.pack(">II", len(table), 0) + table
        else:
            write = payload
        if start + capacity > FLASH_SIZE or len(write) > capacity:
            raise ValueError(f"Write exceeds partition: {name}")
        result.append((name, start, write))
    if result[1][2][:4] != b"cs6c" or result[2][2][:4] != b"hsqs":
        raise ValueError("Not a cs6c bridge with SquashFS root")
    for name in ("wireless-key", "https_cert", "uboot_env", "login-key"):
        base, capacity = new[name]
        result.append((name, base, bytes(capacity)))
    result.append(("upgrade-flag-after", 0xF42000,
                   struct.pack(">II", 2, 0) + b"\x01\x01"))
    return result


def emulate(initial, ops, old, new):
    image = bytearray(initial)
    touched = Counter()
    for name, address, payload in ops:
        off = 0
        while off < len(payload):
            absolute = address + off
            sector = absolute & ~(SECTOR_SIZE - 1)
            inside = absolute - sector
            count = min(SECTOR_SIZE - inside, len(payload) - off)
            old_sector = image[sector:sector + SECTOR_SIZE]
            new_sector = old_sector[:]
            new_sector[inside:inside + count] = payload[off:off + count]
            image[sector:sector + SECTOR_SIZE] = new_sector
            touched[sector] += 1
            off += count

    changed = {name for name, _, _ in ops}
    same_base = [n for n, (base, size) in old.items()
                 if n not in changed and n in new and new[n][0] == base]
    for name in same_base:
        base, length = old[name]
        if image[base:base + length] != initial[base:base + length]:
            raise AssertionError(f"Unexpected modification: {name}")

    assert image[0xF40000:0xF40008] == struct.pack(">II", 0x540, 0)
    assert image[0xF40008:0xF4000C] == b"\x00\x04\x00\x00"
    assert image[:0x40000] == initial[:0x40000]
    assert image[0x040000:0x040004] == b"cs6c"
    assert image[0x400000:0x400004] == b"hsqs"
    assert image[0xF42000:0xF4200A] == struct.pack(">II", 2, 0) + b"\x01\x01"
    assert image[0xFF0000:] == initial[0xFF0000:]
    n_written = sum(touched.values())
    shared = {hex(s): n for s, n in sorted(touched.items()) if n > 1}
    if shared != {"0xf40000": 7, "0xfe0000": 4}:
        raise AssertionError(f"Unexpected repeated sector rewrites: {shared}")
    if (len(ops), len(touched), n_written) != (16, 238, 247):
        raise AssertionError("Model differs from observed 1.1.22 -u ioctl count")
    print("PASS:", len(ops), "logical phases,", len(touched),
          "different sectors,", n_written, "modeled Flash ioctl writes")
    print("PASS: partition-table Flash prefix =",
          image[0xF40000:0xF4000C].hex(" "))
    print("PASS:", len(same_base),
          "same-base preexisting partitions unchanged (including Bootloader and ART)")
    print("Multi-write sectors:", shared)
    digest = hashlib.sha256(image).hexdigest()
    print("In-memory image SHA256:", digest)
    return digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("official_1122_cloud", type=Path)
    p.add_argument("decrypted_cs6c_cloud", type=Path)
    p.add_argument("--old-flash", type=Path, help="Optional exact 16 MiB pre-upgrade dump")
    p.add_argument("--compare-flash", type=Path, help="Optional second 16 MiB baseline")
    args = p.parse_args()
    old_cloud = args.official_1122_cloud.read_bytes()
    bridge_cloud = args.decrypted_cs6c_cloud.read_bytes()
    old, new, updates = load_layout(old_cloud, bridge_cloud)
    ops = operations(bridge_cloud, new, updates)
    if args.old_flash:
        baseline = args.old_flash.read_bytes()
        if len(baseline) != FLASH_SIZE:
            raise ValueError("Flash baseline must be exactly 16 MiB")
        print("Mode: supplied Flash backup")
        first_digest = emulate(baseline, ops, old, new)
        if args.compare_flash:
            other = args.compare_flash.read_bytes()
            if len(other) != FLASH_SIZE:
                raise ValueError("Comparison baseline must be exactly 16 MiB")
            covered = bytearray(other)
            for name, start, payload in ops:
                covered[start:start + len(payload)] = baseline[start:start + len(payload)]
            if covered != baseline:
                raise ValueError("Baselines differ outside complete target payload ranges")
            print("\nMode: second supplied Flash baseline")
            second_digest = emulate(other, ops, old, new)
            if first_digest != second_digest:
                raise AssertionError("Modeled upgrade outputs differ")
            print("PASS: both baselines produce the same modeled post-upgrade image SHA256")
    else:
        if args.compare_flash:
            raise ValueError("--compare-flash requires --old-flash")
        print("Mode: SYNTHETIC; no genuine pre-upgrade Flash backup available")
        for label, baseline in [("all-FF", bytes([0xFF]) * FLASH_SIZE),
                                ("byte-ramp", bytes(range(256)) * (FLASH_SIZE // 256))]:
            print("\nBaseline:", label)
            emulate(baseline, ops, old, new)
    print("\nMODEL: operation order and counts are grounded in an actual 1.1.22 QEMU -u")
    print("trace with a test-key-signed cs6c package and intercepted virtual Flash.")
    print("LIMIT: mode-1 and SPI NOR sector behavior are separately modeled from")
    print("kernel disassembly, not executed as the original vendor kernel driver.")
    print("No hardware write, boot success or recovery test is implied.")


if __name__ == "__main__":
    main()
