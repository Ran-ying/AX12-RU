# AX12-RU M5 — 首次升级离线最终验收（2026-11-03）

## 判定

**旧 1.1.22 升级器的候选固件接受 / 物理写入地址与顺序：离线动态验收通过。**

**真实首次刷写：尚不放行。** 拥有者正式签名的 cs6c 候选包已生成并通过独立校验以及 QEMU `-c`、`-u` 验收；仍需在实机确认可用的 UART / TFTP 恢复流程。无法靠更多静态检查证明新系统能够在本机成功启动，因此第一次启动仍是受控硬件实验，不应称为“安全无风险”。

本轮全部操作均在独立 Linux Panel VPS 的 QEMU / PRoot 中进行。**没有连接 AX12 Flash 设备，没有写入或重启实机。**

## 实际运行，而非静态猜测

测试使用已保存的 AX12 RU 1.1.22 `nvrammanager` MIPS ELF，仅将验证公钥替换为**一次性测试公钥**；`-u` 实际执行的是厂商升级程序本身（不是 Python 重写升级器）。

- Linux guest：原 1.1.22 RootFS，QEMU `qemu-mipsel-static` + PRoot。
- Flash 接口：GDB 在该 ELF 的 `ioctl@plt 0x4198a0` 截获 `0x4001B301`（读取）与 `0x8001B302`（写入），后端为 VPS 内的合成 **16 MiB** Flash 字节数组，绝无真实路由器设备。
- 测试固件：`TEST-KEY-ONLY-CS6C-NOT-FOR-FLASH.bin`（SHA-256 `68bfe89d1be8e17542fa86ddca5f8eed474a9d334d49ff251d9a4d9c6c2c4a69`）；内核头是 `cs6c`，Cloud 清单没有 `fs-uboot` 更新项，签名仅供一次性测试，不可刷机。
- 16 MiB 合成基线 SHA-256：`43317182ad2d83348f74c876fc89b231b2b28dbce24f12e24ef612738f96c694`，来自旧官方 Cloud 的分区和载荷及不含私密配置的 AX12 RU 产品身份测试字段。**未在 QEMU 中使用实际用户设备的 Flash 镜像**。
- 原始固件旧 `nvrammanager -s` 在截获 Flash 读请求后成功识别旧 24 分区；换用临时测试公钥的 `-c` 成功。
- **真实 `-u` 控制流运行到** `Firmwave supports, check OK.`、`check firmware ok!`、`Done.`、`upgradeFirmware success...`。
- QEMU 中 `main` 最终报告 `pthread_cancel failed!` 且进程以 **255** 退出（隔离环境的运行时服务不完整）。因此本文的“升级成功”指**厂商写入逻辑执行完成并发出成功日志**，不表示 clean exit 0 或路由器成功启动。

## 写入轨迹（实际拦截的旧升级器 ioctl）

| 类别 | 请求数 | 关键事实 |
|---|---:|---|
| 升级前状态标志 | 1 | `0xF42000`，mode 1，2 字节 `01 00` |
| 目标 Cloud 清单 | 241 | 包括 `0x40000` 的 `cs6c` 内核、`0x400000` 的新 RootFS、分区表与配置 |
| 新分区初始化 | 4 | `0xFE0700`、`0xFE0800`、`0xFE2800`、`0xFE2900` |
| 升级完成状态标志 | 1 | `0xF42000`，mode 1，2 字节 `01 01` |
| **合计** | **247** | 全部被虚拟 Flash 接管 |

**更正早期文件级推测：** 分区表实际 ioctl 为 `0xF40000`、**长度 `0x540`**（28 条记录 × 48 字节）、mode 1；驱动模式 1 还会附加 8 字节头部。Cloud 清单所声明的 `size 0x800` 不等于实际发给 Flash 驱动的用户态写入长度。

- 247 次写入涉及 **238 个**不同的 64 KiB 物理扇区。
- 扇区 `0xF40000` 被更新 **7 次**：元数据 5 次、状态标志前后 2 次。
- 扇区 `0xFE0000` 被更新 **4 次**：四个新分区初始化。与同扇区的设备身份记录相邻，正确的扇区读改写十分关键。
- Bootloader `[0x000000,0x040000)`、ART `[0xFF0000,0x1000000)` **均没有 ioctl 写入请求**；其不变性仍取决于实际内核扇区读改写遵循已经反汇编分析的机制。

## 独立的完整字节级对照

修改后的 [`simulate_cs6c_driver_writes.py`](simulate_cs6c_driver_writes.py) 包含全部 16 个逻辑阶段 / 247 次请求（包括状态、分区表特殊头部、四个新增分区），与动态跟踪的写入位置、长度和模式对应。

对完全相同的上述合成 Flash 基线与 `cs6c` Cloud 明文进行比较：

