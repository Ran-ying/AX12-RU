"""Owner 1.5.1: simplified Chinese r2 and Web locale registration."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CGI_ORIGINAL = b'#!/usr/bin/lua\nrequire "luci.cacheloader"\nrequire "luci.sgi.cgi"\nluci.dispatcher.indexcache = "/tmp/luci-indexcache"\nluci.sgi.cgi.run()'
CGI_INSERT = b'local locale = require "luci.controller.locale"\nlocal _, allowed = debug.getupvalue(locale.set_sysinfo, 4)\nallowed.zh_CN = allowed.zh_TW\n'


def apply(rootfs):
    cgi = rootfs / 'www/cgi-bin/luci'
    if cgi.read_bytes() != CGI_ORIGINAL or cgi.stat().st_mode & 0o777 != 0o755:
        raise ValueError('Expected 1.5.0 CGI and executable permission')
    cgi.write_bytes(CGI_ORIGINAL.replace(b'require "luci.sgi.cgi"\n',
                                          b'require "luci.sgi.cgi"\n' + CGI_INSERT))

    for relative, mode in (
        ('www/webpages/locale/zh_CN/index-AX12r2.js.gz', 0o600),
        ('www/webpages/js/update-store-DnZhtCy9.js.gz', 0o700),
    ):
        source = ROOT / 'assets/1.5.1' / relative
        dest = rootfs / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        dest.chmod(mode)
    print('APPLIED owner 1.5.1: zh_CN r2, CGI locale registration and JS loader')
