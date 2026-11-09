# iOS 16.7.16 target: Galaxy S10 Exynos

## Scope

This directory tracks a new XNU and iOS userland bring-up target based on
[`ios-sweet`](https://github.com/dipa-studio/ios-sweet). The intended first
device is the base Galaxy S10 Exynos model:

| Property | Target |
| --- | --- |
| Samsung model | SM-G973F (international) or SM-G973N (Korea) |
| Device tree codename | `beyond1lte` / `beyond1lteks` |
| SoC | Samsung Exynos 9820 (S5E9820) |
| CPU topology | 8 cores: Exynos M4, Cortex-A75, Cortex-A55 |
| Display | 6.1-inch Dynamic AMOLED, 1440 × 3040 native |
| iOS userland | iPhone X, iOS 16.7.16 (20H392), inherited from ios-sweet |

The `beyond1lte` identity and specifications are cross-checked against the
[LineageOS device record](https://lineageos.github.io/lineage_wiki/devices/beyond1lte/)
and the [Samsung Exynos 9820 device tree inventory](https://github.com/ExtremeXT/android_device_samsung_exynos9820).
This excludes S10+ (`beyond2lte`), S10e (`beyond0lte`), S10 5G (`beyondx`), and
Snapdragon models. Other regional variants must be confirmed from their model
number and live device tree before they are included.

## Status

**XNU bring-up remains at source/patch stage; no S10 kernel has been built or
booted.** User-supplied SM-G973F firmware now grounds the CPU, PSCI, timer,
GIC-compatible register layout, UFS, and display findings below. Its DT is the
pre-bootloader base tree, not the final live tree passed to a kernel.
The working implementation in this repository is specific to the Qualcomm
SM7150 Redmi Note 10 Pro (`sweet`). Its memory map, GIC addresses, UFS
controller, framebuffer, touch, keys, power management, and bootloader handoff
must not be reused for Exynos 9820.

| Area | State | Work required |
| --- | --- | --- |
| XNU build target | `xnu/patches/0082-s10-machine-config.patch` adds `MACHINE_CONFIG=S10`, 8 CPUs across 2 MPIDR affinity clusters and plain arm64 | Build against pinned XNU 8796; convert stock FDT topology to the Apple Device Tree shape XNU consumes |
| XNU platform expert | `xnu/patches/0083-s10-platform-expert.patch` matches `samsung,exynos9820` and publishes CPU/device nubs | Verify the converted ADT on the target boot handoff |
| XNU boot CPU | `xnu/patches/0084-s10-single-cpu-bringup.patch` registers the boot processor when the ADT exposes only one CPU | Verify the XNU CPU topology fields against an S10-derived ADT; add PSCI secondary startup and interrupt signaling |
| XNU GIC/timer | `xnu/patches/0085-s10-gicv2-timer.patch` uses the stock DT's memory-mapped GICD/GICC interface and virtual timer PPI 27 | Confirm NS EL1 GIC access and timer delivery on hardware; SMP/IPI support is not implemented |
| iOS 16.7.16 root image | Reusable build flow, device identity requires review | Decide whether to retain the iPhone X product identity used by sweet; verify iOS display class and `/product` ADT data |
| Samsung boot path | Local Android boot v1 packer matches the supplied boot header | Verify bootloader acceptance and the ABL-provided live FDT/initrd on hardware; do not flash |
| Shim handoff | Separate arm64 Linux-Image shim and shared XNU payload loader compile locally; minimal FDT-to-ADT converter exists | Validate EL2/EL1 entry, chosen initrd handoff, final RAM map and framebuffer behavior on the exact handset |
| Exynos XNU platform | Partial: machine config, platform expert, one-CPU service, and initial GICD/GICC timer path | Establish live RAM/reserved map, exception level, GIC security state, PSCI behavior, cache coherency, and secondary CPU startup from the final handoff tree |
| Storage/root | Not implemented | Identify Exynos UFS controller and partition layout; add a read-only probe first, then an independent root device driver |
| Display/input | Not implemented | Identify panel/DSI mode, boot framebuffer handoff, touch controller/bus, key path, regulator requirements; bring up framebuffer before interactive HID |
| iOS services | Not evaluated | Add only after the kernel can reliably boot and mount a test root; hardware-specific IOKit services will be needed |

## Bring-up sequence

1. Confirm the physical device is SM-G973F or SM-G973N, record firmware/build
   identifiers, and obtain a complete off-device backup of user data and
   device-specific partitions. Keep dumps, serial numbers, calibration data,
   and proprietary firmware out of git.
2. Inspect the stock firmware and published
   [Exynos 9820 Linux kernel source](https://github.com/LineageOS/android_kernel_samsung_exynos9820)
   only as a hardware reference for boot-chain facts, board DTB, memory map,
   and peripheral identification. Do not build, modify, or boot that Linux
   kernel as the port. Treat community device trees as leads; verify addresses
   and panel/touch details against the actual target's DTB and XNU requirements.
3. Add an isolated `beyond1lte` shim/platform configuration. Do not alter
   `tools/mkadt.py` sweet defaults or `shim/build.sh` defaults to make an S10
   image. Derive every MMIO address and reserved range from target artifacts.
4. Bring up diagnostics and a safe early kernel path: entry/handoff, exception
   vectors, timer, GIC, memory allocator, and a persistent log. Confirm restart
   and recovery access before testing storage writes.
5. Add read-only UFS discovery, then framebuffer presentation, touch, buttons,
   and storage-backed XNU root in independently reviewable stages. The user
   approved using the existing `userdata` partition for the iOS root without
   GPT changes and allows Android to be deleted. Preserve bootloader, recovery,
   modem, persist, and backups; confirm each destructive operation before
   executing it.
6. Reuse the iPhone X 20H392 root-image workflow only after resolving the
   identity, display scaling, activation, and missing SEP/baseband service
   behavior for this non-Apple hardware.

## First required artifacts

Remaining boot bring-up depends on a real SM-G973F/N and its final live device
tree. Required, kept locally and out of git:

- Exact model (`SM-G973F` or `SM-G973N`), bootloader revision, and firmware
  build identifier.
- A matching stock AP/BL/CP/CSC firmware set; the current archives mix three
  firmware build IDs and must not be treated as a coherent release.
- A complete backup and a confirmed recovery route (Samsung Download Mode and
  the applicable restore tooling).
- If available, a serial/debug log from a harmless stock or custom-recovery
  boot that exposes the kernel handoff and framebuffer state.

The sweet target's `fastboot boot` flow is not evidence that this Samsung
device accepts the same flow. Supplied stock-DT MMIO values below are
firmware-derived; final RAM carve-outs, panel timing details, touch behavior,
and a safe boot method still require the live handoff/device.

## Supplied SM-G973F firmware evidence (2026-11-08)

The AP and BL archives identify `G973FXXSGHWC1`; supplied CP is
`G973FXXSGHWB3` and CSC is `G973FOXMGHWA3`, so the files are not one matching
firmware release set. They remain untracked inputs. Extracted images and
reports are under ignored `research/s10-firmware/`.

AP contains separate `boot.img.lz4`, `dt.img.lz4`, and `dtbo.img.lz4`. The
decompressed boot header is Android v1, with a 45,049,868-byte kernel and no
ramdisk or embedded DTB. The base DT (`samsung,exynos9820`) lists eight CPU
MPIDRs `0..5` and `0x100..0x101` in two Aff1 MPIDR clusters and three CPU
compatible/core types; PSCI method is
`smc`. Its timer node declares 26 MHz and the virtual timer as PPI 11, INTID
27. The interrupt-controller binding is `arm,cortex-a15-gic` /
`arm,cortex-a9-gic` with four MMIO regions. The first two are GICD
`0x10101000` and GICC `0x10102000`, each 4 KiB. This replaces the former
GICv3 system-register assumption. XNU now has a memory-mapped GIC path for
the one-CPU bring-up, not yet built or run on an S10.

`tools/mkadt-s10.py` converts a merged FDT into the minimal one-CPU Apple
Device Tree for initial bring-up when given an explicit XNU RAM window. A
sample conversion with overlay 20 and a high-memory window checked the parser
and serializer only; it is not established as safe for the handset because
the final live tree and Samsung bootloader fixups are not available.

The base tree describes UFS at `0x13d60000`, PHY at `0x13d64000`, and DSI at
`0x19080000`. Its three memory entries total 6 GiB and reserved-memory nodes
are incomplete; neither is the final boot memory map. The DTBO table contains
nine `BEYOND1LTE EUR OPEN` board variants (17–24 and 26). Variant 20 was
applied for analysis, but the phone's actual overlay selection is unknown.
Samsung bootloader fixups and the live final DT are still required for exact
RAM, reserved ranges, chosen/bootargs, and the selected overlay.
