#include <stdint.h>
#include "../loader.h"

void shim_main(uint64_t fdt)
{
	(void)loader_boot((uintptr_t)fdt);
	for (;;)
		__asm__ volatile("wfe");
}

void s10_exception(uint64_t slot, uint64_t *registers)
{
	(void)slot;
	(void)registers;
	for (;;)
		__asm__ volatile("wfe");
}
