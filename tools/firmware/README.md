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

## Persistence research

Live SSH inspection found:

- `/dev/root / squashfs ro`: `/www` is read-only.
- `/overlay` is `tmpfs`, `/etc` is `ramfs`, and `/tmp` is `tmpfs`; direct writes there disappear on reboot.
- No `/storage` or `/data` mount is available on this unit.
- An existing `/usr/bin/nvrammanager` can access proprietary config Flash via `/dev/flash_chrdev`, but no safe, general-purpose boot-time script storage interface has yet been proven.

**Fastest low-risk persistence option:** keep tested patch files on an always-on Mac mini and use a macOS `launchd` job to reapply a small RAM overlay over `ssh ax12` after AX12 reboots. This does not make AX12 autonomous: Mac mini must be available for recovery. Do not install the job before an idempotent, tested deploy/rollback script is ready.

**Alternative:** offline modification and repacking of 1.5.0; decrypting and repacking a filesystem does **not** imply custom image signature validation will pass. This remains untested and unsigned custom firmware must not be flashed. A stock GUI update or rootfs MTD write has materially higher risk and should be considered only after offline validation and verified recovery.

**Security:** do not commit firmware ZIP/BIN, 16 MiB device Flash dumps, credentials, unique calibration data or device-specific keys.
