#!/usr/bin/env python3
"""Replace the RSA-2048 verification trust anchor in an offline test ELF copy.

This makes a single-key TEST library. It is NOT a dual-key upgrader.
"""
import argparse
import base64
import hashlib
import re
import struct
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("vendor_elf", type=Path)
    p.add_argument("owner_public_pem", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()

    blob = args.vendor_elf.read_bytes()
    matches = [m for m in re.finditer(rb"BgIAAA[A-Za-z0-9+/=]{60,}", blob)
               if len(base64.b64decode(m.group())) == 276]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one RSA-2048 key blob, found {len(matches)}")

    key = serialization.load_pem_public_key(args.owner_public_pem.read_bytes())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048:
        raise ValueError("Expected RSA-2048 owner public key")
    numbers = key.public_numbers()
    pubblob = base64.b64decode(matches[0].group())[:16] + struct.pack(
        "<I", numbers.e
    ) + numbers.n.to_bytes(256, "little")
    owner_encoded = base64.b64encode(pubblob)
    current = matches[0]
    if len(owner_encoded) != len(current.group()):
        raise ValueError("RSA blob would change ELF layout")

    patched = blob[:current.start()] + owner_encoded + blob[current.end():]
    args.output.write_bytes(patched)
    args.output.chmod(args.vendor_elf.stat().st_mode & 0o777)
    print("Original ELF SHA256:", hashlib.sha256(blob).hexdigest())
    print("Owner-key ELF SHA256:", hashlib.sha256(patched).hexdigest())
    print("Replaced one 2048-bit public key at ELF offset:", hex(current.start()))
    print("Output:", args.output)

if __name__ == "__main__":
    main()
