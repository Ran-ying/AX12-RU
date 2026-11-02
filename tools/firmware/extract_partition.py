#!/usr/bin/env python3
"""Extract a named partition from a readable TP-Link Cloud firmware container."""

import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("firmware", type=Path, help="Plaintext Cloud container, e.g. decrypted .bin.dec")
parser.add_argument("partition", help="e.g. file-system, os-image, partition-table")
parser.add_argument("output", type=Path)
args = parser.parse_args()

data = args.firmware.read_bytes()
manifest = data[0x1014:0x1814].split(b"\0", 1)[0]
entries = {
    name.decode(): (int(offset, 16), int(size, 16))
    for name, offset, size in re.findall(
        rb"fwup-ptn ([\w-]+) base 0x([a-f0-9]+) size 0x([a-f0-9]+)", manifest
    )
}
offset, size = entries[args.partition]
start = 0x1014 + offset
end = start + size
if end > len(data):
    raise ValueError(f"Partition {args.partition} extends beyond firmware size")
args.output.write_bytes(data[start:end])
print(f"{args.partition}: offset={start:#x}, size={size:#x}, output={args.output}")
