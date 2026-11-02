# 02 · 拆解 RootFS，加入自定义 SSH 和公钥

[返回首页](../README.md) · [上一步](01-uart-and-backup.md)

## 设备软件环境（实机验证）

- Linux `Akronite 4.4.176`；MIPS 24Kc V8.5、MIPS32r2、little-endian。
- 用户态 uClibc 0.9.33、BusyBox v1.19.4、Dropbear v2019.78、`uhttpd`。
- `/dev/mtdblock2` 挂载 `/`，SquashFS **只读**；`/etc` 是 RAMFS。
- Web 进程：`/usr/sbin/uhttpd -f -h /www ... -p 0.0.0.0:80`，原厂管理功能保留。

## 本次 VPS 文件路径

VPS 工作目录 **`~/AX12-research`**；以下命令都从该目录运行。

- 原厂 Flash 备份在 VPS：`source/ax12-flash-16MiB.bin`（不要上传到公开仓库）。
- 已加入 SSH 的基础 SquashFS：`reports/rootfs-ssh-password.sqfs`。
- 最终公钥版解包目录：`reports/rootfs-ssh-pubkey-source`。
- 最终公钥版压缩文件：`reports/rootfs-ssh-pubkey.sqfs`。
- Realtek 封装：`reports/rootfs-ssh-pubkey-realtek.bin`。
- 写 Flash 前补齐到 4 KiB 的文件：`reports/rootfs-ssh-pubkey-flash.bin`。

基础 SSH 镜像（不是最终公钥版）SHA256：

```text
603f2d4cc69b28f896f511c078893c9b2b26b2d6d3c1ee8adde372f29fcf2617
```

## SSH 启动脚本

归档源码：[`../tools/ax12-ssh`](../tools/ax12-ssh)。在运行中的 AX12，文件安装位置**确实是**：

```text
/etc/init.d/ax12-ssh
/etc/rc.d/S99zzzzzzzzssh -> ../init.d/ax12-ssh
```

脚本在 `br-lan` 检测 LAN IP，通过 iptables 阻止非 `br-lan` 进入 2222，然后启动独立 Dropbear 实例：

```sh
/usr/sbin/dropbear -L -6 \
  -P /var/run/ax12-ssh.pid \
  -r /etc/dropbear/dropbear_rsa_host_key \
  -p "${lan_ip}:2222"
```

实机进程已经验证，例如：

```text
/usr/sbin/dropbear -L -6 -P /var/run/ax12-ssh.pid -r /etc/dropbear/dropbear_rsa_host_key -p 192.168.0.1:2222
```

原厂 Dropbear 仍保留在端口 20001，未被覆盖。自定义启动脚本通过 RootFS 固化，避免依赖只读根文件系统的运行时修改。

## 最终采用 SSH 公钥而非密码

本次先尝试直接写入 root 的 MD5-crypt `/etc/shadow` 密码哈希，但 **SSH 和 UART 密码认证均失败**；获得 root 后 `passwd root` 修改 RAMFS 中的 `/etc/shadow` 也未使 SSH 密码登录成功。因此实际完成的是 **RSA 公钥登录**，并未实现双因素/双认证方式。

MacBook 生成专用 RSA 密钥（私钥仍在本地）：

```bash
ssh-keygen -t rsa -b 3072 -f ~/.ssh/ax12_root -C "ax12-root"
```

MacBook 上传**公钥**到 VPS（`root@linveo` 为此次实际 VPS 主机别名）：

```bash
scp ~/.ssh/ax12_root.pub root@linveo:~/AX12-research/reports/
```

MacBook 将私钥安全地复制到本次 LAN 直连 AX12 的 Mac mini（实验中 IP 为 `10.7.0.4`）：

```bash
ssh ranying@10.7.0.4 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'
scp ~/.ssh/ax12_root ranying@10.7.0.4:~/.ssh/ax12_root
ssh ranying@10.7.0.4 'chmod 600 ~/.ssh/ax12_root'
```

不要将私钥、完整 `authorized_keys` 或设备账户文件提交至公开仓库。

## 在 VPS 上制作公钥版 RootFS（已成功的具体来源）

**从已验证能启动 SSH 的 `reports/rootfs-ssh-password.sqfs` 解包，不能从旧的 `reports/rootfs-repack-source` 直接重建。** 曾经错误地使用后者，导致新镜像只有 2495 inode，丢失了 SSH 改动。

```bash
cd ~/AX12-research
unsquashfs -d reports/rootfs-ssh-pubkey-source reports/rootfs-ssh-password.sqfs

SRC=reports/rootfs-ssh-pubkey-source
PUB=reports/ax12_root.pub

install -d -m 700 "$SRC/root/.ssh"
install -m 600 "$PUB" "$SRC/root/.ssh/authorized_keys"
install -m 600 "$PUB" "$SRC/etc/dropbear/authorized_keys"

test -x "$SRC/etc/init.d/ax12-ssh"
test -L "$SRC/etc/rc.d/S99zzzzzzzzssh"
cmp "$PUB" "$SRC/root/.ssh/authorized_keys"
cmp "$PUB" "$SRC/etc/dropbear/authorized_keys"

mksquashfs "$SRC" reports/rootfs-ssh-pubkey.sqfs \
  -noappend -comp xz -b 262144 \
  -always-use-fragments -exports -all-root
unsquashfs -s reports/rootfs-ssh-pubkey.sqfs
```

本次实际产出：**2500 inode，1903 files，302 symlinks，295 directories**；SquashFS `bytes_used=10111276`。公钥同时放入 `/root/.ssh/authorized_keys` 和 `/etc/dropbear/authorized_keys`，实机 RSA 公钥认证成功。

## Realtek 封装和 4 KiB 填充

已上传脚本：[`../tools/ax12_seal_realtek_rootfs.py`](../tools/ax12_seal_realtek_rootfs.py)。

```bash
python3 ~/AX12-RU/tools/ax12_seal_realtek_rootfs.py \
  reports/rootfs-ssh-pubkey.sqfs \
  reports/rootfs-ssh-pubkey-realtek.bin
```

这里 `~/AX12-RU` 是在 VPS 克隆本仓库后的路径；如果没有克隆，可使用原有 Notebook 工具实际路径：
`~/Notebook/CS/AX12/ax12_seal_realtek_rootfs.py`。

本次输出长度 `10113026` 字节、SHA256：

```text
28b26cf55779d558a0a359625a79945d6d1c43b2869587f21b3da54cb2aaad58
```

完整校验字可能跨越最后一个 Flash 对齐边界，因此须再补齐至 `0x9A6000`（**10,117,120 字节**），不可只写 `0x9A5000`：

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('reports/rootfs-ssh-pubkey-realtek.bin')
b = p.read_bytes()
assert len(b) == 0x9A5002
assert (sum(int.from_bytes(b[i:i+2], 'big') for i in range(0,len(b),2)) & 0xffff) == 0
Path('reports/rootfs-ssh-pubkey-flash.bin').write_bytes(b.ljust(0x9A6000,b'\xff'))
PY
sha256sum reports/rootfs-ssh-pubkey-flash.bin
```

本次最终对齐文件 SHA256：

```text
c582f050d711f58911dd5c71388186d64cb522da1f54b4d6af3ffd01b008ddf5
```

下一步：[03 · RootFS 校验格式与失败修复](03-realtek-checksum.md)。
