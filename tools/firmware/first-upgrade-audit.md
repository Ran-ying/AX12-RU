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
