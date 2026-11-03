#!/usr/bin/env python3
"""Offline WAN-port board-layout patch for the AX12 RU 1.5.0/1.5.1 kernel.

Makes the unsupported default-layout BNE fall through to the existing WAN=port1
layout. Does not write Flash or communicate with a router. Restricted to the
verified exact patch instruction and Realtek cr6c/cs6c kernel format.
"""
import argparse
import lzma
import struct
from pathlib import Path

LZMA_OFFSET = 0x2818
INSTRUCTION_OFFSET = 0x80BE5548 - 0x80000000
EXPECTED_BNE = 0x14450023


def patch(kernel):
    if kernel[:4] not in (b"cr6c", b"cs6c"):
        raise ValueError("Expected AX12 Realtek kernel wrapper")
    if int.from_bytes(kernel[12:16], "big") + 17 != len(kernel):
        raise ValueError("Unexpected kernel wrapper length")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    original = decoder.decompress(kernel[LZMA_OFFSET:])
    if not decoder.eof:
        raise ValueError("Incomplete kernel LZMA stream")
    stream_length = len(kernel) - LZMA_OFFSET - len(decoder.unused_data)
    current = struct.unpack_from("<I", original, INSTRUCTION_OFFSET)[0]
    if current != EXPECTED_BNE:
        raise ValueError(f"Refusing unexpected patch-site instruction {current:#x}")

    updated = bytearray(original)
    struct.pack_into("<I", updated, INSTRUCTION_OFFSET, 0)
    compressed = bytearray(lzma.compress(updated, format=lzma.FORMAT_ALONE, preset=6))
    struct.pack_into("<Q", compressed, 5, len(updated))
    if len(compressed) > stream_length:
        raise ValueError("Compressed kernel would overflow original wrapper")

    output = bytearray(kernel)
    output[LZMA_OFFSET:LZMA_OFFSET + stream_length] = compressed.ljust(stream_length, b"\0")
    output[-3:-1] = b"\0\0"
    body = output[16:-1]
    checksum = -sum(int.from_bytes(body[i:i+2], "big") for i in range(0, len(body), 2)) & 0xffff
    output[-3:-1] = checksum.to_bytes(2, "big")

    check = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    if check.decompress(output[LZMA_OFFSET:]) != updated or not check.eof:
        raise ValueError("Kernel decompression roundtrip differs")
    if sum(int.from_bytes(output[16+i:18+i], "big") for i in range(0,len(output)-17,2)) & 0xffff:
        raise ValueError("Realtek kernel checksum mismatch")
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = patch(args.input.read_bytes())
    args.output.write_bytes(result)
    print("PASS: WAN-port board-layout BNE -> NOP, LZMA roundtrip, Realtek checksum")
    print("Output:", args.output)
    print("This is a kernel partition experiment, NOT a flashable Cloud firmware")


if __name__ == "__main__":
    main()
