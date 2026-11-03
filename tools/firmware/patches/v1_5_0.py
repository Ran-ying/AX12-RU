"""Owner 1.5.0 foundation: owner RSA verifier, LAN SSH, and old-Bootloader bridge.

Only portable owner-key changes; no original-device credentials are included.
"""
import hashlib
import shutil
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

OFFICIAL_NV_SHA256 = '105fa06cae200c43702f4f5d4e5438754eef1e7962e622bec8b4fed49701f607'


def apply(rootfs, owner_public, workdir, repo):
    vendor_lib = rootfs / 'usr/lib/libnvrammanager.so'
    if hashlib.sha256(vendor_lib.read_bytes()).hexdigest() != OFFICIAL_NV_SHA256:
        raise ValueError('Unexpected official verifier; refusing owner-key patch')
    key = serialization.load_pem_public_key(owner_public.read_bytes())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048:
        raise ValueError('Owner key must be RSA-2048')
    owner_lib = workdir / 'libnvrammanager-owner.so'
    subprocess.run([sys.executable, str(repo / 'tools/firmware/patch_trust_anchor.py'),
                    str(vendor_lib), str(owner_public), str(owner_lib)], check=True)
    shutil.copy2(owner_lib, vendor_lib)

    ssh_dest = rootfs / 'etc_ro/init.d/ax12-ssh'
    shutil.copy2(repo / 'tools/ax12-ssh', ssh_dest)
    ssh_dest.chmod(0o755)
    (rootfs / 'etc/rc.d/S99zzzzzzzzssh').symlink_to('../init.d/ax12-ssh')
    ssh_pub = key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b'\n'
    for relative in ('root/.ssh/authorized_keys', 'etc/dropbear/authorized_keys'):
        dest = rootfs / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(ssh_pub)
        dest.chmod(0o600)
    (rootfs / 'root/.ssh').chmod(0o700)

    # Stock CGI is not executable; keep admin Web usable on the first migration.
    (rootfs / 'www/cgi-bin/luci').chmod(0o755)
    print('APPLIED owner 1.5.0: RSA verifier, root SSH, basic Web CGI execute permission')


def apply_kernel(kernel):
    if kernel[:4] != b'cr6c':
        raise ValueError('1.5.0 bootstrap expects original cr6c kernel')
    # The original Realtek Bootloader skips its old-offset RootFS probe for cs6c.
    return b'cs6c' + kernel[4:]
