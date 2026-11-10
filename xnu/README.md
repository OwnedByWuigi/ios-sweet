# XNU targets

## `sweet`

Built on GitHub's macOS arm64 runners by `.github/workflows/xnu.yml`, using
[blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) (MIT) at a pinned commit.

- `MACOS_VERSION=13.5` -> xnu-8796 (same generation as iOS 16.6/16.7, the last iOS for iPhone 8).
- `patches/*.patch` are copied into the build script's patch dir and applied to the xnu tree with `git apply`.
- Output: `kernel.<config>.vmapple` (later: our own SWEET machine config) as a workflow artifact.

Fetch the latest build: `gh run download -R dipa-studio/ios-sweet -n xnu-kernel -D xnu/out`

## Galaxy S10 Exynos (`S10`)

`xnu/patches/0082-s10-machine-config.patch` adds an isolated XNU `MACHINE_CONFIG=S10`
compile target for the Exynos 9820 CPU complex. `0087-s10-master-config.patch`
adds the matching `MASTER.arm64.s10`, based on the working plain-arm64 Sweet
config and enabling XNU’s open-source ARM assembly and pmap implementations
(`nos_arm_asm`, `nos_arm_pmap`) instead of expecting Apple’s unavailable SoC KDK library. The Sweet process sampler is enabled only in the Sweet master config, and the
no-monitor stub also covers S10. Stock SM-G973F AP DT evidence
shows eight CPU nodes across two MPIDR Aff1 clusters and three compatible
core types. `0083-s10-platform-expert.patch`
adds an XNU `IODTPlatformExpert` for `samsung,exynos9820` and publishes the
device-tree CPU/device nubs. `0084-s10-single-cpu-bringup.patch` registers one
boot CPU from the ADT; secondary CPU startup and IPIs remain unimplemented.
`0088-s10-no-apple-cpu-override.patch` keeps the Exynos cluster-aware MPIDR
path while skipping Apple-only `CPU_OVRD` accesses.
`0085-s10-gicv2-timer.patch` adds a first memory-mapped GICD/GICC IRQ path
using the stock DT register regions and virtual timer PPI 27. The AP DT uses
the `arm,cortex-a15-gic` / `arm,cortex-a9-gic` binding; non-secure EL1 access
and timer delivery still need hardware verification. The port does not import
or build the Linux/Android kernel; Linux device trees and drivers are hardware
references only. A separate S10 arm64 shim now builds locally, and
`tools/mkadt-s10.py` converts a merged FDT to a minimal one-CPU ADT. Neither
has been tested on-device, and the sample DTB is pre-bootloader rather than
the live tree. Storage, display, input, the final memory map, and a bootable
XNU build remain unfinished. The first S10 Actions build selected the S10 target
but failed at link; its missing master config and skipped S10 registration hunks
are fixed in the current patch series. No S10 kernel has been built or booted.

Once the patch can be built in the pinned XNU 8796 workflow, use the `S10`
machine config for compile diagnostics. A successful build will not by itself
make the kernel safe to boot; board handoff and the early platform drivers must
be completed and checked against a real S10 firmware/device tree first.

The workflow now targets `macos-15` because GitHub retired the macOS 14 runner
images in November 2026. Patch `0086-xcode16-iig-compat.patch` backports the
kernel-only `IORPC.kernelContent` member expected by Xcode 16's IIG output.
