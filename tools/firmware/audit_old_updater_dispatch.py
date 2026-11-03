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
    0x402628: (0x00A03025, "move payload pointer to ioctl buffer argument"),
    0x40262C: (0x00402825, "move requested length to ioctl length argument"),
    0x402638: (0x00C01025, "special wrapper starts with source length"),
    0x40263C: (0x24070001, "special Flash ioctl argument a3=1"),
    0x402630: (0x081008DB, "mode-0 wrapper reaches same ioctl"),
    0x402648: (0x081008DB, "mode-1 wrapper reaches same ioctl"),
    0x402380: (0xAFA40018, "store Flash destination at ioctl offset 0"),
    0x402388: (0xAFA5001C, "store length at ioctl offset 4"),
    0x402398: (0xAFA60020, "store data pointer at ioctl offset 8"),
    0x4023A0: (0xAFA70028, "store mode at ioctl offset 16"),
    0x4023D0: (0x3C058001, "Flash ioctl request high bits"),
    0x4023D8: (0x34A5B302, "Flash ioctl request 0x8001b302"),
}

# 1.1.22 running kernel's tp_flash_ioctl and the common Flash handler.
KERNEL_INSTRUCTIONS = {
    0x801E1F98: (0x8E42000C, "load payload length into fifth argument"),
    0x801E1F9C: (0x8E470008, "load payload pointer into a3"),
    0x801E1FA0: (0x8E450010, "load mode into a1"),
    0x801E1FA4: (0x8E460000, "load Flash destination into a2"),
    0x801E1FA8: (0x0C07863E, "call common Flash handler"),
    0x801E1928: (0x8FB40080, "handler reads payload length"),
    0x801E1930: (0xAFA00024, "clear second header word"),
    0x801E1934: (0x7C1410A0, "swap bytes within 16-bit halves of length"),
    0x801E1938: (0x00221402, "rotate swapped length by 16 bits"),
    0x801E1940: (0xAFA20020, "store big-endian payload length in header"),
    0x801E193C: (0x10A0009C, "mode 0 branches to ordinary path"),
    0x801E1944: (0x26940008, "mode 1 includes eight extra bytes"),
    0x801E196C: (0x24080008, "explicit eight-byte header count"),
    0x801E1C20: (0x02432021, "header destination is sector buffer + in-sector offset"),
    0x801E1C2C: (0x27A50020, "source is the two-word stack header"),
    0x801E1C30: (0x01003025, "copy exactly eight header bytes"),
    0x801E1C34: (0x0C059340, "copy header to sector buffer"),
    0x801E1C54: (0x02883023, "remaining length excludes header"),
    0x801E1C74: (0x0C059341, "copy raw payload after header"),
    0x801E1C8C: (0x0C059340, "preserve untouched suffix from old sector"),
    0x801E1BB0: (0x02861021, "ordinary path uses unextended length"),
    0x801E19AC: (0x0C077DFE, "Flash driver reads existing sector"),
    0x801E1D28: (0x0C078366, "Flash driver calls sector erase helper"),
    0x801E1D50: (0x0C0781AD, "Flash driver calls SPI NOR writer"),
}

def entries(blob, pattern):
    return [(m[1].decode(), int(m[2], 16), int(m[3], 16))
            for m in pattern.finditer(blob)]

def audit(updater, cloud, kernel):
    elf = updater.read_bytes()
    for addr, (expected, meaning) in INSTRUCTIONS.items():
        actual = struct.unpack_from("<I", elf, addr - 0x400000)[0]
        if actual != expected:
            raise ValueError(f"{addr:#x}: expected {expected:08x}, got {actual:08x}")
        print(f"PASS MIPS {addr:#010x}: {meaning}")

    if kernel is not None:
        code = kernel.read_bytes()
        for addr, (expected, meaning) in KERNEL_INSTRUCTIONS.items():
            actual = struct.unpack_from("<I", code, addr - 0x80000000)[0]
            if actual != expected:
                raise ValueError(f"{addr:#x}: expected {expected:08x}, got {actual:08x}")
            print(f"PASS KERNEL {addr:#010x}: {meaning}")

    raw = cloud.read_bytes()
    updates = entries(raw[START:0x1814], ENTRY)
    partitions = {name: (base, count) for name, base, count
                  in entries(raw[0x1818:0x2014], PART)}
    if not updates or any(n == "fs-uboot" for n, _, _ in updates):
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
    print("PASS: partition-table uses ioctl mode 1 (length + 8); nine ordinary updates use mode 0")
    print("NOT PROVEN: actual mode-1 header bytes; complete -u acceptance,")
    print("     physical writes, power-loss recovery, or boot success")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_1122_updater", type=Path)
    p.add_argument("decrypted_cs6c_cloud", type=Path)
    p.add_argument("--old-kernel", type=Path, help="1.1.22 decompressed Linux binary for ioctl audit")
    args = p.parse_args()
    audit(args.stock_1122_updater, args.decrypted_cs6c_cloud, args.old_kernel)

if __name__ == "__main__":
    main()
