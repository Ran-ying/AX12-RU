#!/usr/bin/env python3
"""Audit a built 1.5.3 RootFS: zh_CN default, English selectable, no other Web packs."""
import argparse
import gzip
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rootfs', type=Path)
    root = p.parse_args().rootfs

    locale = root / 'www/webpages/locale'
    assert {d.name for d in locale.iterdir()} == {'zh_CN'}
    assert {p.name for p in (locale / 'zh_CN').iterdir()} == {'index-AX12r3.js.gz'}
    assert {p.name for p in (root / 'usr/lib/lua/luci/i18n').iterdir()} == {
        'base.en.lmo', 'firewall.zh-cn.lmo',
    }
    config = (root / 'etc/config/locale').read_text()
    for line in ("option force   'false'", "option default 'zh_CN'", "option locale  'zh_CN'"):
        assert line in config

    startup = root / 'etc_ro/init.d/ax12-owner-locale'
    service = startup.read_text()
    assert startup.stat().st_mode & 0o777 == 0o755
    assert (root / 'etc/rc.d/S95ax12-owner-locale').readlink().as_posix() == '../init.d/ax12-owner-locale'
    for snippet in ('locale.sysinfo.locale', 'locale.sysinfo.default',
                    'locale.sysinfo.force', 'locale.sysinfo.owner_153_locale_init', 'uci commit locale'):
        assert snippet in service

    js = root / 'www/webpages/js'
    def read(name):
        return gzip.decompress((js / name).read_bytes()).decode('utf-8')

    store = read('update-store-DnZhtCy9.js.gz')
    assert 'await Fs(a.value)' in store
    assert 'a.value=l.locale==="en_US"?"en_US":"zh_CN"' in store
    assert 't.value=[{label:"简体中文",value:"zh_CN"},{label:"English",value:"en_US"}]' in store
    assert 'changeLanguage:async(l,u)=>{await lc(l,u),a.value=l,Fs(l)}' in store
    assert '../locale/zh_CN/index-AX12r3.js' in store
    assert './langs/en_US/index.ts' in store
    assert '../locale/zh_TW/' not in store
    assert 'Promise.resolve().then(()=>Hl)' in store

    # Preserve all three language selectors and their original API-backed change handlers.
    assert 'pcCurrentLanguageSelect' in read('index-HhSH241k.js.gz')
    assert 'mobileCurrentLanguageSelect' in read('index-HhSH241k.js.gz')
    assert 'changeLangBtn' in read('index-DtHn6Ijf.js.gz')
    assert '__name:"Language"' in read('index-MrF7bc_q.js.gz')
    print('PASS: zh_CN default, en_US selectable, 27 other Web locales removed')
    print('PASS: original 3 UI language selectors and backend UCI migration present')


if __name__ == '__main__':
    main()
