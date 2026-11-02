#!/usr/bin/env python3
"""Reassemble an AX12 Cloud container with a new RootFS for offline tests only.

Does not guarantee that TP-Link's full upgrade validation accepts the result.
"""
import argparse
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from repack_proof import public_key_from_elf
from self_sign_lab import cloud_decrypt, self_sign, verify, SIG_START, SIG_END

MANIFEST_START, MANIFEST_END = 0x1014, 0x1814
PATTERN = re.compile(rb"fwup-ptn ([\w-]+) base 0x([0-9a-f]+) size 0x([0-9a-f]+)")


def repack(plaintext, new_rootfs):
    metadata = bytes(plaintext[MANIFEST_START:MANIFEST_END])
    entries = {
        match.group(1): (int(match.group(2), 16), int(match.group(3), 16))
        for match in PATTERN.finditer(metadata)
    }
    old_base, old_size = entries[b"file-system"]
    start = MANIFEST_START + old_base
    delta = len(new_rootfs) - old_size
    replaced = bytearray(plaintext[:start] + new_rootfs + plaintext[start + old_size:])
    replaced[:4] = len(replaced).to_bytes(4, "big")

    def rewrite(match):
        name, base_text, size_text = match.groups()
        base, size = int(base_text, 16), int(size_text, 16)
        if name == b"file-system":
            size = len(new_rootfs)
        elif base >= old_base + old_size:
            base += delta
        return (
            b"fwup-ptn " + name
            + b" base 0x" + f"{base:0{len(base_text)}x}".encode()
            + b" size 0x" + f"{size:0{len(size_text)}x}".encode()
        )

    new_manifest = PATTERN.sub(rewrite, metadata)
    if len(new_manifest) != len(metadata):
        raise ValueError("Cloud manifest field width would change")
    replaced[MANIFEST_START:MANIFEST_END] = new_manifest
    print(f"RootFS old={old_size:#x} new={len(new_rootfs):#x}, delta={delta:+#x}")
    return replaced


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("official_bin", type=Path)
    p.add_argument("old_nvrammanager", type=Path)
    p.add_argument("owner_private", type=Path)
    p.add_argument("new_sealed_rootfs", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()

    official = args.official_bin.read_bytes()
    public = public_key_from_elf(args.old_nvrammanager)
    private = serialization.load_pem_private_key(args.owner_private.read_bytes(), password=None)
    payload = args.new_sealed_rootfs.read_bytes()
    if payload[:4] != b"hsqs" or len(payload) > 0xB08000:
        raise ValueError("Sealed RootFS invalid or exceeds AX12 1.5.0 Flash partition")

    plain = cloud_decrypt(official, public)
    changed = repack(plain, payload)
    package = self_sign(changed, private)
    verify(package, private.public_key())
    restored = cloud_decrypt(package, private.public_key())
    assert restored[:SIG_START] == changed[:SIG_START]
    assert restored[SIG_END:] == changed[SIG_END:]
    assert payload in restored
    args.output.write_bytes(package)
    print("PASS self-signed Cloud encrypted container validates and decrypts")
    print("Offline image:", args.output, "size", hex(len(package)))


if __name__ == "__main__":
    main()
