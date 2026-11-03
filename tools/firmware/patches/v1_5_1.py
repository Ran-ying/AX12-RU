"""1.5.1: owner trust, LAN SSH, Web CGI and initial simplified Chinese UI."""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent
OFFICIAL_NV_SHA256 = '105fa06cae200c43702f4f5d4e5438754eef1e7962e622bec8b4fed49701f607'
CGI_ORIGINAL = b'#!/usr/bin/lua\nrequire "luci.cacheloader"\nrequire "luci.sgi.cgi"\nluci.dispatcher.indexcache = "/tmp/luci-indexcache"\nluci.sgi.cgi.run()'
CGI_INSERT = b'local locale = require "luci.controller.locale"\nlocal _, allowed = debug.getupvalue(locale.set_sysinfo, 4)\nallowed.zh_CN = allowed.zh_TW\n'


def apply(rootfs, owner_public, workdir, repo):
    vendor_lib = rootfs / 'usr/lib/libnvrammanager.so'
    if hashlib.sha256(vendor_lib.read_bytes()).hexdigest() != OFFICIAL_NV_SHA256:
        raise ValueError('Unexpected vendor firmware verifier; refusing public-key patch')
    owner_lib = workdir / 'libnvrammanager-owner.so'
    subprocess.run([sys.executable, str(repo / 'tools/firmware/patch_trust_anchor.py'),
                    str(vendor_lib), str(owner_public), str(owner_lib)], check=True)
    shutil.copy2(owner_lib, vendor_lib)

    ssh_source = repo / 'tools/ax12-ssh'
    ssh_dest = rootfs / 'etc_ro/init.d/ax12-ssh'
    shutil.copy2(ssh_source, ssh_dest)
    ssh_dest.chmod(0o755)
    ssh_link = rootfs / 'etc/rc.d/S99zzzzzzzzssh'
    ssh_link.symlink_to('../init.d/ax12-ssh')
    owner_key = serialization.load_pem_public_key(owner_public.read_bytes())
    ssh_pub = owner_key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b'\n'
    for relative in ('root/.ssh/authorized_keys', 'etc/dropbear/authorized_keys'):
        dest = rootfs / relative
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        dest.write_bytes(ssh_pub)
        dest.chmod(0o600)
    (rootfs / 'root/.ssh').chmod(0o700)

    cgi = rootfs / 'www/cgi-bin/luci'
    if cgi.read_bytes() != CGI_ORIGINAL:
        raise ValueError('Original CGI differs from official 1.5.0')
    cgi.write_bytes(CGI_ORIGINAL.replace(b'require "luci.sgi.cgi"\n',
                                          b'require "luci.sgi.cgi"\n' + CGI_INSERT))
    cgi.chmod(0o755)

    for relative in ('www/webpages/locale/zh_CN/index-AX12r2.js.gz',
                     'www/webpages/js/update-store-DnZhtCy9.js.gz'):
        source = ROOT / 'assets/1.5.1' / relative
        dest = rootfs / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    print('APPLIED 1.5.1: owner verifier, SSH, CGI, zh_CN r2')
