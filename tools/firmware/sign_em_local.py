#!/usr/bin/env python3
"""Perform only the private RSA operation locally. Do not upload the private key."""
import argparse
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("private_pem", type=Path)
parser.add_argument("encoded_pss", type=Path)
parser.add_argument("signature_out", type=Path)
args = parser.parse_args()

private = serialization.load_pem_private_key(args.private_pem.read_bytes(), password=None)
if not isinstance(private, rsa.RSAPrivateKey) or private.key_size != 2048:
    raise ValueError("AX12 Cloud format currently requires RSA-2048")
numbers = private.private_numbers()
em = args.encoded_pss.read_bytes()
if len(em) != 256 or int.from_bytes(em, "big") >= numbers.public_numbers.n:
    raise ValueError("Invalid 256-byte encoded message")

sig = pow(int.from_bytes(em, "big"), numbers.d, numbers.public_numbers.n)
args.signature_out.write_bytes(sig.to_bytes(256, "big"))
print("Local RSA operation completed, output bytes: 256")
print("Signature SHA256:", hashlib.sha256(args.signature_out.read_bytes()).hexdigest())
