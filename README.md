# TP-Link Archer AX12 RU v1：UART → 持久 Root SSH

**本仓库只保留最终验证成功的路线。** 从 UART 接入、备份 16 MiB SPI Flash、离线构建携带 RSA 公钥的 RootFS、修正 Realtek 校验、UART V2 传输与回读，到在 Mac mini 上以私钥取得 `uid=0(root)`。不使用实验中失败的 TFTP、XMODEM、BusyBox 登录补丁或密码猜测路线。

最终实机：RTL8197F / MIPS32 little-endian、Linux 4.4.176、SquashFS v4 XZ、Dropbear 2019.78，TP-Link 原厂 Web 后台正常，自定义 Dropbear 在 `192.168.0.1:2222` 提供 **公钥登录**。密码登录**没有验证成功**。

> 设备仅为本次 **Archer AX12 RU v1**；其他硬件/地区版本的地址、分区、密钥和 Bootloader 校验方式可能不同。下面 `FLW` 会擦写 Flash，务必在备份和逐字节校验完成后使用。

## 仓库文件：仅成功方案

| 文件 | 用途 |
|---|---|
| [`tools/ax12_flash_dump.py`](tools/ax12_flash_dump.py) | UART Bootloader `FLR` + `DB` 备份整片 16 MiB Flash（只读） |
| [`tools/ax12-ssh`](tools/ax12-ssh) | 已验证的 LAN Dropbear 启动脚本 |
| [`tools/ax12_seal_realtek_rootfs.py`](tools/ax12_seal_realtek_rootfs.py) | RootFS 加厂商长度字段与 checksum |
| [`tools/ax12_uart_send.py`](tools/ax12_uart_send.py) | UART V2 发送器（只写 RAM） |
| [`tools/receiver.S`](tools/receiver.S) | MIPS RAM 接收器源码 |
| [`tools/link.ld`](tools/link.ld) | 接收器链接地址 `0xA0800000` |
| [`tools/build.sh`](tools/build.sh) | 编译接收器 |
| [`tools/receiver.bin`](tools/receiver.bin) | **实机使用的 992 字节接收器** |
| [`tools/zh-cn/README.md`](tools/zh-cn/README.md) | 简体中文语言包生成、轻量 RAM 挂载、回滚（实机验证） |
| [`tools/firmware/README.md`](tools/firmware/README.md) | 官方 1.1.22 与 1.5.0 Cloud 固件结构比较、非刷机持久化研究 |
| [`tools/firmware/inspect_cloud.py`](tools/firmware/inspect_cloud.py) | Cloud 固件只读头部、manifest、分区表检查工具 |

这三个文件已在当前构建环境实际重建并确认**逐字节一致**：`receiver.S` + `link.ld` + `build.sh` → `receiver.bin`。

```bash
# 安装有 clang、ld.lld、llvm-objcopy 的 LLVM 工具链后执行：
sh tools/build.sh
sha256sum tools/receiver.bin
# 7d10d6e6a149eb6ae41ced851db26f0f26da85de3f0b6944438f7a7ab814903f
```

## 1 · UART 连接与 Bootloader

**Mac mini** 使用 3.3 V TTL 的 USB-UART、TX/RX 交叉、共地、115200 8N1。串口的本次真实路径：

```text
/dev/cu.usbserial-2120
```

焊盘排列需要按具体主板实际确认，本项目未保存可复核的主板引脚坐标，故不臆造排列。上电时按 **Esc** 进入 `<RealTek>`。

```bash
ls /dev/cu.usbserial*
lsof -nP /dev/cu.usbserial-2120
screen /dev/cu.usbserial-2120 115200
```

如果出现 `Resource busy`，运行 `screen -ls`，先恢复或退出旧 `screen`（`Ctrl+A`、`K`、`Y`）。执行 Python 串口程序前必须释放该设备。

## 2 · 备份原厂整片 SPI Flash

Bootloader 停在 `<RealTek>`，退出 `screen` 后，在 Mac mini：

```bash
git clone https://github.com/Ran-ying/AX12-RU.git ~/AX12-RU
python3 -m pip install pyserial

python3 ~/AX12-RU/tools/ax12_flash_dump.py \
  --port /dev/cu.usbserial-2120 \
  --output ~/Desktop/ax12-flash-16MiB.bin

shasum -a 256 ~/Desktop/ax12-flash-16MiB.bin
```

