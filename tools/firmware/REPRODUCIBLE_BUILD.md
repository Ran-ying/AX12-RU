# AX12 RU v1 — Build strictly from official 1.5.0 plus versioned patches

The immutable source input is the **pristine official firmware**. The owner-signed 1.5.2 image is kept as a hardware-tested reference, never as the base for new releases.

## 1. Obtain exact official firmware

Obtain `Archer AX12(RU) v1.0 1.5.0 Build 20260605 Rel.41062` from TP-Link's regional support distribution. The exact firmware extracted in this project is named:

`ver1-5-0-P1[20260605-rel41062]_2026-06-04_20.24.42.bin`

It has size **15,379,164 bytes**, SHA-256:

`50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`

- **Direct TP-Link RU 1.5.0 ZIP:** https://static.tp-link.com/upload/firmware/2026/202606/20260609/ver1-5-0-P1%5B20260605-rel41062%5D.zip
- **Official regional firmware list:** https://www.tp-link.com/kz/support/download/archer-ax12/v1.80/
- **Verified ZIP SHA-256:** `45374b326f5bcada7fb7b297ebf8cd140a5d384c8288310603ba60a414c06a6a` (ZIP size 15,850,056 bytes). On 2026-11-03 the embedded BIN digest exactly matched the verified build baseline.
- Download/unpack/check instructions: [Official 1.5.0 source record](../../firmware/OFFICIAL-1.5.0.sources.md).

Save it locally as `inputs/official-1.5.0.bin` (this file is not required to be checked into Git). **RU vs EU/US packages are not interchangeable just because their version strings match**. The build rejects any file with a different digest.

The original verification *public* key is `keys/tplink_official_verifier_public.pem`, extracted from the original official vendor library and tested against the original Cloud signature. The owner public key is `keys/ax12_owner_2026_public.pem`.

## 2. Build the selected custom version

On Linux:

```sh
sudo apt-get install squashfs-tools python3 python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install cryptography
python3 build.py --version 1.5.0  # Only owner trust, SSH and boot bridge
python3 build.py --version 1.5.3  # All four patch levels
# Equivalent explicit input: python3 build.py --official inputs/official-1.5.0.bin --version 1.5.3
```

Possible versions: **1.5.0, 1.5.1, 1.5.2, 1.5.3**. The patches are applied from owner 1.5.0 through the selected target, never by incremental mutation of an already customized firmware image.

| Patch | Contents | File |
|---|---|---|
| 1.5.0 | owner RSA verifier, LAN root SSH, executable CGI, cs6c boot bridge, omit U-Boot update | `tools/firmware/patches/v1_5_0.py` and shared builder |
| 1.5.1 | zh_CN r2, Web CGI locale registration and language loader | `tools/firmware/patches/v1_5_1.py` and assets |
| 1.5.2 | WAN port1 ASIC/VLAN MIPS BNE→NOP, kernel compressed wrapper and checksum | `tools/firmware/patches/v1_5_2.py`, `patch_wan_port1.py` |
| 1.5.3 | Chinese v3; zh_CN default, selectable en_US; remove 27 unused Web locale packs; one-time UCI migration | `tools/firmware/patches/v1_5_3.py`, `zh_cn_en.py` and assets |

The `--workdir` defaults to `build/ax12-from-official-<version>/`; outputs: fresh `rootfs/`, `rootfs.sqfs`, `rootfs.sealed`, `unsigned.bin` and `em-for-owner-signing.bin`. `unsigned.bin` is **NOT flashable**.

The minimal custom 1.5.0 is **not byte-identical to the historical first-flashed custom 1.5.0**, which also included early Chinese UI adjustments. Its soft-version text is the same as stock 1.5.0, so identify it by signer/key, file hash and build provenance—not the displayed version string alone. Neither the newly rebuilt custom 1.5.0 nor 1.5.3 has been approved by live boot tests. See [M12 refactor regression](M12-owner-1.5.0-versioned-refactor.md).

The builder verifies the official SHA and RSA-PSS signature, decrypts AES, validates vendor verifier bytes, checks the patch file-level diff, applies the known-good WAN kernel patch, checks the real RootFS/Flash limits, rewrites the Cloud manifest and version, drops the U-Boot write entry, re-encrypts and prepares a new PSS EM. The gzip/mksquashfs output may vary in nondeterministic metadata, so **do not compare encrypted BIN SHA values across builds**; compare original input hashes, target inner kernel, file-level RootFS content, and final RSA/AES/partition verification.

## 3. Sign and finalize

Optional integrated sign-on-the-same-machine mode (explicitly opt in):

```sh
python3 build.py --version 1.5.3 --sign-key keys/ax12_owner_2026_private.pem
```

This signs using the matching private key **locally in the executing process**, never copies the private key to another host, and verifies the signed package before writing the final file to `build/ax12-from-official-1.5.3/AX12-RU-1.5.3-owner-signed.bin`. No router access is performed. If the private key is on another host, prefer the manual separated signing flow below.


The repository's code does not automatically read any signing private key. For a 256-byte already PSS-encoded EM, macOS LibreSSL supports a raw RSA operation:

