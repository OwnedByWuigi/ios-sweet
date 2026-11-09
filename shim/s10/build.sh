#!/bin/sh
set -eu
cd "$(dirname "$0")"
CC=${CC:-aarch64-linux-gnu-gcc}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
READELF=${READELF:-aarch64-linux-gnu-readelf}
NM=${NM:-aarch64-linux-gnu-nm}
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra -DS10"
mkdir -p out
for f in start.S main.c console.c ../fdt.c ../loader.c; do
	obj=$(basename "${f%.*}")
	$CC $CFLAGS -c "$f" -o "out/$obj.o"
done
abs=$($READELF -r out/main.o out/console.o out/fdt.o out/loader.o | awk '/R_AARCH64_ABS64/ {n++} END {print n+0}')
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T ../shim.ld -Wl,--build-id=none -Wl,-N \
	out/start.o out/main.o out/console.o out/fdt.o out/loader.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image
end=$($NM out/shim.elf | awk '$3=="_end" {print $1}')
python3 - "$end" out/Image <<'PY'
import pathlib, struct, sys
size = int(sys.argv[1], 16)
path = pathlib.Path(sys.argv[2])
image = bytearray(path.read_bytes())
if image[56:60] != b"ARM\x64":
    raise SystemExit("linked image is missing the arm64 Image magic")
struct.pack_into("<Q", image, 16, size)
if len(image) < size:
    image.extend(bytes(size - len(image)))
path.write_bytes(image)
print(f"S10 shim Image: {len(image)} bytes, image_size={size:#x}")
PY
