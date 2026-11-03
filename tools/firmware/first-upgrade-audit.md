# AX12 RU 1.1.22 → 自签名 1.5.0：首次迁移静态审计

> **关键阻断发现（2026-11-03）**：原版 1.1.22 Bootloader 在 `cr6c` 内核启动路径中会使用物理地址 **`0x440000`** 检查 SquashFS；1.5.0 的 RootFS 已迁到 **`0x400000`**。因此现有正式签名的 **`NO-UBOOT-CANDIDATE.bin` 不得刷写**。详见文末“旧 Bootloader RootFS 检查阻断”章节。候选包 RSA 验签和模拟升级通过不构成启动兼容性证明。\n\n
更新：2026-11-02。**只读研究，无 Flash 写入、无重启。** 本文针对本机已验证的 RTL8197F / 16 MiB SPI Flash，不能直接推广到其他硬件版本。

## 已通过的实际验收

- 1.5.0 自签名 Cloud 候选包由 Mac mini 上新生成的 RSA-2048 私钥签名；私钥未传给 Linux Panel。Linux Panel 上完整 BIN 的 SHA256 为 `c5a66492c4dac14a5731b9cbaa6298678414e30d7a50b83c703fa49180e3b542`。
- 独立 C 解密工具和 Python 验证均通过，解密后的 `file-system` 与含有 SSH 及自有公钥验证器的 RootFS 镜像逐字节一致。
- AX12 实机 1.1.22 在 RAM 中使用官方 `nvrammanager -c` 检查时拒绝该包；使用只替换嵌入 RSA-2048 **公钥**的临时程序 `/tmp/nvrammanager-owner-check -c` 时返回成功、退出码 0。注意成功日志明确说 `Check RSA2048 FW, no need analysis firmware, return OK.`，因此这不代表已验证升级写入逻辑。
- 上述临时测试数据已从 AX12 `/tmp` 删除，出厂程序未被覆盖。

## 本轮新证据：实际写入程序及处理顺序

旧版 MIPS 可执行文件 `/tmp/ax12-nvrammanager` 是 stripped ELF，但通过与 1.5.0 未剥离符号的 `libnvrammanager.so` 比较，已经找到同一类写入循环：

| 对象 | 函数/代码位置 | 静态证据 |
|---|---|---|
| 1.1.22 | `0x403010` 附近 | 升级数据写入循环，记录步长 48 字节，末端 `+0x558`，容量 **28** |
| 1.5.0 | `nm_updateDataToNvram` at `0x3D58` | 对 48 字节的记录逐项处理，末端 `+0x618`，容量 **32** |
| 1.5.0 | `nm_lib_parsePtnIndexFile` at `0x2FE4` | 读取 Cloud 清单记录，调用 `nm_lib_fetchUnusedPtnEntry` |
| 1.5.0 | `nm_lib_fetchUnusedPtnEntry` at `0x2E60` | 扫描并分配第一个未使用的分区记录槽位 |
| 1.5.0 | `nm_upgradeFwupFile` at `0x5140` | 调用 `nm_updateDataToNvram`，随后调用 `nm_updateRuntimePtnTable`（内存中的表更新） |

据此，**静态推断**清单的分区顺序通常会传递到更新写入顺序；当前 1.5.0 清单顺序：

`fs-uboot → os-image → file-system → re-def-config → partition-table → soft-version → extra-para → support-list → profile → default-config → ap-def-config`

**警告**：不能断言 `fs-uboot` 已经被实机证实为第一个写入的分区。其他预检查、写入标志、条件分支可能影响实际顺序；本轮未运行 `nvrammanager -u`，也没有模拟厂商私有 Flash 的完整设备接口。

写入过程会按分区、多次调用 Flash I/O，且有擦除与更新步骤；没有发现可依赖的 A/B 固件槽或事务式回滚机制。**更新前几步断电可能让设备无法启动**。

## 分区兼容性

两代官方 Cloud 固件的物理分区记录：

- 1.1.22：**24** 条；当前实机 `nvrammanager -s` 与该清单一致。
- 1.5.0：**28** 条，恰好达到旧版升级程序的 28 条记录容量，新加 `wireless-key`、`https_cert`、`uboot_env`、`login-key`。
- 1.1.22 `os-image` 为 `0x40000..0x440000`，`file-system` 为 `0x440000..0xF08000`。
- 1.5.0 `os-image` 为 `0x40000..0x400000`，`file-system` 为 `0x400000..0xF08000`。
- 换言之，**新版 RootFS 在原旧版内核分区的最后 256 KiB 处开始**。必须确定临时升级环境如何选择目标分区表；不能沿用旧版 Flash 写入地址。
- `fs-uboot` 分区地址和容量均不变，但新版 143,677 字节 Bootloader 载荷与原始 Flash 对应位置有 106,984 字节差异。不能假定保留旧 Bootloader 后可启动新内核；也不能在未验证恢复条件前优先写入新 Bootloader。

`tools/firmware/migration_preflight.py` 可读取两代 Cloud 明文和原始 Bootloader 的私有本地副本，以只读方式复现以上分区尺寸、顺序与差异分析。

## 恢复环境核查

- 原始 16 MiB Flash 备份仍在 Mac mini，大小为 16,777,216 字节，SHA256 `22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1`，本轮重新复核通过。
- Mac mini 已不再有旧记录中的 `/dev/cu.usbserial-2120`；本轮枚举到 FTDI 的 **FT232R USB UART**（串口设备路径已改变）。**USB 枚举不证明 UART TX/RX/GND 仍连接到路由器**；需实际确认接线和 Bootloader 115200 串口恢复能力。
- 当前系统正常运行，内核 `4.4.176`，可继续 SSH 管理。
- 用户此前在聊天中公开了旧 RSA-3072 SSH 私钥：旧密钥须视为泄露，验证新密钥正常登录后应撤销旧授权。新 RSA-2048 私钥保留在 Mac mini；不提交密钥、Flash 镜像或固件到公开仓库。