```sh
openssl rsautl -sign -raw \
  -inkey ~/.ssh/ax12_owner_2026 \
  -in build/ax12-from-official-1.5.3/em-for-owner-signing.bin \
  -out build/ax12-from-official-1.5.3/owner-signature.big

python3 tools/firmware/finalize_owner_cloud.py \
  build/ax12-from-official-1.5.3/unsigned.bin \
  build/ax12-from-official-1.5.3/owner-signature.big \
  keys/ax12_owner_2026_public.pem \
  build/ax12-from-official-1.5.3/rootfs.sealed \
  build/AX12-RU-1.5.3-owner-signed.bin
```

If building/signing on separate computers, transfer only the EM/signature between them. The finalizer verifies RSA-PSS, AES decryption and the sealed RootFS. Inspect kernel and manifest before considering an upgrade. Keep the proven 1.5.2 firmware as rollback.

## 4. Baseline-independent validation

The following **were executed** from the original official 1.5.0 image on 2026-11-03:

- 1.5.1 unsigned Cloud with correctly patched owner verifier, SSH, Web + zh_CN r2: PASS.
- 1.5.2 unsigned Cloud, patched kernel SHA-256 `773b66e574a11b4cf6ce8962f83541272df69a0e0cc0084571a104ed5b2400f8` **byte-identical to known-good 1.5.2 kernel**; extracted RootFS paths, byte hashes, symlinks and modes identical to hardware-tested 1.5.2: PASS.
- 1.5.3 unsigned Cloud with zh_CN r3: PASS; previous 1.5.2 files retained and exactly two expected additions/changes in JS resources. RootFS **11,509,763 bytes**, leaving **24,573 bytes** under `0xB00000`.

Neither the newly built 1.5.3 nor a rebuilt 1.5.2 Cloud has been reflashed for live verification. The older `tools/firmware/build_owner_153.py` remains only as a legacy compatibility experiment and must not replace this official-base workflow.

## Initial 1.1.22 migration is a separate historical workflow

The original physical device started on **1.1.22 Build 20240311**, not 1.1.12. First migration used UART for backup and early SSH provisioning, a **RAM-only owner-public-key-patched `nvrammanager`** for its first owner-signed Cloud upgrade, and a persistent owner verifier embedded in the new 1.5.0 RootFS. **No blanket UART rewrite of the complete Flash to install a public key was needed for that actual first major-version upgrade.** The original Bootloader was preserved, with `cs6c` and no `fs-uboot` write entry. Do not conflate this with an untested direct 1.1.22→1.5.2 update. See [FIRST_MIGRATION_1.1.22.md](FIRST_MIGRATION_1.1.22.md) and [M6 real hardware record](M6-first-flash-2026-11-03.md).

## Starting on original vendor 1.1.22 is a separate migration

If the AX12 is still running vendor **1.1.22 Build 20240311**, first follow the [staged, hardware-gated migration guide](MIGRATE_STOCK_1.1.22_TO_OWNER.md). It covers old-RootFS SSH bootstrap, UART backup/write verification, RAM-only old upgrader public-key patching and the special self-signed 1.5.0 first upgrade with `cs6c` and no U-Boot write. The versioned `build.py` is intended for a system whose persistent updater already trusts the owner's key; it does **not** prove the old factory upgrader accepts direct 1.1.22→1.5.3. The new bootstrap helper and first-upgrade signing tooling have independently passed synthetic/offline tests (see [M11](M11-migration-kit-offline-tests.md)); the direct one-step 1.1.22→1.5.3 route and 1.5.3 real boot remain **untested**.

## Version split verification (M12)

The new `v1_5_0.py` isolates the initial owner trust and SSH layer. `v1_5_1.py` now only applies locale/Web language changes. The Cloud PSS/AES preparation code lives in `cloud_signing.py`, independent of the legacy `build_owner_153.py`. All four targets passed full offline builds and disposable-key RSA-PSS signing and AES decrypt checks. The 1.5.1 and 1.5.2 extracted RootFS trees are byte-for-byte/file-mode/symlink equivalent to the proven 1.5.2 RootFS. To re-run the file-level regression after building all four versions:

```sh
python3 tools/firmware/verify_patch_chain.py \
  --workdir-150 build/ax12-from-official-1.5.0 \
  --workdir-151 build/ax12-from-official-1.5.1 \
  --workdir-152 build/ax12-from-official-1.5.2 \
  --workdir-153 build/ax12-from-official-1.5.3
```

Optionally pass `--known-good-rootfs PATH` when an independent, locally extracted trusted 1.5.2 RootFS is available. Do not commit original extracted vendor files or device Flash.

## M13 1.5.3 bilingual-only RootFS size optimization

The latest 1.5.3 is **not** the original M9/M12 multi-language dry-run build. It keeps `zh_CN` as the default and `en_US` as an explicit setting, retains all existing language selectors, uses the built-in English dictionary and removes 27 other Web language directories. Default `/etc/config/locale` is now `zh_CN`, and an `S95` one-shot UCI boot hook migrates the inherited 1.5.2 English default exactly once while preserving subsequent intentional choices. `verify_bilingual.py` checks those invariants. **Exact RootFS size 10,121,219 bytes, 1,413,117 bytes free** (saving 1,388,544 bytes vs the historical 1.5.3 with all locales). All values were measured after SquashFS + Realtek sealing, not merely summed asset sizes.

See [M13](M13-1.5.3-zh_CN-en_US-flash-optimization.md) for tests and limitations. 1.5.3 remains **unsigned by default**, and has *not* received actual router boot or factory-reset acceptance testing. The prior 11,509,763-byte M9/M12 numbers describe the **previous** multilingual 1.5.3 design.
