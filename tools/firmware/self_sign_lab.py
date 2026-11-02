#!/usr/bin/env python3
"""Offline AX12 Cloud RSA-PSS/AES signing experiment; never flashes hardware."""
import argparse
import hashlib
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from repack_proof import public_key_from_elf

SIG_START, SIG_END, HEADER = 0x130, 0x230, 0x14


def mgf1(seed, length):
    return b"".join(
        hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        for i in range((length + 31) // 32)
    )[:length]


def verify(image, key):
    data = bytearray(image[HEADER:])
    data[SIG_START - HEADER:SIG_END - HEADER] = bytes(256)
    key.verify(
        bytes(image[SIG_START:SIG_END][::-1]), bytes(data),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.AUTO),
        hashes.SHA256(),
    )


def salt_from_signature(image, public):
    numbers = public.public_numbers()
    encoded = pow(
        int.from_bytes(image[SIG_START:SIG_END], "little"),
        numbers.e, numbers.n,
    ).to_bytes(256, "big")
    if encoded[-1] != 0xBC:
        raise ValueError("Not an RSA-PSS signature")
    digest = encoded[-33:-1]
    masked = mgf1(digest, 223)
    database = bytes(a ^ b for a, b in zip(encoded[:223], masked))
    database = bytes([database[0] & 0x7F]) + database[1:]
    delimiter = database.index(bytes([1]))
    return database[delimiter + 1:]


def aes_crypt(data, key, iv, encrypt):
    out = bytearray(data)
    end = SIG_START + ((len(data) - SIG_START) // 16) * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    out[SIG_START:end] = ctx.update(bytes(out[SIG_START:end])) + ctx.finalize()
    return out


def cloud_decrypt(image, public):
    verify(image, public)
    salt = salt_from_signature(image, public)
    data = bytearray(image)
    data[SIG_START:SIG_END] = bytes(256)
    plain = aes_crypt(data, salt[:16], salt[16:32], False)
    if not plain[0x1014:0x1814].startswith(b"fwup-ptn "):
        raise ValueError("Decrypted Cloud partition manifest missing")
    return plain


def sign_with_salt(data, private, salt):
    msg = bytearray(data[HEADER:])
    msg[SIG_START - HEADER:SIG_END - HEADER] = bytes(256)
    digest = hashlib.sha256(msg).digest()
    h = hashlib.sha256(bytes(8) + digest + salt).digest()
    db = bytes(223 - len(salt) - 1) + bytes([1]) + salt
    masked = bytearray(x ^ y for x, y in zip(db, mgf1(h, 223)))
    masked[0] &= 0x7F
    encoded = bytes(masked) + h + bytes([0xBC])
    numbers = private.private_numbers()
    signed = pow(int.from_bytes(encoded, "big"), numbers.d, numbers.public_numbers.n)
    return signed.to_bytes(256, "little")


def self_sign(plain, private):
    salt = secrets.token_bytes(48)
    prepared = bytearray(plain)
    cipher = Cipher(algorithms.AES(salt[:16]), modes.CBC(salt[16:32]))
    ctx = cipher.decryptor()
    prepared[SIG_START:SIG_END] = ctx.update(bytes(256)) + ctx.finalize()
    ciphertext = aes_crypt(prepared, salt[:16], salt[16:32], True)
    assert ciphertext[SIG_START:SIG_END] == bytes(256)
    ciphertext[SIG_START:SIG_END] = sign_with_salt(ciphertext, private, salt)
    return bytes(ciphertext)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original")
    p.add_argument("original_nvrammanager")
    p.add_argument("private_key")
    p.add_argument("output")
    args = p.parse_args()

    image = Path(args.original).read_bytes()
    vendor = public_key_from_elf(Path(args.original_nvrammanager))
    private = serialization.load_pem_private_key(Path(args.private_key).read_bytes(), password=None)
    owner = private.public_key()

    plain = cloud_decrypt(image, vendor)
    custom = self_sign(plain, private)
    verify(custom, owner)
    restored = cloud_decrypt(custom, owner)
    assert restored[:SIG_START] == plain[:SIG_START]
    assert restored[SIG_END:] == plain[SIG_END:]
    print("PASS owner RSA-PSS/SHA256 signature")
    print("PASS AES-128-CBC round-trip with owner PSS salt")
    try:
        verify(custom, vendor)
    except InvalidSignature:
        print("PASS vendor trust correctly rejects owner-signed image")
    else:
        raise AssertionError("Unexpected vendor acceptance")

    corrupt = bytearray(custom)
    corrupt[0x4000] ^= 1
    try:
        verify(corrupt, owner)
    except InvalidSignature:
        print("PASS owner trust rejects one-byte tampering")
    else:
        raise AssertionError("Tampered image accepted")

    Path(args.output).write_bytes(custom)
    print("Test-only Cloud container:", args.output)
    print("SHA256:", hashlib.sha256(custom).hexdigest())


if __name__ == "__main__":
    main()
