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
compile target for the Exynos 9820 CPU complex. It retains XNU as the kernel and
does not import or build the Linux/Android kernel. The Linux device tree and
drivers are hardware references only. This config does not yet implement
Samsung's boot protocol, interrupt routing, memory discovery, storage, or
display, and no S10 kernel has been booted.

Once the patch can be built in the pinned XNU 8796 workflow, use the `S10`
machine config for compile diagnostics. A successful build will not by itself
make the kernel safe to boot; board handoff and the early platform drivers must
be completed and checked against a real S10 firmware/device tree first.