本机完整备份为 `16777216` 字节，SHA256：

```text
22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1
```

备份含设备唯一校准数据与个人配置，**不要上传到公开 GitHub**。

本次实际分区边界：

| 分区 | 起始 | 结束（不含） |
|---|---|---|
| Bootloader | `0x000000` | `0x040000` |
| 内核 | `0x040000` | `0x440000` |
| RootFS | **`0x440000`** | **`0xF08000`** |
| 工厂数据/配置 | `0xF08000` | `0x1000000` |

**绝不覆盖 `0xF08000` 之后的工厂区。**

## 3 · VPS 上从原厂备份制作带公钥的 RootFS

本次 VPS 为 `root@linveo`，工作目录是 **`/root/AX12-research`**。把已备份的文件私下复制过去：

```bash
# Mac mini
ssh root@linveo 'mkdir -p ~/AX12-research/source'
scp ~/Desktop/ax12-flash-16MiB.bin root@linveo:~/AX12-research/source/
```

VPS 上安装 `squashfs-tools`、Python 3，克隆仓库并提取原厂 `file-system` 分区：

```bash
git clone https://github.com/Ran-ying/AX12-RU.git ~/AX12-RU
cd ~/AX12-research
mkdir -p reports

# 0x440000/4096=1088; 0xAC8000/4096=2760
dd if=source/ax12-flash-16MiB.bin of=reports/original-file-system.bin \
  bs=4096 skip=1088 count=2760 status=progress

unsquashfs -d reports/rootfs-pubkey-source reports/original-file-system.bin
```

使用 MacBook 上的**公钥**（无需上传私钥）：

```bash
# MacBook，仅首次生成
ssh-keygen -t rsa -b 3072 -f ~/.ssh/ax12_root -C ax12-root
scp ~/.ssh/ax12_root.pub root@linveo:~/AX12-research/reports/ax12_root.pub
```

在 VPS，把已经实际运行成功的 SSH 启动脚本和公钥装进解包目录：

```bash
cd ~/AX12-research
SRC=reports/rootfs-pubkey-source
PUB=reports/ax12_root.pub

# 固件中 /etc/init.d 实际是指向 /etc_ro/init.d 的符号链接
install -m 755 ~/AX12-RU/tools/ax12-ssh "$SRC/etc_ro/init.d/ax12-ssh"
ln -s ../init.d/ax12-ssh "$SRC/etc/rc.d/S99zzzzzzzzssh"

install -d -m 700 "$SRC/root/.ssh"
install -m 600 "$PUB" "$SRC/root/.ssh/authorized_keys"
install -m 600 "$PUB" "$SRC/etc/dropbear/authorized_keys"

test -x "$SRC/etc_ro/init.d/ax12-ssh"
test -L "$SRC/etc/rc.d/S99zzzzzzzzssh"
cmp "$PUB" "$SRC/root/.ssh/authorized_keys"
cmp "$PUB" "$SRC/etc/dropbear/authorized_keys"
```

原厂基础镜像约 2495 inode；加 SSH 服务、启动链接及两份公钥后，**本次成功版为 2500 inode**。不修改 `/bin/busybox`，也不依赖密码认证。

```bash
mksquashfs "$SRC" reports/rootfs-pubkey.sqfs \
  -noappend -comp xz -b 262144 \
  -always-use-fragments -exports -all-root

unsquashfs -s reports/rootfs-pubkey.sqfs
```

### Realtek 特殊长度字段和校验

该 Bootloader 不接受普通、未封装的 SquashFS：需要把 RootFS 头部 offset `0x08` 写成厂商长度字段，并在尾部追加 16-bit checksum，使大端 16 位字和为零。**必须在刷写前封装**。

```bash
python3 ~/AX12-RU/tools/ax12_seal_realtek_rootfs.py \
  reports/rootfs-pubkey.sqfs \
  reports/rootfs-pubkey-realtek.bin
```

