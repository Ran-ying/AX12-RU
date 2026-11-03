#!/usr/bin/env python3
"""Build unsigned AX12 RU 1.5.3 from the known-good owner-signed 1.5.2 image.

Offline only: no router connection, Flash operations, or signing-key access.
Requires cryptography and squashfs-tools (mksquashfs/unsquashfs).
"""
import argparse
import hashlib
import lzma
import re
import secrets
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from repack_cloud_lab import repack
from self_sign_lab import aes_crypt, cloud_decrypt, mgf1

REPO = Path(__file__).resolve().parents[2]
BASE_SHA256 = "1c8905d500e77cc5fc04addfb355aea4ec49d9bd67dccfe953f097eb46051136"
VERSION_152 = b"soft_ver:1.5.2 Build 20261103 Rel. 41064"
VERSION_153 = b"soft_ver:1.5.3 Build 20261103 Rel. 41065"


def partition(image, name):
    manifest = image[0x1014:0x1814]
    match = re.search(rb"fwup-ptn " + name + rb" base 0x([0-9a-f]+) size 0x([0-9a-f]+)", manifest)
    if not match:
        raise ValueError(f"Cloud manifest missing {name!r}")
    return 0x1014 + int(match[1], 16), int(match[2], 16)


def run(*args):
    subprocess.run(args, check=True)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Locally supplied verified 1.5.2 owner-signed BIN")
    parser.add_argument("--owner-public", type=Path, default=REPO / "keys/ax12_owner_2026_public.pem")
    parser.add_argument("--workdir", type=Path, default=REPO / "build/ax12-1.5.3")
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASE_SHA256:
        raise ValueError("Baseline is not the verified 1.5.2 owner firmware")
    public = serialization.load_pem_public_key(args.owner_public.read_bytes())
    original = cloud_decrypt(baseline, public)
    kernel_start, kernel_size = partition(original, b"os-image")
    kernel = bytes(original[kernel_start:kernel_start + kernel_size])
    if kernel[:4] != b"cs6c":
        raise ValueError("Expected verified cs6c kernel")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    unpacked = decoder.decompress(kernel[0x2818:])
    if not decoder.eof:
        raise ValueError("Kernel LZMA stream incomplete")
    if struct.unpack_from("<I", unpacked, 0xBE5548)[0] != 0:
        raise ValueError("Verified WAN=port1 kernel patch missing")
    if b"fwup-ptn fs-uboot " in original[0x1014:0x1814]:
        raise ValueError("Unexpected Bootloader upgrade entry")

    root_start, root_size = partition(original, b"file-system")
    sealed = bytes(original[root_start:root_start + root_size])
    args.workdir.mkdir(parents=True, exist_ok=True)
    input_image = args.workdir / "base.sealed.sqfs"
    input_image.write_bytes(sealed)
    extracted = args.workdir / "rootfs"
    if extracted.exists():
        shutil.rmtree(extracted)
    run("unsquashfs", "-processors", "2", "-d", str(extracted), str(input_image))

    overlay = REPO / "tools/firmware/overlays/zh_cn_v3"
    for source in overlay.rglob("*"):
        if source.is_file():
            destination = extracted / source.relative_to(overlay)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    sqfs = args.workdir / "rootfs.sqfs"
    if sqfs.exists():
        sqfs.unlink()
    run("mksquashfs", str(extracted), str(sqfs), "-noappend", "-comp", "xz",
        "-b", "262144", "-always-use-fragments", "-exports", "-all-root", "-processors", "2")
    sealed_new = args.workdir / "rootfs.sealed"
    run(sys.executable, str(REPO / "tools/firmware/seal_rootfs.py"),
        str(sqfs), str(sealed_new), "--partition-size", "0xb00000")
    payload = sealed_new.read_bytes()
    if len(payload) > 0xB00000:
        raise ValueError("RootFS exceeds actual mtd2 partition")

    rebuilt = repack(original, payload)
    version_start, version_size = partition(rebuilt, b"soft-version")
    old_version = bytes(rebuilt[version_start:version_start + version_size])
    if old_version.count(VERSION_152) != 1 or len(VERSION_152) != len(VERSION_153):
        raise ValueError("Unexpected soft-version metadata")
    rebuilt[version_start:version_start + version_size] = old_version.replace(VERSION_152, VERSION_153)
    new_kernel_start, new_kernel_size = partition(rebuilt, b"os-image")
    if rebuilt[new_kernel_start:new_kernel_start + new_kernel_size] != kernel:
        raise ValueError("WAN-fixed 1.5.2 kernel unexpectedly changed")
    if b"fwup-ptn fs-uboot " in rebuilt[0x1014:0x1814]:
        raise ValueError("Unexpected Bootloader upgrade entry")

    unsigned, em = prepare_unsigned(rebuilt)
    if len(unsigned) != int.from_bytes(unsigned[:4], "big") or len(unsigned) > 0x1000000:
        raise ValueError("Cloud size field or Flash capacity invalid")
    (args.workdir / "unsigned-1.5.3.bin").write_bytes(unsigned)
    (args.workdir / "em-for-owner-signing.bin").write_bytes(em)
    print("PASS: original owner signature, verified WAN-fixed kernel, RootFS, version, no U-Boot update")
    print("PASS: AES roundtrip and RSA-PSS encoded-message preparation")
    print("RootFS bytes:", len(payload), "headroom:", 0xB00000 - len(payload))
    print("Unsigned firmware bytes:", len(unsigned), "SHA256:", hashlib.sha256(unsigned).hexdigest())
    print("Signing input:", args.workdir / "em-for-owner-signing.bin")
    print("Signing is a separate operation; unsigned file must NOT be flashed")


if __name__ == "__main__":
    main()
