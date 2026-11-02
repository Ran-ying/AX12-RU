# 06 · 实验路径索引、工具清单与踩坑记录

[返回首页](../README.md)

本文只列出从实际终端、脚本及镜像得到的**正确路径**；不对未见到的文件假设仓库位置。

## 正确文件路径

### Mac mini（运行串口与最终 SSH）

以下路径均出现在本次 Mac mini 的 `~/Desktop` 列表或实际执行命令中：

| 绝对路径 | 功能 |
| --- | --- |
| `/Users/ranying/Desktop/ax12_uart_send.py` | 经过实测的 UART Loader V2 发送器（**原文件未归档到本仓库**） |
| `/Users/ranying/Desktop/receiver.bin` | 992 字节 MIPS V2 RAM 接收器（原文件未归档） |
| `/Users/ranying/Desktop/receiver.S` | 接收器汇编源码（原文件未归档） |
| `/Users/ranying/Desktop/receiver.elf` | 其 ELF 产物（原文件未归档） |
| `/Users/ranying/Desktop/eb_upload.py` | 早期 `EB` 上传工具（原文件未归档） |
| `/Users/ranying/Desktop/ax12_flash_dump.py` | 早期 Flash 备份脚本（源码现已归档为 [tools/ax12_flash_dump.py](../tools/ax12_flash_dump.py)） |
| `/Users/ranying/Desktop/ax12-flash-16MiB.bin` | 16 MiB 原厂备份，**私有，不上传** |
| `/Users/ranying/Desktop/rootfs-ssh-password.sqfs` | 曾用于启动测试的 RootFS，**不上传** |
| `/Users/ranying/Desktop/rootfs-ssh-pubkey-flash.bin` | 实际成功刷入的公钥版 RootFS，**不上传** |
| `/Users/ranying/.ssh/ax12_root` | 本机 SSH 私钥，**绝不上传** |
| `/dev/cu.usbserial-2120` | 本次接 UART 的 macOS 设备路径，**仅本实验适用** |

注意 `~/Desktop/ax12-uart/` 目录本次实际为空（仅隐藏 `.DS_Store`），**真正的发送器和 receiver 位于 `~/Desktop/` 根目录**。不要错误地提供 `~/Desktop/ax12-uart/ax12_uart_send.py` 路径。

### VPS（本次 `root@linveo`）

所有路径相对于 `/root/AX12-research`：

| 相对路径 | 实际用途 |
| --- | --- |
| `source/ax12-flash-16MiB.bin` | Flash 备份 |
| `source/gpl-meta/GPL_AX12v1/rtl8197/bootcode/boot/init/utility.c` | Realtek 校验逻辑分析用源码 |
| `reports/rootfs-ssh-password.sqfs` | 首次 SSH RootFS，含 `ax12-ssh` 启动脚本 |
| `reports/rootfs-ssh-pubkey-source/` | 最终公钥版 RootFS 解包目录 |
| `reports/ax12_root.pub` | MacBook 上传的 SSH 公钥，**不上传** |
| `reports/rootfs-ssh-pubkey.sqfs` | 公钥版标准 SquashFS |
| `reports/rootfs-ssh-pubkey-realtek.bin` | 加 Realtek 厂商校验的 RootFS |
| `reports/rootfs-ssh-pubkey-flash.bin` | 对齐到 4 KiB，实际用于 UART V2 传输/刷写的文件 |

最初存于 Notebook 的两个工具路径（本次确实存在，现已有本仓库版本）：

```text
/root/Notebook/CS/AX12/ax12_seal_realtek_rootfs.py
/root/Notebook/CS/AX12/ax12_login_root_shadow_patch.py
```

其中 `ax12_login_root_shadow_patch.py` 是**未实机验收的 BusyBox 实验性分支**，**最终成功公钥版没有使用它**，因此没有把它当作成功方案工具放进本仓库。

### AX12 运行时（SSH 登录后确认）

```text
/etc/init.d/ax12-ssh
/etc/rc.d/S99zzzzzzzzssh
/etc/dropbear/authorized_keys
/root/.ssh/authorized_keys
/usr/sbin/dropbear
/usr/sbin/uhttpd
/www
/etc/shadow
/dev/net/tun
```

## 已确认使用的工具和命令

