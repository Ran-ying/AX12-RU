# TP-Link Archer AX12 (RU v1) UART → Root SSH 逆向记录

> 本仓库记录**已实际完成**的 AX12-RU 固件研究过程：UART 接入、16 MiB SPI-NOR 备份、RootFS 分析与重构、Realtek 校验修复、UART V2 RAM 传输、Flash 回读验证，直至 **SSH RSA 公钥登录获得 root Shell**。
>
> 最终成功验证：`uid=0(root)`、Linux 4.4.176 / MIPS 24Kc、原厂 `uhttpd` Web 后台可用、自定义 Dropbear 在 LAN `192.168.0.1:2222` 上工作。**Linux 密码 SSH 登录未修复；实际成功方式是公钥认证。**

## 文档导航

1. [硬件、UART、Bootloader 与 16 MiB 备份](docs/01-uart-and-backup.md)
2. [固件拆解、SSH 启动脚本与 RootFS 构建](docs/02-rootfs-and-ssh.md)
3. [Realtek 校验格式与两扇区启动修复](docs/03-realtek-checksum.md)
4. [UART V2 RAM 传输、Flash 写入与回读](docs/04-uart-v2-flashing.md)
5. [SSH 密钥登录与最终验收](docs/05-ssh-key-auth.md)
6. [踩坑记录、工具清单和路径索引](docs/06-lessons-and-paths.md)

## 已归档的实际工具

| 仓库路径 | 用途 | 状态 |
| --- | --- | --- |
| [`tools/ax12_flash_dump.py`](tools/ax12_flash_dump.py) | 通过 `FLR` + `DB` 从 UART 读取整片 16 MiB SPI NOR；无 Flash 写操作 | 使用过的源代码 |
| [`tools/ax12_seal_realtek_rootfs.py`](tools/ax12_seal_realtek_rootfs.py) | 离线添加 AX12 RootFS 厂商长度字段及 16 位校验字 | 实际完成过封装并成功启动 |
| [`tools/ax12-ssh`](tools/ax12-ssh) | 已在 RootFS 内使用的自定义 Dropbear 开机脚本 | 实机成功运行 |

UART V2 发送脚本、MIPS 接收器源码和接收器二进制，**已确认保存在本次实验所用 Mac mini 的桌面**（见[真实路径索引](docs/06-lessons-and-paths.md)），但其完整源码/二进制没有作为可读原件提供到本次仓库归档环境，因此**暂不伪造或替换上传**。后续可从 Mac mini 将原文件单独提交。

## 设备与范围

- **设备**：TP-Link Archer AX12，RU v1（**不保证适用其他区域/硬件版本**）
- **SoC / CPU**：Realtek RTL8197F，MIPS 24Kc（32-bit little-endian, MIPS32r2）
- **内存**：`/proc/meminfo` 总计 116,864 KiB（约 114 MiB）
- **Flash**：Winbond W25Q128，16 MiB SPI NOR
- **固件**：Linux 4.4.176、SquashFS v4 XZ、uClibc 0.9.33、Dropbear 2019.78、uhttpd
- **调试连接**：macOS USB-UART，115200 8N1，`<RealTek>` monitor

## 不上传的内容

**本仓库是公开仓库。** 不提交整片 SPI Flash、含 Wi-Fi/账户设置的配置分区、私钥、`/etc/shadow`、授权密钥原文、设备 host key、完整串口日志或厂商固件二进制。文中仅记录文件名、SHA256、非敏感偏移和命令。

## 状态与提醒

- 最终成功的是 **SSH 私钥认证**，不是自定义密码+私钥双认证。
- `/etc` 挂载为 RAMFS；`passwd root` 虽可以更新当前文件，重启不一定保留，且该固件密码 SSH 登录实测失败。
- `/dev/net/tun` 节点、Web `/www`、`opkg` 存在，但 Tailscale 安装和 Web 后台改造**尚未在本项目中完成**。
- 刷写修改版固件有变砖风险。先留好完整原厂备份、恢复串口和回读校验流程；涉及 `FLW` 的命令**仅为成功实验记录，不应脱离上下文直接执行**。

记录日期：2026-10-31 至 2026-11-02。