以 `0xFF` 填充到 4 KiB 对齐后供 UART 发送，检查不会超出 RootFS 分区：

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
src = Path('reports/rootfs-pubkey-realtek.bin')
dst = Path('reports/rootfs-pubkey-flash.bin')
b = src.read_bytes()
size = (len(b)+4095)//4096*4096
assert size <= 0xAC8000
assert sum(int.from_bytes(b[i:i+2],'big') for i in range(0,len(b),2)) & 65535 == 0
dst.write_bytes(b.ljust(size,b'\xff'))
print('Flash length hex:',hex(size),'bytes:',size)
print('SHA256:',hashlib.sha256(dst.read_bytes()).hexdigest())
PY
```

**参考成功产物（2026-11-02）**：同样的公钥版固件，当次封装后为 `0x9A5002` 字节，对齐后 `0x9A6000`（10,117,120 字节），SHA256：
`c582f050d711f58911dd5c71388186d64cb522da1f54b4d6af3ffd01b008ddf5`。

新编译的 SquashFS 时间戳与文件布局可能变化，**不要求哈希相同；Flash 写入长度应使用新文件实际打印的十六进制对齐长度。**

## 4 · 传到 Mac mini，再通过 UART V2 传入 RAM

```bash
# VPS
scp ~/AX12-research/reports/rootfs-pubkey-flash.bin \
  ranying@10.7.0.4:~/Desktop/
```

Mac mini：

```bash
shasum -a 256 ~/Desktop/rootfs-pubkey-flash.bin
# 与 VPS 上输出的 SHA256 完全比较；退出 screen，确保停在 <RealTek>。

cd ~/AX12-RU
python3 tools/ax12_uart_send.py \
  --port /dev/cu.usbserial-2120 \
  --receiver tools/receiver.bin \
  --image ~/Desktop/rootfs-pubkey-flash.bin \
  --allow-large
```

UART V2：`EB` 加载接收器到 `0xA0800000`，`DB` 逐字节验证，`J` 运行；payload 到 `0xA4000000`，每块 256 B 且带 CRC32，接收端还会**重新扫描 RAM 做完整 CRC32**。整个 UART 工具**不写 Flash**。

本次真实传输中出现 `ack(port,b'D')` 等待超时，但所有块已被逐块确认，且 receiver 最终返回 `r<RealTek>`，因此没有重传。**只有完全发送到末尾、确认接收器已通过最终 CRC 并进入等待 R 状态时**，才可用独立的串口调用发送 `R` 恢复 Bootloader；若中途出错，必须从头诊断，不得假装成功：

```python
import serial
with serial.Serial('/dev/cu.usbserial-2120',115200,timeout=5,write_timeout=2) as p:
    print('Pending:',repr(p.read(p.in_waiting)))
    p.write(b'R')
    p.flush()
    print('Reply:',repr(p.read_until(b'<RealTek>')))
