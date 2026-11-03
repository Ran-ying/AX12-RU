# Archer AX12(RU) V1：从原厂 1.1.22 迁移到自定义固件

> **面向其他 AX12 RU V1 设备所有者的工程复现指南。** 这里只记录用户自己拥有并获授权修改的路由器。保留可复现的工具和已验收的历史操作，**不是**“任何旧版都能一键刷到 1.5.3”的承诺。此文档中的硬件 Flash 擦写与首次大版本升级均有变砖风险。

## 0. 范围、证据和关键结论

- 本项目的起点为 **官方 `1.1.22 Build 20240311`**（不是 `1.1.12`），AX12(RU) v1.0、Realtek RTL8197F、小端 MIPS、**16 MiB SPI NOR**、3.3 V TTL UART、115200 8N1。
- **已经实机验证的历史路径**：UART/Bootloader 备份原始 Flash → 在旧 RootFS 内加入 SSH 公钥和 LAN Dropbear 服务 → UART 只替换旧 RootFS → 登录原厂 1.1.22 的 root SSH → 把临时升级器的**RSA 验签公钥**替换为用户自己的公钥（在 RAM `/tmp` 中运行，不先永久修改旧验证器）→ 通过官方升级器的 `-c`、`-u` 写入特制自签名 1.5.0 → 使用原来的 Bootloader 引导新 Linux/RootFS → 逐步升级至已验收的定制 1.5.2。验证记录：[M11 离线迁移工具测试](M11-migration-kit-offline-tests.md)；实机证据：[首次迁移记录](FIRST_MIGRATION_1.1.22.md)、[真实写入与启动](M6-first-flash-2026-11-03.md)、[WAN 修复验收](M8-1.5.2-wan-port-repair.md)。
- **定制 1.5.3 只通过了完整离线构建与一次性测试密钥签名验收，尚未实机启动**；**原厂 1.1.22 直接升级到定制 1.5.3 也未实测**。不能把“补丁链从官方 1.5.0 可构建”误称为“旧固件直刷已验收”。
- **不要将 RSA 私钥上传到路由器**。设备的 SSH `authorized_keys` 放**公钥**；固件签名**私钥**应保留在可信构建电脑上。此公开仓库已有项目原作者公布的私钥；其他用户应**自行创建新密钥对**，不要沿用该已公开私钥作为独占信任根。
- 本流程不能用于 AX12 的 EU/US 版、其他硬件版本或其他 1.1.x 版本而不经重新审核。旧版根文件系统从 Flash `0x440000` 起；新固件从 `0x400000` 起。**严禁复用跨版本的裸写入偏移。**

### 迁移前必须具备

1. 完整可靠的电源和串口连接；串口为 **3.3 V TTL**，只接 GND/TX/RX，不接 5 V，实际焊盘引脚需依主板确认。
2. Bootloader `<RealTek>` 命令行可进入，可只读回读 Flash，已确认所需命令确实存在；不能把一个 USB 串口设备成功枚举等同于恢复通道可用。
3. **自己的完整 16 MiB 原始备份至少一份，最好两次读回一致**，保存原始 SHA-256。尤其保护 `0x000000...0x040000` Bootloader 和 `0xF08000...0x1000000` 设备出厂数据、配置与射频校准区域。任何完整备份均不可公开上传 GitHub。
4. 能接受新 RootFS / 固件失败时必须使用 UART 或外部 SPI NOR 编程器恢复的后果；有稳定的网络与回退方案。不要在设备无法中断服务或没有恢复条件时尝试。
5. Linux 构建端安装 `squashfs-tools`、Python `cryptography`、`opencc-python-reimplemented`；Mac 端 UART 脚本使用 `pyserial`。建议在虚拟环境安装 Python 依赖。

## 1. UART 只读备份原厂 16 MiB Flash

路由器断电后确认连线，上电按 Esc 进入 `<RealTek>`；退出 `screen` 释放串口。串口名只是例子，须以 `ls /dev/cu.usbserial*` 核实。

```sh
python3 -m pip install pyserial
python3 tools/ax12_flash_dump.py \
  --port /dev/cu.usbserial-XXXX \
  --output ./private-work/ax12-stock-1122-flash.bin

stat -f%z ./private-work/ax12-stock-1122-flash.bin   # macOS: 必须 16777216
shasum -a 256 ./private-work/ax12-stock-1122-flash.bin

# 推荐在首次完整备份之后运行一次完整只读逐块复核
python3 tools/ax12_flash_dump.py \
  --port /dev/cu.usbserial-XXXX \
  --output ./private-work/ax12-stock-1122-flash.bin --verify
```

