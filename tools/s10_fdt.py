#!/usr/bin/env python3
"""Summarize the flattened device tree consumed by the S10 XNU bring-up.

This reads DTB data only. It does not execute or extract a Linux/Android kernel.
Pass a merged, target-specific DTB (apply any Samsung DTBO overlays first).
"""
import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path


FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


@dataclass
class Node:
    name: str
    parent: object = None
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    @property
    def path(self):
        if self.parent is None:
            return "/"
        prefix = self.parent.path.rstrip("/")
        return f"{prefix}/{self.name}"


def align4(value):
    return (value + 3) & ~3


def c_string(data, offset):
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated string in DTB")
    return data[offset:end].decode("utf-8", "replace"), end + 1


def parse_dtb(data):
    if len(data) < 40:
        raise ValueError("file is too short to contain an FDT header")
    fields = struct.unpack_from(">10I", data)
    (magic, total_size, struct_off, strings_off, _reserve_off, version,
     last_compatible, _boot_cpu, strings_size, struct_size) = fields
    if magic != FDT_MAGIC:
        raise ValueError(f"bad FDT magic 0x{magic:08x}; expected 0xd00dfeed")
    if total_size > len(data) or total_size < 40:
        raise ValueError("FDT totalsize is outside the input file")
    if version < 16 or last_compatible > 17:
        raise ValueError(f"unsupported FDT version {version}/{last_compatible}")
    struct_end = struct_off + struct_size
    strings_end = strings_off + strings_size
    if struct_end > total_size or strings_end > total_size:
        raise ValueError("FDT structure or strings block exceeds totalsize")

    strings = data[strings_off:strings_end]
    pos = struct_off
    stack = []
    root = None
    while pos + 4 <= struct_end:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == FDT_BEGIN_NODE:
            name, pos = c_string(data, pos)
            pos = align4(pos)
            parent = stack[-1] if stack else None
            node = Node(name, parent)
            if parent:
                parent.children.append(node)
            elif root is None:
                root = node
            else:
                raise ValueError("FDT contains multiple root nodes")
            stack.append(node)
        elif token == FDT_END_NODE:
            if not stack:
                raise ValueError("unexpected FDT_END_NODE")
            stack.pop()
        elif token == FDT_PROP:
            if not stack or pos + 8 > struct_end:
                raise ValueError("FDT property appears outside a node")
            length, name_offset = struct.unpack_from(">II", data, pos)
            pos += 8
            if pos + length > struct_end or name_offset >= len(strings):
                raise ValueError("FDT property exceeds structure or strings block")
            name, _ = c_string(strings, name_offset)
            stack[-1].props[name] = data[pos:pos + length]
            pos = align4(pos + length)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unknown FDT token {token} at offset {pos - 4}")
    if root is None or stack:
        raise ValueError("incomplete FDT structure block")
    return root, {"version": version, "last_compatible_version": last_compatible,
                  "totalsize": total_size}


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def strings_prop(node, name):
    value = node.props.get(name)
    if value is None:
        return []
    return [s.decode("utf-8", "replace") for s in value.split(b"\0") if s]


def cells_prop(node, name, default):
    value = node.props.get(name)
    if value is None:
        return default
    if len(value) != 4:
        return default
    return struct.unpack(">I", value)[0]


def cell_value(cells):
    value = 0
    for cell in cells:
        value = (value << 32) | cell
    return value


