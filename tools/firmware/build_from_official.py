#!/usr/bin/env python3
"""AX12 RU v1 patch-chain builder: pristine official 1.5.0 -> owner 1.5.x.

No router access. Unsigned by default; optional local signing via --sign-key.
Requires squashfs-tools, Python cryptography, and owner RSA public verifier.
"""
import argparse
import hashlib
import lzma
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from patches import v1_5_1, v1_5_2, v1_5_3
from repack_cloud_lab import repack
from self_sign_lab import cloud_decrypt
from build_owner_153 import prepare_unsigned

REPO = Path(__file__).resolve().parents[2]
OFFICIAL_SHA256 = '50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9'
VERSIONS = {
    '1.5.1': b'soft_ver:1.5.1 Build 20261103 Rel. 41063',
    '1.5.2': b'soft_ver:1.5.2 Build 20261103 Rel. 41064',
    '1.5.3': b'soft_ver:1.5.3 Build 20261103 Rel. 41065',
}
VENDOR_VERSION = b'soft_ver:1.5.0 Build 20260605 Rel. 41062'


def partition(plain, name):
    manifest = plain[0x1014:0x1814]
    match = re.search(rb'fwup-ptn ' + name + rb' base 0x([0-9a-f]+) size 0x([0-9a-f]+)', manifest)
    if not match:
        raise ValueError(f'Missing official Cloud partition {name!r}')
    return 0x1014 + int(match[1], 16), int(match[2], 16)


def run(*args):
    subprocess.run(args, check=True)


