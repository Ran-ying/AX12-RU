#!/usr/bin/env python3
"""Apply the owner RSA-2048 private operation to a prepared RSA-PSS encoded message.

Run only on the owner's Mac. The private key never leaves this machine.
Requires: pip install cryptography
"""
import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("encoded_message", type=Path)
parser.add_argument("private_key", type=Path)
parser.add_argument("signature_output", type=Path)
args = parser.parse_args()

raw = args.private_key.read_bytes()
if raw.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----"):
    key = serialization.load_ssh_private_key(raw, password=None)
else:
    key = serialization.load_pem_private_key(raw, password=None)
if not isinstance(key, rsa.RSAPrivateKey) or key.key_size != 2048:
    raise ValueError("Expected an RSA-2048 private key")

message = args.encoded_message.read_bytes()
if len(message) != 256 or message[-1] != 0xBC:
    raise ValueError("Expected a 256-byte RSA-PSS encoded message")

numbers = key.private_numbers()
signature = pow(
    int.from_bytes(message, "big"), numbers.d, numbers.public_numbers.n
).to_bytes(256, "big")
args.signature_output.write_bytes(signature)
print("Wrote 256-byte RSA signature, big endian:", args.signature_output)
