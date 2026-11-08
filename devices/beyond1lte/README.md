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

**Initial XNU machine-config, device-tree platform-expert, and single-core CPU
bring-up patches only. No S10 kernel has been built or booted.**
The working implementation in this repository is specific to the Qualcomm
SM7150 Redmi Note 10 Pro (`sweet`). Its memory map, GIC addresses, UFS
controller, framebuffer, touch, keys, power management, and bootloader handoff
must not be reused for Exynos 9820.

| Area | State | Work required |
| --- | --- | --- |
| XNU build target | `xnu/patches/0082-s10-machine-config.patch` adds `MACHINE_CONFIG=S10` | Build against the pinned XNU 8796 source; then add S10 interrupt and memory support |
| XNU platform expert | `xnu/patches/0083-s10-platform-expert.patch` matches the Exynos 9820 root and publishes DT CPU/device nubs | Confirm the root compatible and ADT CPU shape from the target firmware |
| XNU boot CPU | `xnu/patches/0084-s10-single-cpu-bringup.patch` registers the boot processor when the ADT exposes only one CPU | Verify the XNU CPU topology fields against an S10-derived ADT; add PSCI secondary startup and interrupt signaling |
| iOS 16.7.16 root image | Reusable build flow, device identity requires review | Decide whether to retain the iPhone X product identity used by sweet; verify iOS display class and `/product` ADT data |
| Samsung boot path | Unknown for this project | Establish unlockable bootloader/recovery path and the exact image/container format for the target firmware; document a reversible boot method before writing anything |
| Shim handoff | Not implemented | Obtain a target stock boot/recovery image and live or stock DTB; adapt entry, DTB, initrd, command-line, and framebuffer discovery to Samsung's handoff |
| Exynos XNU platform | Not implemented | Add S5E9820 machine support and establish RAM/reserved regions, exception levels, GIC/timer, PSCI, cache coherency, and secondary CPU startup from the live DTB and published kernel sources |
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
   and storage-backed XNU root in independently reviewable stages. Do not
   overwrite Android userdata until the full target-specific boot flow and
   recovery procedure are verified.
6. Reuse the iPhone X 20H392 root-image workflow only after resolving the
   identity, display scaling, activation, and missing SEP/baseband service
   behavior for this non-Apple hardware.

## First required artifacts

The next engineering step depends on a real SM-G973F/N's stock firmware and
device tree. Required, kept locally and out of git:

- Exact model (`SM-G973F` or `SM-G973N`), bootloader revision, and firmware
  build identifier.
- Stock AP package, or at minimum the stock boot and recovery images plus the
  extracted DTB/DTBO and partition table.
- A complete backup and a confirmed recovery route (Samsung Download Mode and
  the applicable restore tooling).
- If available, a serial/debug log from a harmless stock or custom-recovery
  boot that exposes the kernel handoff and framebuffer state.

Until these exist, numerical MMIO values, memory carve-outs, panel timing,
touch controller identity, and a safe boot command are intentionally left
unspecified. The sweet target's `fastboot boot` flow is not evidence that this
Samsung device accepts the same flow.
