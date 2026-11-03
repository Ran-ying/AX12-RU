#!/usr/bin/env python3
"""Offline only: create AX12 RU v1 1.1.22 SSH RootFS from a *device's own* backup.

Outputs a 4-KiB-aligned RootFS payload for the old 0x440000 flash location.
Does not connect to UART, open a flash device, or write the router.
Requires unsquashfs and mksquashfs, plus a public SSH authorized key.
"""
import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO = Path(__file__).resolve().parents[2]
FLASH_BYTES = 0x1000000
ROOTFS_OFFSET = 0x440000
ROOTFS_CAPACITY = 0xAC8000
STOCK_UPDATER_SHA256 = "b1c396c5f356ded3e67f081b5ebe2ab9e4fe97d39d7714aab5fcd52929fe24ea"


def run(*cmd):
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flash-backup', type=Path, required=True,
                        help='Own original unmodified 16 MiB AX12 RU v1 1.1.22 Flash backup')
    parser.add_argument('--ssh-public', type=Path, required=True,
                        help='SSH public key; never give this tool your SSH private key')
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--reconstructed-flash', action='store_true',
                        help='Also create a private offline 16-MiB recovery/audit model; NOT for generic direct flashing')
    args = parser.parse_args()

    flash = args.flash_backup.read_bytes()
    if len(flash) != FLASH_BYTES:
        raise ValueError('Expected exact 16 MiB original SPI Flash backup')
    if flash[ROOTFS_OFFSET:ROOTFS_OFFSET+4] != b'hsqs':
        raise ValueError('No old 1.1.22 SquashFS at 0x440000; check hardware/firmware version')
    used = struct.unpack_from('<Q', flash, ROOTFS_OFFSET+40)[0]
    if not 0 < used < ROOTFS_CAPACITY:
        raise ValueError('Unexpected old SquashFS size')
    key = args.ssh_public.read_bytes().strip()
    if not key.startswith(b'ssh-rsa ') or not isinstance(serialization.load_ssh_public_key(key), rsa.RSAPublicKey):
        raise ValueError('Expected a valid RSA SSH public key, not an SSH private key')

    work = args.workdir
    work.mkdir(parents=True, exist_ok=True)
    image = work / 'original-rootfs.sqfs'
    image.write_bytes(flash[ROOTFS_OFFSET:ROOTFS_OFFSET+ROOTFS_CAPACITY])
    root = work / 'rootfs'
    if root.exists():
        shutil.rmtree(root)
    run('unsquashfs', '-processors', '2', '-d', str(root), str(image))
    original_updater = root / 'usr/bin/nvrammanager'
    if hashlib.sha256(original_updater.read_bytes()).hexdigest() != STOCK_UPDATER_SHA256:
        raise ValueError('Unexpected old firmware: 1.1.22 stock updater SHA-256 differs')
    if (root / 'etc/rc.d/S99zzzzzzzzssh').exists() or (root / 'etc_ro/init.d/ax12-ssh').exists():
        raise ValueError('SSH bootstrap already present; start from original 1.1.22 backup')

    script = root / 'etc_ro/init.d/ax12-ssh'
    shutil.copyfile(REPO / 'tools/ax12-ssh', script)
    script.chmod(0o755)
    link = root / 'etc/rc.d/S99zzzzzzzzssh'
    link.symlink_to('../init.d/ax12-ssh')
    for name in ('root/.ssh/authorized_keys', 'etc/dropbear/authorized_keys'):
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(key+b'\n')
        dest.chmod(0o600)
    (root/'root/.ssh').chmod(0o700)

    sqfs = work / 'rootfs-ssh.sqfs'
    if sqfs.exists():
        sqfs.unlink()
    run('mksquashfs', str(root), str(sqfs), '-noappend', '-comp', 'xz',
        '-b', '262144', '-always-use-fragments', '-exports', '-all-root',
        '-no-progress', '-processors', '2')
    sealed = work / 'rootfs-ssh-realtek.bin'
    run(sys.executable, str(REPO / 'tools/ax12_seal_realtek_rootfs.py'),
        str(sqfs), str(sealed))
    data = sealed.read_bytes()
    padded = data.ljust((len(data)+4095)//4096*4096, b'\xff')
    if len(padded) > ROOTFS_CAPACITY:
        raise ValueError('Custom RootFS would overwrite neighboring factory partition')
    payload = work / 'rootfs-ssh-bootstrap-flash.bin'
    payload.write_bytes(padded)

    if args.reconstructed_flash:
        reconstructed = flash[:ROOTFS_OFFSET]+padded+flash[ROOTFS_OFFSET+len(padded):]
        if reconstructed[:ROOTFS_OFFSET] != flash[:ROOTFS_OFFSET] or reconstructed[ROOTFS_OFFSET+len(padded):] != flash[ROOTFS_OFFSET+len(padded):]:
            raise ValueError('Reconstruction modified bytes outside RootFS payload')
        (work / 'private-offline-flash-reconstruction-NOT-FOR-DIRECT-FLASH.bin').write_bytes(reconstructed)
    print('PASS: Original Flash kept untouched; SSH private key not used')
    print('Original Flash SHA256:', hashlib.sha256(flash).hexdigest())
    print('RootFS Flash offset:', hex(ROOTFS_OFFSET))
    print('Write payload length:', hex(len(padded)), 'bytes:', len(padded))
    print('Payload SHA256:', hashlib.sha256(padded).hexdigest())
    print('Output:', payload)
    print('Offline staging only; Bootloader recovery, exact target and UART readback required before any hardware write')


if __name__ == '__main__':
    main()