| 工具 | 阶段 | 结果 |
| --- | --- | --- |
| USB TTL / macOS `screen` | UART 115200、Bootloader monitor | 成功 |
| `lsof` / `screen -ls` | 排查串口被旧进程占用 | 成功 |
| `pyserial` + [`ax12_flash_dump.py`](../tools/ax12_flash_dump.py) | `FLR`/`DB` 备份完整 16 MiB Flash | 成功 |
| GPL 的 `utility.c` + Python | 发现 Realtek RootFS 长度字段、16-bit checksum | 成功 |
| `unsquashfs` / `mksquashfs` | 离线拆解/重封装 XZ SquashFS | 成功 |
| [`ax12_seal_realtek_rootfs.py`](../tools/ax12_seal_realtek_rootfs.py) | 构建可启动的 Realtek RootFS 封装 | 成功 |
| [`ax12-ssh`](../tools/ax12-ssh) | 自定义 LAN Dropbear、开机启动 | 成功 |
| `ax12_uart_send.py` + `receiver.bin` | V2 块 CRC32、RAM 传输 | 成功（末尾等待 D 超时后 R 返回） |
| `FLW` / `FLR` / `CMP` | 完整写入和 Flash 回读比较 | 成功 |
| `ssh-keygen` / `scp` / OpenSSH | RSA 公钥登录 root | 成功 |
| 改 `/etc/shadow` / `passwd root` | Linux/SSH 密码尝试 | **SSH 密码失败** |

## 关键踩坑

1. **串口被 `screen` 占用**：`Resource busy` 并不是 Bootloader 问题。先释放串口。
2. **`DB` 长度参数**：`DB <addr> 16` 表示十进制 16；不要混淆其他 monitor 命令使用的十六进制参数。
3. **普通 `mksquashfs` 不可直接启动**：Realtek Bootloader 要求 offset `0x08` 特殊字段与尾部 checksum。第一次镜像已写入但无法启动，后用双扇区修复解决。
4. **完整 payload CRC32 与 `D` 超时**：发送器在全部 ACK 后等 `D` 超时；仅在接收器确实等待 `R` 时，才发送 `R` 返回 `<RealTek>`。这次已实机成功两次。
5. **刷 Flash 必须包括末尾两字节 checksum**：本次封装大小 `0x9A5002`，实际 Flash 文件填充到 `0x9A6000`。若只写 `0x9A5000`，会漏掉校验字。
6. **错误的源目录**：从 `reports/rootfs-repack-source` 重建只得到 2495 inode，SSH 自启动缺失；必须从已加入 SSH 的 2497 inode 镜像重建，最终公钥版 2500 inode。
7. **密码登录失败，不等于 Dropbear 没启动**：自定义 SSH 在 2222 响应，RSA 公钥登录成功。初始 root 密码、`passwd root` 都未使 SSH 密码登录成功；原因尚未严格定位。
8. **SSH 旧主机密钥不匹配**：重刷 RootFS 之后曾见 `REMOTE HOST IDENTIFICATION HAS CHANGED`；验证当前设备身份后只移除对应 host:port 的旧 `known_hosts` 记录。
9. **不要把 RAMFS 当持久存储**：`/etc` 是 RAMFS，`/tmp`、`/overlay`、`/mnt` 是 tmpfs；持久化需修改 RootFS 或找到受控的设备持久区。
10. **不要上传私有固件/日志**：原厂备份含设备独有数据。公开仓库只留脱敏工程记录及代码。

## 成功版本的校验值

```text
Original 16 MiB SPI NOR:
  22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1

SSH-only SquashFS:
  603f2d4cc69b28f896f511c078893c9b2b26b2d6d3c1ee8adde372f29fcf2617

Checksum-fixed SSH-only RootFS:
  2f621f489d0d4c460917e56aed8b1512ac875d2a5a0ed1e253529e76832a6dbc

Final SSH-public-key RootFS with Realtek checksum (10113026 B):
  28b26cf55779d558a0a359625a79945d6d1c43b2869587f21b3da54cb2aaad58

Final 4 KiB padded UART/Flash image (10117120 B):
  c582f050d711f58911dd5c71388186d64cb522da1f54b4d6af3ffd01b008ddf5
```

所有固件 hash 仅用于**证明本次实验中的文件对应关系**，不是跨所有 AX12 RU v1 的通用官方哈希。