## 首次写 Flash 前还必须完成的验收

1. **启动链兼容性**：确认现有 Bootloader 能否加载 1.5.0 的 `os-image`，或者验证首次更新 Bootloader 的安全写入和串口/编程器恢复方式。
2. **完整升级模拟**：对 `nm_updateDataToNvram` 及其调用链运行无硬件写入的设备仿真/桩测试，确认分区目标映射、分区表切换以及具体写入顺序；`-c` 仅能作为签名检查。
3. **硬件级回退**：验证串口连线和可靠的原始备份恢复流程，尤其是擦写 Bootloader 后串口 Bootloader 自身可能不可用的情况；若将写入 Bootloader，应具备外部 SPI 编程恢复计划。
4. **正式更新时明确授权**：不能从“继续研究”推断允许擦写运行中的 AX12。

**当前结论：仍然不能安全地执行首次 `nvrammanager -u`。** 已完成的工作是支持自签名校验、分区尺寸及静态写入路径的验证。


## 后续追加：无 Flash 操作的启动格式检查与虚拟升级（2026-11-02）

### 两代 `cr6c` 内核头与校验和

执行 `tools/firmware/check_kernel_boot_compat.py` 检查**两代官方镜像**：

```text
1.1.22: cr6c load=0x80c20000, burn=0x40000,
        data=0x380c02, package=0x380c13, checksum=PASS
1.5.0:  cr6c load=0x80c20000, burn=0x40000,
        data=0x393c02, package=0x393c13, checksum=PASS
PASS: kernel load address and Flash destination are unchanged
```

对于这两份 `os-image`，Realtek 16 字节大端头均标注同一 RAM 加载地址、内核 Flash 地址；对应数据部分按 16 位大端累加校验都等于零。这是**保留旧 Bootloader 的积极静态证据**，但不能证明实际内核能够执行及挂载新版 RootFS，也不能证明旧 Bootloader 的 RootFS 搜索配置与新版兼容。

旧 Bootloader 与新固件携带的 `fs-uboot` 开头均具有相同的复位代码布局，首处不同偏移约为 `0x124`；而后者仍有大量变化。不能因此跳过 UART 验收。

### 从真实设备备份创建“只读虚拟 Flash 升级”模型

`tools/firmware/virtual_first_upgrade.py` 读取 Mac mini 上先前核验的原始 **16 MiB Flash 备份**及当前经自有公钥验签的 1.5.0 Cloud 包，将新版清单中的 **10 个非 Bootloader 分区**按**新版分区表**写入一个普通磁盘文件，**仅为假设性的保留原 Bootloader 升级模型**，并检查保留内容。

实际在 Mac mini 上通过：

```text
PASS: 10 target partitions modeled, old bootloader preserved
New kernel header at 0x40000 and RootFS magic at 0x400000: PASS
User config, product identity, MAC and radio calibration retained: PASS
Virtual image size: 16777216
Virtual image SHA256:
7f4c3bb48c54ea1a865d75f88eff4fede3d8c6b799caae4ddface32773bc19a9
```

包含设备唯一内容的虚拟 Flash 镜像只保留在用户 Mac mini：`~/Desktop/AX12-RU-1.5.0-owner/VIRTUAL-FIRSTUPGRADE-NOT-FOR-FLASH.bin`。**不可上传公开仓库或整片刷写此测试镜像**。此模型验证所提议布局没有越界、且指定原始设备分区原样保留；它**不**复现原厂 `nvrammanager -u` 实际写入顺序，也不能证明固件可启动。

### 外部恢复与无写入测试路线

