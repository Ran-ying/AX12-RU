# TP-Link Archer AX12(RU) V1 — original 1.5.0 firmware provenance

Product: **Archer AX12(RU), hardware v1.0**, official firmware **1.5.0 Build 20260605 Rel. 41062**. TP-Link publication date: **2026-06-09**. This is the original immutable build input, not the custom 1.5.1/1.5.2/1.5.3 release.

- Official RU firmware listing on TP-Link Kazakhstan support: https://www.tp-link.com/kz/support/download/archer-ax12/v1.80/
- **Direct original ZIP (TP-Link static CDN):** https://static.tp-link.com/upload/firmware/2026/202606/20260609/ver1-5-0-P1%5B20260605-rel41062%5D.zip
- ZIP size: **15,850,056 bytes**.
- ZIP SHA-256: `45374b326f5bcada7fb7b297ebf8cd140a5d384c8288310603ba60a414c06a6a`.
- Embedded BIN filename: `ver1-5-0-P1[20260605-rel41062]_2026-06-04_20.24.42.bin`.
- BIN size: **15,379,164 bytes**.
- BIN SHA-256: `50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`.

## Verified retrieval

The official support page was checked on **2026-11-03**. The exact linked ZIP was downloaded from `static.tp-link.com`, opened as a ZIP, and its embedded BIN's SHA-256 checked **identical to the vendor-RSA-verified, AES-decrypted official 1.5.0 input used for this project's successful offline builds**. The package also contains TP-Link upgrade instructions and GPL license terms.

A clean Linux/macOS setup can obtain the correct input with:

```sh
mkdir -p inputs
curl -fL 'https://static.tp-link.com/upload/firmware/2026/202606/20260609/ver1-5-0-P1%5B20260605-rel41062%5D.zip' -o inputs/ax12-ru-1.5.0.zip
python3 - <<'PY'
from pathlib import Path
from zipfile import ZipFile
import hashlib
archive = Path('inputs/ax12-ru-1.5.0.zip')
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '45374b326f5bcada7fb7b297ebf8cd140a5d384c8288310603ba60a414c06a6a'
with ZipFile(archive) as z:
    data = z.read('ver1-5-0-P1[20260605-rel41062]_2026-06-04_20.24.42.bin')
assert hashlib.sha256(data).hexdigest() == '50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9'
Path('inputs/official-1.5.0.bin').write_bytes(data)
print('PASS: official AX12 RU 1.5.0 verified; build input ready')
PY
```

The source ZIP and extracted BIN are under the ignored `inputs/` directory. Do not replace the input with a different AX12 country variant or release just because the filename/version looks similar. The `build.py` pipeline itself checks the exact BIN SHA-256 and original TP-Link RSA-PSS signature before applying patches.

## Firmware lineage

The router initially ran **1.1.22 Build 20240311**, not `1.1.12`. The **official 1.5.0 is the build source**, not proof it can safely be uploaded unchanged from that old system. Read [first migration](../tools/firmware/FIRST_MIGRATION_1.1.22.md) for the actual successful owner-signed, Bootloader-preserving transition and the difference between historical UART recovery and the temporary RAM upgrade verifier.
