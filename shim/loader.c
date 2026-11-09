/*
 * Milestone 4: act as iBoot for xnu.
 *
 * mkpayload.py already resolved the kernel's chained fixups and built the
 * ADT, so this only has to: find the payload in the ABL ramdisk, copy the
 * segments to phys_base + (vmaddr - virt_base), place the ADT and
 * boot_args behind the kernel, and jump to the entry point with the MMU
 * and caches off, x0 = boot_args (physical).
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_16K		0x4000UL

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[BOOT_LINE_LENGTH];
	struct payload_seg segs[];
};

/* pexpert/pexpert/arm64/boot.h, Revision/Version 2 */
struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[BOOT_LINE_LENGTH];
	uint64_t bootFlags, memSizeActual;
};

_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, Video) == 40, "boot_args layout");
_Static_assert(__builtin_offsetof(struct boot_args, CommandLine) == 108, "boot_args layout");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args layout");

/* MMU off: everything is Device memory, so copy in aligned 8-byte words. */
static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

static int magic_ok(const char *m)
{
	static const char want[] = "SWEETXNU";
	for (int i = 0; i < 8; i++)
		if (m[i] != want[i])
			return 0;
	return 1;
}

static int add_u64(uint64_t a, uint64_t b, uint64_t *out)
{
	if (a > UINT64_MAX - b)
		return 0;
	*out = a + b;
	return 1;
}

typedef void (*xnu_entry_t)(uint64_t boot_args_pa);

const char *loader_boot(uintptr_t dtb)
{
	uint64_t rd_start, rd_end;

	if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
	    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
		return "no initrd in /chosen";
	if (rd_start >= rd_end || rd_end - rd_start < sizeof(struct payload))
		return "invalid initrd bounds";
	con_hex2("INITRD", "lo=", rd_start, "hi=", rd_end);

	const struct payload *p = (const struct payload *)rd_start;
	if (!magic_ok(p->magic))
		return "no SWEETXNU payload";
	uint64_t payload_size = rd_end - rd_start;
	if (p->version != 1 || p->nsegs == 0 || p->nsegs > 64 ||
	    (p->adt_off & 7) || (rd_start & 7))
		return "bad payload header";
	uint64_t table_size = (uint64_t)p->nsegs * sizeof(struct payload_seg);
	if (sizeof(struct payload) + table_size > payload_size ||
	    p->adt_off > payload_size || p->adt_size > payload_size - p->adt_off ||
	    p->adt_size > UINT32_MAX)
		return "payload bounds are invalid";

	uint64_t pa_of_va_base = p->phys_base - p->virt_base;	/* pa = va + this */
	uint64_t kernel_pa_end;
	if (!p->mem_size || !add_u64(p->phys_base, p->mem_size, &kernel_pa_end))
		return "invalid XNU physical memory range";
	con_hex2("PHYS", "base=", p->phys_base, "size=", p->mem_size);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	/* The payload must not overlap where the kernel goes. */
	if (rd_end > p->phys_base && rd_start < kernel_pa_end)
		return "ramdisk overlaps kernel memory";

	int entry_in_segment = 0;
	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uint64_t copy_size, dst, dst_end;
		if (s->file_size > UINT64_MAX - 7)
			return "kernel segment size overflow";
		copy_size = (s->file_size + 7) & ~7ULL;
		if (s->file_off > payload_size || copy_size > payload_size - s->file_off ||
		    s->vmsize < s->file_size ||
		    !add_u64(s->vmaddr, pa_of_va_base, &dst) ||
		    !add_u64(dst, s->vmsize, &dst_end) ||
		    dst < p->phys_base || dst_end > kernel_pa_end)
			return "kernel segment outside payload/RAM";
		if (p->entry_va >= s->vmaddr && p->entry_va - s->vmaddr < s->vmsize)
			entry_in_segment = 1;
		copy64(dst, rd_start + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}
	if (!entry_in_segment)
		return "XNU entry is outside kernel segments";
	con_hex2("SEGS", "n=", p->nsegs, "end=", p->kernel_end + pa_of_va_base);

	/* ADT, then boot_args, behind the kernel; everything below topOfKernelData is ours. */
	uint64_t adt_pa, ba_pa, top;
	if (!add_u64(p->kernel_end, pa_of_va_base, &adt_pa) ||
	    adt_pa < p->phys_base || adt_pa > kernel_pa_end ||
	    p->adt_size > kernel_pa_end - adt_pa ||
	    !add_u64(adt_pa, p->adt_size, &ba_pa) ||
	    !add_u64(ba_pa, PAGE_16K - 1, &ba_pa))
		return "ADT outside kernel RAM";
	ba_pa &= ~(PAGE_16K - 1);
	if (!add_u64(ba_pa, PAGE_16K, &top) || top > kernel_pa_end)
		return "boot_args outside kernel RAM";
	copy64(adt_pa, rd_start + p->adt_off, p->adt_size);

	zero64(ba_pa, PAGE_16K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = p->phys_base;
	ba->memSize = p->mem_size;
	ba->topOfKernelData = top;
#if defined(S10)
	/* The live Samsung handoff has not yet yielded a framebuffer description. */
	ba->Video.v_baseAddr = 0;
	ba->Video.v_display = 0;
	ba->Video.v_rowBytes = 0;
	ba->Video.v_width = 0;
	ba->Video.v_height = 0;
	ba->Video.v_depth = 0;
#else
	ba->Video.v_baseAddr = FB_BASE;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = FB_STRIDE;
	ba->Video.v_width = FB_W;
	ba->Video.v_height = FB_H;
	ba->Video.v_depth = 32;
#endif
	ba->deviceTreeP = adt_pa - pa_of_va_base;	/* xnu reads it with the MMU on: a VA */
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = p->mem_size;
	con_hex2("BOOTARG", "pa=", ba_pa, "top=", top);

	uint64_t entry_pa;
	if (!add_u64(p->entry_va, pa_of_va_base, &entry_pa) ||
	    entry_pa < p->phys_base || entry_pa >= kernel_pa_end)
		return "XNU entry outside physical memory";
	con_hex("JUMP", entry_pa);
	con_str("XNU", "jumping (fbcon clears screen)");

	/* Everything was written with the MMU and caches off; drop any stale I-cache lines too. */
	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}