| 测试方法 | 最终模拟 Flash SHA-256 |
|---|---|
| 真实 MIPS `nvrammanager -u` + GDB 虚拟 Flash | `47bccd070878757a733f5ffcd3f2e21c71527dd5a1edfdff71f93e7abe29a032` |
| 独立 Python 文件级读改写模拟 | `47bccd070878757a733f5ffcd3f2e21c71527dd5a1edfdff71f93e7abe29a032` |

两条路径最终字节级哈希完全一致。**这证明我们已经精确复现了此次 MIPS 程序实际发出的全部写入请求在所建虚拟驱动下的最终内容；它不是 Realtek 内核 SPI 驱动的物理执行证明。**

## 故障注入

在 GDB 后端拦截写 ioctl 并返回失败，使用 [`validate_m5_trace.py`](validate_m5_trace.py) 自动检查：

| 注入位置 | 失败前已发生的写 ioctl | 实测结果 |
|---|---:|---|
| `0x40000`（首个内核块） | 1 | 已置升级中标志；报 WRITE TO NVRAM FAILED，停止后续写入 |
| `0xF40000`（分区表） | 235 | 内核、RootFS 等已被写入；报失败，停止剩余更新 |

**没有自动回滚。** 软件层拒绝后续写入不代表断电或部分固件损坏时可自动复原；这是首次实验前必须准备硬件恢复方案的直接理由。

## 可复现工具与签名准备

- [`qemu_flash_ioctl.py`](qemu_flash_ioctl.py)：GDB Python，拦截真正的 MIPS 原厂 `ioctl@plt` 并写入内存虚拟 Flash；支持按指定地址失败注入及私有输出文件。
- [`validate_m5_trace.py`](validate_m5_trace.py)：校验实际 247 次写入、扇区分布、禁触范围和失败后的停止行为。对成功和两个失败轨迹均已运行 PASS。
- [`simulate_cs6c_driver_writes.py`](simulate_cs6c_driver_writes.py)：基于厂商实际请求修订的文件级模拟，合成 Flash 最终 SHA 与 QEMU 完全一致。
- [`owner_cs6c_signing_request.b64`](owner_cs6c_signing_request.b64)：256 字节 RSA-PSS encoded message 的 Base64，仅为后续 **Mac 本地私钥签名准备**；解码 SHA-256 为 `68b9874e87c3f1cd6227034131abb31369c67dab4dc271a4aec1a2c832699176`。**绝不上传私钥。** 已在 VPS 核对它与未签名 cs6c 容器配对。签完仍须正式 RSA 校验、Cloud 解密和独立目标结构检查。

## 最终决策与明确的退出条件

| M5 验收门 | 状态 |
|---|---|
| 原始 Flash / SSH 历史镜像完整性 | **PASS**（用户本地实测） |
| 旧版 `-u` 硬件识别、RSA、`cs6c` 升级路径 | **PASS — QEMU 合成基线 / 一次性密钥** |
| 247 次写请求、起止地址、分区表特殊头部、最终哈希一致性 | **PASS — 模拟驱动** |
| 两处代表性写失败后的立即停止 | **PASS — 故障注入** |
| 真正的原版 SPI NOR 内核驱动与实机断电恢复 | **未通过实测** |
| 实机旧 Bootloader 启动 1.5.0 内核和 RootFS | **未通过实测** |
| 最终拥有者签名的 `cs6c` 固件 | **PASS — owner 公钥验签、AES/RootFS、QEMU `-c` 与 `-u`** |
| UART 原始备份恢复就绪（非只读 FLR） | **需首次实验前再次现场确认** |

**结论：M5 离线升级器与最终 owner-signed cs6c 候选的测试全部完成；尚不能声称首次刷写没有风险。下一阶段只需核实 UART 实机恢复条件与可接受的首次启动实验风险，刷写必须单独取得用户授权。**


## 正式 owner-signed cs6c 候选最终验证（用户上传签名后）

用户仅上传 256 字节 `sig-cs6c.big`；SHA-256 `3f71e3d020833758f3c406b09c4b3bffb08f15d7fe43afaf831b367f337acbef`。用已有的临时 owner 公钥版旧升级器 ELF 提取 RSA 公钥，实际验证 `sig^e mod n` **严格等于**先前准备的 256 字节编码消息，确认该签名属于同一 RSA-PSS 请求；**没有传输或读取用户私钥**。

在 Linux Panel 离线工作目录生成候选：
`/var/lib/linux-panel/ax12-firmware-work/owner-2026-cs6c-bridge/OWNER-SIGNED-CS6C-NO-UBOOT-CANDIDATE-NOT-FOR-FLASH.bin`

