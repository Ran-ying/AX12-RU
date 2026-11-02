#!/bin/sh
set -eu

# Run on AX12 as root, after uploading /tmp/ax12-zh-cn/zh_CN.
test -s /tmp/ax12-zh-cn/zh_CN/lan.js
if grep -q ' /www/webpages/locale ' /proc/mounts; then
    echo "Locale directory already has a mount; restore it first." >&2
    exit 1
fi
if grep -q "config langinfo 'ZH_CN'" /etc/config/locale; then
    echo "ZH_CN is already registered." >&2
    exit 1
fi

mkdir -p /tmp/ax12-zh-cn-base /tmp/ax12-zh-cn-view
cp /etc/config/locale /tmp/ax12-zh-cn-locale.orig

# Preserve original SquashFS with a read-only bind, then create tiny symlinks.
mount --bind /www/webpages/locale /tmp/ax12-zh-cn-base
for entry in /tmp/ax12-zh-cn-base/*; do
    ln -s "$entry" "/tmp/ax12-zh-cn-view/${entry##*/}"
done
ln -s /tmp/ax12-zh-cn/zh_CN /tmp/ax12-zh-cn-view/zh_CN
mount --bind /tmp/ax12-zh-cn-view /www/webpages/locale

cat >> /etc/config/locale <<'EOF'

config langinfo 'ZH_CN'
    option value 'zh_CN'
EOF

echo "ZH_CN activated in RAM. Hard-refresh the management page."
