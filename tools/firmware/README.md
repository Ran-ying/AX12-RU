# Archer AX12(RU) V1 firmware format notes (2026-11-02)

Read-only offline firmware research. On 2026-11-02, AX12 RU V1 1.5.0 **was successfully decrypted and its SquashFS extracted**. No router firmware upgrade, flash write or device reboot was performed.

## Official packages compared

- **Installed generation:** `1.1.22 Build 20240311` (official package); BIN length 13,850,616 bytes; SHA256 `98c5b0224a0df2379587998b339995e972fc2b2fbb7512a9c63bd02d88019d3f`.
- **RU latest on the official page (checked 2026-11-02):** `1.5.0 Build 20260605`, published 2026-06-09; BIN length 15,379,164 bytes; SHA256 `50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`.
- Official download page: https://www.tp-link.com/kz/support/download/archer-ax12/ . Only RU V1 packages are in scope; EU, US or TW images are not interchangeable without platform-specific verification.

Both use a TP-Link Cloud-style preamble: first four bytes represent big-endian file size, bytes `0x14...` begin `fw-type:Cloud\n`. The 16-byte field at `0x04` was **not** verified as a plain MD5 digest; do not assume a checksum formula.

## Major structural change

- **1.1.22:** At file offset `0x1014`, an ASCII `fwup-ptn ...` manifest is readable. The manifest lists `os-image`, `file-system`, `re-def-config`, etc. At `0x1818`, the plaintext Flash partition table starts with `partition fs-uboot base ...`.
- **1.5.0:** The corresponding offsets contain high-entropy bytes and do not contain the plaintext manifests. Its header region starting around `0x1C0` also changed. This is the RSA-2048/AES protected Cloud upgrade format. Offline verification and decryption have now succeeded with a vendor RSA public key from the AX12 16 MiB Flash image and the open-source `robbins/tp-link-decrypt` implementation.
- **Related research, not an AX12-specific method:** https://github.com/akm-04/tp-link-ax53-fw-hacks documents other TP-Link Cloud devices using firmware decryption routines in `nvrammanager`, sometimes under QEMU. Do not run any upgrade operation on the AX12 while investigating.

Reproduce the inspection:

```sh
python3 tools/firmware/inspect_cloud.py "/path/to/official-Archer-AX12.bin"
```

The older official image advertises these *physical Flash* areas (units hexadecimal bytes), among others:

| Region | Offset | Size |
|---|---:|---:|
| `fs-uboot` | `0x000000` | `0x040000` |
| `os-image` | `0x040000` | `0x400000` |
| `file-system` | `0x440000` | `0xAC8000` |
| `user-config` | `0xF70000` | `0x020000` |
| `router-config` | `0xFB0000` | `0x020000` |
| `radio` | `0xFF0000` | `0x010000` |

These are **not free space**; configuration and calibration data may live there. Never overwrite them to store UI patches. Do not confuse this vendor table with the four Linux `/proc/mtd` entries; some firmware-managed areas are not exposed as independent Linux MTD partitions.


## Verified offline decryption of 1.5.0 (2026-11-02)

