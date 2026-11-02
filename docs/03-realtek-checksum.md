# 03 · Realtek RootFS 校验格式、首次启动失败与最小修复

[返回首页](../README.md) · [上一步](02-rootfs-and-ssh.md)

## 首次失败是如何出现的

第一次仅把新 SquashFS 镜像 `reports/rootfs-ssh-password.sqfs` 的 **`0x9A5000` 字节**写进 Flash 偏移 `0x440000`，并用 `FLR` 与 `CMP` 确认字节正确。结果 Bootloader 仍停在 `<RealTek>`，无法进入 Linux，管理页面进入 TP-Link 故障恢复模式。

这不是传输或写入比较失败，而是 **直接用 `mksquashfs` 生成的标准 SquashFS 不满足 Realtek Bootloader 的厂商校验要求**。

注意：Bootloader 输出的 `no sys signature` / `no rootfs signature` 文本也会出现在原厂正常启动日志中，**单凭这些字符串不能认定故障原因**；这次是通过完整镜像和厂商源码的交叉校验定位。

## 格式来自 GPL 的 Bootloader 源码

本次 VPS 中确实检查过：

```text
~/AX12-research/source/gpl-meta/GPL_AX12v1/rtl8197/bootcode/boot/init/utility.c
```

`check_rootfs()` 使用 `hsqs` 魔数，读取 RootFS 起点偏移 `0x08` 的 **4 字节大端厂商长度字段**，实际校验长度：

```text
verify_length = BE32(rootfs[8:12]) + 640 + 2
```

按大端 16 位字累加该范围（包括末尾 2 字节校验字），要求模 `0x10000` 的和为 **0**：

```python
checksum = sum(
    int.from_bytes(data[i:i+2], "big")
    for i in range(0, len(data), 2)
) & 0xffff
assert checksum == 0
```

标准 SquashFS v4 的 offset 8 原本是 `mkfs_time`；这台机器的 OEM 固件把它当作特殊长度字段使用。必须修正该位置并附加校验字；单改标准 SquashFS 的 `bytes_used` 不够。

## 从原厂备份验证的事实

| 项目 | 原厂 RootFS | 第一次改包（未封装） |
| --- | --- | --- |
| Flash 起点 | `0x440000` | `0x440000` |
| SquashFS 魔数 | `hsqs` | `hsqs` |
| `bytes_used` | `0x9A73C4` | `0x9A46EC` |
| RootFS offset `0x08` | `00 9A 7D 80` | `C4 A4 E7 6A` |
| Bootloader 校验终点（不含） | `0x9A8002` | 错误长度 |
| 尾部校验字 | `F9 8A`（relative `0x9A8000`） | 未按格式生成 |
| 实际校验和 | `0000` | 不满足 |

原厂完整 16 MiB 备份 SHA256：

```text
22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1
```

首次打包 RootFS（不带 Realtek 校验）SHA256：

```text
603f2d4cc69b28f896f511c078893c9b2b26b2d6d3c1ee8adde372f29fcf2617
```

## 本次实际执行成功的两扇区修复

针对当时 Flash 中已经写入但未启动的 `0x9A5000` 字节，离线计算结果是：

| Flash 绝对偏移 | 旧字节 | 修复字节 |
| --- | --- | --- |
| `0x440008` | `C4 A4 E7 6A` | `00 9A 4D 80` |
| `0xDE5000` | 保留的旧数据 | `94 C4` |

因为这两个位置分别位于两个不同的 **4 KiB 擦除扇区**，不能只执行针对单个字节的 Flash 写入并假定周围数据不变。实际先通过 `FLR` 将完整扇区读进 RAM，`EB` 改几个字节，再 `FLW` 写回完整扇区并 `CMP` 验证。

以下是当时故障恢复的**历史命令，仅适用于精确匹配上述旧镜像的状态**。当前设备已经运行更高版本的公钥 RootFS，**不要在当前设备再次照抄这组旧补丁**。

```text
# 当时的状态：已刷入未封装的 rootfs-ssh-password.sqfs，无法启动
FLR A5000000 440000 1000
FLR A5001000 DE5000 1000
DB A5000000 16
DB A5001000 16

# 仅修改 RAM 中的两份 4 KiB 扇区副本
EB A5000008 00 9A 4D 80
EB A5001000 94 C4

# 确认原始文件头与待改字节吻合后，才执行以下实际 Flash 写入
FLW 440000 A5000000 1000 0
FLR A5002000 440000 1000
CMP A5002000 A5000000 1000

FLW DE5000 A5001000 1000 0
FLR A5003000 DE5000 1000
CMP A5003000 A5001000 1000
```

两次 `CMP` 实际均应输出 `No error found`。修复后原厂 Web 后台恢复，随后已确认 SSH 2222 端口能响应。

这次修复后镜像的已验证 SHA256：

```text
2f621f489d0d4c460917e56aed8b1512ac875d2a5a0ed1e253529e76832a6dbc
```

## 后来采用的可靠封装方式

无需再手改两个扇区：后续改成在 VPS 上先运行 [`../tools/ax12_seal_realtek_rootfs.py`](../tools/ax12_seal_realtek_rootfs.py)，生成带长度字段与 16 位校验字的完整镜像，并按 4 KiB 对齐后一次写入。

脚本只操作本地文件，不连接路由器；任何镜像都必须先核对 **`file-system` 范围 `0x440000..0xF08000`**，不能越界写入设备配置/校准区。

后续：[04 · UART V2 RAM 传输及写 Flash](04-uart-v2-flashing.md)。
