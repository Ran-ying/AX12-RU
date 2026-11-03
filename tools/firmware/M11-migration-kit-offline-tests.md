# M11 — First-migration kit offline verification (2026-11-03)

This is a **non-writing offline validation** of the initial 1.1.22 → owner trust bootstrap methods documented in [MIGRATE_STOCK_1.1.22_TO_OWNER.md](MIGRATE_STOCK_1.1.22_TO_OWNER.md). No router connected, rebooted, or flashed during these tests. Inputs were a **synthetic 16-MiB Flash image** assembled from the official 1.1.22 RootFS plus `0xff` filler, and **disposable** or public owner keys. The synthetic image is not a real owner's recoverable hardware backup.

## Old RootFS SSH preparation: PASS (synthetic)

1. Extracted official `1.1.22 Build 20240311` Cloud `file-system` from the unchanged vendor BIN into the synthetic Flash interval `0x440000..`.
2. Executed `tools/firmware/prepare_1122_ssh_bootstrap.py` with the synthetic full Flash and a throwaway sample `ssh-rsa` public key. It rejects an unexpected original `nvrammanager` SHA-256, does not accept SSH private keys, and will only produce files in the given work directory.
3. Fresh SquashFS rebuild: **2,500 inodes**, matching the historical successful SSH RootFS inode count. Sealed image and final UART flash payload: **`0x9A6000` / 10,117,120 bytes**, matching the historical successful aligned payload size. New SSH key produces a different SHA-256 and should not be expected to match that actual historical payload.
4. Verified original synthetic image untouched and optional reconstructed 16-MiB output preserved bytes outside `[0x440000, 0x440000 + payload_len)`. Output is **not** an approved universal Flash image and must not be uploaded with personal contents.

## Old 1.1.22 temporary owner verifier: PASS (offline binary)

- Untouched stock `/usr/bin/nvrammanager`: **114,056 bytes**, SHA256 `b1c396c5f356ded3e67f081b5ebe2ab9e4fe97d39d7714aab5fcd52929fe24ea`.
- Executed `tools/firmware/patch_trust_anchor.py` against the stock ELF, swapping exactly its embedded RSA-2048 **public** key (offset `0x19f44`) for the project's recorded owner public key.
- Patched ELF SHA256: **`fa0b6a9388e952f07fe1f8193409d29b6bb2ab2c49dd9414b9db14c56c8776b2`**, byte-identical to the temporary `nvrammanager-owner-check` already used in M6's successful **real** first firmware upgrade.
- Other owners should use their own newly generated public key, so their patched binary hash differs.

## First custom 1.5.0 Cloud construction: PASS (disposable signing key)

- From the separately verified pristine official 1.5.0, built a fresh owner-RSA verification library + SSH / zh_CN RootFS using `build_owner_rootfs.sh`.
- Used `prepare_owner_cloud.py --omit-uboot --kernel-magic cs6c` to prepare a first-upgrade unsigned Cloud, with source verifier taken from original 1.1.22 ELF.
- Signed its PSS encoded message using a new **disposable** RSA-2048 key and verified with `finalize_owner_cloud.py`; RSA-PSS, AES decryption, declared RootFS bytes, and Cloud size all PASS.
- New trial output RootFS `0xAEF003`; size may differ from previously used owner-signed 1.5.0 in M6. **This new signed trial image has not been flashed or accepted by the original 1.1.22 hardware upgrader**; it is a format/assembly proof only. No test private keys or test signed firmware are committed to the repository.

## Overall limit

The actual **staged route** on the original device succeeded historically and is documented in M6/M7/M8. The new general-purpose offline bootstrap preparer has **not itself been used for a fresh hardware migration by a second owner**. There is no acceptance test establishing **direct** original 1.1.22 → owner 1.5.3, no proof of stock EU/US compatibility, and no unattended OTA/Flash-write provision. No such claim should be made without the native old updater's full simulated `-u` trace, recovery checks and subsequent supervised hardware testing.
