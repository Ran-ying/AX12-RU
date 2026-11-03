# AX12 RU v1.0 — offline owner firmware reproduction

## Inputs included

- `firmware/AX12-RU-1.5.2-owner-signed-WAN1.bin` is the device-tested 1.5.2 owner-signed Cloud baseline, SHA256 `1c8905d500e77cc5fc04addfb355aea4ec49d9bd67dccfe953f097eb46051136`, 15,416,028 bytes.
- `keys/ax12_owner_2026_public.pem` is the exact RSA-2048 public verifier key from that baseline.
- `tools/firmware/overlays/zh_cn_v3/` contains the corrected zh_CN language module and updated Vite lazy import mapping.
- `tools/firmware/locale/build_zh_cn_v3.js` and corresponding JSON/TSV can regenerate and audit the language module from the extracted 1.5.2 RootFS.
- `tools/firmware/patch_wan_port1.py` reproduces the proven BNE→NOP change in the original unpatched Realtek kernel; building from the included 1.5.2 baseline already includes it, so **do not apply the patch a second time**.

## Prerequisites

Ubuntu/Debian: `sudo apt-get install squashfs-tools python3 python3-pip` and `python3 -m pip install cryptography` in a virtual environment. `node` is needed only to regenerate the translation resources. The current baseline has SquashFS 4.0 XZ with 262,144-byte blocks. Use a new empty work directory.

## Build unsigned 1.5.3

```bash
python3 tools/firmware/build_owner_153.py \
  --baseline firmware/AX12-RU-1.5.2-owner-signed-WAN1.bin
```

Output files (all under ignored `build/ax12-1.5.3`): `rootfs.sqfs`, `rootfs.sealed`, `unsigned-1.5.3.bin`, `em-for-owner-signing.bin`. The script checks the exact base SHA, owner public signature, unchanged WAN-patched kernel, no Bootloader update entry, `mtd2` budget, and AES roundtrip.

## Finish signing on a trusted owner machine

Use the owner-controlled RSA-2048 signing key locally. The key is not required on a cloud builder. On macOS with LibreSSL, use raw RSA on the **already-encoded** 256-byte PSS EM; do not apply hashing/PSS padding twice:

```bash
openssl rsautl -sign -raw -inkey ~/.ssh/ax12_owner_2026 \
  -in build/ax12-1.5.3/em-for-owner-signing.bin \
  -out build/ax12-1.5.3/owner-signature.big
python3 tools/firmware/finalize_owner_cloud.py \
  build/ax12-1.5.3/unsigned-1.5.3.bin \
  build/ax12-1.5.3/owner-signature.big \
  keys/ax12_owner_2026_public.pem \
  build/ax12-1.5.3/rootfs.sealed \
  build/AX12-RU-1.5.3-owner-signed-zhCNv3.bin
```

If building on separate machines, transfer the 256-byte EM to the owner computer and only the 256-byte signature back, and run the finalizer where the unsigned package and sealed RootFS are stored. The finalizer checks RSA-PSS, AES decrypt, manifest, and RootFS bytes.

The 1.5.3 package has **not** been booted or tested on the AX12; the owner must choose when to perform a supervised upgrade and rollback test.

## Rebuild locale resources

```bash
node tools/firmware/locale/build_zh_cn_v3.js \
  build/ax12-1.5.3/rootfs/www/webpages \
  build/recreated-zh-cn-v3
```

This will use the original `zh_CN/index-AX12r2.js.gz` inside the extracted baseline. On the 2026-11-03 dataset it preserves 2,713 keys and all placeholders and changes 1,080 values. This is terminology-standardized and substantially improved, but **not** 2,713 individually human-reviewed translations. The checked-in overlay is the reviewed build input; further changes require visual and syntax validation.
