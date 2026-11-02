#!/usr/bin/env python3
"""AX12 UART Loader V2: verified RAM transfer, return to Bootloader; no flash writes."""

import argparse
import hashlib
import re
import struct
import zlib
from pathlib import Path


LOADER_ADDR = 0xA0800000
PAYLOAD_ADDR = 0xA4000000
MAX_PAYLOAD = 0xB00000
PROMPT = b"<RealTek>"
ROW = re.compile(rb"^([0-9A-Fa-f]{8}):\s+((?:[0-9A-Fa-f]{2} ){15}[0-9A-Fa-f]{2})(?:\s|$)")


def read_until(port, marker):
    output = bytearray()
    while marker not in output:
        data = port.read(port.in_waiting or 1)
        if not data:
            raise TimeoutError(f"Timed out waiting for {marker!r}; last RX bytes: {bytes(output[-160:])!r}")
        output.extend(data)
    return bytes(output)


def monitor_command(port, command):
    port.write((command + "\r").encode("ascii"))
    reply = read_until(port, PROMPT)
    if b"Unknown command" in reply or b"Error" in reply:
        raise RuntimeError(f"Monitor rejected {command[:40]}: {reply[-250:]!r}")
    return reply


def load_receiver(port, binary):
    # Keep each command comfortably below the RealTek line-editor buffer size.
    for offset in range(0, len(binary), 16):
        chunk = binary[offset:offset + 16]
        params = " ".join(f"{byte:02X}" for byte in chunk)
        monitor_command(port, f"EB {LOADER_ADDR + offset:08X} {params}")
    print(f"Bootloader EB: loaded {len(binary)} bytes at 0x{LOADER_ADDR:08X}", flush=True)

    # DB's length parameter is decimal, unlike the EB address (hex).
    reply = monitor_command(port, f"DB {LOADER_ADDR:08X} {len(binary)}")
    actual = bytearray()
    for line in reply.splitlines():
        match = ROW.match(line.strip())
        if match:
            address = int(match.group(1), 16)
            if address != LOADER_ADDR + len(actual):
                raise ValueError(f"DB address out of order: {address:08X}")
            actual.extend(bytes.fromhex(match.group(2).decode("ascii")))
    if actual != binary:
        raise ValueError(f"RAM loader verification failed: read {len(actual)} / {len(binary)} bytes")
    print("Bootloader DB: receiver verified byte-for-byte", flush=True)


def ack(port, expected):
    value = port.read(1)
    if value != expected:
        raise RuntimeError(f"Unexpected UART response: {value!r} (wanted {expected!r})")


def transfer(port, payload):
    crc = zlib.crc32(payload)
    port.write(b"AXV2" + struct.pack("<II", len(payload), crc))
    ack(port, b"H")

    for seq, offset in enumerate(range(0, len(payload), 256)):
        block = payload[offset:offset + 256]
        frame = struct.pack("<III", seq, len(block), zlib.crc32(block)) + block
        for attempt in range(4):
            port.write(frame)
            response = port.read(1)
            if response == b"K":
                break
            if response != b"N":
                raise RuntimeError(f"Block {seq} failed: {response!r}; reboot before retrying")
        else:
            raise RuntimeError(f"Block {seq} failed CRC four times")
        if (offset + len(block)) // 65536 != offset // 65536:
            print(f"Transferred {offset + len(block)} / {len(payload)} bytes", flush=True)

    ack(port, b"D")
    print(f"RAM copy verified at 0x{PAYLOAD_ADDR:08X}; length={len(payload)}", flush=True)
    print(f"CRC32={crc:08x}  SHA256={hashlib.sha256(payload).hexdigest()}")
    port.write(b"R")
    ack(port, b"r")
    read_until(port, PROMPT)
    print("Returned to <RealTek>; checking retained RAM bytes...", flush=True)
    for offset in (0, len(payload) - 16) if len(payload) > 16 else (0,):
        count = min(16, len(payload) - offset)
        address = PAYLOAD_ADDR + offset
        reply = monitor_command(port, f"DB {address:08X} {count}")
        actual = bytearray()
        for line in reply.splitlines():
            match = ROW.match(line.strip())
            if match:
                actual.extend(bytes.fromhex(match.group(2).decode("ascii")))
        if actual[:count] != payload[offset:offset + count]:
            raise ValueError(f"RAM changed after returning to Bootloader at 0x{address:08X}")
    print("Monitor RAM spot-check passed. Flash is unchanged.", flush=True)


def main():
    import serial

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-2120")
    parser.add_argument("--receiver", type=Path, default=Path(__file__).with_name("receiver.bin"))
    parser.add_argument("--image", type=Path, help="RAM-only payload; defaults to 4096-byte test pattern")
    parser.add_argument("--allow-large", action="store_true", help="permit RAM payloads above 64 KiB")
    args = parser.parse_args()
    payload = args.image.read_bytes() if args.image else bytes(range(256)) * 16
    receiver = args.receiver.read_bytes()
    if not 16 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError(f"Payload length must be 16..{MAX_PAYLOAD} bytes")
    if len(payload) > 65536 and not args.allow_large:
        raise ValueError("RAM payload is above 64 KiB; pass --allow-large after the small test succeeds")
    if len(receiver) % 16:
        raise ValueError("Receiver binary must be 16-byte aligned")

    with serial.Serial(args.port, 115200, timeout=10, write_timeout=10) as port:
        port.reset_input_buffer()
        port.write(b"\r")
        read_until(port, PROMPT)
        reply = monitor_command(port, "AUTOBURN 0")
        if b"AutoBurning=0" not in reply:
            raise RuntimeError(f"Failed to disable autoburn: {reply[-200:]!r}")
        load_receiver(port, receiver)
        print("Starting receiver via J. Flash is not modified.", flush=True)
        port.reset_input_buffer()
        port.write(f"J {LOADER_ADDR:08X}\r".encode("ascii"))
        read_until(port, b"\x02")
        print("Receiver is running; sending payload...", flush=True)
        transfer(port, payload)


if __name__ == "__main__":
    main()
