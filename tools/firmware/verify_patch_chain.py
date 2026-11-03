#!/usr/bin/env python3
"""Check patch effects across four extracted build workdirs; never flashes hardware."""
import argparse
import hashlib
from pathlib import Path


def files(root):
    result = {}
    for f in root.rglob('*'):
        if f.is_file() or f.is_symlink():
            result[str(f.relative_to(root))] = (
                f.readlink().as_posix() if f.is_symlink() else hashlib.sha256(f.read_bytes()).hexdigest(),
                f.lstat().st_mode & 0o777,
            )
    return result


def differences(a, b):
    return {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for version in ('150', '151', '152', '153'):
        p.add_argument('--workdir-' + version, required=True, type=Path)
    p.add_argument('--known-good-rootfs', type=Path,
                   help='Optional hardware-tested owner 1.5.2 RootFS')
    args = p.parse_args()
    variants = {version: files(getattr(args, 'workdir_' + version) / 'rootfs')
                for version in ('150', '151', '152', '153')}
    expected_151 = {
        'www/cgi-bin/luci', 'www/webpages/js/update-store-DnZhtCy9.js.gz',
        'www/webpages/locale/zh_CN/index-AX12r2.js.gz',
    }
    expected_153 = {
        'etc/config/locale',
        'www/webpages/js/update-store-DnZhtCy9.js.gz',
        'etc_ro/init.d/ax12-owner-locale',
        'etc/rc.d/S95ax12-owner-locale',
        'www/webpages/locale/zh_CN/index-AX12r2.js.gz',
        'www/webpages/locale/zh_CN/index-AX12r3.js.gz',
    }
    expected_153.update(
        k for k in variants['152']
        if (k.startswith('www/webpages/locale/') and
            not k.startswith('www/webpages/locale/zh_CN/'))
        or (k.startswith('usr/lib/lua/luci/i18n/') and
            k.rsplit('/', 1)[-1] not in ('base.en.lmo', 'firewall.zh-cn.lmo'))
    )
    assert differences(variants['150'], variants['151']) == expected_151
    assert differences(variants['151'], variants['152']) == set()
    assert differences(variants['152'], variants['153']) == expected_153
    if args.known_good_rootfs:
        reference = files(args.known_good_rootfs)
        assert variants['151'] == reference
        assert variants['152'] == reference
    print('PASS: 1.5.0→1.5.1 changes only CGI/locale/loader')
    print('PASS: 1.5.1→1.5.2 leaves RootFS unchanged; WAN fix is kernel-only')
    print('PASS: 1.5.2→1.5.3 keeps zh_CN/en_US, migrates locale default and removes obsolete translations')
    if args.known_good_rootfs:
        print('PASS: 1.5.1 and 1.5.2 RootFS match hardware-tested reference')


if __name__ == '__main__':
    main()
