# 04 · UART V2 RAM 传输 → Bootloader 返回 → Flash 回读

[返回首页](../README.md) · [上一步](03-realtek-checksum.md)

## 为什么没有使用常规 TFTP/XMODEM

本次尝试过 Realtek Bootloader 网络/TFTP 和串口 XMODEM 恢复方案，遭遇 UART 实现、以太网初始化/交换芯片相关障碍，未得到可重复的完整传输。最终实际成功的是**自制 UART V2 RAM-only 接收器**：

1. 使用 `EB` 把小型 MIPS 接收器写入 RAM，并经 `DB` 逐字节回读。
2. 在 Bootloader 执行 `J A0800000`，由接收器通过串口读入数据。
3. 每个 256 字节数据块带序号、长度、CRC32；结束后验证完整 payload CRC32。
4. 传输结果保存在 `0xA4000000` 起始的 RAM，完成后用 `R` 返回 Bootloader。
5. **只有经校验确认的 RAM 数据**才允许通过单独的 `FLW` 写 Flash。

注意 V2 发送器的源码里明确写着 `no flash writes`：**UART 传输本身不刷写固件**。

## 本次 Mac mini 上实际使用的文件路径

下面的文件已从 Mac mini 的 `ls ~/Desktop` 和运行结果确认：

```text
/Users/ranying/Desktop/ax12_uart_send.py
/Users/ranying/Desktop/receiver.S
/Users/ranying/Desktop/receiver.bin
/Users/ranying/Desktop/receiver.elf
/Users/ranying/Desktop/eb_upload.py
/Users/ranying/Desktop/rootfs-ssh-pubkey-flash.bin
```

`receiver.bin` 大小 **992 字节**，`ax12_uart_send.py` 的帮助信息包含 `--port`、`--receiver`、`--image`、`--allow-large`；其常量有 `LOADER_ADDR=0xA0800000`、`PAYLOAD_ADDR=0xA4000000`、`MAX_PAYLOAD=0xB00000`。

**已归档原件：** [`../tools/ax12_uart_send.py`](../tools/ax12_uart_send.py)、[`../tools/receiver.S`](../tools/receiver.S)、[`../tools/receiver.bin`](../tools/receiver.bin)。三者均来自 Mac mini 原文件上传，没有重写。

| 文件 | SHA256 |
| --- | --- |
| `tools/ax12_uart_send.py` | `48ed8fa4ce00ac214798a271d11ab64a48e572c4483f515b181f354915436ace` |
| `tools/receiver.S` | `af4bdc0e94cdc0d44b25da144fe0c75a9de20072c490e97bd40dbc9fa66bd557` |
| `tools/receiver.bin` | `7d10d6e6a149eb6ae41ced851db26f0f26da85de3f0b6944438f7a7ab814903f` |

从仓库在 Mac 上运行（先 `python3 -m pip install pyserial`，以实际串口设备和镜像为准）：

```bash
cd ~/AX12-RU
python3 tools/ax12_uart_send.py \
  --port /dev/cu.usbserial-2120 \
  --receiver tools/receiver.bin \
  --image ~/Desktop/rootfs-ssh-pubkey-flash.bin \
  --allow-large
```

`build.sh`、`link.ld` 仍在本次 Mac mini 桌面文件清单中，但尚未上传；要从 `receiver.S` **重新生成**与原件逐字节相同的 `receiver.bin`，还需要这两份构建资料。

## 本次新镜像：大小、SHA256

VPS：

```text
~/AX12-research/reports/rootfs-ssh-pubkey-flash.bin
```

Mac mini：

```text
/Users/ranying/Desktop/rootfs-ssh-pubkey-flash.bin
```

两端均应检查：

```text
size:   10117120 bytes  (0x9A6000)
SHA256: c582f050d711f58911dd5c71388186d64cb522da1f54b4d6af3ffd01b008ddf5
```

VPS → Mac mini 本次实际使用的远程路径：

