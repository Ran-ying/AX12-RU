"""1.5.2: Realtek RTL8197F WAN physical port 1 VLAN board-layout fix."""
import hashlib
from patch_wan_port1 import patch

KNOWN_TESTED_KERNEL = '773b66e574a11b4cf6ce8962f83541272df69a0e0cc0084571a104ed5b2400f8'


def apply(kernel):
    if kernel[:4] != b'cs6c':
        raise ValueError('1.5.2 requires the 1.5.0 cs6c boot-format bridge')
    updated = patch(kernel)
    if hashlib.sha256(updated).hexdigest() != KNOWN_TESTED_KERNEL:
        raise ValueError('Result differs from 1.5.2 hardware-tested kernel')
    print('APPLIED 1.5.2: WAN=port1, byte-exact tested kernel')
    return updated
