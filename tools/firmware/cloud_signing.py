"""Pure offline TP-Link Cloud AES/RSA-PSS encoded-message preparation."""
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from self_sign_lab import aes_crypt, mgf1

def prepare_unsigned(plain):
    salt = secrets.token_bytes(48)
    key, iv = salt[:16], salt[16:32]
    prepared = bytearray(plain)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    prepared[0x130:0x230] = decryptor.update(bytes(256)) + decryptor.finalize()
    encrypted = aes_crypt(prepared, key, iv, True)
    if encrypted[0x130:0x230] != bytes(256):
        raise ValueError("RSA signature slot is not zero")
    digest = hashlib.sha256(encrypted[0x14:]).digest()
    h = hashlib.sha256(bytes(8) + digest + salt).digest()
    db = bytes(223 - len(salt) - 1) + b"\x01" + salt
    masked = bytearray(a ^ b for a, b in zip(db, mgf1(h, 223)))
    masked[0] &= 0x7F
    em = bytes(masked) + h + b"\xBC"
    restored = aes_crypt(encrypted, key, iv, False)
    if restored[:0x130] != plain[:0x130] or restored[0x230:] != plain[0x230:]:
        raise ValueError("Unsigned AES roundtrip failed")
    return encrypted, em
