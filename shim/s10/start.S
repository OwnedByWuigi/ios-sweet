/*
 * Samsung S10 Exynos entry: a Linux arm64 Image header for Samsung's ABL,
 * followed by a tiny EL2-to-EL1 transition and the shared XNU payload loader.
 * ABL supplies the merged device tree in x0, as required by the arm64 boot
 * protocol. The stock AP boot image uses page_size=2048 and kernel_addr
 * 0x10008000; tools/mks10boot.py writes the matching Android boot v1 header.
 */
	.section .text.head, "ax"
	.globl _head
_head:
	b	_start
	.long	0
	.quad	0			/* text_offset: entry is at image start */
	.quad	_end			/* image_size, finalized by build.sh */
	.quad	0xa			/* little-endian, 4K granule, relocatable */
	.quad	0
	.quad	0
	.quad	0
	.ascii	"ARM\x64"
	.long	0

	.text
	.globl _start
_start:
	msr	daifset, #0xf
	mov	x20, x0			/* preserve ABL's FDT pointer */
	mrs	x9, CurrentEL
	cmp	x9, #0x8		/* EL2 */
	b.ne	1f
	msr	spsel, #1
	adr	x10, _stack_top
	mov	sp, x10			/* temporary EL2 stack */
	msr	sp_el1, x10
	mov	x10, #0x80000000	/* EL1 is AArch64; no IRQ/FIQ routing */
	msr	hcr_el2, x10
	mov	x10, #3			/* permit EL1 physical/virtual timer access */
	msr	cnthctl_el2, x10
	msr	cntvoff_el2, xzr
	msr	cptr_el2, xzr
	adr	x10, 2f
	msr	elr_el2, x10
	mov	x10, #0x3c5		/* EL1h with DAIF masked */
	msr	spsr_el2, x10
	isb
	eret
1:
	cmp	x9, #0x4		/* EL1 */
	b.ne	.bad_el
2:
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	adr	x1, _bss_start
	adr	x2, _bss_end
3:
	cmp	x1, x2
	b.hs	4f
	str	xzr, [x1], #8
	b	3b
4:
	mov	x0, x20
	bl	shim_main
5:	wfe
	b	5b
.bad_el:
	wfe
	b	.bad_el

	/* Keep the same vector table layout as the Sweet shim. */
.macro vent slot
	.balign	0x80
	stp	x29, x30, [sp, #-16]!
	mov	x29, #\slot
	b	exc_common
.endm
	.balign	0x800
	.globl vectors
vectors:
	vent 0
	vent 1
	vent 2
	vent 3
	vent 4
	vent 5
	vent 6
	vent 7
	vent 8
	vent 9
	vent 10
	vent 11
	vent 12
	vent 13
	vent 14
	vent 15

exc_common:
	sub	sp, sp, #(30 * 8)
	stp	x0, x1, [sp, #0]
	stp	x2, x3, [sp, #16]
	stp	x4, x5, [sp, #32]
	stp	x6, x7, [sp, #48]
	stp	x8, x9, [sp, #64]
	stp	x10, x11, [sp, #80]
	stp	x12, x13, [sp, #96]
	stp	x14, x15, [sp, #112]
	stp	x16, x17, [sp, #128]
	stp	x18, x19, [sp, #144]
	stp	x20, x21, [sp, #160]
	stp	x22, x23, [sp, #176]
	stp	x24, x25, [sp, #192]
	stp	x26, x27, [sp, #208]
	str	x28, [sp, #224]
	mov	x0, x29
	mov	x1, sp
	bl	s10_exception
	ldp	x0, x1, [sp, #0]
	ldp	x2, x3, [sp, #16]
	ldp	x4, x5, [sp, #32]
	ldp	x6, x7, [sp, #48]
	ldp	x8, x9, [sp, #64]
	ldp	x10, x11, [sp, #80]
	ldp	x12, x13, [sp, #96]
	ldp	x14, x15, [sp, #112]
	ldp	x16, x17, [sp, #128]
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldr	x28, [sp, #224]
	add	sp, sp, #(30 * 8)
	ldp	x29, x30, [sp], #16
	eret
