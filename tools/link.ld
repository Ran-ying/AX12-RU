ENTRY(_start)
SECTIONS {
    . = 0xA0800000;
    .text : { *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.comment*) *(.note*) *(.MIPS.abiflags) *(.reginfo) *(.pdr) *(.eh_frame*) }
}
