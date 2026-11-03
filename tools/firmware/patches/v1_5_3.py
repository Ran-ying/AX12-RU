"""1.5.3: mainland Chinese networking terminology, preserving JS module contract."""
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_CHUNK_SHA = 'b3552388b8c4'


def apply(rootfs):
    original = rootfs / 'www/webpages/js/update-store-DnZhtCy9.js.gz'
    if not hashlib.sha256(original.read_bytes()).hexdigest().startswith(BASE_CHUNK_SHA):
        raise ValueError('1.5.3 expects the 1.5.1 locale loader')
    if not (rootfs / 'www/webpages/locale/zh_CN/index-AX12r2.js.gz').exists():
        raise ValueError('1.5.1 Chinese locale missing')
    for relative in ('www/webpages/locale/zh_CN/index-AX12r3.js.gz',
                     'www/webpages/js/update-store-DnZhtCy9.js.gz'):
        source = ROOT / 'assets/1.5.3' / relative
        target = rootfs / relative
        existing = target if target.exists() else rootfs / "www/webpages/locale/zh_CN/index-AX12r2.js.gz"
        mode = existing.stat().st_mode & 0o777
        shutil.copy2(source, target)
        target.chmod(mode)
    print('APPLIED 1.5.3: zh_CN r3 and matching JS loader')
