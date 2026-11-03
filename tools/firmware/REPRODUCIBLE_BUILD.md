# AX12 RU v1 — Build strictly from official 1.5.0 plus versioned patches

The immutable source input is the **pristine official firmware**. The owner-signed 1.5.2 image is kept as a hardware-tested reference, never as the base for new releases.

## 1. Obtain exact official firmware

Obtain `Archer AX12(RU) v1.0 1.5.0 Build 20260605 Rel.41062` from TP-Link's regional support distribution. The exact firmware extracted in this project is named:

`ver1-5-0-P1[20260605-rel41062]_2026-06-04_20.24.42.bin`

It has size **15,379,164 bytes**, SHA-256:

`50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`

Save it locally as `inputs/official-1.5.0.bin` (this file is not required to be checked into Git). **RU vs EU/US packages are not interchangeable just because their version strings match**. The build rejects any file with a different digest.

The original verification *public* key is `keys/tplink_official_verifier_public.pem`, extracted from the original official vendor library and tested against the original Cloud signature. The owner public key is `keys/ax12_owner_2026_public.pem`.

## 2. Build the selected custom version

On Linux:

```sh
sudo apt-get install squashfs-tools python3 python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install cryptography
python3 build.py --version 1.5.3
# Equivalent explicit input: python3 build.py --official inputs/official-1.5.0.bin --version 1.5.3
```

Possible versions: **1.5.1, 1.5.2, 1.5.3**. The patches are applied from 1.5.1 through the selected target, never by incremental mutation of an already customized firmware image.

| Patch | Contents | File |
|---|---|---|
| 1.5.1 | owner RSA verifier library, LAN SSH service, Chinese r2 Web interface, executable CGI, cs6c Bootloader bridge, omit U-Boot update | `tools/firmware/patches/v1_5_1.py` and assets |
| 1.5.2 | WAN port1 ASIC/VLAN MIPS BNE→NOP, kernel compressed wrapper and checksum | `tools/firmware/patches/v1_5_2.py`, `patch_wan_port1.py` |
| 1.5.3 | Chinese v3 terminology improvements and lazy loader | `tools/firmware/patches/v1_5_3.py` and assets |

The `--workdir` defaults to `build/ax12-from-official-<version>/`; outputs: fresh `rootfs/`, `rootfs.sqfs`, `rootfs.sealed`, `unsigned.bin` and `em-for-owner-signing.bin`. `unsigned.bin` is **NOT flashable**.

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