1. The original 16 MiB SPI Flash backup was verified at **16,777,216 bytes** with SHA256 `22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1`. RootFS was carved from flash offset `0x440000` (length `0xAC8000`); `unsquashfs -cat ... usr/bin/nvrammanager` returned an ELF identical byte-for-byte to the live original `/usr/bin/nvrammanager` (SHA256 `b1c396c5f356ded3e67f081b5ebe2ab9e4fe97d39d7714aab5fcd52929fe24ea`).
2. `nvrammanager` contains **RSA-2048** and **RSA-1024** Microsoft PUBLICKEYBLOB values in base64; the 2048-bit one has public exponent 65537, key-blob SHA256 `61f30481c369e0789c17aee876b8729a9de4b65045aaad78441f18afcf41b1ed`. These are **public keys, not firmware signing private keys**. The same public-key blob hashes appear in 1.5.0's `/usr/lib/libnvrammanager.so`. Use `python3 tools/firmware/inspect_keys.py /path/to/nvrammanager` to report metadata without exposing key contents.
3. External implementation: **https://github.com/robbins/tp-link-decrypt** (the tool's source, not copied into this repo). For the offline test it was compiled locally with an AX12-derived RSA-2048 public key as the Cloud key; the repository's unrelated Tapo and switch key placeholders were unused. The tool returned `RSA-2048`, `Firmware verification successful`, and produced `*.bin.dec`. The decrypted output was subsequently validated structurally: `fwup-ptn` ASCII manifest appeared at `0x1014`, `partition fs-uboot` at `0x1818`, and valid SquashFS magic `hsqs` at `0x3B8D64`. This is actual decryption, not just a success message.
4. The decrypted output is 15,379,144 bytes, with file-system entry `base=0x3B7D50`, `size=0xAE6003`. Offsets in the `fwup-ptn` manifest are relative to `0x1014`; thus the SquashFS starts at `0x1014 + 0x3B7D50 = 0x3B8D64`. Extraction was independently verified using:
   ```sh
   python3 tools/firmware/extract_partition.py official.bin.dec file-system file-system.sqfs
   unsquashfs -s file-system.sqfs
   ```
   It identifies SquashFS v4 XZ, 262,144-byte blocks, **2533 inodes** and **11,425,724 bytes of SquashFS content**. The full filesystem was extracted successfully.
5. **Critical Flash layout change:** In old 1.1.22, `os-image` occupies Flash `0x040000...0x440000` and `file-system` occupies `0x440000...0xF08000`. In 1.5.0, `os-image` is `0x040000...0x400000` (size `0x3C0000`) and `file-system` is `0x400000...0xF08000` (size `0xB08000`). **Never reuse old UART or raw Flash write addresses for the new version.**
6. The new Web UI is a different bundled JavaScript frontend: `/www/webpages/js/` has roughly 299 files and contains `zh_CN-*.js.gz` with Simplified Chinese translations. The old `/www/webpages/config/modules.json` and `locale/zh_CN/lan.js` structure is not present; do not transplant old Web overrides directly. The presence of a `zh_CN` chunk alone does not prove its menu selection is enabled.

### Remaining unknowns

- The new `nvrammanager` binary is smaller because key firmware code has moved to `/usr/lib/libnvrammanager.so` (library includes `rsaEnableDecryption`, `AES_cbc_encrypt`, `rsaVerifyPSSSignByBase64EncodePublicKeyBlob`). The cryptographic handling is now understood well enough to decrypt, but **custom package creation, official acceptance, and signature generation are not established**.
- A RSA public key suitable for verification/decryption of this vendor container is **not** a private signing key. Do not conclude that a modified image can be accepted by a production upgrader.
- Do not publish decrypted proprietary firmware, device Flash backups, device credentials, cryptographic key blobs or other extracted contents. Scripts and metadata only.


## Can the modified 1.5.0 image be repacked and accepted? (2026-11-02)

**AES encryption can be reproduced, but vendor RSA-2048-PSS signing remains a blocker for a stock, accepted upgrade.** This is verified experimentally rather than an assumption.

Reproduce the zero-write, offline test (requires `cryptography`):

```sh
python3 tools/firmware/repack_proof.py /path/to/official-1.5.0.bin /path/to/original/nvrammanager
```

Test results on RU 1.5.0:

```text
Original firmware: RSA-2048-PSS verified
Decrypted SquashFS magic at: 0x3b8d64
Unmodified AES re-encryption: exact byte-for-byte original
Modified payload: RSA-PSS verification FAILED (expected)
```

Independent implementation details:

