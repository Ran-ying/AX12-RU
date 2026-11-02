#!/usr/bin/env python3
"""Finish a prepared owner-signed Cloud test package using a signature from the owner computer."""
import argparse
import hashlib
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from self_sign_lab import cloud_decrypt, verify

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("unsigned_container", type=Path)
p.add_argument("rsa_signature_big_endian", type=Path)
p.add_argument("owner_public_pem", type=Path)
p.add_argument("sealed_rootfs", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()

data = bytearray(args.unsigned_container.read_bytes())
signature = args.rsa_signature_big_endian.read_bytes()
if len(signature) != 256:
    raise ValueError("Expected 256-byte RSA-2048 signature")
data[0x130:0x230] = signature[::-1]
public = serialization.load_pem_public_key(args.owner_public_pem.read_bytes())
verify(data, public)
decrypted = cloud_decrypt(data, public)
rootfs = args.sealed_rootfs.read_bytes()
manifest = decrypted[0x1014:0x1814]
match = re.search(rb"fwup-ptn file-system base 0x([0-9a-f]+) size 0x([0-9a-f]+)", manifest)
if match is None:
    raise ValueError("Missing file-system manifest entry")
start = 0x1014 + int(match[1], 16)
size = int(match[2], 16)
if size != len(rootfs) or decrypted[start:start + size] != rootfs:
    raise ValueError("Declared Cloud file-system entry differs from the built RootFS")
if len(data) != int.from_bytes(data[:4], "big"):
    raise ValueError("Cloud file length mismatch")
args.output.write_bytes(data)
print("PASS owner signature, AES decryption and RootFS extraction")
print("Container length", hex(len(data)))
print("SHA256:", hashlib.sha256(data).hexdigest())
