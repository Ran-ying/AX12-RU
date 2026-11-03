#!/usr/bin/env python3
"""Validate the exact 1.1.22 QEMU -u Flash ioctl sequence for the cs6c trial.

This validates the intercepted USERLAND requests, not real-kernel SPI writes.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

WRITE = re.compile(
    r"^WRITE flash=(0x[0-9a-f]+) n=(0x[0-9a-f]+) mode=([01]) first=([0-9a-f]*)$")
FAIL = re.compile(r"^INJECT_FAIL flash=(0x[0-9a-f]+) n=(0x[0-9a-f]+) mode=([01])$")


def spans(base, length):
    return [(base + i, min(0x10000, length - i), 0)
            for i in range(0, length, 0x10000)]


def expected_writes():
    return (
        [(0xF42000, 2, 1)]
        + spans(0x40000, 0x393C13)
        + spans(0x400000, 0xAE4003)
        + [
            (0xF10000, 0x34D9, 0),
            (0xF40000, 0x540, 1),
            (0xF41000, 0x5A, 0),
            (0xF42000, 0xB, 0),
            (0xF43000, 0x42C, 0),
            (0xF47000, 0x1269, 0),
            (0xF50000, 0x3CC9, 0),
            (0xF60000, 0x34D9, 0),
            (0xFE0700, 0x100, 0),
            (0xFE0800, 0x2000, 0),
            (0xFE2800, 0x100, 0),
            (0xFE2900, 0x100, 0),
            (0xF42000, 2, 1),
        ]
    )


def inspect(trace, fail_at):
    writes, failures = [], []
    events = []
    for line in Path(trace).read_text().splitlines():
        match = WRITE.match(line)
        if match:
            address, length, mode = (int(match.group(i), 16) for i in (1, 2, 3))
            writes.append((address, length, mode, match.group(4)))
            events.append(("WRITE", address))
        match = FAIL.match(line)
        if match:
            address, length, mode = (int(match.group(i), 16) for i in (1, 2, 3))
            failures.append((address, length, mode))
            events.append(("INJECT_FAIL", address))

    expected = expected_writes()
    observed = [(a, n, mode) for a, n, mode, _ in writes]

    if fail_at is None:
        if failures or observed != expected or len(writes) != 247:
            raise ValueError("Trace is not the expected complete 247-write path")
    else:
        if observed != expected[:len(observed)] or \
                failures != [expected[len(observed)]] or \
                failures[0][0] != fail_at or events[-1][0] != "INJECT_FAIL":
            raise ValueError("Failure injection did not stop at expected write")

    if writes[0][3] != "0100":
        raise ValueError("Initial upgrade-in-progress flag missing")
    if len(writes) > 1 and writes[1][3][:8] != "63733663":
        raise ValueError("Not a cs6c kernel update")
    if fail_at is None and writes[-1][3] != "0101":
        raise ValueError("Final upgrade-complete flag missing")

    sectors = Counter()
    for address, length, mode, _ in writes:
        end = address + length + (8 if mode else 0)
        if address < 0x40000 or end > 0xFF0000:
            raise ValueError("Bootloader or ART was written")
        for sector in range(address // 0x10000, (end - 1) // 0x10000 + 1):
            sectors[sector * 0x10000] += 1

    print(f"PASS: {len(writes)} intercepted Flash writes, "
          f"{len(sectors)} distinct 64-KiB sectors")
    if fail_at is None:
        shared = {hex(s): count for s, count in sectors.items() if count > 1}
        if len(sectors) != 238 or shared != {"0xf40000": 7, "0xfe0000": 4}:
            raise ValueError(f"Unexpected repeated sectors: {shared}")
        print("PASS: full cs6c update; 0xF40000 x7, 0xFE0000 x4")
    else:
        print(f"PASS: injected failure at {fail_at:#x}; no subsequent Flash writes")
    print("PASS: no Bootloader or ART write request")
    print("LIMIT: GDB interception and a synthetic Flash backend, not a real chip")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--fail-at", type=lambda v: int(v, 0))
    args = p.parse_args()
    inspect(args.trace, args.fail_at)


if __name__ == "__main__":
    main()
