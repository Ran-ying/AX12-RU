/* AX12 RU v1 RTL8197F: read full 16 MiB SPI NOR via stock Flash ioctl.
 *
 * 1.1.22 nvrammanager read_flash() uses ioctl 0x4001B301 with:
 *   struct { u32 flash_offset; void *buf; u32 length; void *buf_copy; u32 mode; }
 * The kernel handler routes to the SPI read function. This executable never
 * calls 0x8001B302 (Flash write), mtd writes, upgrade, erase, or reboot.
 *
 * Compile (MIPS32 little-endian, Linux o32 ABI):
 *   mips-linux-gnu-as -EL -32 -o ax12_flash_read.o ax12_flash_read.S
 *   mips-linux-gnu-ld -EL -m elf32ltsmip -static -e _start \
 *       -o ax12_flash_read ax12_flash_read.o
 *
 * Run on router: /tmp/ax12_flash_read > /tmp/DO_NOT_STORE_16M_ON_ROUTER
 * Instead stream SSH stdout directly to a LOCAL Mac file:
 *   ssh -T ax12 /tmp/ax12_flash_read > ~/Desktop/ax12-full-flash.bin
 * Check exact 16777216-byte result and SHA-256. stdout is raw binary only.
 */

    .set noreorder
    .set mips32
    .text
    .globl _start
_start:
    la      $a0, device_path
    move    $a1, $zero
    li      $v0, 4005            # Linux MIPS o32 open(path, O_RDONLY)
    syscall
    bnez    $a3, failed
    nop

    move    $s0, $v0            # device fd
    la      $s1, io_buffer
    la      $s2, flash_request
    sw      $s1, 4($s2)         # pointer supplied twice by stock nvrammanager
    sw      $s1, 12($s2)
    li      $s6, 0x10000
    sw      $s6, 8($s2)         # 64 KiB request per iteration
    sw      $zero, 16($s2)
    move    $s3, $zero          # start Flash offset = 0
    li      $s4, 0x1000000      # 16 MiB in total

read_sector:
    sw      $s3, 0($s2)
    move    $a0, $s0
    li      $a1, 0x4001B301    # stock READ ioctl only
    move    $a2, $s2
    li      $v0, 4054           # Linux MIPS o32 ioctl syscall
    syscall
    bnez    $a3, failed
    nop
    bnez    $v0, failed         # read ioctl returns zero on success
    nop

    move    $s5, $zero
write_stdout:
    li      $a0, 1              # stdout (SSH binary stream to Mac)
    addu    $a1, $s1, $s5
    subu    $a2, $s6, $s5
    li      $v0, 4004           # write(1,buf,len): NOT a Flash write
    syscall
    bnez    $a3, failed
    nop
    blez    $v0, failed
    nop
    addu    $s5, $s5, $v0
    bne     $s5, $s6, write_stdout
    nop

    addu    $s3, $s3, $s6
    bne     $s3, $s4, read_sector
    nop

    move    $a0, $s0
    li      $v0, 4006           # close Flash read fd
    syscall
    li      $a0, 0
    li      $v0, 4001           # exit(0)
    syscall

failed:
    li      $a0, 2              # stderr, never mix error with dump bytes
    la      $a1, failure_message
    li      $a2, failure_length
    li      $v0, 4004
    syscall
    li      $a0, 1
    li      $v0, 4001           # exit nonzero (incomplete file rejected)
    syscall

    .data
device_path:
    .asciiz "/dev/flash_chrdev"
failure_message:
    .ascii "Flash read failed; reject partial backup.\n"
    .equ failure_length, . - failure_message

    .bss
    .align 4
flash_request:
    .space 20
    .align 4
io_buffer:
    .space 65536
