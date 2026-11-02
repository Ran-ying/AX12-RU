#!/bin/sh
set -eu

# Only for overlays installed by activate.sh; no Flash modifications.
test -f /tmp/ax12-zh-cn-locale.orig
umount /www/webpages/locale
umount /tmp/ax12-zh-cn-base
cp /tmp/ax12-zh-cn-locale.orig /etc/config/locale
echo "Restored original locale and language list."