- The vendor RSA-2048 public-key blob is a little-endian Microsoft PUBLICKEYBLOB. The firmware signature is stored in little-endian order, at file offset `0x130..0x22F`. Verify its **reversed** 256-byte representation using standard RSA-PSS/SHA256 (salt length encoded in PSS).
- Validation hashes the firmware starting at `0x14` with the 256-byte signature field temporarily zeroed. The PSS salt recovered from the signed message contains a 16-byte AES key and a 16-byte CBC IV followed by additional salt. We verified the PSS signature independently using Python `cryptography` — no reliance solely on the community decryptor's success message.
- AES-128-CBC decrypts the 16-byte-aligned span starting at `0x130`, with the signature bytes zeroed first. We independently reproduced byte-for-byte the open-source decryptor's output prefix. Re-encrypting the untouched plaintext and restoring the same 256-byte signature produces a **byte-for-byte copy of the official encrypted BIN**.
- Changing even one payload byte after decryption and re-encryption invalidates the RSA-PSS signature. We separately flipped a byte in an official encrypted BIN and observed `RSA PSS Verify Error 3!` in the TP-Link decryptor. RSA public keys extracted from Flash **cannot generate a new valid signature**.

The stock platform upgrade script's `platform_check_image()` returns success unconditionally, but actual flashing is handed to `nvrammanager -u` where vendor verification is implemented. Consequently, `sysupgrade -F` is **not established as a signature bypass** and must not be attempted as a shortcut.

**Next engineering path:** audit the complete on-device upgrader and Flash mapping offline, and evaluate a root-authorized, controlled installation of a custom 1.5.0 image with exact partition map and verified recovery plan. This would bypass the need to create a vendor-signed update package, but it is **not** yet tested, and must **not** be treated as safe flashing instructions. 1.5.0 includes `fs-uboot` in its update manifest and moves RootFS to Flash offset `0x400000` (instead of `0x440000`), so the bootloader and transition compatibility require special attention before any Flash operation.

Keep the actual BINs, reconstructed AES material and device Flash backups private. This repository publishes reproducible code only.


## Self-signed Cloud repackage and independent verification (2026-11-02)

The following steps **now work on offline copies of RU 1.5.0**. No router Flash was modified.

### Test-only signing and AES encryption

1. Generate an **ephemeral RSA-2048 keypair** outside the repository. Keep the private key private. `tools/firmware/self_sign_lab.py` independently performs RSA-PSS/SHA256 with caller-controlled 48-byte salt. The first 32 salt bytes are a new AES-128 key and CBC IV; AES encrypts the Cloud payload. The RSA signature is encoded as little-endian bytes at `0x130..0x22F`.
2. A subtle CBC requirement: the 256-byte signature slot must encrypt to **all-zero ciphertext** before inserting the RSA signature, because the decryptor first zeros those bytes. The test generates the slot's temporary plaintext by decrypting 256 zero bytes with the **new** AES key and IV. Without this adjustment, the region following the signature cannot be recovered exactly.
3. `self_sign_lab.py` passes the owner's RSA-PSS check, verifies that the vendor key rejects the new signature, and verifies that tampering is rejected. The community C implementation `robbins/tp-link-decrypt`, rebuilt with the test **owner public key**, independently reports `Firmware verification successful`. After decrypting, all bytes outside the unused signature slot match the official plaintext payload.

### Preserve vendor upgrades without changing the verifier's machine code

- `patch_trust_anchor.py` creates an offline copy of `libnvrammanager.so` with only its RSA-2048 **PUBLICKEYBLOB** replaced by an owner public key of equal encoded length. The vendor's original RSA-2048 and RSA-1024 public-key formats are preserved correctly, including the `060200000c240000` PUBLICKEYBLOB prefix. A patched **single-owner-key** library is not in itself a dual-trust verifier.
- `build_test_rootfs.sh` keeps the *original* `/usr/lib/libnvrammanager.so`, adds the owner-only test library under `/usr/lib/ax12-owner/libnvrammanager.so`, and creates a **check-only** wrapper `/usr/sbin/ax12-owner-check` using `LD_LIBRARY_PATH`. It contains no special firmware-write commands and has not been installed on a router.
- MIPS user-mode QEMU, with the extracted 1.5.0 RootFS as its sysroot, was used to observe that `nvrammanager` actually opens `/usr/lib/ax12-owner/libnvrammanager.so` when the owner library path is configured. The process subsequently stopped at `/dev/flash_chrdev` because the isolated environment has no simulated AX12 Flash. This is **loader proof**, not an end-to-end device upgrade acceptance test.

