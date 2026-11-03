#!/usr/bin/env python3
"""Create an *unsigned plaintext* cs6c boot-bridge experiment for AX12 RU.

The old Bootloader recognizes cs6c without the separate rootfs-address probe.
This tests only format and integrity; the old updater and boot path are unproven.
Never flash or upload the output directly to the router.
"""
import argparse
import hashlib
import re
import struct
from pathlib import Path

KERNEL_ENTRY = re.compile(rb"fwup-ptn os-image base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decrypted_owner_cloud", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    original = args.decrypted_owner_cloud.read_bytes()
    match = KERNEL_ENTRY.search(original[0x1014:0x1814])
    offset = 0x1014 + int(match[1], 16)
    size = int(match[2], 16)
    image = original[offset:offset + size]
    magic, load, burn, length = struct.unpack_from(">4sIII", image)
    if magic != b"cr6c" or size != length + 17:
        raise ValueError("Unexpected source kernel format")

    body = image[16:16 + length]
    checksum = sum(int.from_bytes(body[i:i + 2], "big")
                   for i in range(0, len(body), 2)) & 0xFFFF
    if checksum:
        raise ValueError("Source kernel checksum failed")

    modified = bytearray(original)
    modified[offset:offset + 4] = b"cs6c"
    changes = [i for i, (a, b) in enumerate(zip(original, modified)) if a != b]
    if changes != [offset + 1]:
        raise AssertionError(f"Unexpected changes: {changes}")

    args.output.write_bytes(modified)
    print("Kernel magic:", original[offset:offset + 4], "->", modified[offset:offset + 4])
    print(f"Kernel load={load:#x}, burn={burn:#x}, body={length:#x}, checksum=PASS")
    print("Changed bytes:", len(changes), "at Cloud plaintext", hex(changes[0]))
    print("Plaintext SHA-256:", hashlib.sha256(modified).hexdigest())
    print("UNSIGNED EXPERIMENT ONLY: owner RSA signature and encrypted Cloud must be regenerated")
    print("NOT PROVEN: 1.1.22 nvrammanager -u accepts cs6c or Bootloader actually runs it")


if __name__ == "__main__":
    main()
