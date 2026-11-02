#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-/tmp/ax12-zh-cn}

mkdir -p "$out/zh_CN"
ssh ax12 'tar -C /www/webpages/locale/zh_TW -cf - lan.js help.js lan.css' |
    tar -C "$out/zh_CN" -xf -

for name in lan.js help.js; do
    [ -s "$out/zh_CN/$name" ] || continue
    swift "$here/convert.swift" "$out/zh_CN/$name" "$out/zh_CN/$name.tmp"
    mv "$out/zh_CN/$name.tmp" "$out/zh_CN/$name"
done

echo "Generated zh_CN language resources in $out/zh_CN"
