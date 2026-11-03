#!/usr/bin/env python3
"""Repack an owner-signed AX12 Cloud with a revised RootFS; leave it unsigned for local signing."""
import hashlib
import secrets
import sys
import re
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from self_sign_lab import cloud_decrypt, aes_crypt, mgf1
from repack_cloud_lab import repack

source, owner_pub, new_rootfs, unsigned_output, em_output = map(Path, sys.argv[1:])
pub = serialization.load_pem_public_key(owner_pub.read_bytes())
plain = cloud_decrypt(source.read_bytes(), pub)
sealed = new_rootfs.read_bytes()
if len(sealed) > 0xB00000:
    raise ValueError("RootFS exceeds real mtd2 flash region")
modified = repack(plain, sealed)

manifest = modified[0x1014:0x1814]
m = re.search(rb"fwup-ptn soft-version base 0x([0-9a-f]+) size 0x([0-9a-f]+)", manifest)
assert m
start = 0x1014 + int(m[1], 16)
size = int(m[2], 16)
block = bytes(modified[start:start + size])
old = b"soft_ver:1.5.0 Build 20260605 Rel. 41062"
new = b"soft_ver:1.5.1 Build 20261103 Rel. 41063"
assert block.count(old) == 1 and len(old) == len(new)
modified[start:start + size] = block.replace(old, new)
assert modified[0x1014:0x1814].count(b"fwup-ptn fs-uboot ") == 0
assert len(modified) == int.from_bytes(modified[:4], "big")

salt = secrets.token_bytes(48)
key, iv = salt[:16], salt[16:32]
prepared = bytearray(modified)
decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
prepared[0x130:0x230] = decryptor.update(bytes(256)) + decryptor.finalize()
encrypted = aes_crypt(prepared, key, iv, True)
assert encrypted[0x130:0x230] == bytes(256)
digest = hashlib.sha256(encrypted[0x14:]).digest()
H = hashlib.sha256(bytes(8) + digest + salt).digest()
db = bytes(223 - len(salt) - 1) + bytes([1]) + salt
masked = bytearray(a ^ b for a, b in zip(db, mgf1(H, 223)))
masked[0] &= 0x7F
encoded = bytes(masked) + H + bytes([0xBC])
assert len(encoded) == 256
unsigned_output.write_bytes(encrypted)
em_output.write_bytes(encoded)
print("Owner-signed source validated; revised RootFS and custom 1.5.1 version prepared")
print("Unsigned Cloud bytes:", len(encrypted))
print("Encoded RSA-PSS message bytes:", len(encoded))
print("Owner private key was not used")
