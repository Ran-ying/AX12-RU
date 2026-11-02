#!/usr/bin/env python3
"""Offline proof: AX12 Cloud payload can be re-encrypted, but modifications fail RSA-PSS.

Requires: pip install cryptography
Never writes firmware to the router or disk.
"""

import argparse
import base64
import hashlib
import re
import struct
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def public_key_from_elf(path):
    binary = path.read_bytes()
    for match in re.finditer(rb"BgIAAA[A-Za-z0-9+/=]{60,}", binary):
        blob = base64.b64decode(match.group())
        if blob[8:12] != b"RSA1":
            continue
        bits, exponent = struct.unpack_from("<II", blob, 12)
        if bits == 2048:
            modulus = int.from_bytes(blob[20:276], "little")
            return rsa.RSAPublicNumbers(exponent, modulus).public_key()
    raise ValueError("RSA-2048 public key not found")


def verify(public, data):
    message = bytearray(data[0x14:])
    message[0x130 - 0x14:0x230 - 0x14] = bytes(256)
    public.verify(
        bytes(data[0x130:0x230][::-1]),
        bytes(message),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.AUTO),
        hashes.SHA256(),
    )


def aes_params(public, data):
    numbers = public.public_numbers()
    encoded = pow(
        int.from_bytes(data[0x130:0x230], "little"),
        numbers.e,
        numbers.n,
    ).to_bytes(256, "big")
    h = encoded[-33:-1]
    mask = b"".join(
        hashlib.sha256(h + i.to_bytes(4, "big")).digest() for i in range(7)
    )[:223]
    db = bytes(x ^ y for x, y in zip(encoded[:223], mask))
    db = bytes([db[0] & 0x7F]) + db[1:]
    salt = db[db.index(bytes([1])) + 1:]
    return salt[:16], salt[16:32]


def transform(data, key, iv, decrypt):
    content = bytearray(data)
    end = 0x130 + ((len(data) - 0x130) // 16) * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    mode = cipher.decryptor() if decrypt else cipher.encryptor()
    content[0x130:end] = mode.update(bytes(content[0x130:end])) + mode.finalize()
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("nvrammanager", type=Path, help="AX12 MIPS nvrammanager ELF")
    args = parser.parse_args()

    original = args.firmware.read_bytes()
    pub = public_key_from_elf(args.nvrammanager)
    verify(pub, original)
    print("Original firmware: RSA-2048-PSS verified")

    key, iv = aes_params(pub, original)
    unsigned = bytearray(original)
    unsigned[0x130:0x230] = bytes(256)
    plain = transform(unsigned, key, iv, decrypt=True)
    print("Decrypted SquashFS magic at:", hex(plain.find(b"hsqs")))

    encrypted = transform(plain, key, iv, decrypt=False)
    encrypted[0x130:0x230] = original[0x130:0x230]
    assert encrypted == original
    verify(pub, encrypted)
    print("Unmodified AES re-encryption: exact byte-for-byte original")

    plain[plain.index(b"hsqs") + 1] ^= 1
    changed = transform(plain, key, iv, decrypt=False)
    changed[0x130:0x230] = original[0x130:0x230]
    try:
        verify(pub, changed)
    except InvalidSignature:
        print("Modified payload: RSA-PSS verification FAILED (expected)")
    else:
        raise AssertionError("Unexpected valid signature for modified firmware")


if __name__ == "__main__":
    main()
