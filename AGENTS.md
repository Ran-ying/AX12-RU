# AX12-RU — Instructions for AI coding agents

This repository targets **TP-Link Archer AX12 RU hardware v1.0** (RTL8197F, MIPS little endian, 16 MiB SPI NOR). Do not assume binary patches are compatible with other board revisions or regions.

## Primary build contract

1. The immutable base is **official RU 1.5.0 Build 20260605 Rel. 41062**. Verify its full-file SHA-256 against `firmware/OFFICIAL-1.5.0.sha256` before decrypting or editing anything.
2. Read `tools/firmware/REPRODUCIBLE_BUILD.md`, then use `python3 build.py --version 1.5.3` (with `inputs/official-1.5.0.bin` present; `--official` overrides the path) to create an unsigned Cloud firmware and a 256-byte RSA-PSS encoded message (EM).
3. All changes must live in explicit versioned patches under `tools/firmware/patches/`: owner 1.5.0 verification key + LAN SSH + executable CGI + `cr6c → cs6c` boot bridge, owner 1.5.1 zh_CN r2 + Web locale registration, owner 1.5.2 WAN=port1 kernel patch, owner 1.5.3 zh_CN v3.
4. The builder must always start fresh from the official 1.5.0 image, applying patches sequentially through the requested version. **Do not** treat the previously owner-signed 1.5.2 image as the editable source for future versions.
5. Only the exact MIPS patch site and known-good original SHA are supported. Check original bytes and known-good output digest. Re-evaluate offsets when upgrading to a different official base.
6. Preserve the actual `0xB00000` mtd2 RootFS budget, special Realtek 16-bit checksum, Cloud partition manifest, owner RSA-PSS/AES wrapper, and **omit the `fs-uboot` update entry**. Never write device factory/calibration partitions.
7. A valid RSA private key is required to sign; the default unsigned build never reads it, and the explicit `--sign-key PATH` option can sign and finalize on the local machine. Once a signature is supplied, use `tools/firmware/finalize_owner_cloud.py` and inspect all outputs. A valid signature is **not** proof of bootability.
8. Never write Flash, apply a configuration change, or reboot the AX12 without explicit user instructions. Keep UART/Bootloader recovery available for any new firmware test.

## Historical evidence and limitations

- **1.5.2 actual hardware PASS:** LAN Web/SSH, port1 WAN VLAN8, port2–4 LAN VLAN9, 1Gbps carrier, DHCP, DNS, routed Internet and Mac mini LAN client.
- `firmware/AX12-RU-1.5.2-owner-signed-WAN1.bin` is a known-good **comparison/rollback artifact only**.
- The 1.5.3 rebuild (zh_CN v3) has passed unsigned offline construction; it **has not been signed or boot-tested**.
- Locale v3 changed 1,080/2,713 strings and preserved placeholders and JS module structure; complete human/UI review is still pending.
- Backend/UI feature presence alone does not imply the AX12's runtime feature flags support it.

All future modifications should be small, explicit, and testable. Do not hide failures with optional fallbacks. Maintain this file and version evidence whenever the pipeline changes.

Initial-device migration (`1.1.22` → owner-signed `1.5.0`) is historically documented at `tools/firmware/FIRST_MIGRATION_1.1.22.md`; it is distinct from the current official-1.5.0-base **build** workflow. Do not claim direct 1.1.22→owner 1.5.2 was tested, and do not assume UART whole-Flash rewrite is required for every upgrade.

## First-time owners migrating from stock 1.1.22

Start with [`tools/firmware/MIGRATE_STOCK_1.1.22_TO_OWNER.md`](tools/firmware/MIGRATE_STOCK_1.1.22_TO_OWNER.md), not the versioned `build.py` alone. The `prepare_1122_ssh_bootstrap.py` tool only builds a local old-RootFS UART payload from **the new owner's own backup** plus a valid SSH **public key**; it does not interact with the router or require their private key. Old 1.1.22's first owner-signed Cloud upgrade historically used a RAM-only patched verification **public** key and a `cs6c` Bootloader bridge with no `fs-uboot` write. The new 1.5.3 patch-chain package is not evidence that direct 1.1.22→1.5.3 flashing was tested. Require separate authorization and per-device calibration/backups for all actual hardware writes; do not reuse the public repository's disclosed owner signing private key as an exclusive trust root for other owners. See [M11 tests](tools/firmware/M11-migration-kit-offline-tests.md).

**Version semantics:** `build.py --version 1.5.0` builds a new minimal owner-key/SSH bootstrap, not a byte-identical copy of the historical first-flashed 1.5.0 (which additionally contained early Chinese UI edits). `--version` accepts `1.5.0` through `1.5.3`; see [M12](tools/firmware/M12-owner-1.5.0-versioned-refactor.md) and `verify_patch_chain.py`. The old 1.1.22 stock upgrader has not accepted this newly rebuilt 1.5.0 on a second physical router.
