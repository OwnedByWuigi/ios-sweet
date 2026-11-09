#!/usr/bin/env python3
"""Pack the S10 XNU shim and XNU payload into Samsung's Android boot v1 image.

The Samsung AP boot image has no embedded DTB. ABL supplies the merged DT
from its separate DT/DTBO partitions in x0 and the raw payload as the initrd
range in /chosen. This tool writes only a local boot.img; it does not flash.
"""
import argparse
import struct
import sys
from pathlib import Path


PAGE_SIZE = 2048
HEADER_SIZE = 1648
KERNEL_ADDR = 0x10008000
RAMDISK_ADDR = 0x11000000
TAGS_ADDR = 0x10000100
OS_VERSION = 0x18000173
CMDLINE = "androidboot.selinux=permissive androidboot.selinux=permissive loop.max_part=7"


def align(value, boundary):
    return (value + boundary - 1) & ~(boundary - 1)


def build(kernel, payload):
    if len(kernel) < 64 or kernel[56:60] != b"ARM\x64":
        raise ValueError("kernel is not a Linux arm64 Image")
    image_size, = struct.unpack_from("<Q", kernel, 16)
    if not image_size or image_size > len(kernel):
        raise ValueError("Image header image_size exceeds the kernel file")
    if len(payload) < 0x2A8 or payload[:8] != b"SWEETXNU":
        raise ValueError("initrd must be a tools/mkpayload.py XNU payload")

    header = bytearray(HEADER_SIZE)
    header[:8] = b"ANDROID!"
    struct.pack_into("<10I", header, 8,
                     len(kernel), KERNEL_ADDR,
                     len(payload), RAMDISK_ADDR,
                     0, 0, TAGS_ADDR,
                     PAGE_SIZE, 1, OS_VERSION)
    header[48:64] = b"BEYOND1LTE-XNU".ljust(16, b"\0")
    header[64:64 + len(CMDLINE)] = CMDLINE.encode()
    struct.pack_into("<IQI", header, 1632, 0, 0, HEADER_SIZE)

    image = bytearray(header)
    image.extend(bytes(align(len(image), PAGE_SIZE) - len(image)))
    image.extend(kernel)
    image.extend(bytes(align(len(image), PAGE_SIZE) - len(image)))
    image.extend(payload)
    image.extend(bytes(align(len(image), PAGE_SIZE) - len(image)))
    return bytes(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, help="shim/s10/out/Image")
    parser.add_argument("payload", type=Path, help="tools/mkpayload.py output")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    image = build(args.kernel.read_bytes(), args.payload.read_bytes())
    args.output.write_bytes(image)
    print(f"{args.output}: {len(image)} bytes; Android boot header v1, "
          f"kernel={KERNEL_ADDR:#x}, initrd={RAMDISK_ADDR:#x}, page={PAGE_SIZE}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error) as exc:
        print(f"mks10boot: {exc}", file=sys.stderr)
        sys.exit(2)
