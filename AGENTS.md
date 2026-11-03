# AX12-RU — Instructions for AI coding agents

This repository targets **TP-Link Archer AX12 RU hardware v1.0** (RTL8197F, MIPS little endian, 16 MiB SPI NOR). Do not assume binary patches are compatible with other board revisions or regions.

## Primary build contract

1. The immutable base is **official RU 1.5.0 Build 20260605 Rel. 41062**. Verify its full-file SHA-256 against `firmware/OFFICIAL-1.5.0.sha256` before decrypting or editing anything.
2. Read `tools/firmware/REPRODUCIBLE_BUILD.md`, then use `python3 build.py --version 1.5.3 (with inputs/official-1.5.0.bin present; --official overrides path)` to create an unsigned Cloud firmware and a 256-byte RSA-PSS encoded message (EM).
3. All changes must live in explicit versioned patches under `tools/firmware/patches/`: 1.5.1 owner verification key + LAN SSH + Web CGI + zh_CN r2 + `cr6c → cs6c` boot bridge, 1.5.2 WAN=port1 kernel patch, 1.5.3 professional zh_CN v3 locale.
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
