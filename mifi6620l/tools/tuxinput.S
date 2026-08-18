/* SPDX-License-Identifier: MIT */
.syntax unified
.arm
.global _start

.equ SYS_EXIT,   1
.equ SYS_READ,   3
.equ SYS_WRITE,  4
.equ SYS_OPEN,   5

.equ EV_KEY,     1

.equ KEY_LEFT,   105
.equ KEY_RIGHT,  106
.equ KEY_SELECT, 353
.equ KEY_RESTART,408

.section .text

_start:
    /* fd = open("/dev/input/event1", O_RDONLY, 0) */
    ldr     r0, =eventdev
    mov     r1, #0
    mov     r2, #0
    mov     r7, #SYS_OPEN
    svc     #0

    cmp     r0, #0
    blt     fail

    mov     r4, r0              /* fd */

read_event:
    mov     r0, r4
    ldr     r1, =ev
    mov     r2, #16
    mov     r7, #SYS_READ
    svc     #0

    cmp     r0, #16
    bne     read_event

    /*
     * struct input_event on 32-bit ARM:
     *
     * +0  timeval.tv_sec
     * +4  timeval.tv_usec
     * +8  uint16_t type
     * +10 uint16_t code
     * +12 int32_t value
     */

    ldr     r5, =ev

    ldrh    r0, [r5, #8]        /* type */
    cmp     r0, #EV_KEY
    bne     read_event

    ldr     r0, [r5, #12]       /* value */

    /* Only report initial key presses. */
    cmp     r0, #1
    bne     read_event

    ldrh    r6, [r5, #10]       /* code */

    cmp     r6, #KEY_LEFT
    beq     print_left

    cmp     r6, #KEY_RIGHT
    beq     print_right

    ldr     r0, =KEY_SELECT
    cmp     r6, r0
    beq     print_select

    ldr     r0, =KEY_RESTART
    cmp     r6, r0
    beq     print_reset

    b       read_event


print_left:
    ldr     r1, =msg_left
    mov     r2, #5
    bl      print
    b       read_event

print_right:
    ldr     r1, =msg_right
    mov     r2, #6
    bl      print
    b       read_event

print_select:
    ldr     r1, =msg_select
    mov     r2, #7
    bl      print
    b       read_event

print_reset:
    ldr     r1, =msg_reset
    mov     r2, #14
    bl      print
    b       read_event


print:
    mov     r0, #1              /* stdout */
    mov     r7, #SYS_WRITE
    svc     #0
    bx      lr


fail:
    mov     r0, #1
    mov     r7, #SYS_EXIT
    svc     #0


.section .bss
.align 4
ev:
    .space 16


.section .rodata
eventdev:
    .asciz "/dev/input/event1"

msg_left:
    .ascii "LEFT\n"

msg_right:
    .ascii "RIGHT\n"

msg_select:
    .ascii "SELECT\n"

msg_reset:
    .ascii "RESET IGNORED\n"