- 文件大小：**15,370,972 字节**
- **SHA-256：`ddf9880b29715a9189666a5256d86b3f2d8daec342219704a01edce0f696bf7c`**
- owner RSA-PSS/SHA-256 验签成功、vendor 原厂公钥拒绝自签名（预期负对照）、AES 解密成功。解密后的固件除签名区域外与先前独立审计的 `cs6c` 明文**逐字节相同**。
- 更新清单为 10 项（无 `fs-uboot`）；新内核头 `cs6c`，load `0x80C20000`，burn `0x40000`，RootFS 载荷 `0xAE4003` 字节，与此前版本 SHA-256 `9ed7f223b8f41aa7d84d346b026fe6374bd6b618a24229fbab25663a9b517c3f` 逐字节一致。
- QEMU **正式 owner 公钥版 1.1.22 `nvrammanager -c`**：签名检查成功，正常退出，Flash **0 写入**。
- QEMU **同一二进制 `nvrammanager -u`**：产品与版本检查通过，打印 `Done.` 和 `upgradeFirmware success...`。GDB 截获 **18 读、247 写**，涉及 **238 扇区**，没有 Bootloader 或 ART 写请求。正式签名包与一次性测试签名包对同一合成 Flash 基线得到**完全相同的虚拟最终哈希** `47bccd070878757a733f5ffcd3f2e21c71527dd5a1edfdff71f93e7abe29a032`；`validate_m5_trace.py` 全 PASS。
- 隔离环境最后仍报 `pthread_cancel failed`，因此 `-u` **进程退出码为 255**，此项未改变。不能将这次日志中的“success”当作正常系统退出、实机成功升级或启动成功的证据。

**重要：** 该候选位于 VPS 的私有研究目录，**没有提交到公开 GitHub，也没有传给 AX12 实机**。绝不可在尚未通过恢复与首次实验授权前通过 Web 升级或 `nvrammanager -u` 烧写。

**最新决策：离线 M5 全部通过；实机首次刷写仍为 NO-GO。**


## M6 方案决定：单公钥信任（用户确认）

用户明确选择保留当前的 **owner-only RSA-2048** 信任模式，不增加双公钥或官方密钥的默认信任分支。当前 `build_owner_rootfs.sh` 将默认 `/usr/lib/libnvrammanager.so` 的 RSA-2048 验签公钥替换为 owner 公钥，故**正式签名 cs6c 候选包无需为此重新构建**。

长期升级策略：后续 TP-Link 新版固件应先逐版解包、核对格式及兼容性，再移植用户定制内容（包括 SSH 和 owner-only trust library）并由用户 Mac mini 上的私钥重新签名。直接升级未修改的官方固件通常会覆盖定制 RootFS，并且被单公钥验证器拒绝；保留旧 Bootloader 不意味着固件验证器自动成为硬件安全根或无法恢复官方固件。

M6 用户最近只读实机输出：内核 `4.4.176`、旧 `/proc/mtd` 分区布局（0x40000 uboot、0x400000 uImage、0xAF0000 rootfs、0x10000 ART）、SSH 正常、Mac 枚举 UART `/dev/cu.usbserial-2120`，`df -h /tmp` 报 tmpfs 0/0（尚不能据此判断实际可用内存）。`/proc/uptime` 约 229.98 秒。需进一步在当前运行状态下只读核对 `/proc/meminfo`、mount 实际情况，以及 UART 实际接线/恢复能力；**本设计决定本身不授权 Flash 写入、升级或重启。**


## M6：真实 AX12 对正式 owner 签名 cs6c 固件的只读检查通过（用户终端实测）

用户已将完整正式候选包和临时 owner 公钥版旧升级器放入 AX12 RAM-backed `/tmp`，分别在 Mac mini 和 AX12 验证完全一致：

- `ax12-cs6c.bin`：`ddf9880b29715a9189666a5256d86b3f2d8daec342219704a01edce0f696bf7c`
- `nvrammanager-owner-check`：`fa0b6a9388e952f07fe1f8193409d29b6bb2ab2c49dd9414b9db14c56c8776b2`

**实机只执行** `/tmp/nvrammanager-owner-check -c /tmp/ax12-cs6c.bin`。实际输出包括 `Reading Partition Table from NVRAM ... OK`、`Parsing Partition Table ... OK`、`RSA2048 PSS`、`md5 or cloud-func verify ok!`、`Check RSA2048 FW, no need analysis firmware, return OK.`、`chekc firmware file success!`，最终 `EXIT_CODE=0`。

此实机测试**仅验证了 RSA 与分区表初始化，-c 明确跳过固件后续分析**。没有执行 `-u`、Flash 擦写、重启或新系统启动。M5 独立 QEMU 升级全流程测试依旧有效，但不能取代实机驱动或启动验证。

**当前决策：软件预检结束；首次 Flash 写入仍需用户明确授权和接受剩余不可恢复风险。** 已备份历史镜像、已测 UART 双向通信；UART 接口连通性不等于在首次写入中断或 Linux 挂载失败后必然可恢复，尤其应避免误判 Bootloader 故障可通过 Bootloader 自己恢复。
