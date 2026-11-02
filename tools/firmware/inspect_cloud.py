#!/usr/bin/env python3
"""Read-only inspection of TP-Link Cloud firmware containers."""

import argparse
import hashlib
import math
import re
from collections import Counter
from pathlib import Path


def entropy(data):
    counts = Counter(data)
    return -sum((n / len(data)) * math.log2(n / len(data)) for n in counts.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()

    blob = args.firmware.read_bytes()
    size = int.from_bytes(blob[:4], "big")
    print(f"File: {args.firmware.name}")
    print(f"Size: {len(blob)} (header: {size}, matches: {size == len(blob)})")
    print(f"SHA256: {hashlib.sha256(blob).hexdigest()}")
    print(f"Type: {blob[0x14:0x14 + 13].decode('ascii', 'replace')!r}")
    print(f"Unknown header field at 0x110: 0x{int.from_bytes(blob[0x110:0x114], 'big'):08x}")
    for start, end in ((0x14, 0x110), (0x1C0, 0x1014), (0x1014, 0x1814)):
        chunk = blob[start:end]
        print(f"Section {start:#x}..{end:#x}: entropy {entropy(chunk):.3f} bits/byte")

    for offset, length, label in ((0x1014, 0x800, "fwup manifest"),
                                  (0x1818, 0x7FC, "flash partition table")):
        raw = blob[offset:offset + length]
        if not raw.startswith(b"fwup-ptn ") and not raw.startswith(b"partition "):
            print(f"{label}: no plaintext structure at {offset:#x}")
            continue
        print(f"{label}:")
        content = raw.split(b"\0", 1)[0].decode("ascii", "replace")
        for line in content.splitlines():
            if re.match(r"^(fwup-ptn|partition) ", line):
                print(" ", line.strip())


if __name__ == "__main__":
    main()
