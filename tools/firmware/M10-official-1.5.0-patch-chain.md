# M10 — Reproducible official-base patch chain (2026-11-03)

## Source of truth

The real **Archer AX12 RU v1.0 official 1.5.0 Build 20260605** encrypted BIN (15,379,164 bytes, SHA256 `50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`) was independently vendor RSA-PSS verified and AES decrypted using a public verifier extracted from the **original** AX12 1.5.0 RootFS. The official RootFS had 2,304 files+symlinks.

## Exact 1.5.1 patch surface

- Adds five: `etc/dropbear/authorized_keys`, `etc/rc.d/S99zzzzzzzzssh`, `etc_ro/init.d/ax12-ssh`, `root/.ssh/authorized_keys`, and `www/webpages/locale/zh_CN/index-AX12r2.js.gz`.
- Changes only three: `usr/lib/libnvrammanager.so` (owner RSA-2048), `www/cgi-bin/luci` (0755 + `zh_CN` locale binding), `www/webpages/js/update-store-DnZhtCy9.js.gz` (language loader).
- Changes Cloud kernel `cr6c→cs6c` for previously verified Bootloader compatibility; excludes `fs-uboot` from update manifest; updates soft-version to 1.5.1.
- Applies all changes to a **freshly extracted** official 1.5.0 RootFS, never an owner baseline.

## 1.5.2 kernel proof

The script `patch_wan_port1.py` changes MIPS instruction at `0x80be5548` from `BNE 0x14450023` to `NOP`. Recompression, Realtek checksum and `cs6c` boot bridge applied to pristine official 1.5.0 yields **exactly** the kernel from hardware-successful 1.5.2, SHA256 `773b66e574a11b4cf6ce8962f83541272df69a0e0cc0084571a104ed5b2400f8`.

## 1.5.3 locale

The patch adds `zh_CN/index-AX12r3.js.gz` and replaces `update-store-DnZhtCy9.js.gz`. Initial packaging audit caught file mode incorrectly carried as 0600 from the development host; patch now explicitly preserves the previous resource mode. 2,713 language keys, 1,080 updated strings, preserved JS placeholders.

## Actual completed build tests

- `python3 build.py --official <exact-file> --version 1.5.1`: **PASS** full unsigned Cloud build.
- `python3 build.py --official <exact-file> --version 1.5.2`: **PASS** full unsigned Cloud build; 5 RootFS files added and 3 changed; full file-level content/mode comparison to known-good hardware-tested 1.5.2 is exact.
- `python3 build.py --official <exact-file> --version 1.5.3`: **PASS** full unsigned Cloud build; 6 files added and 3 changed from pristine 1.5.0; Chinese v3 resource mode corrected; RootFS 11,509,763 bytes, headroom 24,573 bytes.

All 3 emit unsigned Cloud images and owner RSA-PSS encoded messages; AES roundtrip, manifest, mtd size, kernel patch and excludes Bootloader writes PASS. The newly built BIN files are **unsigned**, not independently boot tested, and not suitable for flashing without completed signing and recovery checks.

## Additional complete signed dry run (throwaway key)

The new `--sign-key` flow was executed with a newly generated disposable RSA-2048 key pair, with the official 1.5.0 firmware as input. The pipeline rebuilt the 1.5.1→1.5.2→1.5.3 patch chain, signed the pre-encoded RSA-PSS EM, passed signature verification, AES decryption and sealed RootFS extraction, and compared the signed plaintext to the patched plaintext outside the signature slot. **PASS.** This disposable-key signed image is not the owner's trusted firmware and must not be flashed. No owner private key was accessed for this test.
