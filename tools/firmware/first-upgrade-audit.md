# AX12 RU 1.1.22 → 自签名 1.5.0：首次迁移静态审计

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
