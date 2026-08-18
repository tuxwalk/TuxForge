.syntax unified
.arm
.global _start

.section .text
_start:
    ldr r0, =devfb
    mov r1, #2
    mov r2, #0
    mov r7, #5
    svc #0

    cmp r0, #0
    blt fail

    mov r4, r0

    mov r0, r4
    movw r1, #0x9999
    ldr r2, =rect
    mov r7, #54
    svc #0

    cmp r0, #0
    blt fail

    mov r0, #0
    mov r7, #1
    svc #0

fail:
    mov r0, #1
    mov r7, #1
    svc #0

.section .data
.align 4
rect:
    .word 0
    .word 0
    .word 220
    .word 176

devfb:
    .asciz "/dev/fb0"
