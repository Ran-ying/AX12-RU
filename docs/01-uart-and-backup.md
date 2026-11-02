# 01 · UART 接入、Realtek Monitor、16 MiB Flash 备份

[返回首页](../README.md)

## 设备与接线

本次成功使用 USB-TTL 串口适配器连接 **Archer AX12 RU v1** 的主板 UART，参数 **115200 8N1**。TX 与 RX 交叉、GND 共地，只接 **3.3V TTL 信号**；不要把 5V 接入 UART。**具体主板焊盘顺序未在可核验资料中保存，不在此臆造引脚图；实际操作需按原板测量/确认。**

Mac mini 本次端口：`/dev/cu.usbserial-2120`（换 USB 接口或适配器后名称可能不同）。

```bash
ls /dev/cu.usbserial*
lsof -nP /dev/cu.usbserial-2120
screen /dev/cu.usbserial-2120 115200
```

串口占用排查：

```bash
screen -ls
lsof -nP /dev/cu.usbserial-2120
```

之前出现过后台 `screen` 进程占用串口的情况：先 `screen -r` 恢复已有会话，或从 `screen` 用 `Ctrl+A`、`K`、`Y` 结束它，再使用 Python。**不要让 `screen` 和发送脚本同时占用串口。**

重新上电，在启动时按 **Esc**，直到串口出现：

```text
<RealTek>
```

这里是 Realtek Bootloader monitor，不是 Linux Shell。

## 本次用到的 Monitor 指令

| 指令 | 含义 |
| --- | --- |
| `DB <RAM-address> <length>` | 显示 RAM 字节；本次使用的 `DB` 长度参数按**十进制**解释 |
| `EB <RAM-address> <hex-bytes...>` | 修改 RAM 字节；只作用于 RAM |
| `FLR <RAM-address> <SPI-offset> <hex-length>` | 从 SPI Flash 读入 RAM；**不修改 Flash** |
| `FLW <SPI-offset> <RAM-address> <hex-length> 0` | 从 RAM 写 SPI Flash，**会擦写 Flash** |
| `CMP <RAM-address-1> <RAM-address-2> <hex-length>` | 比较两个 RAM 区域 |
| `J <RAM-address>` | 执行 RAM 中的机器码 |

`FLR` / `FLW` 会提示确认；确认前必须核对参数。不要把 RAM 地址与 Flash 偏移混淆。

## 备份整片 16 MiB SPI NOR（已实际完成）

归档脚本：[`../tools/ax12_flash_dump.py`](../tools/ax12_flash_dump.py)。它通过 `FLR` + `DB` 每次读取 4096 字节，可断点继续，并支持完整复核。需要 Mac 上的 `pyserial`。

```bash
python3 -m pip install pyserial
git clone https://github.com/Ran-ying/AX12-RU.git ~/AX12-RU
python3 ~/AX12-RU/tools/ax12_flash_dump.py \
  --port /dev/cu.usbserial-2120 \
  --output ~/Desktop/ax12-flash-16MiB.bin
```

原厂备份大小：`16777216` 字节（`0x1000000`），实际 SHA256：

```text
22926a520f7d58e8abe1789cf8ba6f947c824c5807b0b5d217deed59d79793b1
```

校验备份文件：

```bash
shasum -a 256 ~/Desktop/ax12-flash-16MiB.bin
```

如需再次从同一台路由器完整回读核对（耗时很久）：

```bash
python3 ~/AX12-RU/tools/ax12_flash_dump.py \
  --port /dev/cu.usbserial-2120 \
  --output ~/Desktop/ax12-flash-16MiB.bin \
  --verify
```

**备份包含设备独有参数及用户配置，不上传到本公开仓库。**

## Flash 区域（本设备实测分析）

| 区域 | 起始 | 结束（不含） | 大小 |
| --- | ---: | ---: | ---: |
| `fs-uboot` | `0x000000` | `0x040000` | `0x040000` |
| `os-image` | `0x040000` | `0x440000` | `0x400000` |
| `file-system` | `0x440000` | `0xF08000` | `0xAC8000` |
| 设备配置、工厂及校准数据等 | `0xF08000` | `0x1000000` | 其余空间 |

**本项目仅针对 `file-system` 改动；不得把 RootFS 镜像刷进 `os-image` 或后面的校准/配置分区。**

原厂 RootFS 为 SquashFS v4、XZ 压缩、块大小 262144，约 2495 inode。本次改版后变为 2497 inode，最终公钥版 2500 inode。

后续：[02 · RootFS 与 SSH](02-rootfs-and-ssh.md)。