# 本次成功回复包含 b'r<RealTek>'
```

完整 CRC32 与 Bootloader 返回确认后，重新用 `screen` 核对 RAM 开头/尾部，且和 Mac 本地 `xxd` 对比：

```text
DB A4000000 16
```

> 这里需要的是 **RAM 接收内容正确**，不是仅看到发送脚本运行结束。最终文件尾部/写入边界须与本地镜像一致。

## 5 · 写 Flash、全量回读，再启动

**以下命令有擦写风险，只是本次成功写入文件长度为 `0x9A6000` 时使用的准确命令。若新产物长度不同，全部长度参数必须一起相应调整，且不得超出 `file-system` 分区。**

```text
FLW 440000 A4000000 9A6000 0
FLR A5000000 440000 9A6000
CMP A5000000 A4000000 9A6000
```

`FLW` / `FLR` 有确认提示；严格核对地址再按 `Y`。只有 `CMP` 返回 `No error found`，才重启 AX12。不要触碰内核或 Bootloader 分区。

## 6 · Mac mini 使用私钥进入 Root Shell

本次 MacBook 生成密钥，实际接路由器的 Mac mini IP 是 `10.7.0.4`。只在两台可信 Mac 之间通过 SSH 加密传输**私钥**：

```bash
# MacBook
ssh ranying@10.7.0.4 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'
scp ~/.ssh/ax12_root ranying@10.7.0.4:~/.ssh/ax12_root
ssh ranying@10.7.0.4 'chmod 600 ~/.ssh/ax12_root'
```

重启 AX12 并确认 `192.168.0.1:2222` 属于自己的路由器。若 OpenSSH 提示主机密钥变化，应先核实确实是此设备的新主机密钥，再移除**这一条**旧记录：

```bash
ssh-keygen -R '[192.168.0.1]:2222'
```

Mac mini 最终实际成功登录命令：

```bash
ssh -i ~/.ssh/ax12_root \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  -p 2222 root@192.168.0.1
```

实机验收：

```text
root@Akronite:~# id
uid=0(root) gid=0(root) groups=0(root)
root@Akronite:~# uname -a
Linux Akronite 4.4.176 #1 Mon Mar 11 19:51:57 CST 2024 mips GNU/Linux
```

可在 Mac mini 的 `~/.ssh/config` 设置专用 `Host ax12` 并将上面的 RSA 兼容参数只限定到这一台路由器，以后执行 `ssh ax12`。

## 7 · Web 后台简体中文（已实机验证）

2026-11-02，保留 AX12 原厂 Web 后台，在登录页面成功增加 **简体中文** 选项并完成选择验证。采用 `zh_TW` 资源的繁简转换和常用术语替换，不提交原厂网页与翻译内容。语言注册不依赖目录扫描：必须同时在 `/etc/config/locale` 新增 `config langinfo 'ZH_CN'` / `option value 'zh_CN'`。

该设备 `/www` 是只读 SquashFS，`/etc` 是 RAMFS。初次直接复制整个 `locale` 目录的 bind mount 方案导致管理页面 `Operation failed`，已撤回。成功版本将原始 `locale` bind 到只读引用路径，用符号链接构成视图，只新增 `zh_CN` 并 mount 到 `/www/webpages/locale`，减少约 6 MiB 的额外 RAM 占用；俄语和英语资源正常。

在 Mac mini 上复现的构建与部署步骤，以及临时挂载回滚方式详见 **[tools/zh-cn/README.md](tools/zh-cn/README.md)**。其中生成脚本在 Mac mini 测试后输出 `lan.js` 的 SHA256 与实际成功版本一致：`064d7d923a88deb91c34d473968d3b8b7d71787d1a80630c698b333ee2758f2f`。

此补丁仍属于 **RAM 临时改造**，未集成进永久 RootFS，重启后将失效；前端文字还需要人工术语校对。

## 8 · 从原始 16 MiB Flash 解密官方 RU 1.5.0（已验证）

2026-11-02，已从原始 Flash 备份的旧版 `nvrammanager` 提取 RSA-2048 **公钥**，配合 [robbins/tp-link-decrypt](https://github.com/robbins/tp-link-decrypt) 在 VPS 离线完成 RU 1.5.0 官方固件验证和解密；成功恢复 `fwup-ptn` 明文分区清单，提取新版 SquashFS 文件系统（2533 inode）。新版系统改用新的前端打包架构，并附带简体中文 JS 模块。

**重要：新版物理 Flash 分区位置发生变化**，RootFS 从旧版 `0x440000` 改为新版 `0x400000`。不可沿用旧版直接写入地址。目前已经通过离线实验生成自签名 Cloud 测试包，并重新封装了加入自有公钥验证库的 1.5.0 RootFS；独立解密工具验证成功。**这不等于原厂升级程序已接受该包，更不意味着可以安全刷写。** 本次全程未写路由器 Flash，未升级或重启。

完整验证证据、只读工具与注意事项见 [tools/firmware/README.md](tools/firmware/README.md)。

## 安全与保存原则

- 不提交原厂 16 MiB Flash 备份、完整可刷写固件、设备校准数据、SSH 私钥、authorized_keys、公钥身份信息、设备 host key、`/etc/shadow`、个人配置或原始串口日志。
- 目前密码 SSH 登录实测**失败**；公钥登录成功不等于密码登录成功。未来有需要才单独研究密码认证。
- 该设备的 `/etc` 是 RAMFS，普通运行时改动重启会消失；本次 SSH 脚本及公钥已固化进 RootFS。
- 简体中文 Web 语言选项已经在 RAM 中验证；**永久固件集成**、其他隐藏功能的启用，以及 Tailscale 安装仍未经验证。

记录范围：2026-10-31 至 2026-11-02。
