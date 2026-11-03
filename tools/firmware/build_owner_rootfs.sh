#!/bin/sh
# Offline owner-only AX12 RU RootFS build. No device access.
set -eu

if [ "$#" -ne 5 ]; then
    echo "Usage: $0 OFFICIAL_ROOTFS OWNER_SIGNING_PUBLIC_PEM SSH_PUBLIC_KEY SSH_INIT_SCRIPT WORKDIR" >&2
    exit 2
fi

source_rootfs=$1
signing_public=$2
ssh_public=$3
ssh_init=$4
workdir=$5
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$workdir"
if [ -e "$workdir/rootfs" ]; then
    echo "Refusing to overwrite existing workdir/rootfs" >&2
    exit 1
fi
cp -a "$source_rootfs" "$workdir/rootfs"
root="$workdir/rootfs"

# One-key mode: firmware signing and SSH must use the identical RSA-2048 public key.
python3 - "$signing_public" "$ssh_public" <<'PY'
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

signing = serialization.load_pem_public_key(Path(sys.argv[1]).read_bytes())
ssh = serialization.load_ssh_public_key(Path(sys.argv[2]).read_bytes())
if not isinstance(signing, rsa.RSAPublicKey) or signing.key_size != 2048:
    raise ValueError("Cloud signing requires RSA-2048")
if signing.public_numbers() != ssh.public_numbers():
    raise ValueError("SSH and firmware signing public keys are different")
PY

python3 "$here/patch_trust_anchor.py" \
    "$root/usr/lib/libnvrammanager.so" \
    "$signing_public" \
    "$workdir/libnvrammanager-owner.so"
cp "$workdir/libnvrammanager-owner.so" "$root/usr/lib/libnvrammanager.so"

install -m 755 "$ssh_init" "$root/etc_ro/init.d/ax12-ssh"
ln -s ../init.d/ax12-ssh "$root/etc/rc.d/S99zzzzzzzzssh"

install -d -m 700 "$root/root/.ssh"
install -m 600 "$ssh_public" "$root/root/.ssh/authorized_keys"
install -m 600 "$ssh_public" "$root/etc/dropbear/authorized_keys"

# Fix uhttpd CGI execution and add a complete zh_CN Web UI locale.
python3 "$here/patch_ax12_zh_cn.py" "$root"

mksquashfs "$root" "$workdir/rootfs.sqfs" \
    -noappend -comp xz -b 262144 -always-use-fragments \
    -exports -all-root -no-progress -processors 2
python3 "$here/seal_rootfs.py" "$workdir/rootfs.sqfs" "$workdir/rootfs.sealed" --partition-size 0xb00000
