#!/usr/bin/env python3
"""Read-only AX12 RU 1.1.22 updater dispatch audit for a decrypted cs6c Cloud.

Checks the actual old MIPS write-dispatch instructions and the target Cloud
partition mapping. No device open, firmware signing, or Flash-image output.
"""
import argparse
import re
import struct
from pathlib import Path

ENTRY = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
PART = re.compile(rb"partition ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")
START = 0x1014
FLASH_BYTES = 0x1000000
# These instruction words are from the stock 1.1.22 MIPS little-endian ELF.
INSTRUCTIONS = {
    0x4031A0: (0x04400005, "reject invalid update mode"),
    0x4031B0: (0x10430018, "mode 3 skips write"),
    0x403388: (0x8FA5002C, "load partition-table name pointer"),
    0x403390: (0x0C1066E8, "compare 16-byte partition name"),
    0x4033A8: (0x0C101102, "partition-table special write wrapper"),
    0x4033C0: (0x0C1010F5, "ordinary write wrapper"),
    0x4043E0: (0x0C100988, "ordinary wrapper calls mode-0 writer"),
    0x404414: (0x0C10098E, "special wrapper calls mode-1 writer"),
    0x402624: (0x00003825, "ordinary Flash ioctl argument a3=0"),
    0x40263C: (0x24070001, "special Flash ioctl argument a3=1"),
    0x402630: (0x081008DB, "mode-0 wrapper reaches same ioctl"),
    0x402648: (0x081008DB, "mode-1 wrapper reaches same ioctl"),
    0x4023D0: (0x3C058001, "Flash ioctl request high bits"),
    0x4023D8: (0x34A5B302, "Flash ioctl request 0x8001b302"),
}

def entries(blob, pattern):
    return [(m[1].decode(), int(m[2], 16), int(m[3], 16))
            for m in pattern.finditer(blob)]

def audit(updater, cloud):
    elf = updater.read_bytes()
    for addr, (expected, meaning) in INSTRUCTIONS.items():
        actual = struct.unpack_from("<I", elf, addr - 0x400000)[0]
        if actual != expected:
            raise ValueError(f"{addr:#x}: expected {expected:08x}, got {actual:08x}")
        print(f"PASS MIPS {addr:#010x}: {meaning}")

    raw = cloud.read_bytes()
    updates = entries(raw[START:0x1814], ENTRY)
    partitions = {name: (base, count) for name, base, count
                  in entries(raw[0x1818:0x2014], PART)}
    if not updates or "fs-uboot" in dict((n, True) for n, _, _ in updates):
        raise ValueError("Expected a nonempty no-uboot update manifest")
    if len(partitions) != 28 or len(updates) != 10:
        raise ValueError("Unexpected target partition record count")

    sectors = {}
    print("\nTarget operations (manifest order; flags inferred from old writer):")
    for name, offset, size in updates:
        flash_base, capacity = partitions[name]
        if flash_base + capacity > FLASH_BYTES or size > capacity:
            raise ValueError(f"Invalid target partition: {name}")
        source = raw[START + offset:START + offset + size]
        if len(source) != size:
            raise ValueError(f"Truncated Cloud payload: {name}")
        flag = int(name == "partition-table")
        for sector in range(flash_base // 0x10000, (flash_base + size - 1) // 0x10000 + 1):
            sectors.setdefault(sector, []).append(name)
        print(f"{name:18} Flash={flash_base:#08x} size={size:#08x} ioctl_mode={flag}")

    kernel_base, _ = partitions["os-image"]
    kernel = raw[START + next(base for n, base, _ in updates if n == "os-image"):]
    if kernel[:4] != b"cs6c" or kernel_base != 0x40000:
        raise ValueError("Candidate is not a cs6c bridge at 0x40000")
    if partitions["file-system"][0] != 0x400000:
        raise ValueError("Unexpected target RootFS base")
    shared = {hex(s * 0x10000): names for s, names in sectors.items() if len(names) > 1}
    if set(shared) != {"0xf40000"}:
        raise ValueError(f"Unexpected multiply-updated sectors: {shared}")
    print(f"\nPASS: {len(updates)} operations, no fs-uboot update, cs6c at 0x40000")
    print("PASS: only sector 0xF40000 has multiple metadata updates")
    print("PASS: partition-table uses ioctl mode 1; nine ordinary updates use mode 0")
    print("NOT PROVEN: what mode 1 does in the kernel; complete -u acceptance,")
    print("     physical writes, power-loss recovery, or boot success")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_1122_updater", type=Path)
    p.add_argument("decrypted_cs6c_cloud", type=Path)
    args = p.parse_args()
    audit(args.stock_1122_updater, args.decrypted_cs6c_cloud)

if __name__ == "__main__":
    main()
