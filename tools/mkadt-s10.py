#!/usr/bin/env python3
"""Convert a merged Exynos 9820 FDT to the minimal XNU Apple Device Tree.

Use the final Samsung bootloader FDT when available. The AP dt.img is only a
base tree; apply the board DTBO and bootloader fixups before converting it.
The selected XNU RAM window must be provided explicitly.
"""
import argparse
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402
import s10_fdt as fdt  # noqa: E402


def u32(*values):
    return struct.pack("<%dI" % len(values), *values)


def u64(*values):
    return struct.pack("<%dQ" % len(values), *values)


def cstr(value):
    return value.encode() + b"\0"


def adt_node(name, props=(), children=()):
    node = adt.Node()
    node.props = [("name", 0, cstr(name))]
    node.props.extend((key, 0, value) for key, value in props)
    node.children = list(children)
    return node


STRING_PROPS = {
    "compatible", "model", "device_type", "status", "enable-method", "method",
    "name", "label", "clock-names", "interrupt-names", "regulator-name",
    "function", "function-name", "samsung,model_name", "samsung,panel_name",
}


def strings(data):
    if not data or data[-1] != 0:
        return False
    values = data[:-1].split(b"\0")
    return bool(values) and all(value and all(0x20 <= c <= 0x7E for c in value)
                                for value in values)


def convert_reg(node):
    if node.parent is None or "reg" not in node.props:
        return None
    data = node.props["reg"]
    ac = fdt.cells_prop(node.parent, "#address-cells", 2)
    sc = fdt.cells_prop(node.parent, "#size-cells", 1)
    if ac == 1 and sc == 0 and len(data) == 4:
        # XNU's boot-CPU service consumes a 32-bit MPIDR value here.
        return data
    stride = ac + sc
    if stride <= 0 or len(data) % (stride * 4):
        return None
    words = struct.unpack(f">{len(data) // 4}I", data)
    out = bytearray()
    pos = 0
    while pos < len(words):
        address = fdt.cell_value(words[pos:pos + ac]); pos += ac
        size = fdt.cell_value(words[pos:pos + sc]) if sc else 0; pos += sc
        out += struct.pack("<QQ", address, size)
    return bytes(out)


def convert_prop(key, value):
    if key == "reg":
        return None
    if key in STRING_PROPS or key.endswith("-names"):
        if strings(value):
            return value
    if strings(value) and (key.endswith("-name") or key.endswith("-description")):
        return value
    if len(value) == 0:
        return value
    if len(value) % 4 == 0:
        cells = struct.unpack(f">{len(value) // 4}I", value)
        return u32(*cells)
    return value


def convert_node(source, name=None):
    target = adt_node(name if name is not None else (source.name or "device-tree"))
    for key, value in source.props.items():
        if key == "name":
            continue
        converted = convert_reg(source) if key == "reg" else convert_prop(key, value)
        if converted is not None:
            target.props.append((key, 0, converted))
    target.children = [convert_node(child) for child in source.children]
    return target


def find(node, path):
    parts = [part for part in path.strip("/").split("/") if part]
    current = node
    for part in parts:
        current = next((child for child in current.children if child.name == part), None)
        if current is None:
            return None
    return current


def prop(node, key):
    return next((value for name, _flags, value in node.props if name == key), None)


def set_prop(node, key, value):
    for i, (name, flags, _old) in enumerate(node.props):
        if name == key:
            node.props[i] = (name, flags, value)
            return
    node.props.append((key, 0, value))


def cpu_mpidr(cpu):
    if cpu.parent is None or "reg" not in cpu.props:
        raise ValueError(f"{cpu.path}: missing CPU reg")
    ac = fdt.cells_prop(cpu.parent, "#address-cells", 1)
    if ac < 1 or len(cpu.props["reg"]) < ac * 4:
        raise ValueError(f"{cpu.path}: malformed CPU reg")
    words = struct.unpack(f">{ac}I", cpu.props["reg"][:ac * 4])
    return fdt.cell_value(words)


def memory_ranges(root):
    ranges = []
    for node in fdt.walk(root):
        if fdt.strings_prop(node, "device_type") != ["memory"]:
            continue
        for entry in fdt.reg_entries(node):
            if "address" in entry and "size" in entry:
                ranges.append((int(entry["address"], 16), int(entry["size"], 16)))
    return ranges


def reserved_ranges(root):
    region = next((n for n in fdt.walk(root) if n.path == "/reserved-memory"), None)
    if region is None:
        return []
    ranges = []
    for node in region.children:
        for entry in fdt.reg_entries(node):
            if "address" in entry and "size" in entry:
                ranges.append((node.path, int(entry["address"], 16), int(entry["size"], 16)))
    return ranges


