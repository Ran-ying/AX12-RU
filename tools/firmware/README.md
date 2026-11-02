# Archer AX12(RU) V1 firmware format notes (2026-11-02)

Read-only research only; no firmware upgrade, flash write, device reboot or decryption attempted.

## Official packages compared

- **Installed generation:** `1.1.22 Build 20240311` (official package); BIN length 13,850,616 bytes; SHA256 `98c5b0224a0df2379587998b339995e972fc2b2fbb7512a9c63bd02d88019d3f`.
- **RU latest on the official page (checked 2026-11-02):** `1.5.0 Build 20260605`, published 2026-06-09; BIN length 15,379,164 bytes; SHA256 `50b09cbc1f18140cd18ebf7fbe611851ab98e21b05d67303307673b5de5003c9`.
- Official download page: https://www.tp-link.com/kz/support/download/archer-ax12/ . Only RU V1 packages are in scope; EU, US or TW images are not interchangeable without platform-specific verification.

Both use a TP-Link Cloud-style preamble: first four bytes represent big-endian file size, bytes `0x14...` begin `fw-type:Cloud\n`. The 16-byte field at `0x04` was **not** verified as a plain MD5 digest; do not assume a checksum formula.

## Major structural change

- **1.1.22:** At file offset `0x1014`, an ASCII `fwup-ptn ...` manifest is readable. The manifest lists `os-image`, `file-system`, `re-def-config`, etc. At `0x1818`, the plaintext Flash partition table starts with `partition fs-uboot base ...`.
- **1.5.0:** The corresponding offsets contain high-entropy bytes and do not contain the plaintext manifests. Its header region starting around `0x1C0` also changed. This is evidence of a protected/encrypted upgrade container, but the exact cryptographic algorithm and signature verification path remain to be demonstrated.
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

## Persistence research

Live SSH inspection found:

- `/dev/root / squashfs ro`: `/www` is read-only.
- `/overlay` is `tmpfs`, `/etc` is `ramfs`, and `/tmp` is `tmpfs`; direct writes there disappear on reboot.
- No `/storage` or `/data` mount is available on this unit.
- An existing `/usr/bin/nvrammanager` can access proprietary config Flash via `/dev/flash_chrdev`, but no safe, general-purpose boot-time script storage interface has yet been proven.

**Fastest low-risk persistence option:** keep tested patch files on an always-on Mac mini and use a macOS `launchd` job to reapply a small RAM overlay over `ssh ax12` after AX12 reboots. This does not make AX12 autonomous: Mac mini must be available for recovery. Do not install the job before an idempotent, tested deploy/rollback script is ready.

**Alternative:** offline decrypt/repack 1.5.0 and determine whether stock verifier accepts custom images; decrypting and repacking a filesystem does not itself bypass RSA/signature verification. A stock GUI update or rootfs MTD write has materially higher risk and should be considered only after offline validation and verified recovery.

**Security:** do not commit firmware ZIP/BIN, 16 MiB device Flash dumps, credentials, unique calibration data or device-specific keys.
