# AX12-RU — instructions for future AI agents

Scope: TP-Link Archer AX12 RU hardware v1.0, Realtek RTL8197F, 16 MiB SPI NOR. This is an owner-controlled firmware-research project, **not** a generalized firmware builder for different models or regions.

## Ground truth

- Tested on hardware: **1.5.2 owner-signed** image boots, zh_CN/Web works, WAN physical port1 is in VLAN 8, LAN ports0/2/3/4/8 in VLAN 9, WAN 1000 Full/`LOWER_UP`, DHCP address acquired, Internet and LAN work (owner's live acceptance on 2026-11-03).
- Kernel repair is the 1.5.0 MIPS `0x80BE5548` instruction `BNE 0x14450023 -> NOP`, validated at runtime; the extracted kernel is under `cs6c` Cloud packaging.
- 1.5.3 zh_CN-v3 builder is **offline tested through unsigned package/EM**, not yet owner signed or boot tested. Do not assert it is a validated release.
- The public repo contains owner firmware signing **public** key. Private signing key is not managed by this repository; no signing private key is needed for the unsigned build.

## Build and verification

1. Read `tools/firmware/REPRODUCIBLE_BUILD.md` and the latest `M8-...` / `M9-...` records before changing code.
2. Use the exact `firmware/AX12-RU-1.5.2-owner-signed-WAN1.bin` baseline or explicitly verify the same SHA256. Do not substitute RU 1.1.22, RU 1.5.0 or other regional hardware images.
3. Modify only required files in a copied RootFS or make an isolated kernel patch. Maintain the real `0xB00000` mtd2 limit, correct Realtek checksums, owner signing format, and **no** `fs-uboot` update entry.
4. Build 1.5.3 with `python3 tools/firmware/build_owner_153.py --baseline firmware/AX12-RU-1.5.2-owner-signed-WAN1.bin`; this outputs unsigned package, encoded-message signing input, and the sealed RootFS to ignored `build/`.
5. Sign the 256-byte EM locally with an owner-controlled RSA-2048 private key; use `tools/firmware/finalize_owner_cloud.py` to assemble and verify a signed package. Do not commit other private credentials or device-specific 16 MiB Flash dumps.
6. Read back and verify the complete signed result before offering it for hardware testing. Never equate offline signature validation with successful boot, and never flash/restart the device unless the owner expressly requests that action.

## Security and source control

The GitHub repository is public. Treat private keys, device calibration, admin credentials, Wi-Fi passwords and raw Flash dumps as sensitive. Do not add such material as an incidental side effect of debugging or packaging. The owner may separately choose to disclose signing material, but this does not imply permission to collect unrelated credentials.

Keep scripts simple, expose failures instead of silently substituting defaults, and verify every changed binary segment and Flash partition size.
