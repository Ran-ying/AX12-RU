# M6 — AX12 RU 首次 owner-signed cs6c 实机刷写与启动检查（2026-11-03）

## 执行授权与镜像

用户明确授权首次刷写，并确认 UART 恢复通道可用、此前完整 Flash 备份已经完成。本轮远程执行链路仅为连接到用户的 Mac mini，再由其通过既有 `ssh ax12` 连接本人 AX12。

固件文件在 Mac 与设备 RAM 中的 SHA-256 均为：

`ddf9880b29715a9189666a5256d86b3f2d8daec342219704a01edce0f696bf7c`（15,370,972 字节）

临时 owner 公钥版旧固件升级器 SHA-256：

`fa0b6a9388e952f07fe1f8193409d29b6bb2ab2c49dd9414b9db14c56c8776b2`（114,056 字节）

旧版 1.1.22 实机 `-c` 此前已通过，退出码 0。升级前再次检查两份文件 SHA-256，并由路由器 `start-stop-daemon` 在 `/tmp` 独立执行：

`/tmp/nvrammanager-owner-check -u /tmp/ax12-cs6c.bin`

独立后台执行是为了让 SSH 会话中断不必然中止正在执行的 Flash 写入。执行前不存在其他同名后台刷写任务。**本轮只做一次真实升级；没有升级 bootloader 的清单条目**。

## 真实写入结论：成功

AX12 原始实机日志在用户 Mac mini 保存为：

`~/Desktop/AX12-RU-1.5.0-owner/ax12-first-flash-20261103.log`

关键输出：

```text
Reading Partition Table from NVRAM ... OK
Parsing Partition Table ... OK
md5 verify ok!
Firmwave supports, check OK.
(curFw_ver, newFw_ver) == (1.1, 1.5)
check firmware ok!
set integer flag to 0.
...
/bin/sh: reboot: not found
Done.
set integer flag to 1.
upgradeFirmware success...
UPGRADE_EXIT_CODE=0
```

用户授权的**实际 Flash 写入阶段完成，厂商升级器退出码 0**。但其自动重启命令因原系统挂载地址已经被新 RootFS 覆盖而无法找到（无法从日志单独确认确切原因）；故需要单独重启。

记录了前次写入成功日志后，通过原系统现有的绝对路径 `/sbin/reboot` 正常发起了一次重启（命令返回码 0），没有使用强制复位或 sysrq。UART 采集从重启前启动，日志保存于 Mac mini 私有工作目录：

`~/Desktop/AX12-RU-1.5.0-owner/ax12-first-boot-20261103.uart.log`

**切勿提交这些完整 UART 日志到公开 GitHub**：它们可能包含设备配置、无线网卡地址或其他设备私有信息。

## 新版内核与 RootFS 已实机引导成功

UART 确认使用了现有的 RTL8197F 原版 Bootloader，SPI NOR 仍被识别为 16 MiB 的 Winbond `w25q128`。新内核成功启动：

```text
Linux version 4.4.176-gd3618c8d0-dirty
0x000000400000-0x000000f00000 : "rootfs"
VFS: Mounted root (squashfs filesystem) readonly on device 31:2.
Freeing unused kernel memory: 180K
```

内核是 2026-06-05 官方衍生版本，RootFS MTD 基址为 `0x400000`，与计划一致。启动随后进入网络、Wi-Fi、LAN bridge 与 EasyMesh 配置，串口日志中出现 `saveconfig() end`、`eth0: link is up`、`br-lan` forwarding。**Bootloader → 新 cs6c 内核 → 新 RootFS 的首次实机启动已通过**，否定了此前最关键的启动链兼容性担忧。

## 尚未完成：SSH 与管理接口

无法确认新版的 SSH 管理入口已经恢复。此前 `ssh ax12` 指向 `192.168.0.1:2222`；升级后 Mac mini 测试得到 SSH 交换 banner 前连接关闭，但此测试存在关键路由干扰：Mac mini `route -n get 192.168.0.1` 显示默认走 `utun1500`（VPN TUN），而其有线 `en0` 持有酒店侧旧 DHCP 地址 `192.168.156.63/20`，没有直接 `192.168.0.0/24` 路由。因此不能根据这次代理 TCP 响应断言 AX12 Dropbear 失败。

新 RootFS 内确有 `/etc/rc.d/S99zzzzzzzzssh` 自启动链接，实际脚本使用 `/usr/sbin/ip -4 -o addr show dev br-lan`、RSA host key、`/usr/sbin/dropbear -p "$lan_ip:2222"`，但首次启动时 LAN 地址、Dropbear host key 与脚本是否成功均须继续验证。新固件的默认官方 Dropbear 配置还声明 port 22，而自定义实例位于 2222。

由于 Mac 现有 VPN 路由对 `192.168.0.1` 的覆盖，应优先从 Mac mini Ethernet `en0` 建立**临时直接路由/IPv4 alias**，随后测试 `192.168.0.1:2222` 与 22；这需要用户 sudo 授权，不能在当前无密码远程会话中擅自进行。另一个办法是通过已连接的 UART 串口在登录后读取 `ip addr` 和 `ps | grep dropbear`。

用户 Mac mini 的 UART screen 会话 `59431` 正在被占用，后续命令应避免抢占串口。

## 当前结论

**实机刷写完成、厂商升级器返回 0、旧 Bootloader 成功加载新内核、新内核成功挂载新 RootFS。** 管理入口的可达性与定制 SSH 功能尚未验收。下一步是**恢复局域网直连与 SSH**，不是重新刷写，也不是重复备份。无额外 Flash 擦写或二次重启。


## M6 后续：用户实机确认 SSH root 登录成功

切换到实际可达的 LAN 端口后，Mac mini 对 `192.168.0.1` 的 ARP 恢复至 `5c:62:8b:f3:83:c0`，ICMP 2/2 成功；原先的 LAN 不通主要由端口映射或接线口选择导致。

`ssh ax12` 原默认私钥指纹 `SHA256:rXNBCRUiTLSt2Q0d1BUmSjvafQ7sAgVYJIsZnQUPWtQ` 被定制 Dropbear 拒绝。已封装 RootFS 内的 `authorized_keys` 公钥指纹为 `SHA256:uk37qU02Omc8kre/ChPBGvKE+/ZH6CxuotWl0VursFQ`，为 owner 固件签名公钥。用户明确决定两项用途共用签名私钥 `~/.ssh/ax12_owner_2026`。

新版 Dropbear 仅提供 `ssh-rsa` 主机密钥协商（OpenSSH 默认禁用）；在为 AX12 单主机显式允许 `HostKeyAlgorithms=+ssh-rsa` 与 `PubkeyAcceptedAlgorithms=+ssh-rsa`，并指定签名私钥后，**用户确认已成功以 root 登录真实 AX12**。故实机定制 SSH 功能已通过。

**仍待验收：** Web UI 在浏览器内无限刷新。HTTP `GET /` 返回 200 OK，非 HTTP 3xx 重定向；应优先排查浏览器 JS、会话 cookie、后台 API 以及新旧持久化配置兼容。无需再刷写。