def translate_address(bus, address, size):
    """Translate one bus address through FDT ranges; return None if unknown."""
    if bus.parent is None:
        return address
    ranges = bus.props.get("ranges")
    if ranges is None:
        return None
    if len(ranges) == 0:
        return translate_address(bus.parent, address, size)
    child_ac = cells_prop(bus, "#address-cells", 2)
    parent_ac = cells_prop(bus.parent, "#address-cells", 2)
    size_c = cells_prop(bus, "#size-cells", 1)
    stride = child_ac + parent_ac + size_c
    if stride == 0 or len(ranges) % (stride * 4):
        return None
    words = struct.unpack(f">{len(ranges) // 4}I", ranges)
    i = 0
    while i < len(words):
        child_base = cell_value(words[i:i + child_ac]); i += child_ac
        parent_base = cell_value(words[i:i + parent_ac]); i += parent_ac
        span = cell_value(words[i:i + size_c]); i += size_c
        if child_base <= address and address + size <= child_base + span:
            return translate_address(bus.parent, parent_base + address - child_base, size)
    return None


def reg_entries(node):
    data = node.props.get("reg")
    if data is None or node.parent is None:
        return []
    address_cells = cells_prop(node.parent, "#address-cells", 2)
    size_cells = cells_prop(node.parent, "#size-cells", 1)
    stride = address_cells + size_cells
    if stride == 0 or len(data) % (stride * 4):
        return [{"raw_cells": [f"0x{x:x}" for x in struct.unpack(f">{len(data) // 4}I", data)]}]
    words = struct.unpack(f">{len(data) // 4}I", data)
    result = []
    i = 0
    while i < len(words):
        address = cell_value(words[i:i + address_cells]); i += address_cells
        size = cell_value(words[i:i + size_cells]) if size_cells else 0
        i += size_cells
        item = {"address": f"0x{address:x}", "size": f"0x{size:x}"}
        physical = translate_address(node.parent, address, size)
        if physical is not None:
            item["physical_address"] = f"0x{physical:x}"
        result.append(item)
    return result


def phandle_map(root):
    result = {}
    for node in walk(root):
        for prop in ("phandle", "linux,phandle"):
            value = node.props.get(prop)
            if value and len(value) == 4:
                result[struct.unpack(">I", value)[0]] = node
    return result


def inherited_prop(node, name):
    while node is not None:
        if name in node.props:
            return node.props[name]
        node = node.parent
    return None


def interrupt_summary(node, handles):
    extended = node.props.get("interrupts-extended")
    if extended is not None and len(extended) % 4 == 0:
        words = list(struct.unpack(f">{len(extended) // 4}I", extended))
        result = []
        pos = 0
        while pos < len(words):
            parent = handles.get(words[pos])
            pos += 1
            if parent is None:
                return {"raw_interrupt_cells": [f"0x{x:x}" for x in words],
                        "interrupt_parent": "unresolved phandle"}
            count = cells_prop(parent, "#interrupt-cells", 0)
            if not count or pos + count > len(words):
                return {"raw_interrupt_cells": [f"0x{x:x}" for x in words],
                        "interrupt_parent": parent.path}
            result.append({"interrupt_parent": parent.path,
                           "specifier": [f"0x{x:x}" for x in words[pos:pos + count]]})
            pos += count
        return {"interrupts_extended": result}

    parent_id = inherited_prop(node, "interrupt-parent")
    if not parent_id or len(parent_id) != 4:
        return {"raw_interrupt_cells": raw_cells(node, "interrupts")}
    parent = handles.get(struct.unpack(">I", parent_id)[0])
    if parent is None:
        return {"raw_interrupt_cells": raw_cells(node, "interrupts"),
                "interrupt_parent": "unresolved phandle"}
    count = cells_prop(parent, "#interrupt-cells", 0)
    words = raw_cells(node, "interrupts")
    if not count or len(words) % count:
        return {"raw_interrupt_cells": words, "interrupt_parent": parent.path}
    return {"interrupt_parent": parent.path,
            "interrupt_specifiers": [words[i:i + count] for i in range(0, len(words), count)]}


def raw_cells(node, name):
    value = node.props.get(name)
    if value is None or len(value) % 4:
        return []
    return [f"0x{x:x}" for x in struct.unpack(f">{len(value) // 4}I", value)]


