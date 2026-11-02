#!/usr/bin/env python3
"""Seal a 4 KiB-aligned AX12 SquashFS for the official Cloud file-system entry.

Matches the length/checksum/trailing-pad pattern in RU 1.1.22 and RU 1.5.0.
This only creates an offline partition payload, not a signed upgrade.
"""
import argparse
import hashlib
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("squashfs", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--partition-size", type=lambda s: int(s, 0), default=0xB08000)
args = parser.parse_args()

data = bytearray(args.squashfs.read_bytes())
filesystem_size = struct.unpack_from("<Q", data, 40)[0]
if data[:4] != b"hsqs" or len(data) % 4096 or filesystem_size > len(data):
    raise ValueError("Expected a valid padded, 4 KiB-aligned SquashFS")
if len(data) + 3 > args.partition_size:
    raise ValueError("Sealed image would exceed Flash file-system partition")

data[8:12] = (len(data) - 640).to_bytes(4, "big")
checksum = -sum(int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)) & 65535
data.extend(checksum.to_bytes(2, "big") + bytes(1))
assert len(data) - int.from_bytes(data[8:12], "big") == 643
assert sum(int.from_bytes(data[i:i + 2], "big")
           for i in range(0, len(data) - 1, 2)) & 65535 == 0
args.output.write_bytes(data)
print("Sealed partition payload:", args.output)
print("Length:", hex(len(data)))
print("Flash headroom:", args.partition_size - len(data))
print("SHA256:", hashlib.sha256(data).hexdigest())
