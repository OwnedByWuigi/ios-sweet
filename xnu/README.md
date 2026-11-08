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
compile target for the Exynos 9820 CPU complex. `0083-s10-platform-expert.patch`
adds an XNU `IODTPlatformExpert` for the Exynos root compatible and publishes
the device-tree CPU and device nubs. The port does not import or build the
Linux/Android kernel; Linux device trees and drivers are hardware references
only. Samsung's boot protocol, interrupt routing, memory discovery, CPU-start
service, storage, and display remain unimplemented, and no S10 kernel has been
booted.

Once the patch can be built in the pinned XNU 8796 workflow, use the `S10`
machine config for compile diagnostics. A successful build will not by itself
make the kernel safe to boot; board handoff and the early platform drivers must
be completed and checked against a real S10 firmware/device tree first.
