.syntax unified
.arm
.global _start

.section .text
_start:
    ldr r0, =0xfee1dead
    ldr r1, =0x28121969
    ldr r2, =0xa1b2c3d4
    ldr r3, =mode

    mov r7, #88
    svc #0

    cmp r0, #0
    rsblt r0, r0, #0
    movge r0, #0

    mov r7, #1
    svc #0

.section .rodata
mode:
    .asciz "bootloader"
