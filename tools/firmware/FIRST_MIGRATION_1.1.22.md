# AX12(RU) V1 — first migration from original 1.1.22 to owner-signed 1.5.0

**This is a record of an already completed owner-authorized hardware migration, not an instruction to reflash the router now.** The initial firmware was `1.1.22 Build 20240311` (not 1.1.12). The currently verified custom runtime is owner-signed **1.5.2** with WAN port1 fixed.

## Three distinct operations (do not conflate)

1. **UART/Bootloader historical setup:** the original 16 MiB SPI NOR Flash was backed up via UART; an earlier RootFS-only modification was written to enable persistent root SSH with an authorized key while keeping the original Bootloader. UART was also retained as a recovery path. This was not itself the 1.1.22→1.5.0 firmware upgrade.
2. **Temporary first-upgrade RSA verifier:** while running old 1.1.22 Linux with root SSH, a copy of its native `nvrammanager` was patched to replace the RSA-2048 verification *public* key. The modified executable ran only from `/tmp`, the RAM-backed filesystem, first with `-c` (check), then with `-u` (upgrade). The old resident `nvrammanager` binary did **not** have to be permanently overwritten just to accept the owner-signed first-upgrade image.
3. **First actual upgrade:** the native `nvrammanager -u` write path processed the owner-signed Cloud image derived from official 1.5.0. The image used a `cs6c` kernel header to boot under the existing Realtek Bootloader and had no `fs-uboot` update descriptor. The upgrade installed the new RootFS containing the **persistent owner-public-key verification library**, SSH startup and updated partition layout. Real device logs showed `check firmware ok!`, `Done.`, `upgradeFirmware success...`, `UPGRADE_EXIT_CODE=0`. A separate restart succeeded; UART proved the new kernel and RootFS booted, and SSH root login was subsequently confirmed. See [M6 actual device record](M6-first-flash-2026-11-03.md).

The first-upgrade owner-signed Cloud image size was **15,370,972 bytes**, SHA-256 `ddf9880b29715a9189666a5256d86b3f2d8daec342219704a01edce0f696bf7c`. It is a **historical** artifact, not interchangeable with the plain official 1.5.0 BIN, and should not be reflashed on the now working device.

## What actually needed the key

- The **firmware RSA-2048 private signing key** signs a compatible Cloud update; it does not by itself grant a remote upgrade interface.
- The **verification RSA public key** belongs to the user-space upgrade verifier, `libnvrammanager.so` / the corresponding updater. It was first used in a RAM-only modified updater, and only **after** the successful upgrade was it stored persistently in the new RootFS.
- The **Bootloader** was not reflashed during this first major-version upgrade; the boot compatibility workaround was the validated `cr6c → cs6c` kernel wrapper.
- UART was necessary for our earlier recovery/SSH-provisioning workflow, but it is **not a universal prerequisite** to manually reflash an entire 16 MiB image before every owner-signed upgrade.

## Upgrade paths: tested vs not tested

| Path | Evidence / recommendation |
|---|---|
| Old 1.1.22 + original factory updater → owner-signed 1.5.x | Original factory updater rejected owner RSA signature. An authorized RAM-only verifier replacement was required for our tested first-upgrade workflow. |
| Old 1.1.22 + temporary owner verifier → tailored 1.5.0 | **Actual hardware PASS**, with `cs6c` boot bridge and no U-Boot manifest write; inspect full M5/M6 records. |
| Old 1.1.22 → owner 1.5.2 **directly** | **Not tested.** Do not assume the successfully validated indirect sequence proves direct compatibility. |
| Old 1.1.22 → unchanged official 1.5.0 via ordinary Web upgrade | **Not tested in this project.** A vendor-signed image may meet vendor signature checks, but Bootloader/partition-update requirements and hardware-specific release constraints are separate issues. Do not claim guaranteed compatibility. |
| Already installed owner 1.5.2 → another owner-signed compatible release | Existing owner verifier persists in RootFS, so a fresh UART Flash rewrite just to install the public key is unnecessary. Signed update still requires preflight and rollback readiness. |

## Security boundaries

A complete 16 MiB Flash image includes device-specific data, wireless calibration and configuration. Do not blindly write a complete generic image or the wrong regional firmware over it; retain backups and never overwrite Bootloader, ART or factory regions without a specifically validated recovery plan. The owner's original backup, serial logs and calibration data stay private. The current public repository may contain the user's published signing key; possession of that key allows signature generation but does not itself provide remote device access or automatic update permission.
