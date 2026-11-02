#!/bin/sh
set -eu
cd "$(dirname "$0")"
clang -target mipsel-linux-gnu -mips32 -mno-abicalls -fno-pic -c -x assembler receiver.S -o receiver.o
ld.lld -m elf32ltsmip -T link.ld -o receiver.elf receiver.o
llvm-objcopy -O binary --only-section=.text receiver.elf receiver.bin
python3 - <<'PY'
from pathlib import Path
p = Path('receiver.bin')
p.write_bytes(p.read_bytes().ljust((p.stat().st_size + 15) & ~15, b'\x00'))
print(f'Built {p} ({p.stat().st_size} bytes)')
PY