def describe(node, handles):
    result = {"path": node.path}
    compatible = strings_prop(node, "compatible")
    if compatible:
        result["compatible"] = compatible
    for name in ("device_type", "model", "status", "enable-method", "method"):
        value = strings_prop(node, name)
        if value:
            result[name] = value if len(value) > 1 else value[0]
    for name in ("#address-cells", "#size-cells", "clock-frequency", "size",
                 "alignment", "alloc-ranges", "no-map", "reusable",
                 "interrupt-controller", "reg-names"):
        value = node.props.get(name)
        if value is None:
            continue
        if name in ("no-map", "reusable", "interrupt-controller"):
            result[name] = True
        elif name in ("alloc-ranges",):
            result[name] = raw_cells(node, name)
        elif name == "reg-names":
            strings = strings_prop(node, name)
            if strings:
                result[name] = strings
        elif len(value) % 4 == 0:
            result[name] = [f"0x{x:x}" for x in struct.unpack(f">{len(value) // 4}I", value)]
    if "reg" in node.props:
        result["reg"] = reg_entries(node)
    if "interrupts" in node.props:
        result.update(interrupt_summary(node, handles))
    return result


def build_report(root, header):
    handles = phandle_map(root)
    nodes = list(walk(root))
    strings = strings_prop(root, "compatible")
    model = strings_prop(root, "model")
    overlay = any(n.name.startswith("fragment@") for n in nodes) or any(
        n.name == "__fixups__" for n in nodes)
    report = {
        "format": "FDT",
        "header": header,
        "model": model[0] if model else None,
        "compatible": strings,
        "overlay_unmerged": overlay,
        "warnings": [],
    }
    if overlay:
        report["warnings"].append("This appears to be a DTBO overlay, not a merged device tree.")
    if not any("9820" in s.lower() or "beyond1lte" in s.lower() for s in strings):
        report["warnings"].append("Root compatible does not identify beyond1lte/Exynos 9820; verify the selected DTB.")

    chosen = next((n for n in nodes if n.path == "/chosen"), None)
    if chosen:
        report["chosen"] = describe(chosen, handles)
        args = strings_prop(chosen, "bootargs")
        if args:
            report["chosen"]["bootargs"] = " ".join(args)

    report["memory"] = [describe(n, handles) for n in nodes
                        if strings_prop(n, "device_type") == ["memory"]]
    reserved = next((n for n in nodes if n.path == "/reserved-memory"), None)
    report["reserved_memory"] = ([describe(n, handles) for n in reserved.children]
                                 if reserved else [])

    cpus_node = next((n for n in nodes if n.path == "/cpus"), None)
    report["cpus"] = ([describe(n, handles) for n in cpus_node.children
                       if strings_prop(n, "device_type") == ["cpu"]]
                      if cpus_node else [])
    report["psci"] = [describe(n, handles) for n in nodes
                      if any("psci" in s.lower() for s in strings_prop(n, "compatible"))]
    report["timers"] = [describe(n, handles) for n in nodes
                        if any("timer" in s.lower() for s in strings_prop(n, "compatible"))]
    report["interrupt_controllers"] = [describe(n, handles) for n in nodes
        if "interrupt-controller" in n.props or
        any("gic" in s.lower() for s in strings_prop(n, "compatible"))]

    def matches(node, words):
        haystack = (node.path + " " + " ".join(strings_prop(node, "compatible"))).lower()
        return any(word in haystack for word in words)

    report["ufs"] = [describe(n, handles) for n in nodes if matches(n, ("ufs", "ufshc"))]
    report["display_and_input"] = [describe(n, handles) for n in nodes
        if matches(n, ("dsi", "panel", "touch", "sec_ts", "synaptics"))]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", type=Path, help="merged stock S10 flattened device tree")
    parser.add_argument("-o", "--output", type=Path, help="write JSON report to this file")
    args = parser.parse_args()
    try:
        data = args.dtb.read_bytes()
        root, header = parse_dtb(data)
        report = build_report(root, header)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered)
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError, struct.error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
