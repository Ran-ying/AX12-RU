#!/usr/bin/env python3
"""Prepare an offline, owner-signed AX12 Cloud package without a private key.

Writes a test-only unsigned container and a 256-byte RSA-PSS encoded message.
The RSA private-key operation must happen separately on the owner's computer.
"""
import argparse
import hashlib
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from repack_proof import public_key_from_elf
from self_sign_lab import aes_crypt, cloud_decrypt, mgf1
from repack_cloud_lab import repack

SIG_START, SIG_END, HEADER = 0x130, 0x230, 0x14

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("official", type=Path)
p.add_argument("old_nvrammanager", type=Path)
p.add_argument("sealed_rootfs", type=Path)
p.add_argument("unsigned_output", type=Path)
p.add_argument("encoded_message_output", type=Path)
args = p.parse_args()

original = args.official.read_bytes()
vendor = public_key_from_elf(args.old_nvrammanager)
plain = cloud_decrypt(original, vendor)
payload = args.sealed_rootfs.read_bytes()
changed = repack(plain, payload)

salt = secrets.token_bytes(48)
key, iv = salt[:16], salt[16:32]
prepared = bytearray(changed)
decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
prepared[SIG_START:SIG_END] = decryptor.update(bytes(256)) + decryptor.finalize()
encrypted = aes_crypt(prepared, key, iv, True)
assert encrypted[SIG_START:SIG_END] == bytes(256)

digest = hashlib.sha256(encrypted[HEADER:]).digest()
H = hashlib.sha256(bytes(8) + digest + salt).digest()
db = bytes(223 - len(salt) - 1) + bytes([1]) + salt
masked = bytearray(a ^ b for a, b in zip(db, mgf1(H, 223)))
masked[0] &= 0x7F
encoded = bytes(masked) + H + bytes([0xBC])
assert len(encoded) == 256

args.unsigned_output.write_bytes(encrypted)
args.encoded_message_output.write_bytes(encoded)
print("Prepared unsigned Cloud length", len(encrypted))
print("PSS encoded message length", len(encoded))
print("No private key used")