- 2026-10-03 发布的 [Archer AX12 V1 韩版救砖记录](https://thisok.org/board/Program/15) 报告通过 Realtek UART 提示符，使用 `AUTOBURN 0` 将 TFTP 文件仅加载到 RAM，再以显式 Flash 命令恢复 0x40000 内核分区和 0x400000 RootFS 分区，最终启动成功。案例与新版分区地址相符，但属于**他人其他地区板卡的报告**，不应直接当作我们 RU 机器上的实测结果，也不能使用韩版原始镜像覆盖俄版或设备专属区域。
- [Realtek 旧型号引导命令参考](https://jbit.net/Elecom_WRC-733FEBK_Part1/) 提供 `AUTOBURN`、`LOADADDR`、`J`、`FLR` 等命令背景；必须先在本机串口 `HELP` 中确认命令实际存在。
- **仅向 RAM 传入新版普通 `os-image`，即使成功执行，也可能尝试从 Flash 挂载其预期的新 RootFS；现有 Flash 仍是 1.1.22 布局，因此不能通过这种方法独立证明完整 1.5.0 系统启动兼容。** 若要全程不擦写测试新系统，需验证是否有适合 AX12 的专用 initramfs/RAM 启动构建及内存布局。
- Mac mini 上检测到 FT232R USB UART 设备，但串口与 AX12 的 TX/RX/GND 接线、Realtek 引导提示符都没有实机验证。不能把“USB 设备已枚举”视为“救砖功能已通过”。

**当前状态：离线内核头验证与假设性 16 MiB 虚拟迁移全部通过；实际 Bootloader 兼容性、Flash 写入顺序、UART 恢复还未通过。没有触碰真实 Flash。**



## Live UART verification: TFTP RAM and FLR flash reads (2026-11-03)

From the user's live `<RealTek>` session, **AutoBurning=0** and `IPCONFIG` shows target `192.168.0.1`. A 64-byte test file was loaded by TFTP into `0x81000000`; `DB` readback verified all 64 bytes. Next `FLR` reads were confirmed successful without any Flash write:

| Flash offset | 64-byte readback destination | Live magic/result |
|---|---|---|
| `0x000000` | `0x81001000` | `03 00 00 08`, matches original Bootloader backup |
| `0x040000` | `0x81002000` | `cr6c`, load `0x80c20000`, Flash burn `0x00040000`, payload length `0x380c02` |
| `0x440000` | `0x81003000` | `hsqs`, live inode count `0x09c4=2500` |

The original Mac mini Flash backup at `0x440000` instead starts with `hsqs`, inode count `0x09bf=2495`. This is **expected**: that full 16 MiB backup predates the previously successful root-SSH RootFS modification, whose documented final SquashFS contained **2500** inodes. The original backup is valid, but it is **not a byte-for-byte snapshot of the current running firmware**.

The USB-UART is now `/dev/cu.usbserial-A5069RR4`. The already-proven read-only `tools/ax12_flash_dump.py` was staged on Mac mini under `~/Desktop/AX12-RU-1.5.0-owner/ax12_flash_dump.py`; `pyserial 3.5` was installed in `~/Desktop/ax12-owner-venv`. Neither the backup script nor Flash-writing commands were executed during this inspection. Recommended next step is a distinct **current-state** full 16 MiB read-only backup (different filename from the original factory-state backup).

**Status:** UART monitor and per-partition readback proven. Full live-state backup, recovery after write failure, and old-Bootloader/new-kernel runtime compatibility remain separate checks.


## Bootloader-preserving Cloud trial (2026-11-03)

A new **experimental offline** option in [prepare_owner_cloud.py](prepare_owner_cloud.py) is `--omit-uboot`. It removes **only** the `fwup-ptn fs-uboot` update descriptor from the encrypted Cloud manifest before preparing a new RSA-PSS signing request; the original `fs-uboot` payload bytes remain in the Cloud container, but are not listed as an update target. **This is not permission to flash.**

A format-test package was built using a **disposable** signing key, not the owner's private key. Its RSA-PSS/SHA256 signature, AES decryption and exact custom RootFS check passed. Compared to the already signed owner 1.5.0 candidate, all decrypted Cloud bytes except the signature slot and update manifest are unchanged. The resulting manifest order is:

`os-image → file-system → re-def-config → partition-table → soft-version → extra-para → support-list → profile → default-config → ap-def-config`

Test-only staging on Linux Panel `10.7.0.1`: `/var/lib/linux-panel/ax12-firmware-work/owner-2026-no-uboot/`. The owner-signing input is `em.bin` (256 bytes) and has also been copied to Mac mini as `~/Desktop/AX12-RU-1.5.0-owner/em-no-uboot.bin`. **No new owner signature has been produced yet**; the 15-MB `unsigned.bin` is not a signed firmware. The owner's RSA-2048 private key stays exclusively on Mac mini.

**Caveat:** this is a structurally valid owner-signing request and disposable format-test only. We have NOT demonstrated that the proprietary 1.1.22 `nvrammanager -u` honors the missing bootloader update entry, correctly switches to the new partition table, or can boot 1.5.0 with the existing Bootloader. Do not execute `-u` or write any Flash sectors based on this result.


## 2026-11-03: owner-signed no-Bootloader Cloud built and independently verified

The user executed the Mac mini RSA-2048 private-key signing of the 256-byte EM request. Only the **256-byte signature** was copied from Mac mini to Linux Panel `10.7.0.1`; the private key remained on Mac mini.

Final candidate **local VPS only**:
`/var/lib/linux-panel/ax12-firmware-work/owner-2026-no-uboot/signed.bin`

- Full size: **15,370,972** bytes; SHA-256 `617a691801cde764075e45cd1cf20dd11491f7d48c8e64725ab3bb72257a9df9`.
- `finalize_owner_cloud.py` passed owner RSA-PSS/SHA256 verification, AES-128-CBC decryption, and exact sealed RootFS comparison.
- Independently compiled, owner-public-key-enabled **C** `tp-link-decrypt` printed `Firmware verification successful` and successfully decrypted. Its output matches the Python plaintext byte-for-byte across its full 15,370,952-byte output. This C tool omits the final 20 bytes of the original Cloud container.
- `migration_preflight.py` confirms 10 manifest update entries starting with `os-image` and **no `fs-uboot` update descriptor**. The new 28-entry Flash partition table, new `os-image` at `0x40000` and `file-system` at `0x400000`, and partition capacities pass offline structural checks.
- After decryption, comparison to the earlier **owner-signed** 1.5.0 Cloud candidate proves every byte except the signature slot `0x130..0x230` and manifest `0x1014..0x1814` is identical. The **bootloader payload remains inside the container** but has no manifest update descriptor; this is intentional to preserve subsequent payload offsets. This is not a proof that the old proprietary updater honors the omitted entry.
- A direct 15-MB copy back to Mac mini **timed out** and the destination is therefore **not a valid completed firmware file**. Before any future use, independently verify a complete local copy's size and SHA-256 above. **Do not use an incomplete transferred file.**
- At last user-reported status, AX12 remained at the live `<RealTek>` Bootloader prompt, not running 1.1.22 Linux. No live `nvrammanager -c` test was run on this new image, and no Flash write or reboot occurred.

**Remaining first-flash blockers:** full 1.1.22 `-u` write-path target mapping and behavior with missing `fs-uboot` descriptor; old Bootloader booting the new kernel/rootfs; validated recovery strategy, especially if a write crosses Flash partition boundaries. A successful `-c` at a later time would check signature but **not** these blockers.


## 2026-11-03: 1.1.22 更新模式静态推演（无 Flash 写入）

新增可重复运行的只读脚本 [plan_no_uboot_upgrade.py](plan_no_uboot_upgrade.py)，读取原始 1.1.22 Cloud 明文及已经正式签名验签后的 no-uboot 1.5.0 Cloud 明文，按 **1.1.22 `nvrammanager` 的相关 MIPS 反汇编**推演各分区模式。这个工具**没有执行**官方升级程序，也**没有**模拟 Flash I/O。

反汇编证据：旧版 `0x403c54..`（近似 `nm_getDataFromNvram`）在 Cloud 未提供某分区更新内容时，若当前 NVRAM 与目标分区的 Flash 基址相同，就设置记录偏移 `+0x2c` 为 **3**；否则会把原 Flash 内容读入内存并设置模式 **2**。旧版写入循环从 `0x403010` 开始，按 48 字节的分区记录遍历，检查模式并在模式 3 的情况下跳过写入。显式出现在 Cloud 更新清单中的分区对应模式 **1**；新表中但旧表里不存在、也没有 Cloud 载荷的分区为模式 **0**，数据大小为零。以上由静态代码和数据结构推断，未进行运行时 MTD 追踪。

对完整的正式签名 no-uboot Cloud 解密后运行脚本，结果：

| 推断模式 | 数量 | 内容 |
|---|---:|---|
| 1 — Cloud 载荷覆盖 | 10 | `os-image`、`file-system`、`re-def-config`、`partition-table`、`soft-version`、`extra-para`、`support-list`、`profile`、`default-config`、`ap-def-config` |
| 2 — 从旧 Flash 搬迁内容 | **0** | 无 |
| 3 — 原基址不变、跳过写入 | **14** | 包括 `fs-uboot`、`user-config`、`ap-config`、`router-config`、`product-info`、`default-mac`、`pin`、`device-id`、`radio` 等 |
| 0 — 新增、无升级内容 | **4** | `wireless-key`、`https_cert`、`uboot_env`、`login-key` |

在用户 Mac mini 的**原始 16 MiB Flash 备份**上逐段检查，这四个新增地址范围（`0xFE0700..0xFE2A00`）全部是 `0xFF`。这是旧备份的证据，不应假定现有 Flash 经过运行后仍完全一致；如果后续需要证明实机当前状态，应只读复查。

**重要限制**：这份模式推演不是 `nvrammanager -u` 运行实测，且未包含旧版升级器的所有条件和报错路径（例如固件策略、时序、Flash 擦除边界）。旧 Bootloader 能否启动新内核和新 RootFS 也未实测。首次升级必须满足这两项验证以及恢复能力要求，不能仅凭签名成功、模式推演成功就进行 Flash 写入。


## 2026-11-03: full owner-signed no-uboot candidate delivered and live 1.1.22 RSA acceptance test passed

**Complete Mac mini candidate**: `~/Desktop/AX12-RU-1.5.0-owner/AX12-RU-1.5.0-owner-NO-UBOOT-CANDIDATE.bin`. Independently checked on Mac mini: **15,370,972 bytes**, SHA-256 `617a691801cde764075e45cd1cf20dd11491f7d48c8e64725ab3bb72257a9df9`; matches the complete Linux Panel VPS file. The previously incomplete transfer is distinct and not used.

AX12 was restarted into the previous 1.1.22 system: `ssh ax12 'id; uname -r'` yielded `uid=0(root)` and `4.4.176`. Dropbear on port 2222 presented a new host key, which the owner confirmed and added to known_hosts.

For **read-only** live testing, the exact 15,370,972-byte candidate was copied via Mac mini into AX12's RAM-backed `/tmp/ax12-owner-no-uboot.bin`; its SHA-256 on the router matched exactly. A temporary 114,056-byte standalone copy of the 1.1.22 `nvrammanager` ELF with **only the embedded RSA-2048 verification public key** replaced by the owner public key was placed at `/tmp/nvrammanager-owner-check`. Its SHA-256 was `fa0b6a9388e952f07fe1f8193409d29b6bb2ab2c49dd9414b9db14c56c8776b2`. The installed `/usr/bin/nvrammanager` was unchanged.

- `/tmp/nvrammanager-owner-check -c /tmp/ax12-owner-no-uboot.bin`: output `RSA2048 PSS`, `md5 or cloud-func verify ok!`, `Check RSA2048 FW, no need analysis firmware, return OK.`, `chekc firmware file success!`; **exit 0**.
- **Negative control:** `/usr/bin/nvrammanager -c /tmp/ax12-owner-no-uboot.bin`: `RSA PSS Verify Error 1!`, `check firmware file failed!`; **exit 255**. This rejection is expected from the unmodified vendor RSA trust anchor.
- Both RAM-backed temporary files were removed after testing, and AX12 returned to ~44.6 MiB available memory. No Flash write, upgrade `-u`, reboot, or persistent router file change was performed during this test.

**Interpretation limit:** `-c` explicitly returns after RSA-PSS validation, without checking the full upgrade partition mapping or running any update writer. The old updater's real `-u` partition mapping and the old Bootloader's runtime ability to boot 1.5.0 remain unverified. Do not flash based on this positive signature result alone.


## 2026-11-03: MIPS write-loop branch, flash driver interface and decompressed kernel evidence

**Exact old 1.1.22 write-loop disassembly evidence (offline ELF only):**

- At `0x4031a0`, the mode field at record `+0x2c` is compared against 3; at `0x4031b0`, mode **3** branches directly to `0x403214` (advance to the next 48-byte record), bypassing the I/O calls. At `0x4031c0` mode 1 enters the source-to-Flash block, which calls wrapper `0x4043d4` and then `0x402620`. Thus **the actual old writer skips mode 3**; the inference that `fs-uboot` receives mode 3 remains based on its unchanged base, no Cloud payload and the old record-merging logic.
- `0x40236c` opens **`/dev/flash_chrdev`**, sending an ioctl request `0x8001b302` with destination Flash address, size, source buffer and mode fields. This is a dedicated Realtek character device, **not equivalent to writing `/dev/mtd1`**. The exact kernel driver erase/preservation behavior is **not yet validated**. In particular, several late firmware metadata partitions are smaller than the 64 KiB SPI erase size and may share erase blocks.
- Current AX12 Linux `/proc/cmdline`: `console=ttyS0,115200 root=/dev/mtdblock2 init=/etc/preinit`; `/proc/mtd` reports `uboot 0x40000`, `uImage 0x400000`, `rootfs 0xAF0000`, `ART 0x10000` with erase size `0x10000`. **MTD names/sizes do not independently prove actual physical offsets.** An independent RTL8197F vendor-kernel community report (https://github.com/adaasch/mr1500x-openwrt) cautions that its `rtkxxpart` driver misreports the `uImage` offset. That is a **related-device warning, not yet confirmed as an AX12-specific bug**.

**Both official Cloud `os-image` payloads contain an LZMA kernel at relative `0x2818`.** New repeatable readonly script [inspect_kernel_mtd.py](inspect_kernel_mtd.py) extracted and verified the LZMA stream:

| | Stock 1.1.22 | Stock-derived owner 1.5.0 |
|---|---:|---:|
| `cr6c` payload bytes | `0x380c13` | `0x393c13` |
| Decompressed MIPS Linux image | **12,215,964** bytes | **12,561,504** bytes |
| Linux version | 4.4.176, 2024-03-11 | 4.4.176-gd3618c8d0-dirty, 2026-06-05 |
| Target SoC string | RTL8197F | RTL8197F |
| MTD partition parser | `rtkxxpart` | `rtkxxpart` |
| Default root cmdline | `root=/dev/mtdblock2` | `root=/dev/mtdblock2` |

Both kernels use the same Realtek MSDK GCC 6.4.1 toolchain identifier. These shared driver/root conventions support the plausibility of a version-only kernel replacement, but **do not prove** the new kernel's partition offsets or the old Bootloader's ability to execute it.

**Independent virtual check repeated for the FINAL owner-signed no-uboot candidate** (not the original signed package), using original 16 MiB Flash backup **only on Mac mini** and [virtual_first_upgrade.py](virtual_first_upgrade.py): 10 target partitions, old Bootloader unchanged, `cr6c` at `0x40000`, `hsqs` at `0x400000`, original factory identity/radio/user partitions unchanged; output hash `7f4c3bb48c54ea1a865d75f88eff4fede3d8c6b799caae4ddface32773bc19a9`, identical to the previous virtual scenario. **This file must not be used for direct whole-chip flashing.**

Remaining unproven before real flash: **flash_chrdev ioctl erase/partial-sector behavior, full `-u` control flow, and old Bootloader → 1.5.0 kernel → new RootFS real boot compatibility.** No destructive action was taken.


## 2026-11-03: live-kernel Flash ioctl disassembly and sector-RMW file simulation

New evidence from the exact extracted 1.1.22 Linux kernel image `/tmp/ax12-unpacked-linux-old.bin` (12,215,964 bytes), matched against AX12 live `/proc/kallsyms`:

- `tp_flash_ioctl` at `0x801e1f00` dispatches ioctl **`0x8001b302`** to `0x801e18f8` and `0x4001b301` to `0x801e1818`.
- `0x801e18f8` is a nontrivial 64 KiB read-modify-write handler. The disassembly uses `0x10000`-sized buffers/blocks, calls the SPI NOR read path `0x801df7f8`, incorporates new bytes via buffer-copy operations, then performs erase and write through MTD/NOR helper calls. Other branches directly call `spiflash_ioctl_erase` (`0x801e0d98`) and `spi_nor_write` (`0x801e06b4`). Thus there is concrete binary evidence for preservation of adjacent bytes during **partial-sector updates**. This does **not** prove all branches, power-failure behavior, or return-code handling.
- Live `/proc/kallsyms` exports `spiflash_ioctl_read`, `spiflash_ioctl_write`, `spiflash_ioctl_erase`, `spi_nor_read`, `spi_nor_write`, `spi_nor_erase`; all four `/sys/class/mtd/mtd{0..3}/erasesize` report **65536** bytes.
- The TP-Link [AX12 V1 GPL archive](https://static.tp-link.com/upload/gpl-code/2024/202410/20241022/GPL_AX12v1.tar.gz) is publicly listed and HTTP advertises **1,695,028,301 bytes (~1.6 GiB)**. It was not downloaded into the small VPS. The extracted shipped kernel and live symbol table give directly relevant evidence without requiring the full archive.

To test the consequence of ordered, sector-preserving writes, created the read-only local file tool [simulate_sector_rmw.py](simulate_sector_rmw.py). This takes the **original 16 MiB Mac mini Flash backup** and the **fully verified owner-signed no-uboot Cloud**. It applies all 10 Cloud manifest updates in order as 64 KiB sector read-modify-erase-rewrite operations, never touches router interfaces, and does not generate a flashable image.

Results **on Mac mini**:

```
PASS: all 10 Cloud updates applied in declared order
PASS: 14 same-base legacy partitions unchanged, including fs-uboot and radio
Touched sectors: 237 of 256
Multiply-updated sectors: [('0xf40000', 5)]
Virtual RMW SHA256: 4fb23d4836c5ecb41cc6f104dd165428117417c5b94206d83ceb82cb71947f00
```

`0xF40000` is the shared 64 KiB erase block for **partition-table**, **soft-version**, **extra-para**, **support-list**, and **profile**. The file model preserves earlier updates to that sector when later records change small subranges. This provides evidence that these five logically separate metadata updates need correct physical sector RMW behavior.

**Why this SHA differs from the earlier virtual upgrade model:** the earlier [virtual_first_upgrade.py](virtual_first_upgrade.py) models clearing each **entire target partition** to `0xFF` before writing, whereas the present sector-RMW model replaces only the **explicit manifest payload bytes** and retains all unchanged trailing bytes within partitions. The difference is expected, and **neither SHA can predict the true post-upgrade Flash bitstream without full `nvrammanager -u` control flow and driver execution**.

**Still open:** full vendor update `-u` invocation and rollback/error path, proof that the existing Bootloader loads 1.5.0 Linux and that it mounts the new RootFS, and repeatable hardware recovery including interruption scenarios. No Flash writes, real upgrades or router reboots performed for this analysis.


## 2026-11-03: confirmed AX12 1.5.0 kernel RootFS offset from binary MTD structures

**Strong new positive finding:** directly extracted the actual `struct mtd_partition` definitions from both Linux 4.4.176 kernel images, not just the TP-Link Cloud update manifest. The actual 1.1.22 MIPS kernel image (12,215,964 bytes) contains the four 32-byte MTD records at virtual `0x80a5c408`; the official-stock-derived owner 1.5.0 Linux image (12,561,504 bytes) contains them at `0x80aac208`. Their string-name pointers (`uboot`, `uImage`, `rootfs`, `ART`) each resolve into the exact respective kernel image, and the 64-bit size and offset fields were decoded little-endian.

| Embedded kernel MTD definition | 1.1.22 | 1.5.0 |
|---|---|---|
| `uboot` | base `0x0`, size `0x40000` | unchanged |
| `uImage` | base `0x40000`, size `0x400000` | base `0x40000`, size **`0x3c0000`** |
| `rootfs` | base **`0x440000`**, size `0xb00000` | base **`0x400000`**, size `0xb10000` |
| `ART` | nominal base `0x1000000`, size `0x10000` | same nominal definition |

The `rtkxxpart_parse` kernel parser is the same substantive MIPS instruction sequence between versions (relocated from `0x801dc4b0` to `0x801dd600`). The parser adjusts some MTD sizes / terminal boundaries dynamically: on the live 1.1.22 system, `/sys/class/mtd/mtd{0..3}/offset` reports `0, 262144, 4456448, 16711680`, confirming the old kernel's actual rootfs `0x440000` and final ART `0xff0000` despite its nominal `0x1000000` table marker. The old runtime rootfs size is `0xaf0000`, rather than its nominal `0xb00000`. New offsets after runtime adjustment are **not proven** until a real boot, but the kernel's actual static new RootFS base is definitively `0x400000`.

A new readonly, reproducible tool [inspect_kernel_partitions.py](inspect_kernel_partitions.py) decompresses each Cloud `os-image` LZMA kernel, follows actual embedded name pointers, and decodes all four 32-byte MTD records. The tool passed both exact images.

To check safe physical capacity, parsed actual SquashFS superblocks from each Cloud's `file-system` payload. Stock 1.1.22 `bytes_used=0x9a73c4`, ending at `0xde73c4` when based at `0x440000`. Owner 1.5.0 `bytes_used=0xae3a0c`, ending at **`0xee3a0c`**, before the conservative `0xf00000` boundary; new target `file-system` partition starts at `0x400000` with capacity `0xb08000`. No RootFS end overlap is indicated by this size check.

**Meaning:** the specific feared mismatch “new Linux still tries the old 0x440000 RootFS base” is now ruled out at the **compiled static MTD layout** level. This substantially improves the preserve-old-Bootloader migration case. It still does not demonstrate old Bootloader → new Linux boot, runtime MTD partition parsing, successful SquashFS mount, or driver error handling. No router reboot or Flash write was performed.


## 2026-11-03: 旧 Bootloader RootFS 检查阻断（Critical blocker）

**明确撤回原先仅凭一致的 `cr6c` 头、内核加载地址和新 MTD 表就推断旧 Bootloader 能正常启动 1.5.0 的乐观结论。现在有代码级反证。**

Realtek 1.1.22 Bootloader `fs-uboot` 的首阶段在原始 Flash 镜像偏移 `0x8D60` 包含 gzip 第二阶段；解压完整 223,232 B。新版官方 1.5.0 `fs-uboot` 在相同压缩流偏移解出 257,184 B。两版第二阶段均包含 `cs6c`（Linux kernel）、`cr6c`（Linux kernel (root-fs)）、`hsqs` SquashFS 检查和 `no rootfs signature at %X!` 报错文本。

对确切的 MIPS 小端指令进行逐条核对：

- **旧 1.1.22：** `0x80017D04` 处调用 RootFS 检查函数 `0x800176D4`，延迟槽 `0x80017D08: lui a0,0xB044`，即 **`0xB0440000`** 映射的 Flash 地址 **`0x440000`**。
- **新 1.5.0：** `0x8001CF50` 调用检查函数 `0x8001C920`，延迟槽 `0x8001CF54: lui a0,0xB040`，即 Flash **`0x400000`**。
- 旧 `0x80017A28..0x80017A80` 根据 `cs6c` / `cr6c` 匹配设置不同图像类型：`cs6c` 对应类型 1，`cr6c` 对应类型 2。旧 `0x80017C84..0x80017C90` 的 `v0 == 2` 分支进一步进入独立 RootFS 检查。旧 `0x80015278` 的启动初始化链调用 `0x80017D48`，后者调用这些镜像检查逻辑并依据结果进入启动 / 恢复分支。
- 正式签名的 `NO-UBOOT-CANDIDATE` Cloud 明文在目标 Flash `0x400000` 的文件头为 `68 73 71 73` (`hsqs`)，但目标 Flash `0x440000` 位置为 `62 53 62 66`，不满足旧 Bootloader 的 RootFS magic 检查。对其他固定回退地址 `0x260000`、`0x270000`、`0x2B0000` 也没有构造 RootFS 镜像。

**结论：当前正式签名 `NO-UBOOT-CANDIDATE.bin` 与旧 Bootloader 的正常 `cr6c` 启动检查不兼容，禁止刷写。** 静态分析虽不是启动实测，但证据已经足以认定现有迁移方案存在高概率启动失败风险，不应进一步冒险实机升级。

可重复运行的只读验证：[check_bootloader_rootfs_gate.py](check_bootloader_rootfs_gate.py)，已通过旧／新 Bootloader 原始镜像和正式新 Cloud 的三方核对。

### 新的候选研究路线：`cs6c` 内核标记

已建立 **仅离线明文实验** `prepare_cs6c_bridge.py`。该实验只把新 `os-image` 头部 **一个字节**从 `cr6c` 改为 `cs6c`，其余 15MB Cloud 明文完全不变；内核载入 `0x80c20000`、Flash 目标 `0x40000`、长度 `0x393c02` 和16位数据校验和全部维持有效。局部实验明文 SHA256 `bcacc976914ce8c3f9e4fc9dfff2c7c9653d9507cc00c9666bb6bbd0c9c8a1b7`，仅保存在 Linux Panel：

`/var/lib/linux-panel/ax12-firmware-work/owner-2026-no-uboot/EXPERIMENT-CS6C-UNSIGNED-NOT-FOR-FLASH.dec`

**理论依据：** 原 Bootloader 内核类型 1 (`cs6c`) 分支在 `0x80017C88` 绕过仅对类型 2 (`cr6c`) 执行的旧 RootFS 预检查；随后可由新的 1.5.0 Linux 内核通过其已证实的 `rootfs` `0x400000` MTD 定义挂载根文件系统。

**不可跳过的验证：** 尚未实测旧 Bootloader 对修改后的 Linux 内核格式执行及解压结果，也未验证 1.1.22 `nvrammanager -u` 是否允许 `cs6c` 镜像或其真实写入流程。实验文件是 **未签名的解密明文，不能作为固件上传或写入**。不能据此认定 `cs6c` 技巧已解决启动兼容性问题。未执行任何路由器重启或 Flash 写入。


### Bootloader 所有固定 RootFS 检查位置的实测目标字节

在新 1.5.0 Cloud 的 `os-image`、`file-system` 中提取模拟 Flash 的以下四字节，证实旧检查候选地址全部不含 SquashFS magic：

| Flash 地址 | 更新后数据前四字节 | 对应 |
|---|---|---|
| `0x260000` | `12 35 46 CB` | 新 Linux 内核数据 |
| `0x270000` | `57 45 9C 53` | 新 Linux 内核数据 |
| `0x2B0000` | `0F 7C 04 1F` | 新 Linux 内核数据 |
| `0x440000` | `62 53 62 66` | 新 SquashFS 中间的压缩数据 |
| **`0x400000`** | **`68 73 71 73` (`hsqs`)** | **新的正确 RootFS 起点** |

在旧第二阶段的 `0x80017A24..0x80017A80`，`cs6c` 对应类型 1，`cr6c` 对应类型 2；`0x80017C88` 对模式 2 执行旧 RootFS 预检查，模式 1 可以绕过并进入后续内核执行分支。两代 Bootloader 的对应跳转检查代码已人工核对。因此 **`cs6c` 是值得进一步验证的保留旧 Bootloader 路线**，但不是已经通过实机启动的解决方案。

一次性、未签名实验通过 `prepare_cs6c_bridge.py` 只更改新版 Cloud 明文中内核魔数的第二个字节（明文偏移 `0x25152`），保持整个内核 body 和 checksum 不变。再用修订后的 `inspect_kernel_partitions.py` 检查，证明 `cs6c` 实验版本仍包含正确的 1.5.0 MTD 定义：`uImage` `0x40000`、`rootfs` `0x400000`。**未签名，未生成可供升级的 BIN，未执行任何路由器写入。**


### 2026-11-03：`cs6c` 封包格式实验（仅一次性测试密钥）

扩展 `prepare_owner_cloud.py`，新增可选 `--kernel-magic cs6c`（默认仍是 `cr6c`），可与 `--omit-uboot` 同时使用。新版完整官方 Cloud 与既有封存 RootFS 重新打包后，在无私钥环境产生仅供实验的待签名容器及 256-byte RSA-PSS encoded message。

为避免误用，**未调用用户 Mac mini 上的正式私钥**。测试用一次性 RSA 密钥签名，产出 VPS 本地文件 `owner-2026-cs6c-bridge/TEST-KEY-ONLY-CS6C-NOT-FOR-FLASH.bin`。后续用对应公钥执行 RSA-PSS 验签、AES 解密和 RootFS 校验，均通过，**不能作为用户实际可升级的固件**。SHA256 `68bfe89d1be8e17542fa86ddca5f8eed474a9d334d49ff251d9a4d9c6c2c4a69`。

将其解密数据与先前正式签名的 `NO-UBOOT-CANDIDATE` 解密数据作逐字节比较：在签名和随机盐位置之后，**仅偏移 `0x25152` 一个字节不同**（`cr6c` → `cs6c`），其余全部一致，且更新清单仍不含 `fs-uboot`。改动前后 kernel load=`0x80c20000`、burn=`0x40000`、payload=`0x393c02`、16 位数据校验和全部通过。修订后的 `inspect_kernel_partitions.py` 接受 `cs6c` 并确认 RootFS MTD 基址仍为 `0x400000`。

**研究状态：** 此方案可能利用类型 1 内核加载路径绕过旧 Bootloader 的 `0x440000` RootFS 预验证；但不等于已证明能启动，而且还没有对真实旧版升级器的 `-u` 行为进行完整仿真。**现有 owner 签名 NO-UBOOT 固件仍为禁刷状态。新实验未实际写 Flash、未重启 AX12。**


### 2026-11-03：旧 Bootloader 的 `cs6c` → 内核跳转路径复核

**新增独立证据来自 Realtek 开源 SDK（相关型号，非 AX12 原厂精确源码）：** [`rtk.h`](https://github.com/jameshilliard/WECB-VZ-GPL/blob/master/rtl819x/bootcode/boot/init/rtk.h) 明确定义 `cs6c` 为 `FW_SIGNATURE`、`cr6c` 为 `FW_SIGNATURE_WITH_ROOT`。[同仓库 `utility.c`](https://github.com/jameshilliard/WECB-VZ-GPL/blob/master/rtl819x/bootcode/boot/init/utility.c) 的 `check_system_image` 把前者映射为返回值 1、后者映射为 2；`check_image_header` 仅在返回值为 2 时执行 `check_rootfs_image`；成功后 `goToLocalStartMode` 读取镜像头、复制内核到 RAM 并跳转到其 `startAddr`。这与 AX12 上一轮反汇编结论一致，但不能用相关设备源码直接代替本机验证。

为避免仅依据类比，重新在 **Linux Panel 的原始 AX12 RU 1.1.22 Bootloader 二进制** `/tmp/ax12-uboot-original.bin` 上核查了第二阶段（223,232 B，SHA256 `304776874874547f63f34134e511bd9f1c92dfb64ba1f337c1b35e2ad00de60c`）：

- `0x80029438` / `0x80029450` 分别指向 `cs6c` / `cr6c` 字符串；`0x80017A5C` 与 `0x80017A78` 将匹配类型分别设为 1 / 2。
- `0x80017B94` 返回已验证的镜像类型；`0x80017C84` / `0x80017C88` 将类型 2 送入独立 RootFS 校验，类型 1 则跳过。旧根文件系统硬编码地址仍是 `0x80017D08: lui a0,0xB044`。
- 在调用链下游，`0x80017D78` 调用镜像校验函数 `0x80017BC8`，返回非零时 `0x80017D90` 调用共同加载函数 `0x800173B4`。后者在 `0x80017490` 调用数据复制函数，并在 `0x80017528..0x8001752C` 执行 `move t9,s0; jalr t9`，跳转至从头部取得的 RAM 加载地址。

新增只读回归工具 [`audit_cs6c_boot_path.py`](audit_cs6c_boot_path.py)，对原始 Bootloader 的魔数位置与 **16 个**关键 MIPS 指令逐一验证。已在 Linux Panel 使用 GitHub 精确提交 `9e117b77ab59df6b4a7a0c66d3d12407405873f9` 的脚本运行，16 项全部 PASS，退出码 0。该测试既不接触路由器，也不修改固件。

**更新后的边界：** 已经有 AX12 自身的二进制证据表明 `cs6c` 类型 1 能沿正常的检查成功路径到达共同的内核复制 / 跳转代码，且不会因旧的 `0x440000` 独立 RootFS 预检查被拒绝；**尚未证明**实际执行新内核后能够挂载 `0x400000` 的 RootFS，更没有证明旧 `nvrammanager -u` 会接受或正确写入这种镜像。当前无可刷写的 `cs6c` 正式候选包；禁止运行任何真实 Flash 写入或升级命令，直到升级器全路径仿真、当前 Flash 只读备份与恢复能力验证完成。


### 2026-11-03：旧升级器 `-u` 分区写入分派与内核 ioctl 双侧核对

新只读工具 [`audit_old_updater_dispatch.py`](audit_old_updater_dispatch.py) 使用原始 1.1.22 `nvrammanager` ELF、解压的同版 Linux 内核和仅离线的 `cs6c` Cloud 明文，核对 **21 条升级器 MIPS 指令及 12 条内核指令**。Linux Panel 本地执行均通过；只读取已保存文件，未执行 `nvrammanager -u`、未调用真实 `/dev/flash_chrdev`，也未触碰 AX12。

**用户态实际分派：**

- `0x4031B0`：模式 3 跳过写入；`0x403388..0x4033C4`：16 字节分区名称匹配 `partition-table` 时选择 `0x404408`，否则选 `0x4043D4`。
- 普通写入经 `0x402620` 设置 ioctl 参数模式 **0**，分区表专用写入经 `0x402638` 设置模式 **1**；两者均汇入 `0x40236C`，通过请求 **`0x8001B302`** 使用 `/dev/flash_chrdev`。
- ioctl 结构字段从偏移 0 起依次是 Flash 目的地址、payload 长度、payload 指针、payload 长度副本和模式参数；这些字段转发由用户态指令和下面的内核处理同时交叉核对。

**内核实际分派：**

- `tp_flash_ioctl` 的 `0x801E1F98..0x801E1FAC` 把模式作为第二参数、Flash 目的地址作为第三参数、payload 指针作为第四参数、长度作为第五参数传给共同处理函数 `0x801E18F8`。
- `0x801E193C: beqz a1,0x801E1BB0`：模式 **0** 进入普通路径；模式 **1** 顺序执行 `0x801E1944: addiu s4,s4,8`，对传入长度 **额外计入 8 字节**，并执行另一套头部/扇区处理。两个分支最终都使用 SPI NOR 读、擦除和写入相关助手，但**不表示两种模式产生相同的 Flash 字节布局**。
- 这 8 字节属于驱动行为，并未体现在 Cloud 清单 `partition-table size 0x800` 中。尚未还原特殊模式最终写入的所有头部字节和失败路径；任何按原始 Cloud payload 直接覆盖模拟分区表的模型，都不得视为真实驱动写入结果的逐字节预测。

对现有 `cs6c` 实验 Cloud 的静态分派共 10 项：9 项使用模式 0，独立的 `partition-table` 使用模式 1；无 `fs-uboot` 更新记录。新分区表中的内核基址 `0x40000`、RootFS 基址 `0x400000` 和清单范围检查通过。物理 `0xF40000` 的 64 KiB 扇区承载 5 次元数据更新（`partition-table`、`soft-version`、`extra-para`、`support-list`、`profile`），必须验证后续四次更新不会覆盖先前分区表提交。

**明确收窄模拟模型结论：** `virtual_first_upgrade.py` 与 `simulate_sector_rmw.py` 都属于文件级假设性布局检查，尚未准确实现 mode-1 附加 8 字节的实际头部/写入语义，既不能以其 SHA-256 预测实机 Flash，也不能以「10 项模拟更新通过」作为升级器安全证明。旧升级器是否在前置校验中接受 `cs6c`、是否按目标新表正确映射、以及实机启动与恢复能力仍未通过。下一项应是把内核 mode-1 的最终字节布局和旧升级器完整错误处理链解出，再建立有隔离 Flash 后端的实际 `-u` 测试。**禁刷状态保持不变。**