```bash
scp ~/AX12-research/reports/rootfs-ssh-pubkey-flash.bin \
  ranying@10.7.0.4:~/Desktop/
```

这里 `10.7.0.4` 是本次 Mac mini 的实验内网地址，迁移设备后不能默认相同。

## V2 发送命令（实际执行并成功完成）

确保 Mac 端 `screen` 已退出，Realtek Monitor 处于 `<RealTek>`，且串口未被其他进程占用：

```bash
lsof -nP /dev/cu.usbserial-2120
cd ~/Desktop

python3 ax12_uart_send.py \
  --port /dev/cu.usbserial-2120 \
  --receiver receiver.bin \
  --image rootfs-ssh-pubkey-flash.bin \
  --allow-large
```

本次总长度 `0x9A6000`，单块 256 字节，共 **39520 块**，从 `0xA4000000` 起装入 RAM；发送器上限 `0xB00000`，不会超限。

## 最后等待 D 超时的恢复（本次确实发生过）

发完所有带 ACK 的块后，发送器会等待最终 `D`。本次终端打印：

```text
Transferred 10092544 / 10117120 bytes
RuntimeError: Unexpected UART response: b'' (wanted b'D')
```

这里进度 `10092544` 是最近一个 64 KiB 打印节点，不是发送循环最终字节数。程序已执行到 `ack(port,b'D')`，说明所有块均被发送并分别确认。

**仅在确认已到这个 `ack(D)` 阶段、未重新上电的情况下**，使用如下非 Flash 写入的恢复尝试：

```python
import serial, time

with serial.Serial("/dev/cu.usbserial-2120", 115200,
                   timeout=5, write_timeout=2) as port:
    time.sleep(0.2)
    print("Pending:", repr(port.read(port.in_waiting)))
    port.write(b"R")
    port.flush()
    reply = port.read_until(b"<RealTek>")
    print("Reply:", repr(reply))
```

本次实际返回：

```text
SUCCESS: returned to Realtek Bootloader
```

在该 V2 协议中，接收器等待 `R` 并返回 `r<RealTek>`，它是在完整 CRC32 验证之后才到达的状态。**对其他串口协议或中途失败不能直接发送 `R` 并假定传输成功**。

## 写 Flash 前后的 RAM 验证

已回到 `<RealTek>` 后，`screen` 重连（先关闭 Python 串口句柄）：

```text
DB A4000000 16
DB A49A5000 16
DB A49A5FF0 16
```

Mac 本地参考：

```bash
xxd -l 16 ~/Desktop/rootfs-ssh-pubkey-flash.bin
xxd -s 0x9A5000 -l 16 ~/Desktop/rootfs-ssh-pubkey-flash.bin
xxd -s 0x9A5FF0 -l 16 ~/Desktop/rootfs-ssh-pubkey-flash.bin
```

**下面是危险、实际会写 SPI NOR 的历史操作。** 必须先确认已备份原厂 Flash、原有 Bootloader 仍能进入、镜像 hash/长度/地址/CRC32 均正确，且没有网卡/配置分区越界问题：

```text
FLW 440000 A4000000 9A6000 0
```

确认提示中参数准确无误后才回复 `Y`。本次写入范围是 Flash `[0x440000,0xDE6000)`，完全位于 `file-system` 分区 `[0x440000,0xF08000)` 之内。

**刷完先完整回读，再允许重启：**

```text
FLR A5000000 440000 9A6000
CMP A5000000 A4000000 9A6000
```

只有 `CMP` 返回 `No error found`，才说明回读的 Flash 与 RAM 镜像完全一致。随后正常重启，等待原厂 Web 后台与 SSH 服务恢复。

⚠️ 刷写安全条件比速度重要；不可把 `FLR`/ `CMP` 误写成 `FLW`，更不可覆盖 `0xF08000` 后的设备工厂数据。

后续：[05 · SSH 公钥登录成功](05-ssh-key-auth.md)。
