#!/usr/bin/env python3
"""Build AX12 owner firmware by applying versioned patches to official RU 1.5.0.

Example:
    python3 build.py --official inputs/AX12-RU-1.5.0.bin --version 1.5.3
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools/firmware'))
from build_from_official import main

if __name__ == '__main__':
    main()
