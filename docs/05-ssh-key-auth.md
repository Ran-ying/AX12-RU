# 05 · 用 Mac mini 私钥登录 AX12 Root Shell（最终成功）

[返回首页](../README.md) · [上一步](04-uart-v2-flashing.md)

## 最终验证结果

2026-11-02，在已刷入公钥版 RootFS 的 AX12 RU v1 上，Mac mini 通过 RSA 私钥成功登录到：

```text
BusyBox v1.19.4 (2024-03-11 20:11:46 CST) built-in shell (ash)
root@Akronite:~# id
uid=0(root) gid=0(root) groups=0(root)

root@Akronite:~# uname -a
Linux Akronite 4.4.176 #1 Mon Mar 11 19:51:57 CST 2024 mips GNU/Linux
```

当时进程中同时存在原厂 Dropbear 和自定义 Dropbear：

```text
/usr/sbin/dropbear -P /var/run/dropbear.1.pid -p 20001 -C -6 -B
/usr/sbin/dropbear -L -6 -P /var/run/ax12-ssh.pid -r /etc/dropbear/dropbear_rsa_host_key -p 192.168.0.1:2222
```

- `-C` 是这个 TP-Link 定制 Dropbear 的 **Web Server account login**。
- 自定义实例 **不带 `-C`**，而且 `-L` 允许 SSH 会话登录。
- 成功的是 **publickey** 身份认证，不是 Linux root 密码认证。

## Mac mini 的实际登录命令

最终私钥在 Mac mini：

```text
/Users/ranying/.ssh/ax12_root
```

AX12 的 LAN IP 本次为 `192.168.0.1`，Dropbear 监听端口 `2222`：

```bash
ssh -i ~/.ssh/ax12_root \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  -p 2222 root@192.168.0.1
```

该固件 Dropbear v2019.78 只提供旧式 `ssh-rsa` 主机密钥签名，现代 macOS OpenSSH 默认不接受，因此需要显式的兼容参数。**只对本主机设置，不要全局降低所有 SSH 主机的算法要求。**

推荐写入 Mac mini 的 `~/.ssh/config`：

```sshconfig
Host ax12
    HostName 192.168.0.1
    Port 2222
    User root
    IdentityFile ~/.ssh/ax12_root
    IdentitiesOnly yes
    PreferredAuthentications publickey
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
```

之后只要 `ssh ax12`。

## 重刷 RootFS 后主机密钥变化

此次重刷后 OpenSSH 曾提示：

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

可能是 Dropbear 主机密钥重新生成。**先通过受信任的 UART/设备侧方式验证确实连接自己路由器、核验新指纹**，然后才清理这一个地址端口对应的旧记录：

```bash
ssh-keygen -R '[192.168.0.1]:2222' -f ~/.ssh/known_hosts
```

再次连接时确认新的指纹后输入 `yes`。不要简单地使用全局 `StrictHostKeyChecking=no` 跳过安全验证。

## root 密码失败：如实记录

实际情况：

1. 原始修改版 `/etc/shadow` 内的 MD5-crypt 哈希与事先设定的测试密码相匹配。
2. 但是 UART `login` 和 SSH 密码登录均拒绝该密码。
3. 公钥登录获得 root 后，运行 `passwd root` 两次，系统报告 `Password for root changed by root`。
4. `/etc/shadow` 文件变化，但 SSH 密码登录仍失败。
5. `mount` 显示 `none on /etc type ramfs (rw,noatime)`，`/` 是只读 SquashFS；因此运行时密码改动也不保证重启持久化。

`/usr/sbin/dropbear -h` 显示：

```text
-s  Disable password logins
-g  Disable password logins for root
-L  Enable SSH session login
-C  Use Web Server account login
```

运行的自定义 Dropbear 参数不带 `-s`、`-g`、`-C`，仍不能证明其密码认证使用了哪条内部逻辑。**本次没有确定密码失败的最终根因，也没有实现密码+密钥双登录。** 在没有证据时不把猜测写成结论。

## 成功后在 AX12 上的环境检查

```sh
id
uname -a
ps | grep '[d]ropbear'
cat /proc/cpuinfo
ls -l /lib/ld-* /lib/libc.so*
which opkg
mount | grep -E ' / | /etc '
ps | grep uhttpd
```

已验证：

- RTL8197F / MIPS 24Kc、uClibc 0.9.33。
- `/etc` 为 RAMFS，`/tmp`、`/overlay`、`/mnt` 亦是内存型存储。
- `/dev/net/tun` 设备节点存在；**未实际完成 Tailscale 安装**。
- `uhttpd` 使用 `/www`，默认网页位于原厂只读文件系统；**未完成后台 Web 改造**。

**验收结论：自定义 LAN Dropbear + 预置 RSA 公钥已获得 root Shell，原厂管理后台仍能正常访问。**

最后：[06 · 踩坑、工具清单及准确路径](06-lessons-and-paths.md)。