**此阶段不写 Flash。** 完整工具与独立只读 ioctl 备份方法见 [READ_ONLY_FLASH_BACKUP.md](READ_ONLY_FLASH_BACKUP.md)。如曾经改过固件，应备份实际当前状态，并明确记录它**不是**出厂原样镜像；不可把其他人的 16 MiB 备份当成自己的恢复镜像。

## 2. 制作“原厂 1.1.22 + 自定义 root SSH”初始 RootFS

先在自己电脑产生**单独用于首次 SSH 引导的公私钥**。签名私钥与 SSH 私钥不必是同一个密钥；本阶段只有 `.pub` 进入 RootFS。

```sh
ssh-keygen -t rsa -b 3072 -f ~/.ssh/ax12_bootstrap_ssh -C ax12-bootstrap
```

在 Linux 构建环境使用本仓库的离线生成工具（将原始 Flash 和 `*.pub` 私下复制到该构建环境，绝不提交）。仓库已通过 `.gitignore` 排除 `private-work/`，但仍应自行保管或加密备份：

```sh
mkdir -p private-work
python3 tools/firmware/prepare_1122_ssh_bootstrap.py \
  --flash-backup private-work/ax12-stock-1122-flash.bin \
  --ssh-public ~/.ssh/ax12_bootstrap_ssh.pub \
  --workdir private-work/bootstrap-ssh \
  --reconstructed-flash
```

该工具会从 **旧版 `0x440000`** 提取 SquashFS、创建 `etc_ro/init.d/ax12-ssh` 与启动链接、写入两份 `authorized_keys`、重新生成 XZ SquashFS、追加 Realtek 头字段与校验和、用 `0xFF` 填充到 4096 字节对齐，检查不能超过旧 RootFS 容量 `0xAC8000`。**不会在路由器上写入任何数据。**

产生：

- `private-work/bootstrap-ssh/rootfs-ssh-bootstrap-flash.bin`：**仅旧 1.1.22 RootFS 目标分区的 UART 写入载荷**；其文件长度、SHA-256 以本次工具输出为准。
- 可选 `private-offline-flash-reconstruction-NOT-FOR-DIRECT-FLASH.bin`：在自己原始备份上**只替换该 RootFS 片段**的离线恢复/审计模型，大小 16 MiB，含该台设备私有数据。**不能**将它作为通用整片 Flash 镜像公开或随意直刷。

使用官方 1.1.22 RootFS 的**隔离合成 Flash 测试**已得出 `2500` 个 inode 和 `0x9A6000` 字节对齐载荷，符合之前实机成功时的文件数量和长度。但这不代表其他用户生成的 RootFS 一定得到同一个哈希或长度；每次必须重新核实。

## 3. UART 传入 RAM，核对后只写旧 RootFS 分区

先将 `rootfs-ssh-bootstrap-flash.bin` 私下复制到运行 USB-UART 的电脑，记录并重新核对 SHA-256。使用 `tools/ax12_uart_send.py` 和仓库已编译 `tools/receiver.bin` 将载荷传到 Bootloader RAM 地址 **`0xA4000000`**：

```sh
python3 tools/ax12_uart_send.py \
  --port /dev/cu.usbserial-XXXX \
  --receiver tools/receiver.bin \
  --image private-work/bootstrap-ssh/rootfs-ssh-bootstrap-flash.bin \
  --allow-large
```

该脚本本身**只写 RAM**：加载接收器、逐块 CRC32 传输并验证内容，返回 `<RealTek>`。必须检查最终成功确认、Bootloader RAM 起止地址 `DB` 回读与本地载荷一致；**有超时或校验不一致就停止，禁止继续写 Flash**。

下面的 `FLW` 是**历史上这台硬件已成功的旧 RootFS 分区写入方式**，会实际擦写 Flash，绝不是仿真。必须先人工核实自己的设备仍为原厂 1.1.22 布局、备份与回退就绪，RAM 数据已验证，并使用本次工具打印的十六进制实际长度替代 `LENGTH_HEX`。输入前确认不会越过 `0xF08000`。

```text
# RealTek Bootloader 交互提示符下的历史写入模板（会擦写！）
FLW 440000 A4000000 LENGTH_HEX 0
FLR A5000000 440000 LENGTH_HEX
CMP A5000000 A4000000 LENGTH_HEX
```