def build(root, phys_base, mem_size, boot_mpidr, model):
    compatible = fdt.strings_prop(root, "compatible")
    if not any("exynos9820" in item.lower() for item in compatible):
        raise ValueError("root compatible does not identify Exynos 9820")
    if phys_base & 0x3FFF or mem_size <= 0 or mem_size & 0x3FFF:
        raise ValueError("XNU RAM base/size must be positive and 16 KiB aligned")
    if not any(start <= phys_base and phys_base + mem_size <= start + size
               for start, size in memory_ranges(root)):
        raise ValueError("selected XNU RAM window is not contained in one FDT memory range")
    for path, start, size in reserved_ranges(root):
        if phys_base < start + size and start < phys_base + mem_size:
            raise ValueError(f"XNU RAM overlaps reserved range {path} ({start:#x}+{size:#x})")

    converted = convert_node(root, "device-tree")
    chosen_source = next((n for n in fdt.walk(root) if n.path == "/chosen"), None)
    chosen = convert_node(chosen_source, "chosen") if chosen_source else adt_node("chosen")
    for name in ("linux,initrd-start", "linux,initrd-end"):
        chosen.props = [item for item in chosen.props if item[0] != name]
    bootargs = fdt.strings_prop(chosen_source, "bootargs") if chosen_source else []
    if bootargs:
        set_prop(chosen, "boot-args", cstr(" ".join(bootargs)))
    set_prop(chosen, "dram-base", u64(phys_base))
    set_prop(chosen, "dram-size", u64(mem_size))
    if not any(child.name == "memory-map" for child in chosen.children):
        chosen.children.append(adt_node("memory-map"))

    cpus_source = next((n for n in fdt.walk(root) if n.path == "/cpus"), None)
    if cpus_source is None:
        raise ValueError("FDT has no /cpus node")
    candidates = [n for n in cpus_source.children if fdt.strings_prop(n, "device_type") == ["cpu"]]
    cpu = next((n for n in candidates if cpu_mpidr(n) == boot_mpidr), None)
    if cpu is None:
        raise ValueError(f"boot MPIDR {boot_mpidr:#x} is not present in /cpus")
    one_cpu = convert_node(cpus_source, "cpus")
    one_cpu.children = [convert_node(cpu, "cpu0")]
    cpu_adt = one_cpu.children[0]
    mpidr = cpu_mpidr(cpu)
    set_prop(cpu_adt, "reg", u32(mpidr))
    set_prop(cpu_adt, "cpu-id", u32(0))
    set_prop(cpu_adt, "logical-cpu-id", u32(0))
    set_prop(cpu_adt, "cluster-id", u32(0))
    set_prop(cpu_adt, "cluster-type", u32(0))
    set_prop(cpu_adt, "die-cluster-id", u32((mpidr >> 16) & 0xFF))
    set_prop(cpu_adt, "cluster-core-id", u32(mpidr & 0xFF))
    set_prop(cpu_adt, "state", cstr("running"))
    set_prop(cpu_adt, "enable-method", cstr("psci"))
    timer = next((n for n in fdt.walk(root)
                  if any("armv8-timer" in value for value in fdt.strings_prop(n, "compatible"))), None)
    if timer and len(timer.props.get("clock-frequency", b"")) == 4:
        freq = struct.unpack(">I", timer.props["clock-frequency"])[0]
        set_prop(cpu_adt, "timebase-frequency", u32(freq))

    # XNU's early GIC path and future drivers use the conventional Apple ADT
    # node location. Preserve the complete FDT controller properties below it.
    gic_source = next((n for n in fdt.walk(root) if "interrupt-controller" in n.props and
                       any("gic" in value.lower() for value in fdt.strings_prop(n, "compatible"))), None)
    arm_io = adt_node("arm-io", [
        ("device_type", cstr("samsung-io")),
        ("compatible", cstr("samsung,exynos9820") + cstr("arm-io")),
        ("#address-cells", u32(2)),
        ("#size-cells", u32(2)),
    ], [convert_node(gic_source, "gic")] if gic_source else [])

    # Replace only the source tree's chosen/cpus/GIC top-level nodes with the
    # XNU versions; retain all other board nodes and their compatible strings.
    root_node = converted
    root_node.children = [child for child in root_node.children
                          if child.name not in ("chosen", "cpus", "arm-io") and
                          not child.name.startswith("interrupt-controller@")]
    root_node.children.extend((chosen, one_cpu, arm_io))
    set_prop(root_node, "compatible",
             cstr("D22AP") + cstr(model) + cstr("samsung,exynos9820") +
             cstr("samsung,armv8") + cstr("AppleARM"))
    set_prop(root_node, "model", cstr(model))
    set_prop(root_node, "target-type", cstr("D22"))
    set_prop(root_node, "target-sub-type", cstr("D22AP"))
    set_prop(root_node, "manufacturer", cstr("Apple Inc."))
    return root_node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fdt", type=Path, help="merged Samsung FDT from the bootloader")
    parser.add_argument("output", type=Path)
    parser.add_argument("--phys-base", type=lambda x: int(x, 0), required=True,
                        help="start of the contiguous XNU-managed RAM window")
    parser.add_argument("--mem-size", type=lambda x: int(x, 0), required=True,
                        help="size of the XNU-managed RAM window")
    parser.add_argument("--boot-mpidr", type=lambda x: int(x, 0), default=0)
    parser.add_argument("--model", default="iPhone10,3")
    args = parser.parse_args()
    data = args.fdt.read_bytes()
    source, header = fdt.parse_dtb(data)
    output = adt.serialize(build(source, args.phys_base, args.mem_size,
                                 args.boot_mpidr, args.model))
    args.output.write_bytes(output)
    print(f"{args.output}: {len(output)} bytes; boot MPIDR={args.boot_mpidr:#x}; "
          f"XNU RAM={args.phys_base:#x}+{args.mem_size:#x}; FDT v{header['version']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error) as exc:
        print(f"mkadt-s10: {exc}", file=sys.stderr)
        sys.exit(2)