### Rebuild a modified complete image, still offline

- `seal_rootfs.py` applies the Realtek SquashFS header length and 16-bit checksum, plus the trailing zero observed on both official 1.1.22 and 1.5.0 Cloud `file-system` entries. Both official entries have length `padded_rootfs + 3`, with the vendor length field exactly 643 bytes less than the final entry.
- `build_test_rootfs.sh` repacks the extracted RootFS using XZ, 256-KiB blocks and the original SquashFS options. The verified offline test image is `0xAED003` bytes after sealing, **110,589 bytes under the 1.5.0 partition capacity `0xB08000`**. It contains the two libraries and a read-only check wrapper.
- `repack_cloud_lab.py` replaces the Cloud `file-system` payload, updates its manifest entry length and subsequent partition offsets by `+0x7000`, updates the overall file length, AES-encrypts and owner-signs the new Cloud package. The test container was `0xEB1ADC` bytes long.
- The independent C decryptor with the owner public key verified this complete newly signed package. Its decrypted `file-system` exactly matched the generated RootFS entry, and the manifest offsets and file length were checked independently.

Reproduction overview (all commands run on your **offline copies**, not the router):

```sh
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out test-private.pem
openssl pkey -in test-private.pem -pubout -out test-public.pem
python3 tools/firmware/self_sign_lab.py official.bin original-nvrammanager \
  test-private.pem original-content-self-signed-test.bin
sh tools/firmware/build_test_rootfs.sh EXTRACTED_OFFICIAL_ROOTFS test-public.pem WORKDIR
python3 tools/firmware/repack_cloud_lab.py official.bin original-nvrammanager \
  test-private.pem WORKDIR/rootfs.sealed WORKDIR/selfsigned-custom-test.bin
```

**Remaining blockers:** the running AX12 has not accepted the custom package, and 1.5.0's bootloader/Flash layout transition has not been validated. The extracted `nvrammanager -c` cannot complete in QEMU without its proprietary Flash device. The 16-byte header at file offset `0x04` and any additional vendor checks must be validated before attempting a write. The test images are **not validated flashable upgrades**. No signed packages, extracted proprietary RootFS, device backups or private keys have been pushed to GitHub.

## Single-owner-key upgrade policy and writable Web development strategy

Decision recorded 2026-11-02:

- **Owner-only public key is sufficient for a private router.** New official RU images may be decrypted and re-signed by the owner offline, provided the owner build tools understand that exact future Cloud/boot format. Vendor signatures will not be accepted by the owner-only updater; retain original vendor firmware, key fingerprints and hardware UART recovery. The owner private signing key must remain off-router, uncommitted, and backed up securely.
- The extracted **1.5.0** firmware contains approximately **4,832 KiB** under `/www` and **2,188 KiB** under `/usr/lib/lua/luci`. The latter contains the Lua controllers and models used by LuCI. The filesystem is **SquashFS**, read-only, as in the live 1.1.22.
- **Writable vs persistent are different requirements.** A startup `tmpfs` and bind-mounted writable copies (either full copies or an original-file symlink tree) can expose edit-in-place `/www` and Lua-backend paths over SSH immediately, but these RAM modifications disappear on reboot. This mechanism has been tried in principle with the live language-only patch, but **a full new-1.5.0 writable Web/backend mount has not been tested on hardware**. Lua/module caches and the Web server may need reloads for edits to appear.
- **On-device reboot persistence requires nonvolatile storage.** The current AX12's `/overlay` is tmpfs, `/etc` is ramfs and `/tmp` is tmpfs. The live 1.1.22 `/proc/filesystems` lists SquashFS/ramfs/tmpfs but **not JFFS2 or OverlayFS**. The 1.5.0 extracted `/lib/modules` contains no obvious JFFS2/OverlayFS/NFS client modules; this does not conclusively establish the new kernel's built-in support. Boot scripts reference JFFS2 generically but no `/storage` or `/data` partition is mounted on current hardware.
- The official 1.5.0 Flash `file-system` partition is **`0xB08000` bytes**; official RootFS payload is `0xAE6003`, leaving only **139,261 bytes** of headroom. Our offline owner-library test RootFS `0xAED003` leaves **110,589 bytes**. This cannot hold copies of the full Web frontend and Lua backend. TP-Link proprietary `user-config`, `router-config` and wireless/calibration partitions are **not free space**.
- For self-contained persistent editing, investigate **reserving a separate small wear-aware writable Flash partition** (e.g. JFFS2), modifying the kernel/partition table as required and keeping only **changed files** there. This necessarily alters Flash layout and boot assumptions and is not yet safe to implement. A truly independent writable whole `/www` + LuCI tree would need far more Flash space or additional storage.
- Lower-risk interim approach: hot-edit via RAM bind mounts, store version-controlled changes on the owner's Mac mini, and restore changes by SSH after reboot. This avoids repeated firmware flashing but depends on that host; it is not autonomous router persistence.
- **Do not flash the current offline experiment package:** although self-signed RSA-PSS/AES and SquashFS rebuild are independently validated, the proprietary on-device upgrade and new Bootloader/Flash layout transition are still unverified.