写入 `FLW` 与读回 `FLR` 均应核对设备提示的地址/大小并按需显式确认；`CMP` 必须返回 **`No error found`** 才允许启动。实际曾成功使用的长度是 `0x9A6000`，**这不是固定常量**。不要对 `0x000000` Bootloader、`0x040000` 内核或 `0xF08000` 后的设备专属数据动手。操作记录见 [README 的第 3–6 步](../../README.md)。

## 4. 验证旧版 1.1.22 的 root SSH

退出 Bootloader 正常启动，Mac 与设备连接 LAN，确认 ARP/路由确实指向自己的路由器。原本的 SSH 引导只监听 `br-lan` 地址 **TCP 2222**，并在 INPUT 规则里拦截非 LAN 流量：

```sh
ssh -i ~/.ssh/ax12_bootstrap_ssh \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  -p 2222 root@192.168.0.1
```

在设备上执行 `id`，要求 `uid=0(root)`；确认 `/proc/mtd`、`/usr/bin/nvrammanager` 路径和版本为预期原厂 1.1.22。仅为这台已确认设备启用上述旧版 SSH 算法；请勿对所有 SSH 主机全局放宽配置。**至此只完成 SSH 引导，不代表已升级固件。**

## 5. 为第一次大版本升级建立**自己的**签名密钥

在可信构建电脑上新建 RSA-2048 固件密钥。**不要复制此公开仓库内的任何他人私钥**；以下使用个人工作目录中的独立文件。

```sh
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out ~/.ssh/ax12_firmware_owner.pem
chmod 600 ~/.ssh/ax12_firmware_owner.pem
openssl pkey -in ~/.ssh/ax12_firmware_owner.pem -pubout \
  -out ~/.ssh/ax12_firmware_owner_public.pem
ssh-keygen -y -f ~/.ssh/ax12_firmware_owner.pem \
  > ~/.ssh/ax12_firmware_owner.pub
```

这里是两种不同用途的凭据：

| 凭据 | 存放位置和用途 |
|---|---|
| `~/.ssh/ax12_bootstrap_ssh` | 旧 1.1.22 的 SSH 登录私钥，只留在电脑 |
| `~/.ssh/ax12_bootstrap_ssh.pub` | 加入最初写入的旧 RootFS `authorized_keys` |
| `~/.ssh/ax12_firmware_owner.pem` | 新固件 Cloud 签名的 RSA-2048 私钥，只留在电脑 |
| `~/.ssh/ax12_firmware_owner_public.pem` | 临时旧版升级器和新版 `libnvrammanager.so` 用于验签的公钥 |
| `~/.ssh/ax12_firmware_owner.pub` | 用于新版 SSH 登录的同一 RSA-2048 公钥（当前 1.5.x 补丁的既有约定） |

**不应将任何 `*.pem` 私钥或完整旧 Flash 备份交给公开网站。** 即使私钥被上传到私有 Git 仓库，也应单独评估访问权限与备份风险。后续切换到 owner 新系统后，不能假定旧 `ax12_bootstrap_ssh` 会继续被接受；新 RootFS 的 `authorized_keys` 使用的是固件签名公钥。

## 6. 准备旧 1.1.22 RAM-only 临时验签升级器

通过已经建立的 root SSH，从**本机**旧 RootFS 中取出原生 `/usr/bin/nvrammanager`。对于记录中的确切官方 1.1.22，其 SHA-256 为 `b1c396c5f356ded3e67f081b5ebe2ab9e4fe97d39d7714aab5fcd52929fe24ea`、文件大小 **114,056 字节**；不符合这些值时应停止并重新分析，不要直接把该结果当成同款 1.1.22。

```sh
mkdir -p private-work/first-upgrade
# 端口、SSH 私钥和 IP 应与第 4 步一致
ssh -i ~/.ssh/ax12_bootstrap_ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  -p 2222 root@192.168.0.1 \
  'cat /usr/bin/nvrammanager' \
  > private-work/first-upgrade/nvrammanager-stock-1122
shasum -a 256 private-work/first-upgrade/nvrammanager-stock-1122
```

对该**离线副本**替换**公钥**，不修改升级器的机器代码，也不改路由器 Flash 里的旧可执行文件：

```sh
python3 tools/firmware/patch_trust_anchor.py \
  private-work/first-upgrade/nvrammanager-stock-1122 \
  ~/.ssh/ax12_firmware_owner_public.pem \
  private-work/first-upgrade/nvrammanager-owner-check
```

