#!/usr/bin/env python3
"""Offline seal of a 4KiB-aligned AX12 Realtek SquashFS image.

Adds the vendor-specific length field and trailing 16-bit checksum.
No device operations are performed.
"""
import hashlib
import struct
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit('Usage: python3 ax12_seal_realtek_rootfs.py IMAGE.sqfs OUTPUT.bin')

src, dst = map(Path, sys.argv[1:])
data = bytearray(src.read_bytes())
size = struct.unpack_from('<Q', data, 40)[0]
if data[:4] != b'hsqs' or len(data) % 4096 or size > len(data):
    raise ValueError('Expected padded, 4KiB-aligned SquashFS image')
if len(data) + 2 > 0xAC8000:
    raise ValueError('Image exceeds AX12 file-system partition')
if len(data) + 2 - 640 > 0xffffffff:
    raise ValueError('Vendor length field overflow')
data[8:12] = (len(data) - 640).to_bytes(4,'big')
checksum = (-sum(int.from_bytes(data[i:i+2],'big') for i in range(0,len(data),2))) & 0xffff
data.extend(checksum.to_bytes(2,'big'))
assert sum(int.from_bytes(data[i:i+2],'big') for i in range(0,len(data),2)) & 0xffff == 0
assert int.from_bytes(data[8:12],'big') + 642 == len(data)
dst.write_bytes(data)
print('Output:',dst,'size:',len(data),'SHA256:',hashlib.sha256(data).hexdigest())
