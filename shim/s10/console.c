/* The S10 framebuffer location is not present in the supplied base DT. */
#include <stdint.h>
#include "../console.h"

volatile uint32_t *con_fb;

void con_clear(uint32_t bg) { (void)bg; }
void con_skip(void) {}
void con_str(const char *label, const char *s) { (void)label; (void)s; }
void con_hex(const char *label, uint64_t value) { (void)label; (void)value; }
void con_hex2(const char *label, const char *a, uint32_t av,
              const char *b, uint32_t bv)
{
	(void)label; (void)a; (void)av; (void)b; (void)bv;
}