已用项目原作者的那把公钥在原版 1.1.22 ELF 上实测：替换位置 `0x19F44`，并产生了与此前 M6 实机使用的临时升级器**完全相同的 SHA-256**。对于其他所有者的独立公钥，输出 SHA-256 自然不同。

完成后可将该临时文件上传到运行中 AX12 的 RAM-backed `/tmp`，使用 `chmod 700` 并先以只读 `-c` 对**准备好的完整签名固件**执行验证；**不是**把私钥、修改过的整片 Flash、或此程序写入非易失 RootFS。 `-c` 的日志含“no need analysis firmware”，只能代表签名等预检查，不能代替实际完整 Flash 写入路径验收。

## 7. 第一次大版本迁移：构建特制的 owner-signed 1.5.0

**不要上传未经修改的官方 1.5.0 BIN 代替这份镜像。** 需要使用官方 1.5.0 作为构建来源，写入自有**公钥验证器**、root SSH，按当时成功的 `cs6c` 兼容旧 Bootloader 格式处理新内核，并从 Cloud 更新清单**省略 `fs-uboot`**。后者不能省略或随意恢复；旧 Bootloader `cr6c` 路径会错误检查新版 RootFS 的旧地址 `0x440000`。

新统一构建器已经支持**最小化自定义 1.5.0**，不再要求用户手动调用几种不同的固件封装脚本。先核对 [官方 1.5.0 SHA-256 与下载来源](../../firmware/OFFICIAL-1.5.0.sources.md)。**注意**：新的最小化 1.5.0 不带当年首次刷入的部分中文修改，**与历史成功镜像不是同一个二进制**；本次只通过离线签名和 RootFS 验证，**未在第二台旧版设备实机首刷**。

### 推荐：统一构建入口

```sh
# 位于仓库根目录，已安装 squashfs-tools 和 cryptography，
# 事先放入 inputs/official-1.5.0.bin
python3 build.py --version 1.5.0 \
  --owner-public ~/.ssh/ax12_firmware_owner_public.pem \
  --sign-key ~/.ssh/ax12_firmware_owner.pem
```

输出：`build/ax12-from-official-1.5.0/AX12-RU-1.5.0-owner-signed.bin`。构建程序验证官方签名、加入 owner 公钥和 SSH、切换 `cs6c`、在 Cloud 清单中移除 `fs-uboot` 更新项、签名并解密回读；**它不会刷写路由器**。旧 1.1.22 仍需要本指南第 6 节 RAM 临时升级器和下面的写入前人工验收，不能因为这条构建命令成功便直接升级。

### 仅供复核的历史手工组合方式

此前使用下列 `build_owner_rootfs.sh` + `prepare_owner_cloud.py` + 本地签名的组合构建当时的特制 1.5.0，它**可能包含新版最小化 1.5.0 未包含的中文文件**；用于对照历史迁移资料，不再作为新用户的首选构建入口。以下组合曾在隔离环境重验签名、解密和 RootFS，并非独立的第二次实机首刷。

Linux 工作环境准备：

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install cryptography opencc-python-reimplemented
# 系统还需安装 squashfs-tools；当前目录为仓库根目录
mkdir -p private-work/first-upgrade
```

验证原厂签名，并提取官方 1.5.0 的 RootFS：

```sh
python3 - <<'PY'
from pathlib import Path
from cryptography.hazmat.primitives import serialization
import sys
sys.path.insert(0, 'tools/firmware')
from self_sign_lab import cloud_decrypt
public = serialization.load_pem_public_key(Path('keys/tplink_official_verifier_public.pem').read_bytes())
image = Path('inputs/official-1.5.0.bin').read_bytes()
Path('private-work/first-upgrade/official-1.5.0.plain.bin').write_bytes(cloud_decrypt(image, public))
PY
python3 tools/firmware/extract_partition.py \
  private-work/first-upgrade/official-1.5.0.plain.bin file-system \
  private-work/first-upgrade/stock-150-rootfs.sqfs
unsquashfs -d private-work/first-upgrade/stock-150-rootfs \
  private-work/first-upgrade/stock-150-rootfs.sqfs
