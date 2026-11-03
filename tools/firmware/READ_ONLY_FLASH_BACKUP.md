# AX12-RU V1：完整 16 MiB Flash 只读备份

此流程适用于已经核对过的 1.1.22 Build 20240311、RTL8197F、小端 MIPS32、16 MiB SPI NOR。**不执行固件升级、不擦除或写入 Flash、不重启路由器。**

## 为什么不是直接拼接四个 MTD 分区？

`/proc/mtd` 当前显示：

| MTD | 容量 | 对应原始 Flash 地址 |
|---|---:|---:|
| `mtd0` uboot | `0x40000` | `0x000000` |
| `mtd1` uImage | `0x400000` | `0x040000` |
| `mtd2` rootfs | `0xAF0000` | `0x440000` |
| `mtd3` ART | `0x10000` | 预计 `0xFF0000`（需通过备份对照验证） |

四个分区的容量总和 `0xF40000`，不能用简单拼接得到完整 `0x1000000` Flash；空缺处含厂家分区表、配置、身份信息等。ART 的预计地址独立于前三个 MTD 的连续地址。

从旧版 `nvrammanager` ELF 反汇编，`read_flash` 在 `0x4022C0` 通过 `/dev/flash_chrdev` 的 **只读** ioctl `0x4001B301` 读取物理地址；内核 `tp_flash_ioctl` 在 `0x801E1FB8` 将该 ioctl 转发到 SPI 读取函数。写入使用**不同请求** `0x8001B302`，本工具不包含它。

## Mac mini 执行（保存到本机，不保存在路由器 Flash）

从本仓库下载离线编译好的 1628 字节 MIPS ELF；原始代码见 [`ax12_flash_read.S`](ax12_flash_read.S)：

```sh
cd ~/Desktop

curl -fsSL https://raw.githubusercontent.com/Ran-ying/AX12-RU/main/tools/firmware/ax12_flash_read.mipsel.b64 \
  | base64 -D > ax12_flash_read

shasum -a 256 ax12_flash_read
# 必须是 cd7215feeb8b294779790dc54db6532357db0be991553534f0d687dd4b2bf713

# /tmp 为路由器 RAM 文件系统；仅复制小型可执行程序，不修改 Flash
cat ax12_flash_read | ssh -T ax12 'cat > /tmp/ax12_flash_read && chmod 700 /tmp/ax12_flash_read'

# 从物理 Flash 0x0 只读流出全部 16 MiB，文件保存在 Mac Desktop
ssh -T ax12 '/tmp/ax12_flash_read' > ax12-full-flash-20261103.bin

stat -f%z ax12-full-flash-20261103.bin
# 必须等于 16777216；若不匹配，文件是不完整备份，不能用于恢复或模拟
shasum -a 256 ax12-full-flash-20261103.bin
```

如果程序输出 `Flash read failed; reject partial backup.`，请**停止**，保留错误信息，先排查；不要尝试写 ioctl 或改写设备。

## 与 MTD 只读接口交叉核对

```sh
# 第一组：Bootloader，物理 0x000000，4 个 64 KiB 块
ssh -T ax12 'dd if=/dev/mtd0ro bs=65536 count=4 2>/dev/null' | shasum -a 256
dd if=ax12-full-flash-20261103.bin bs=65536 count=4 2>/dev/null | shasum -a 256

# 第二组：ART，预计物理 0xFF0000，最后一个 64 KiB 块
ssh -T ax12 'dd if=/dev/mtd3ro bs=65536 count=1 2>/dev/null' | shasum -a 256
dd if=ax12-full-flash-20261103.bin bs=65536 skip=255 count=1 2>/dev/null | shasum -a 256
```

每组两条 SHA-256 应相同。若 ART 比对不一致，**不要直接推断备份错误**，需要进一步检查 MTD3 实际映射地址。

建议另执行一次完整只读备份并比较两份 SHA-256，以发现非稳定读取；无需刷写、重启。

## 隐私与数据保留

**仓库目前为公开（public）。不要把原始 16 MiB 文件、用户 Wi-Fi 配置、密钥、唯一设备身份或射频校准数据直接提交到公开 Git 历史。** 备份建议保留在 Mac mini；若需传送，可直接上传本对话附件，或本地加密后再上传 GitHub。不要把解密密码或私钥提交到仓库。

## 已验证 / 未验证

- 已在独立 Linux Panel 服务器上编译源文件，产出静态 MIPS little-endian ELF；`sha256sum` 与 GitHub 发布的 Base64 解码内容一致。
- QEMU 环境在缺失 `/dev/flash_chrdev` 时，程序明确非零退出、stderr 报错、stdout 长度为 0；不存在静默成功。
- 代码仅使用 `open(O_RDONLY)`、`ioctl(0x4001B301)`、`write(1,...)`、`close`、`exit` 等系统调用。这里的 `write(1,...)` 仅是将读取结果写至 SSH 标准输出，**不是写 Flash**。
- **尚未在真实 AX12 上执行**。能否跨整个 16 MiB 地址范围读取，以及 MTD3 的物理位置，须通过上面的文件长度与哈希校验确认。