## Same-version 1.5.0 reinstallation and first-upgrade plan (2026-11-02)

The preferred workflow is **one custom 1.5.0 baseline upgrade, followed by repeated owner-signed 1.5.0 rebuilds** for future Web/backend changes. This avoids requiring a persistently writable whole `/www` filesystem.

Evidence:
- The official RU 1.5.0 `soft-version` payload advertises `soft_ver:1.5.0 Build 20260605 Rel. 41062`, and the existing offline owner-signed test package preserves that value exactly.
- The new `libnvrammanager.so` exports `nm_checkSoftVer` at virtual address `0x43d4`. Static MIPS disassembly of the version tuple comparisons (`0x45e8..0x46c0`) includes an equality-accepting path; there is **no explicit equality-rejection in that routine**. This suggests (but does not prove) that same-version installs can pass its version comparison. Other gates (`nm_checkUpgradeMode`, signature, platform support list, Flash write) remain untested.
- TP-Link's [AX12 RU download page](https://www.tp-link.com/kz/support/download/archer-ax12/) offers 1.5.0 without documenting a mandatory intermediary for RU 1.1.22, but carries warnings of irreversible version upgrades for other releases. Do not infer safe rollback.
- The initial router runs **1.1.22**, with the stock vendor-only verifier. An owner-signed 1.5.0 image is **not directly accepted** by this stock verifier. Installing the unmodified official 1.5.0 first would likely remove the existing custom root SSH and does not install the owner trust anchor. The initial transition therefore requires a separately validated root-authorized upgrade path or a recovery-enabled one-time Flash procedure.
- The upgrade must deliver an **owner-key** verification library and working root SSH as part of the first custom 1.5.0 RootFS. Future updates can keep `1.5.0` as the firmware version while changing only custom build metadata; the physical Flash update still rewrites relevant NOR sectors and cannot be performed indefinitely without wear.
- 1.5.0 changes the RootFS Flash offset from `0x440000` to `0x400000` and contains an `fs-uboot` payload. Do not assume that the old bootloader can safely boot the new partition table. Verify the exact pre-upgrade Flash map, upgrade operations, recovery path, and preservation of the radio/calibration/config partitions before the first write.

**Status: planned, not deployed.** No same-version reinstallation was attempted on real hardware, and no live upgrade is authorized by this note.


## First-upgrade preflight: owner-only 1.5.0 + SSH (2026-11-02)

The **live AX12 runs RU 1.1.22**, not 1.2.0. The existing flashed SSH keypair was generated on the owner's MacBook and its **RSA-3072 private key** is kept on the Mac mini under `~/.ssh/ax12_root`. The local Mac mini key fingerprint was checked without publishing the public key or its identifier. The historical successful-flash README documents `authorized_keys` being integrated into the 1.1.22 RootFS and tested root SSH login; this recent check did not directly read current runtime `authorized_keys`.