```

构建自有公钥验证器和 SSH 的新 RootFS（该脚本还使用 OpenCC 建立基础中文界面）：

```sh
sh tools/firmware/build_owner_rootfs.sh \
  private-work/first-upgrade/stock-150-rootfs \
  ~/.ssh/ax12_firmware_owner_public.pem \
  ~/.ssh/ax12_firmware_owner.pub \
  tools/ax12-ssh \
  private-work/first-upgrade/owner-150-rootfs
```

生成**特制的**、还未签名的首次升级 Cloud 包和 256 字节签名输入：

```sh
python3 tools/firmware/prepare_owner_cloud.py \
  inputs/official-1.5.0.bin \
  private-work/first-upgrade/nvrammanager-stock-1122 \
  private-work/first-upgrade/owner-150-rootfs/rootfs.sealed \
  private-work/first-upgrade/unsigned-150.bin \
  private-work/first-upgrade/em-150.bin \
  --omit-uboot --kernel-magic cs6c
```

签名后再做独立解密和 RootFS 一致性验收：

```sh
python3 tools/firmware/sign_em_local.py \
  ~/.ssh/ax12_firmware_owner.pem \
  private-work/first-upgrade/em-150.bin \
  private-work/first-upgrade/signature-150.big

python3 tools/firmware/finalize_owner_cloud.py \
  private-work/first-upgrade/unsigned-150.bin \
  private-work/first-upgrade/signature-150.big \
  ~/.ssh/ax12_firmware_owner_public.pem \
  private-work/first-upgrade/owner-150-rootfs/rootfs.sealed \
  private-work/first-upgrade/owner-150-signed.bin
```

**上述流程的生成物不能直接视为另一台路由器上的“已验证安全刷写镜像”。** 它与本项目第一次实机写入的历史镜像在 RootFS 文件集和打包时间等方面可能不同。应先进行 [M5 模拟升级与写入区间审计](M5-acceptance-2026-11-03.md)，检查整包签名、内核 `cs6c`、U-Boot 不在写入清单、RootFS 容量与所有受保护扇区；当场确保 UART 恢复可用。

### 第一次在旧 1.1.22 上执行升级的人工验收门

只有**完整通过下列门槛**，并由设备所有者明确批准首次不可逆写入时，才进入写入阶段：

1. `nvrammanager-owner-check` 是旧版设备**自身** ELF 的公钥替换副本，未使用其他硬件型号的程序。与升级镜像采用**相同的自有公钥**。
2. 已上传的签名 Cloud 镜像在路由器 RAM 中与构建电脑的 SHA-256 完全相同，大小及设备可用内存足够。
3. `/tmp/nvrammanager-owner-check -c /tmp/<owner-signed-image>` 返回 0，但**还必须**审计真实 `-u` 的分区、Flash 写入模式与配置保留；`-c` 不做这些检查。
4. 升级清单仅指定允许写入的新内核、RootFS、分区元数据等区域；**不包括 Bootloader、ART/射频校准/设备身份**。保留旧 Bootloader，并确认 `cs6c` 启动路径。
5. 旧系统状态、完整 16 MiB 备份、签名固件、供恢复的 UART/TFTP 工具都已重新确认；用户有足够时间、稳定供电和可行的恢复方案。

项目原作者实机的**历史成功步骤**是：将已验签的 `owner-signed-150` 和临时 owner 公钥版 `nvrammanager` 都放在 RAM `/tmp`，确认 `-c` 后，调用那份**临时**升级器的 `-u`，并保留旧 Bootloader；结果 `upgradeFirmware success...`、退出码 0，新内核/RootFS 重启成功。明确的原始写入记录见 [M6](M6-first-flash-2026-11-03.md)。为了避免将这一高风险、跨设备尚未经验证的写入步骤误认为通用命令，本指南不提供无人值守的 `-u` 脚本或自行重启脚本；首先按 M5/M6 检查当次镜像和恢复条件，再由设备所有者决定。

参见 [M12](M12-owner-1.5.0-versioned-refactor.md) 了解新 1.5.0 与历史首次升级镜像的区别、四版本完整验签测试及回归结果。

## 8. 初次迁移后逐版升级至 1.5.3

若首次 1.1.22 → 特制自签名 1.5.0 已经完成且 root SSH、网页、WAN/LAN 和串口启动都通过，后续新 RootFS 的 `libnvrammanager.so` 已永久信任自己的**公钥**，无需再用 UART 修改旧 Flash，也无需再次以临时旧版升级器建立信任。

**建议其他用户先走已观察过的 1.5.0 → 1.5.1 → 1.5.2 版本路径，1.5.3 作为有备份的实机实验升级。** 对每个目标版本，在 Linux 构建机器：

```sh
python3 build.py --version 1.5.1 \
  --owner-public ~/.ssh/ax12_firmware_owner_public.pem \
  --sign-key ~/.ssh/ax12_firmware_owner.pem
