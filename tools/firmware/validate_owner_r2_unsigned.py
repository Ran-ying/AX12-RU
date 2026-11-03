#!/usr/bin/env python3
"""Validate AX12 1.5.1 unsigned Cloud before the owner's private signing."""
import hashlib
import re
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from self_sign_lab import cloud_decrypt, aes_crypt, mgf1
from repack_cloud_lab import repack

src, pubpath, sealedpath, unspath, empath = map(Path, sys.argv[1:])
pub = serialization.load_pem_public_key(pubpath.read_bytes())
source = cloud_decrypt(src.read_bytes(), pub)
rootfs = sealedpath.read_bytes()
expected = repack(source, rootfs)
manifest = expected[0x1014:0x1814]
match = re.search(rb"fwup-ptn soft-version base 0x([0-9a-f]+) size 0x([0-9a-f]+)", manifest)
start = 0x1014 + int(match[1], 16)
old = b"soft_ver:1.5.0 Build 20260605 Rel. 41062"
new = b"soft_ver:1.5.1 Build 20261103 Rel. 41063"
assert expected[start:].count(old) == 1
expected[start:] = expected[start:].replace(old, new)

cipher = unspath.read_bytes()
em = empath.read_bytes()
assert len(em) == 256 and em[-1] == 0xBC
H = em[-33:-1]
db = bytes(a ^ b for a, b in zip(em[:223], mgf1(H, 223)))
db = bytes([db[0] & 0x7F]) + db[1:]
salt = db[db.index(bytes([1])) + 1:]
assert len(salt) == 48
digest = hashlib.sha256(cipher[0x14:]).digest()
assert H == hashlib.sha256(bytes(8) + digest + salt).digest()
plain = aes_crypt(cipher, salt[:16], salt[16:32], False)
assert plain[:0x130] == expected[:0x130]
assert plain[0x230:] == expected[0x230:]
assert len(plain) == int.from_bytes(plain[:4], "big")
assert b"fwup-ptn fs-uboot " not in manifest
assert expected[0x1014:0x1814].count(b"fwup-ptn file-system") == 1
print("PASS unsigned Cloud PSS encoded message and AES plaintext round-trip")
print("PASS unchanged cs6c kernel, no Bootloader update entry, 1.5.1 metadata")
print("PASS sealed RootFS:", len(rootfs), "bytes")
print("Unsigned SHA256:", hashlib.sha256(cipher).hexdigest())