def rootfs_diff(pristine, patched):
    def index(base):
        result = {}
        for p in base.rglob('*'):
            if p.is_file() or p.is_symlink():
                key = str(p.relative_to(base))
                result[key] = (p.is_symlink(), p.readlink().as_posix() if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest(), p.lstat().st_mode & 0o777)
        return result

    a, b = index(pristine), index(patched)
    removed = set(a) - set(b)
    added = set(b) - set(a)
    changed = {k for k in a.keys() & b.keys() if a[k] != b[k]}
    allowed_added = {
        'etc/dropbear/authorized_keys', 'etc/rc.d/S99zzzzzzzzssh',
        'etc_ro/init.d/ax12-ssh', 'root/.ssh/authorized_keys',
        'www/webpages/locale/zh_CN/index-AX12r2.js.gz',
    }
    allowed_changed = {
        'usr/lib/libnvrammanager.so', 'www/cgi-bin/luci',
        'www/webpages/js/update-store-DnZhtCy9.js.gz',
    }
    if 'www/webpages/locale/zh_CN/index-AX12r3.js.gz' in added:
        allowed_added.add('www/webpages/locale/zh_CN/index-AX12r3.js.gz')
    if removed or added != allowed_added or changed != allowed_changed:
        raise ValueError(f'Unexpected RootFS patch diff: added={sorted(added)} removed={sorted(removed)} changed={sorted(changed)}')
    print('PASS: RootFS file-level diff, added',len(added),'changed',len(changed),'removed=0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official', type=Path, default=REPO / 'inputs/official-1.5.0.bin', help='Exact AX12 RU v1 official 1.5.0 Build 20260605 BIN')
    parser.add_argument('--version', choices=VERSIONS.keys(), required=True)
    parser.add_argument('--owner-public', type=Path, default=REPO / 'keys/ax12_owner_2026_public.pem')
    parser.add_argument('--vendor-public', type=Path, default=REPO / 'keys/tplink_official_verifier_public.pem')
    parser.add_argument('--workdir', type=Path, default=None)
    parser.add_argument('--sign-key', type=Path, help='Optional RSA-2048 private PEM on this machine; default is unsigned only')
    args = parser.parse_args()
    workdir = args.workdir or REPO / 'build' / ('ax12-from-official-' + args.version)
    workdir.mkdir(parents=True, exist_ok=True)

    official = args.official.read_bytes()
    if hashlib.sha256(official).hexdigest() != OFFICIAL_SHA256:
        raise ValueError('Official firmware SHA256 differs from verified AX12 RU v1 1.5.0')
    vendor_public = serialization.load_pem_public_key(args.vendor_public.read_bytes())
    owner_public = serialization.load_pem_public_key(args.owner_public.read_bytes())
    plain = cloud_decrypt(official, vendor_public)
    if b'fwup-ptn fs-uboot ' not in plain[0x1014:0x1814]:
        raise ValueError('Official Bootloader update entry missing')

    kernel_start, kernel_size = partition(plain, b'os-image')
    original_kernel = bytes(plain[kernel_start:kernel_start + kernel_size])
    if original_kernel[:4] != b'cr6c':
        raise ValueError('Expected unmodified official cr6c kernel')

    root_start, root_size = partition(plain, b'file-system')
    root_image = workdir / 'official-file-system.sealed'
    root_image.write_bytes(plain[root_start:root_start + root_size])
    root = workdir / 'rootfs'
    if root.exists():
        shutil.rmtree(root)
    run('unsquashfs','-processors','2','-d',str(root),str(root_image))
    stock = workdir / 'pristine-1.5.0'
    if stock.exists():
        shutil.rmtree(stock)
    shutil.copytree(root, stock, symlinks=True)

    # v1.5.1: owner trust, SSH, Chinese and Web CGI fixes; cs6c bootstrap bridge.
    v1_5_1.apply(root, args.owner_public, workdir, REPO)
    kernel = bytearray(original_kernel)
    kernel[:4] = b'cs6c'
    if args.version in ('1.5.2', '1.5.3'):
        kernel = bytearray(v1_5_2.apply(bytes(kernel)))
    if args.version == '1.5.3':
        v1_5_3.apply(root)
    rootfs_diff(stock, root)

    sqfs = workdir / 'rootfs.sqfs'
    if sqfs.exists():
        sqfs.unlink()
    run('mksquashfs', str(root), str(sqfs), '-noappend', '-comp', 'xz', '-b', '262144',
        '-always-use-fragments', '-exports', '-all-root', '-processors', '2')
    sealed_file = workdir / 'rootfs.sealed'
    run(sys.executable, str(REPO / 'tools/firmware/seal_rootfs.py'),
        str(sqfs), str(sealed_file), '--partition-size', '0xb00000')
    new_rootfs = sealed_file.read_bytes()
    if len(new_rootfs) > 0xB00000:
        raise ValueError('Exceeds actual mtd2 RootFS partition')

    rebuilt = repack(plain, new_rootfs)
    new_kernel_start, new_kernel_size = partition(rebuilt, b'os-image')
    if new_kernel_size != len(kernel):
        raise ValueError('Modified kernel size differs from official partition')
    rebuilt[new_kernel_start:new_kernel_start + new_kernel_size] = kernel

    manifest = bytes(rebuilt[0x1014:0x1814])
    lines = manifest.rstrip(b'\0').splitlines(keepends=True)
    keep = [s for s in lines if not s.startswith(b'fwup-ptn fs-uboot ')]
    if len(lines) - len(keep) != 1:
        raise ValueError('Expected exactly one fs-uboot entry to omit')
    rebuilt[0x1014:0x1814] = b''.join(keep).ljust(0x800, b'\0')

    version_start, version_size = partition(rebuilt, b'soft-version')
    version_data = bytes(rebuilt[version_start:version_start + version_size])
    if len(VENDOR_VERSION) != len(VERSIONS[args.version]) or version_data.count(VENDOR_VERSION) != 1:
        raise ValueError('Unexpected official soft-version field')
    rebuilt[version_start:version_start + version_size] = version_data.replace(VENDOR_VERSION, VERSIONS[args.version])

    if b'fwup-ptn fs-uboot ' in rebuilt[0x1014:0x1814]:
        raise ValueError('Bootloader update still in manifest')
    kernel_final_start, kernel_final_size = partition(rebuilt, b'os-image')
    if rebuilt[kernel_final_start:kernel_final_start + kernel_final_size] != kernel:
        raise ValueError('Kernel patch changed unexpectedly during repacking')

    unsigned, em = prepare_unsigned(rebuilt)
    if len(unsigned) != int.from_bytes(unsigned[:4],'big') or len(unsigned) > 0x1000000:
        raise ValueError('Cloud size field or Flash capacity invalid')
    (workdir / 'unsigned.bin').write_bytes(unsigned)
    (workdir / 'em-for-owner-signing.bin').write_bytes(em)
    print(f'PASS: original official 1.5.0 -> patch chain 1.5.1..{args.version}')
    print('PASS: owner trust, boot bridge, kernel/RootFS partition, no Bootloader update')
    print('PASS: unsigned AES roundtrip, 256-byte RSA-PSS EM')
    print('RootFS size',len(new_rootfs),'free',0xB00000-len(new_rootfs))
    print('Unsigned size',len(unsigned),'SHA256',hashlib.sha256(unsigned).hexdigest())
    print('Build output:',workdir)
    if args.sign_key:
        private = serialization.load_pem_private_key(args.sign_key.read_bytes(), password=None)
        if not isinstance(private, rsa.RSAPrivateKey) or private.key_size != 2048 or private.public_key().public_numbers() != owner_public.public_numbers():
            raise ValueError('Signing key must be the matching owner RSA-2048 private key')
        numbers = private.private_numbers()
        signature = pow(int.from_bytes(em, 'big'), numbers.d, numbers.public_numbers.n).to_bytes(256, 'big')
        signature_file = workdir / 'owner-signature.big'
        signature_file.write_bytes(signature)
        signed_file = workdir / f'AX12-RU-{args.version}-owner-signed.bin'
        run(sys.executable, str(REPO / 'tools/firmware/finalize_owner_cloud.py'),
            str(workdir / 'unsigned.bin'), str(signature_file), str(args.owner_public),
            str(sealed_file), str(signed_file))
        signed = cloud_decrypt(signed_file.read_bytes(), owner_public)
        if signed[:0x130] != rebuilt[:0x130] or signed[0x230:] != rebuilt[0x230:]:
            raise ValueError('Signed Cloud content differs from patched plaintext')
        print('PASS: signed RSA-PSS/AES Cloud matches patched plaintext (except signing slot)')
        print('Signed firmware:', signed_file)
        print('Firmware has not yet passed live device boot testing')
    else:
        print('This output is unsigned and MUST NOT be flashed; rerun with --sign-key or use finalize_owner_cloud.py')


if __name__ == '__main__':
    main()
