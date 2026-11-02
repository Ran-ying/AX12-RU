#!/usr/bin/env python3
"""List RSA public-key blob metadata inside an AX12 ELF without printing keys."""

import argparse
import base64
import hashlib
import re
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("binary", type=Path)
args = parser.parse_args()

for match in re.finditer(rb"BgIAAA[A-Za-z0-9+/=]{60,}", args.binary.read_bytes()):
    blob = base64.b64decode(match.group())
    if blob[8:12] != b"RSA1":
        continue
    bits, exponent = struct.unpack_from("<II", blob, 12)
    print(f"RSA-{bits}, exponent={exponent}, public-blob SHA256={hashlib.sha256(blob).hexdigest()}")
