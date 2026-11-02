#!/bin/sh
# Build an offline AX12 1.5.0 RootFS lab image with two independent trust libraries.
set -eu

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 EXTRACTED_ROOTFS OWNER_PUBLIC_PEM WORKDIR" >&2
    exit 2
fi

source_rootfs=$1
public_key=$2
workdir=$3
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$workdir"
if [ -e "$workdir/rootfs" ]; then
    echo "Refusing to overwrite an existing staged RootFS" >&2
    exit 1
fi
cp -a "$source_rootfs" "$workdir/rootfs"
root="$workdir/rootfs"

mkdir -p "$root/usr/lib/ax12-owner"
python3 "$here/patch_trust_anchor.py" \
    "$root/usr/lib/libnvrammanager.so" \
    "$public_key" \
    "$root/usr/lib/ax12-owner/libnvrammanager.so"

cat > "$root/usr/sbin/ax12-owner-check" <<'SCRIPT'
#!/bin/sh
# Check-only owner signature path; never performs a firmware write.
export LD_LIBRARY_PATH=/usr/lib/ax12-owner
exec /usr/bin/nvrammanager -c "$1"
SCRIPT
chmod 755 "$root/usr/sbin/ax12-owner-check"

mksquashfs "$root" "$workdir/rootfs.sqfs" \
    -noappend -comp xz -b 262144 -always-use-fragments \
    -exports -all-root -no-progress -processors 2
python3 "$here/seal_rootfs.py" "$workdir/rootfs.sqfs" "$workdir/rootfs.sealed"
