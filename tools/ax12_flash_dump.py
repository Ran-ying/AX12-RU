#!/usr/bin/env python3
"""Read a 16 MiB AX12 SPI-NOR through Realtek monitor FLR + DB. Never writes flash."""

import argparse
import hashlib
import re
from pathlib import Path

import serial

FLASH_SIZE = 0x1000000
BLOCK_SIZE = 0x1000
RAM_ADDRESS = 0xA0800000
PROMPT = b"<RealTek>"
ROW = re.compile(rb"^([0-9A-Fa-f]{8}):\s+((?:[0-9A-Fa-f]{2} ){15}[0-9A-Fa-f]{2})(?:\s|$)")


def receive_until(port, marker):
    output = bytearray()
    while marker not in output:
        chunk = port.read(port.in_waiting or 1)
        if not chunk:
            raise TimeoutError(f"UART timeout waiting for {marker!r}; last output: {bytes(output[-160:])!r}")
        output.extend(chunk)
    return bytes(output)


def fetch_block(port, offset):
    port.write(f"FLR {RAM_ADDRESS:08X} {offset:X} {BLOCK_SIZE:X}\r".encode())
    reply = receive_until(port, b"-->")
    expected = f"Flash read from {offset:08X} to {RAM_ADDRESS:08X} with {BLOCK_SIZE:08X} bytes".encode()
    if expected not in reply:
        raise RuntimeError(f"Unexpected FLR confirmation: {reply[-300:]!r}")

    port.write(b"Y\r")
    reply = receive_until(port, PROMPT)
    if b"Flash Read Successed!" not in reply:
        raise RuntimeError(f"FLR failed at offset 0x{offset:X}: {reply[-300:]!r}")

    port.write(f"DB {RAM_ADDRESS:08X} {BLOCK_SIZE}\r".encode())
    reply = receive_until(port, PROMPT)
    data = bytearray()
    for line in reply.splitlines():
        match = ROW.match(line.strip())
        if match:
            address = int(match.group(1), 16)
            if address != RAM_ADDRESS + len(data):
                raise ValueError(f"DB address mismatch: {address:08X} != {RAM_ADDRESS + len(data):08X}")
            data.extend(bytes.fromhex(match.group(2).decode("ascii")))

    if len(data) != BLOCK_SIZE:
        raise ValueError(f"Incomplete DB dump at flash 0x{offset:X}: {len(data)} / {BLOCK_SIZE} bytes")
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description="Backup AX12 SPI flash through the Realtek UART monitor")
    parser.add_argument("--port", default="/dev/cu.usbserial-2120")
    parser.add_argument("--output", type=Path, default=Path("ax12-flash-16MiB.bin"))
    parser.add_argument("--verify", action="store_true", help="compare the complete backup against a fresh read")
    args = parser.parse_args()

    existing = args.output.stat().st_size if args.output.exists() else 0
    if args.verify:
        if existing != FLASH_SIZE:
            raise ValueError("Verification requires an existing complete 16 MiB image")
    elif existing > FLASH_SIZE or existing % BLOCK_SIZE:
        raise ValueError("Existing file length must be a multiple of 4096 and at most 16 MiB")

    with serial.Serial(args.port, 115200, timeout=10, write_timeout=5) as port:
        port.reset_input_buffer()
        port.write(b"\r")
        receive_until(port, PROMPT)
        mode = "rb" if args.verify else ("r+b" if args.output.exists() else "w+b")
        with args.output.open(mode) as output:
            start = 0 if args.verify else existing
            if existing and not args.verify and existing < FLASH_SIZE:
                # Check that the saved tail matches this exact router before resuming.
                offset = existing - BLOCK_SIZE
                output.seek(offset)
                if output.read(BLOCK_SIZE) != fetch_block(port, offset):
                    raise ValueError("Existing image tail does not match flash; refusing to resume")
            for offset in range(start, FLASH_SIZE, BLOCK_SIZE):
                block = fetch_block(port, offset)
                output.seek(offset)
                if args.verify:
                    if output.read(BLOCK_SIZE) != block:
                        raise ValueError(f"Verification mismatch at flash 0x{offset:06X}")
                else:
                    output.write(block)
                    output.flush()
                if (offset // BLOCK_SIZE + 1) % 64 == 0:
                    print(f"{('Verified' if args.verify else 'Saved')}: {(offset + BLOCK_SIZE) // 1048576:.2f} / 16 MiB", flush=True)

    with args.output.open("rb") as f:
        sha = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    print(f"{'Verified' if args.verify else 'Backup complete'}: {args.output}")
    print(f"SHA-256: {sha.hexdigest()}")


if __name__ == "__main__":
    main()