#!/usr/bin/env python3
"""Apply confirmed AX12 owner firmware fixes to a copied 1.5.0 RootFS."""
import gzip
from pathlib import Path
import sys
from opencc import OpenCC

root = Path(sys.argv[1])
web = root / "www/webpages"

source = web / "locale/zh_TW/index-D4zcoeEt.js.gz"
locale_dir = web / "locale/zh_CN"
locale_dir.mkdir(exist_ok=True)
target_name = "index-AX12r2.js"
translation = OpenCC("t2s").convert(gzip.decompress(source.read_bytes()).decode("utf-8"))
assert "export" in translation and "無線" not in translation
with (locale_dir / (target_name + ".gz")).open("wb") as f:
    f.write(gzip.compress(translation.encode("utf-8"), mtime=0))

chunk = web / "js/update-store-DnZhtCy9.js.gz"
js = gzip.decompress(chunk.read_bytes()).decode("utf-8")
old = '"./langs/zh_TW/index.ts":()=>_e(()=>import("../locale/zh_TW/index-D4zcoeEt.js"),[],import.meta.url)'
new = '"./langs/zh_CN/index.ts":()=>_e(()=>import("../locale/zh_CN/' + target_name + '"),[],import.meta.url),' + old
assert js.count(old) == 1
js = js.replace(old, new)
before = 't.value=l.map(u=>({label:Kl[u.name]||"",value:u.value}))'
after = before + ';t.value.some(u=>u.value==="zh_CN")||t.value.push({label:"简体中文",value:"zh_CN"})'
assert js.count(before) == 1
js = js.replace(before, after)
chunk.write_bytes(gzip.compress(js.encode("utf-8"), mtime=0))
print("PASS: Simplified Chinese locale full module and language selector integration")
print("Translation bytes:", len(translation.encode("utf-8")))
print("Added path:", locale_dir / (target_name + ".gz"))
