"""GDB Python hook for AX12 1.1.22 nvrammanager under QEMU user mode.

Run ONLY against a QEMU process whose /dev/flash_chrdev is a regular
file inside an isolated guest rootfs. No router or host Flash access.

Environment of GDB:
  AX12_FLASH_BASELINE  full 16-MiB *offline* baseline (synthetic is fine)
  AX12_IOCTL_TRACE     path for textual ioctl trace
  AX12_FAIL_FLASH_ADDR optional hex address to inject a failed write
  AX12_EMU_OUTPUT      optional output path for simulated 16-MiB end state

Breaks at the stock 1.1.22 ELF's ioctl@plt (0x4198a0) and emulates
only 0x4001B301 READ / 0x8001B302 WRITE. It models mode-1 header
bytes and the end-state of sector read-modify-write. It is NOT the
actual Realtek kernel or SPI controller.
"""
import gdb
import hashlib
import os
import struct
from pathlib import Path

FLASH_SIZE = 0x1000000
flash = bytearray(Path(os.environ["AX12_FLASH_BASELINE"]).read_bytes())
if len(flash) != FLASH_SIZE:
    raise ValueError("Expected exactly 16 MiB offline Flash input")
trace = open(os.environ["AX12_IOCTL_TRACE"], "w", buffering=1)
fail_address = os.environ.get("AX12_FAIL_FLASH_ADDR")
fail_address = int(fail_address, 16) if fail_address else None
counts = {"READ": 0, "WRITE": 0, "INJECT_FAIL": 0}


class FlashIoctl(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x4198a0", internal=True)

    def stop(self):
        inferior = gdb.selected_inferior()
        request = int(gdb.parse_and_eval("$a1")) & 0xFFFFFFFF
        argument = int(gdb.parse_and_eval("$a2")) & 0xFFFFFFFF

        if request == 0x4001B301:
            offset, length, pointer, repeated_length = struct.unpack(
                "<4I", inferior.read_memory(argument, 16))
            if length != repeated_length or offset + length > FLASH_SIZE:
                raise ValueError("Invalid intercepted Flash READ arguments")
            inferior.write_memory(pointer, flash[offset:offset + length])
            trace.write(f"READ flash={offset:#x} n={length:#x}\n")
            counts["READ"] += 1
            result = 0
        elif request == 0x8001B302:
            offset, length, pointer, repeated_length, mode = struct.unpack(
                "<5I", inferior.read_memory(argument, 20))
            if length != repeated_length or mode not in (0, 1):
                raise ValueError("Invalid intercepted Flash WRITE arguments")
            total = length + (8 if mode else 0)
            if offset + total > FLASH_SIZE:
                raise ValueError("Write exceeds the virtual 16 MiB Flash")
            if offset == fail_address:
                trace.write(
                    f"INJECT_FAIL flash={offset:#x} n={length:#x} mode={mode}\n")
                counts["INJECT_FAIL"] += 1
                result = -1
            else:
                source = bytes(inferior.read_memory(pointer, length))
                data = struct.pack(">II", length, 0) + source if mode else source
                flash[offset:offset + len(data)] = data
                trace.write(
                    f"WRITE flash={offset:#x} n={length:#x} mode={mode} "
                    f"first={source[:8].hex()}\n")
                counts["WRITE"] += 1
                result = 0
        else:
            raise ValueError(f"Unexpected ioctl request {request:#x}")

        gdb.execute(f"set $v0={result}", to_string=True)
        gdb.execute("set $pc=$ra", to_string=True)
        return False


def on_exit(event):
    digest = hashlib.sha256(flash).hexdigest()
    trace.write(f"EXIT code={event.exit_code} simulated_sha256={digest}\n")
    trace.write(f"COUNTS {counts}\n")
    print("QEMU Flash interception:", counts, "SHA256:", digest)
    output = os.environ.get("AX12_EMU_OUTPUT")
    if output:
        Path(output).write_bytes(flash)
    trace.close()


FlashIoctl()
gdb.events.exited.connect(on_exit)
print("Read-only QEMU Flash interception active; no hardware Flash access")
