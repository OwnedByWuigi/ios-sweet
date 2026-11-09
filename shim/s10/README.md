# Galaxy S10 Exynos shim

This is a separate shim path for the base SM-G973F Android boot v1 header. It
does not change the working Sweet shim. Its arm64 Linux `Image` header lets
Samsung ABL load the shim at the stock boot-image kernel address. The entry
accepts the flattened device tree in `x0`, switches EL2 to EL1 when necessary,
and passes the tree to the shared XNU payload loader. The loader expects
`/chosen/linux,initrd-start` and `linux,initrd-end` to point to a payload
created by `tools/mkpayload.py`.

Build with an AArch64 bare-metal compiler and linker. For example, with LLVM:

```sh
CC='clang --target=aarch64-none-elf --ld-path=/path/to/ld.lld' \
OBJCOPY=llvm-objcopy READELF=readelf NM=nm ./shim/s10/build.sh
```

After building an S10 XNU Mach-O and its one-CPU ADT, create the payload and
Android boot image:

```sh
python3 tools/mkpayload.py KERNEL.development.s10 /path/to/s10.adt /tmp/s10.payload \
  --cmdline 'debug=0xc cpus=1 keepsyms=1'
python3 tools/mks10boot.py shim/s10/out/Image /tmp/s10.payload /tmp/s10-boot.img
```

The packer uses the supplied stock header values: Android boot v1, 2 KiB page
size, kernel address `0x10008000`, ramdisk address `0x11000000`, and tags
address `0x10000100`. The output is a local image only. Header compatibility,
ABL's initrd/FDT handoff, the EL at shim entry, memory reservations, and the
selected live FDT have not been verified on a handset. Use no flash command
until those are checked and a recovery path is ready.
