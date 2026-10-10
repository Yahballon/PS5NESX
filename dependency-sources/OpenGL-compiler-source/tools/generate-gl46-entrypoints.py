#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate static wrappers for GL 4.6 commands Mesa exposes only as dispatch stubs."""

import argparse
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def symbols(*archives: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", *(str(path) for path in archives)],
        check=True, text=True, stdout=subprocess.PIPE).stdout
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)$", output, re.MULTILINE))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("bridge", type=Path)
    parser.add_argument("glapi", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    root = ET.parse(args.registry).getroot()
    commands = set()
    for feature in root.findall("feature"):
        if (feature.get("api") != "gl" or
                tuple(map(int, feature.get("number").split("."))) > (4, 6)):
            continue
        for requirement in feature.findall("require"):
            if requirement.get("profile") in (None, "core"):
                commands.update(item.get("name") for item in requirement.findall("command"))
        for removal in feature.findall("remove"):
            if removal.get("profile") == "core":
                commands.difference_update(item.get("name") for item in removal.findall("command"))
    if len(commands) != 657:
        raise SystemExit(f"unexpected OpenGL 4.6 command count: {len(commands)}")

    exported = symbols(args.bridge, args.glapi)
    missing = sorted(commands - exported)
    nodes = {node.findtext("proto/name"): node for node in root.findall("commands/command")}
    stubs = {}
    for name in missing:
        exact = "_dispatch_stub_" + name[2:]
        candidates = ([exact] if exact in exported else
                      [exact + suffix for suffix in ("ARB", "EXT", "NV", "KHR")])
        candidates = [candidate for candidate in candidates if candidate in exported]
        if len(candidates) != 1:
            raise SystemExit(f"expected one Mesa dispatch stub for {name}, got {candidates}")
        stubs[name] = candidates[0]

    lines = [
        "/* Generated from Khronos gl.xml and Mesa's static GLAPI symbol table. */",
        "#define GL_GLEXT_PROTOTYPES 1",
        "#include <GL/glcorearb.h>",
        "",
    ]
    for name in missing:
        node = nodes[name]
        proto = node.find("proto")
        return_type = "".join(proto.itertext()).replace(name, "").strip()
        params = ["".join(param.itertext()).strip() for param in node.findall("param")]
        arguments = [param.findtext("name") for param in node.findall("param")]
        stub = stubs[name]
        signature = ", ".join(params) or "void"
        lines.extend([
            f"extern {return_type} APIENTRY {stub}({signature});",
            f"{return_type} APIENTRY {name}({signature})",
            "{",
            f"   {'return ' if return_type != 'void' else ''}{stub}({', '.join(arguments)});",
            "}",
            "",
        ])
    args.output.write_text("\n".join(lines), newline="\n")
    print(f"generated {len(missing)} static wrappers for 657 OpenGL 4.6 Core commands")


if __name__ == "__main__":
    main()
