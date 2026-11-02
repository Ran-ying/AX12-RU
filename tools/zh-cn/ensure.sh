#!/bin/sh
set -eu

# Run periodically on the Mac mini; this does not write AX12 flash.
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
if ssh -o BatchMode=yes -o ConnectTimeout=5 ax12 \
    'test -s /www/webpages/locale/zh_CN/lan.js && grep -q ZH_CN /etc/config/locale'; then
    echo "AX12 zh_CN already active"
    exit 0
fi

out="$HOME/Library/Application Support/AX12-RU/locale"
sh "$repo/tools/zh-cn/build.sh" "$out"
tar -C "$out" -cf - zh_CN | ssh -o BatchMode=yes ax12 \
    'mkdir -p /tmp/ax12-zh-cn && tar -C /tmp/ax12-zh-cn -xf -'
ssh -o BatchMode=yes ax12 sh -s < "$repo/tools/zh-cn/activate.sh"
echo "AX12 zh_CN restored in RAM"
