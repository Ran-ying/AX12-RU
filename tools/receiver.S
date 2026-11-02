/* AX12 RTL8197FH-VG UART0 RAM-only receiver V2.
 * Runs at 0xA0800000; payload goes to uncached RAM at 0xA4000000.
 * Does not access NOR flash or initialize UART hardware.
 * On successful transfer, wait for host command R then restore the
 * Bootloader caller registers and return to CmdCfn().
 * Assumes UART0 is already running at 115200 8N1.
 */
    .set noreorder
    .set noat
    .text
    .globl _start

    .macro READ32 reg
        jal recv_byte
        nop
        move \reg, $v0
        jal recv_byte
        nop
        sll $t1, $v0, 8
        or \reg, \reg, $t1
        jal recv_byte
        nop
        sll $t1, $v0, 16
        or \reg, \reg, $t1
        jal recv_byte
        nop
        sll $t1, $v0, 24
        or \reg, \reg, $t1
    .endm

_start:
    /* CmdCfn invokes us using a C function pointer. Preserve its stack
     * and MIPS callee-saved registers so jr $ra can return to the monitor.
     */
    addiu $sp, $sp, -48
    sw $s0, 0($sp)
    sw $s1, 4($sp)
    sw $s2, 8($sp)
    sw $s3, 12($sp)
    sw $s4, 16($sp)
    sw $s5, 20($sp)
    sw $s6, 24($sp)
    sw $s7, 28($sp)
    sw $s8, 32($sp)
    sw $ra, 36($sp)

    lui $s0, 0xB814
    ori $s0, $s0, 0x7014    /* UART LSR */
    lui $s1, 0xB814
    ori $s1, $s1, 0x7000    /* UART RBR/THR */
    lui $s2, 0xA400       /* fixed destination = physical RAM 64 MiB */
    li $s4, -1           /* running CRC32 state */
    move $s6, $zero      /* block sequence counter */

    li $v0, 2           /* binary ready marker */
    jal send_byte
    nop

    READ32 $t2            /* magic: ASCII AXV2 */
    li $t3, 0x32565841
    bne $t2, $t3, fatal
    nop
    READ32 $s3            /* byte count */
    beqz $s3, fatal
    nop
    li $t3, 0x00B00000  /* maximum 11 MiB, within physical RAM */
    sltu $t4, $t3, $s3
    bnez $t4, fatal
    nop
    READ32 $s5            /* expected full-file CRC32 */
    li $v0, 'H'
    jal send_byte
    nop

packet:
    READ32 $t2            /* block sequence number */
    READ32 $s7            /* block length: 1-256 */
    READ32 $t6            /* block CRC32 */

    bne $t2, $s6, fatal
    nop
    beqz $s7, fatal
    nop
    sltiu $t4, $s7, 257
    beqz $t4, fatal
    nop
    sltu $t4, $s3, $s7
    bnez $t4, fatal
    nop

    li $t8, -1           /* per-block CRC state */
    move $t9, $s4        /* candidate running CRC state */
    move $t7, $zero      /* byte index */

read_payload:
    jal recv_byte
    nop
    move $a1, $v0
    addu $t1, $s2, $t7
    sb $a1, 0($t1)

    move $a0, $t8
    jal crc32_byte
    nop
    move $t8, $v0
    move $a0, $t9
    jal crc32_byte
    nop
    move $t9, $v0

    addiu $t7, $t7, 1
    bne $t7, $s7, read_payload
    nop

    nor $t2, $t8, $zero
    bne $t2, $t6, resend
    nop

    move $s4, $t9
    addu $s2, $s2, $s7
    subu $s3, $s3, $s7
    addiu $s6, $s6, 1
    li $v0, 'K'
    jal send_byte
    nop
    bnez $s3, packet
    nop

    nor $t2, $s4, $zero
    bne $t2, $s5, fatal
    nop

    /* Verify the completed payload by reading uncached RAM again. */
    lui $t7, 0xA400
    li $t8, -1
verify_ram:
    lbu $a1, 0($t7)
    move $a0, $t8
    jal crc32_byte
    nop
    move $t8, $v0
    addiu $t7, $t7, 1
    bne $t7, $s2, verify_ram
    nop
    nor $t2, $t8, $zero
    bne $t2, $s5, fatal
    nop
    li $v0, 'D'
    jal send_byte
    nop

    /* A completed payload remains in RAM. Explicit R triggers return.
     * No flash writes and no arbitrary address jumps are possible.
     */
wait_return:
    jal recv_byte
    nop
    li $t2, 'R'
    bne $v0, $t2, wait_return
    nop
    li $v0, 'r'
    jal send_byte
    nop
    lw $ra, 36($sp)
    lw $s8, 32($sp)
    lw $s7, 28($sp)
    lw $s6, 24($sp)
    lw $s5, 20($sp)
    lw $s4, 16($sp)
    lw $s3, 12($sp)
    lw $s2, 8($sp)
    lw $s1, 4($sp)
    lw $s0, 0($sp)
    addiu $sp, $sp, 48
    jr $ra
    nop

halt:
    b halt
    nop

resend:
    li $v0, 'N'
    jal send_byte
    nop
    b packet
    nop

fatal:
    li $v0, 'E'
    jal send_byte
    nop
    b halt
    nop

/* Returns byte in v0, clobbers t0. */
recv_byte:
1:
    lbu $t0, 0($s0)
    andi $t0, $t0, 1     /* LSR DR */
    beqz $t0, 1b
    nop
    lbu $v0, 0($s1)
    jr $ra
    nop

/* Sends low byte of v0, clobbers t0. */
send_byte:
1:
    lbu $t0, 0($s0)
    andi $t0, $t0, 0x20  /* LSR THRE */
    beqz $t0, 1b
    nop
    sb $v0, 0($s1)
    jr $ra
    nop

/* CRC32/ISO-HDLC reflected update: a0 = current raw state, a1 = byte. */
crc32_byte:
    xor $v0, $a0, $a1
    li $t3, 8
    li $t4, 0xEDB88320
1:
    andi $t5, $v0, 1
    srl $v0, $v0, 1
    beqz $t5, 2f
    nop
    xor $v0, $v0, $t4
2:
    addiu $t3, $t3, -1
    bnez $t3, 1b
    nop
    jr $ra
    nop