**Do not mix the SSH RSA-3072 key with the firmware RSA-2048 signer.** The latter used so far is a disposable experiment key on the VPS and must be replaced with a backed-up long-term *owner* signing key before any actual firmware installation.

The initial dual-library 1.5.0 offline lab build is **not boot-ready**: inspection confirmed it contains neither `root/.ssh/authorized_keys` nor the previously proven `etc_ro/init.d/ax12-ssh` startup hook. Never flash that artifact.

`tools/firmware/build_owner_rootfs.sh` is now a tested **offline build entrypoint** for an **owner-only verification library** plus the existing LAN-only SSH startup script. It takes five explicit arguments:

```sh
sh tools/firmware/build_owner_rootfs.sh \
  EXTRACTED_OFFICIAL_1_5_0_ROOTFS OWNER_SIGNING_PUBLIC_PEM \
  SSH_PUBLIC_KEY tools/ax12-ssh PRIVATE_WORKDIR
```

The SSH key input must be the user's **current authorized RSA-3072 public key**, obtainable from the user's Mac via `ssh-keygen -y -f ~/.ssh/ax12_root` (avoid copying the private SSH key to the VPS). No device-specific SSH key has been committed to the repository. The script has now passed a complete offline test-build using a **disposable test-only SSH public key**, with both SSH authorization files and their permissions checked, the autostart symlink verified, and the original RSA-2048 trust anchor replaced in the single default library. The sealed RootFS length is `0xAE4003`, leaving **147,453 bytes** in the new `0xB08000` Flash RootFS partition. The owner-signed Cloud test package was validated and decrypted by an independent C implementation, and its RootFS was byte-for-byte identical to the offline build. **It has not used the user's real SSH public key, has not executed the full upgrader, and is NOT approved for Flash.**

The next indispensable gates before first actual Flash write are:

1. Build a 1.5.0 owner-only RootFS with the **real** existing SSH public key and confirm the private key still opens a root session via the expected LAN-only port after startup. Retain a recovery copy of the unmodified factory library and full 16-MiB Flash.
2. Verify the **current 1.1.22** upgrade path accepts or can safely install the newly owner-signed 1.5.0 package *without* losing SSH, and independently verify the package's bootloader and new Flash partition transition. A successful Python/C self-signature test does not verify this upgrade step.
3. Validate writable metadata fields, partition bounds, vendor-specific checks and recovery procedure. The 1.5.0 `nm_checkSoftVer` routine has a static path compatible with equality; this alone does **not** prove that full same-version reinstalls work.
4. **Only after** all checks pass should the first hardware firmware update be considered. No authorization for actual flashing is implied here.

## Persistence research

Live SSH inspection found:

- `/dev/root / squashfs ro`: `/www` is read-only.
- `/overlay` is `tmpfs`, `/etc` is `ramfs`, and `/tmp` is `tmpfs`; direct writes there disappear on reboot.
- No `/storage` or `/data` mount is available on this unit.
- An existing `/usr/bin/nvrammanager` can access proprietary config Flash via `/dev/flash_chrdev`, but no safe, general-purpose boot-time script storage interface has yet been proven.

**Fastest low-risk persistence option:** keep tested patch files on an always-on Mac mini and use a macOS `launchd` job to reapply a small RAM overlay over `ssh ax12` after AX12 reboots. This does not make AX12 autonomous: Mac mini must be available for recovery. Do not install the job before an idempotent, tested deploy/rollback script is ready.

**Alternative:** offline modification and repacking of 1.5.0; decrypting and repacking a filesystem does **not** imply custom image signature validation will pass. This remains untested and unsigned custom firmware must not be flashed. A stock GUI update or rootfs MTD write has materially higher risk and should be considered only after offline validation and verified recovery.

**Security:** do not commit firmware ZIP/BIN, 16 MiB device Flash dumps, credentials, unique calibration data or device-specific keys.
