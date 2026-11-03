#!/usr/bin/env python3
"""Verify the cs6c boot path in the known AX12 RU 1.1.22 Bootloader.

Static regression check against the original fs-uboot dump. This reads a
local file only: it cannot test Linux boot, upgrade acceptance or Flash writes.
"""
import argparse
import struct
import zlib
from pathlib import Path

# Exact MIPS little-endian instructions from the verified 1.1.22 stage 2.
# The listed addresses map to offsets address - 0x80000000 in the image.
EXPECTED = {
    0x80017A5C: (0x24030001, "cs6c classified as type 1"),
    0x80017A64: (0xAFA30128, "type 1 saved"),
    0x80017A78: (0x24030002, "cr6c classified as type 2"),
    0x80017A80: (0xAFA30128, "type 2 saved"),
    0x80017B94: (0x8FA20128, "validated image type returned"),
    0x80017C84: (0x24030002, "compare against type 2"),
    0x80017C88: (0x14430016, "non-type-2 branches past rootfs checks"),
    0x80017C90: (0x0C005DB5, "type 2 rootfs validation call"),
    0x80017D04: (0x0C005DB5, "old fixed rootfs validation call"),
    0x80017D08: (0x3C04B044, "old rootfs address is 0x440000"),
    0x80017D78: (0x0C005EF2, "boot path calls image validator"),
    0x80017D80: (0x10400007, "zero return enters failure path"),
    0x80017D90: (0x0C005CED, "successful path calls image loader"),
    0x80017490: (0x0C0048E0, "loader copies image data to RAM"),
    0x80017528: (0x0200C821, "loader moves target address into t9"),
    0x8001752C: (0x0320F809, "loader jumps through t9"),
}


def second_stage(bootloader):
    pos = bootloader.index(b"\x1f\x8b\x08")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    image = decoder.decompress(bootloader[pos:]) + decoder.flush()
    if not decoder.eof:
        raise ValueError("Incomplete Bootloader stage 2")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_1122_uboot", type=Path)
    args = parser.parse_args()

    code = second_stage(args.original_1122_uboot.read_bytes())
    for address, magic in ((0x80029438, b"cs6c"), (0x80029450, b"cr6c")):
        if code[address - 0x80000000:address - 0x80000000 + 4] != magic:
            raise ValueError(f"Unexpected magic at {address:#x}")

    for address, (expected, description) in EXPECTED.items():
        actual = struct.unpack_from("<I", code, address - 0x80000000)[0]
        if actual != expected:
            raise ValueError(
                f"{address:#010x}: expected {expected:08x}, got {actual:08x}"
            )
        print(f"PASS {address:#010x} {description}")

    print(f"PASS: 1.1.22 stage 2 ({len(code):,} bytes) has the cs6c bypass "
          "and the common kernel copy/jump path")
    print("NOT PROVEN: old upgrader -u accepts cs6c, full kernel boot, "
          "new RootFS mount or safe Flash recovery")


if __name__ == "__main__":
    main()