# 该版本实机功能通过后，再分别将 1.5.1 改为 1.5.2、1.5.3 构建后续包
```

`build.py` 始终以**原始官方 1.5.0** 为输入，按 `1.5.0 → 1.5.1 → 1.5.2 → 1.5.3` 顺序应用补丁，**不是**用已经定制的旧固件二次解包作为新源码。每次构建的公钥必须与正在运行的持久升级器信任锚一致；换公钥需要另行设计受控密钥轮换，不能只更换签名私钥。更多请读 [REPRODUCIBLE_BUILD.md](REPRODUCIBLE_BUILD.md)。

升级前每次都独立验证签名、解密结果、分区边界、RootFS 空间、内核布局、网页/SSH 的新旧兼容；写入由设备所有者单独确认，不要把构建脚本与自动刷机绑定。

## 9. 能不能从 1.1.22 **直接**升级到 1.5.3？

**就固件构造而言，可以从官方 1.5.0 加载完整 `1.5.0+1.5.1+1.5.2+1.5.3` 补丁集生成一个 1.5.3 自签名 Cloud 包；但是这不等于它在原厂 1.1.22 上可安全直接升级。**

当前验证覆盖矩阵：

| 操作 | 证据 |
|---|---|
| 原厂 1.1.22 → UART SSH RootFS → root 登录 | **实机 PASS**（项目作者这一台） |
| 临时公钥版旧升级器 → 自签名特制 1.5.0 | **实机 PASS**（项目作者这一台） |
| 自签名 1.5.0 → 1.5.1 → 1.5.2 | **实机分别成功**，最终 WAN/LAN/互联网 PASS |
| 官方 1.5.0 → 补丁链构建自定义 1.5.0/1.5.1/1.5.2/1.5.3 | **四版本离线构建和一次性密钥签名均 PASS** |
| 补丁链 1.5.3 的 RSA-PSS / AES 完整签名回读 | **一次性测试密钥离线 PASS** |
| 从原厂 1.1.22 **一步**升级 owner-signed 1.5.3 | **未实测，不能推荐为直接刷写路径** |
| 首次升级后直接跳过 1.5.1、1.5.2 到 1.5.3 | **未完成实机验收** |
| 1.5.3 本身启动、Web、WAN 和无线功能 | **尚未实机验收** |

未来要把“1.1.22 一步直升 1.5.3”变成正式支持路径，至少要用确切的 1.1.22 原厂 `nvrammanager`、匹配该用户公钥的 1.5.3 签名包完成 `-c` 和**全路径模拟 `-u` 写入**，对写请求、分区表、NVRAM 状态、保护区和断电失败做独立验收；最后才能在具备 UART / 外部编程器恢复能力的设备上进行经用户明确许可的实机测试。不能把“同一签名格式、同一硬件型号”当成这些测试的替代。

## 10. 发生问题时的处理边界

- **备份 / 解包失败**：立即停止，不进入 Flash 写入。
- **UART RAM CRC/比对失败**：停止，不允许执行 `FLW`。
- **旧 SSH 不可达**：先确认网线与端口、LAN IP、Mac 路由、SSH 公钥及 Dropbear 状态，不直接重新全片刷机。
- **升级镜像签名不通过或 `-c` 返回非零**：禁止 `-u`；核对所有者公钥、RSA-2048 签名、Cloud 打包与版本。
- **新系统开机不成功**：使用事先准备并验证过的 UART / TFTP 恢复计划，保留 Bootloader/ART；不要通过盲写整片备份覆盖当前设备的独有分区，也不要使用别人的 16 MiB 备份。
- **固件成功启动但 WAN 失效**：检查 [M8 WAN 物理端口映射](M8-1.5.2-wan-port-repair.md)，而不是把 PPPoE/DHCP 问题全部归咎于酒店网络。

**结论**：这是可供其他同型号设备所有者复现、逐项验收的**分阶段迁移方案**。它能完成从旧版固件到最新补丁链的开发和验证工作，但截至 2026-11-03，**不能声称“老原厂一键直升 1.5.3”已经通过实机验收**。所有 Flash 操作都留给操作者在其设备通过门槛检查后单独执行。
