"""Owner 1.5.3: Simplified Chinese default with an English switch and no other languages.

Vite edits must match exact known original snippets. No device access.
"""
import gzip
import shutil
from pathlib import Path

WEB = Path('www/webpages')


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'Expected exactly one matching compiled JS snippet: {old[:72]!r}')
    return source.replace(old, new, 1)


def edit_js(rootfs, filename, transform):
    path = rootfs / WEB / 'js' / filename
    original = gzip.decompress(path.read_bytes()).decode('utf-8')
    updated = transform(original)
    if updated == original:
        raise ValueError(f'No changes applied to {filename}')
    mode = path.stat().st_mode & 0o777
    path.write_bytes(gzip.compress(updated.encode('utf-8'), compresslevel=9, mtime=0))
    path.chmod(mode)


def update_store(content):
    # On upgrades the old backend may retain a third-party language; migrate it to zh_CN.
    content = replace_once(content,
        'a.value=l.locale,e.force=l.force,e.productModel=l.model',
        'a.value=l.locale==="en_US"?"en_US":"zh_CN",e.force=l.force,e.productModel=l.model')
    content = replace_once(content, 'await Fs(l.locale)', 'await Fs(a.value)')
    content = replace_once(content,
        'i=async()=>{if(t.value.length===0){const l=await sc();t.value=l.map(u=>({label:Kl[u.name]||"",value:u.value}));t.value.some(u=>u.value==="zh_CN")||t.value.push({label:"简体中文",value:"zh_CN"})}}',
        'i=async()=>{t.value=[{label:"简体中文",value:"zh_CN"},{label:"English",value:"en_US"}]}')
    start = 'Object.assign({"./langs/ar_AR/index.ts"'
    end = '),`./langs/${e}/index.ts`,4)'
    if content.count(start) != 1 or content.count(end) != 1:
        raise ValueError('Unexpected original Vite dynamic-import locale table')
    a = content.index(start)
    b = content.index(end, a + len(start))
    replacements = ('Object.assign({'
        '"./langs/en_US/index.ts":()=>_e(()=>Promise.resolve().then(()=>Hl),void 0,import.meta.url),'
        '"./langs/zh_CN/index.ts":()=>_e(()=>import("../locale/zh_CN/index-AX12r3.js"),[],import.meta.url)}')
    return content[:a] + replacements + content[b:]


def apply(rootfs):
    config = rootfs / 'etc/config/locale'
    s = config.read_text()
    s = replace_once(s, "option default 'en_US'", "option default 'zh_CN'")
    s = replace_once(s, "option locale  'en_US'", "option locale  'zh_CN'")
    config.write_text(s)

    edit_js(rootfs, 'update-store-DnZhtCy9.js.gz', update_store)

    # Preserve factory reset defaults and update once from an existing 1.5.2 English config.
    startup = rootfs / 'etc_ro/init.d/ax12-owner-locale'
    startup.write_text('''#!/bin/sh /etc/rc.common
START=95

start() {
    [ "$(uci -q get locale.sysinfo.owner_153_locale_init)" = "1" ] && return
    uci set locale.sysinfo.default='zh_CN' &&
    uci set locale.sysinfo.locale='zh_CN' &&
    uci set locale.sysinfo.force='false' &&
    uci set locale.sysinfo.owner_153_locale_init='1' &&
    uci commit locale
}
''')
    startup.chmod(0o755)
    (rootfs / 'etc/rc.d/S95ax12-owner-locale').symlink_to('../init.d/ax12-owner-locale')

    locale_dir = rootfs / WEB / 'locale'
    removed = []
    for folder in locale_dir.iterdir():
        if folder.name != 'zh_CN':
            removed.append(folder.name)
            shutil.rmtree(folder)
    (locale_dir / 'zh_CN/index-AX12r2.js.gz').unlink()

    # Keep LuCI's minimal English fallback and Chinese firewall translations.
    i18n = rootfs / 'usr/lib/lua/luci/i18n'
    for file in i18n.iterdir():
        if file.name not in ('base.en.lmo', 'firewall.zh-cn.lmo'):
            file.unlink()
    print(f'APPLIED 1.5.3: zh_CN default + en_US switch; removed {len(removed)} unused Web locale directories')
