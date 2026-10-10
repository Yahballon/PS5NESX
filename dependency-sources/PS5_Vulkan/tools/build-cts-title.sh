#!/usr/bin/env bash
# PS5 Vulkan - build the Vulkan CTS title (PPSA99015).
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
#
# deqp-vk from my CTS fork (../PS5_VK-GL-CTS, branch main: the
# vulkan-cts-1.4.6.2 release with a PlayStation 5 platform, DEQP_TARGET=ps5)
# linked with RADV (tools/radv-link.sh) into dist/PPSA99015. The CTS's own
# build compiles everything; its final link is replaced by this title's, whose
# inputs are read from that build's graph: every object and archive deqp-vk
# links, except the generic main (framework/platform/tcuMain.cpp), since the
# PS5 platform's main reads its arguments from /app0/cts/args.txt.
#
# CTS_BUILD names the CTS build directory (default: the fork's build-ps5);
# RADV_ARCHIVE the RADV archive (default: the Mesa fork's build-ps5).

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cts=${PS5_CTS_FORK:-$root/../PS5_VK-GL-CTS}
cts_build=${CTS_BUILD:-$cts/build-ps5}
mesa=${PS5_MESA_FORK:-$root/../PS5_Mesa}
archive=${RADV_ARCHIVE:-$mesa/build-ps5/src/amd/vulkan/libvulkan_radeon.a}
sdk_root="$root/.deps/native/ps5-payload-sdk"
native="$root/tooling/native"
tool="$root/build/host/ps5-native-tool"
work="$root/build/cts"
param="$root/sce_sys/param-cts.json"
ninja=${NINJA:-$(command -v ninja || echo "$HOME/.local/bin/ninja")}

for file in "$archive" "$tool" "$param" "$cts_build/build.ninja"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done
title_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["titleId"])' "$param")
mkdir -p "$work/obj" "$work/stubs"
cc() { PS5_PAYLOAD_SDK="$sdk_root" sh "$root/tooling/prospero-clang18" "$@"; }

# deqp-vk's link inputs, from the CTS build's own command, in its order.
"$ninja" -C "$cts_build" deqp-vk >/dev/null 2>&1 || true
mapfile -t cts_inputs < <("$ninja" -C "$cts_build" -t commands deqp-vk | tail -n 1 | python3 -c '
import shlex, sys, os
words = shlex.split(sys.stdin.read())
base = sys.argv[1]
for word in words:
    if word.endswith((".o", ".a")) and "tcuMain.cpp.o" not in word:
        print(word if os.path.isabs(word) else os.path.join(base, word))
' "$cts_build")
(( ${#cts_inputs[@]} > 10 )) || { echo "could not read deqp-vk's link inputs" >&2; exit 2; }
# RADV brings zlib (1.3.1, its shader cache's) since the on-disk cache: the
# CTS's own copy (1.2.13) would define every zlib function twice, so the CTS
# and its libpng take RADV's, which has the same interface.
radv_symbols=$(llvm-nm --defined-only "$archive" 2>/dev/null || true)
if grep -q " T inflate$" <<< "$radv_symbols"; then
    kept=()
    for input in "${cts_inputs[@]}"; do
        [[ $input == */external/zlib/libz.a ]] || kept+=("$input")
    done
    cts_inputs=("${kept[@]}")
fi

cc -std=c++20 -O2 -fno-exceptions -fno-rtti -c "$native/app_crt.cpp" -o "$work/obj/app_crt.o"
stub() {
    local library=$1 source=$2
    cc -std=c11 -O2 -fPIC -c "$root/$source" -o "$work/obj/${library}_stub.o"
    "$sdk_root/bin/prospero-lld" --shared -soname "${library}.prx" \
        -o "$work/stubs/${library}.so" "$work/obj/${library}_stub.o"
}
stub libSceAgc vendor/ps5/sdk/stubs/agc_canary_link_stub.c
stub libSceAgcDriver vendor/ps5/sdk/stubs/agc_driver_canary_link_stub.c

# shellcheck source=tools/radv-link.sh
source "$root/tools/radv-link.sh"
radv_link_recipe "$root" "$sdk_root" "$archive" || exit 2
# The CTS is C++ with exceptions: the app runtime's replacement operators are
# not linked (app_cpp_runtime.cpp is built without exceptions), libc++'s are.
"$sdk_root/bin/prospero-lld" "${radv_linker_script[@]}" --eh-frame-hdr --error-limit=0 "${radv_link_flags[@]}" \
    --version-script "$native/app-symbols.map" --exclude-libs=ALL \
    -e _start -o "$work/llvm-pie.elf" \
    "$work/obj/app_crt.o" "$work/stubs/libSceAgc.so" "$work/stubs/libSceAgcDriver.so" \
    --start-group "${cts_inputs[@]}" --end-group \
    "${radv_link_inputs[@]}" \
    --as-needed "$sdk_root"/target/lib/*.so
"$tool" link --in "$work/llvm-pie.elf" --out "$work/eboot.elf" \
    --stub-dir "$sdk_root/target/lib" --stub "$work/stubs/libSceAgc.so" \
    --stub "$work/stubs/libSceAgcDriver.so" --module-sdk 0x02000009 \
    --companion-sdk 0x08050001 --file-name eboot.elf

app="$root/dist/$title_id"
mkdir -p "$app/sce_sys" "$app/sce_module" "$app/cts"
"$tool" self --sign --in "$work/eboot.elf" --out "$app/eboot.bin.new" --magic 0x1D3D154F
mv "$app/eboot.bin.new" "$app/eboot.bin"
cp "$param" "$app/sce_sys/param.json"
for asset in icon0.png pic0.dds pic1.dds snd0.at9; do
    [[ -f $root/sce_sys/$asset ]] && cp "$root/sce_sys/$asset" "$app/sce_sys/$asset"
done
(cd "$root/runtime" && sha256sum --check --strict --quiet libc.prx.sha256)
cp "$root/runtime/libc.prx" "$app/sce_module/libc.prx"
# The CTS's data (images, amber scripts, video clips): 17 MB, the archive
# directory the platform passes as --deqp-archive-dir.
rsync -a --delete "$cts/external/vulkancts/data/vulkan/" "$app/cts/vulkan/"
# What this build is, for tools/run-cts.py to note beside the results it runs.
printf 'CTS %s, RADV %s, eboot.bin sha256 %s\n' \
    "$(git -C "$cts" describe --always --dirty --abbrev=11 --exclude='*')" \
    "$(git -C "$mesa" describe --always --dirty --abbrev=11 --exclude='*')" \
    "$(sha256sum "$app/eboot.bin" | cut -c1-16)" > "$app/cts/build.txt"
printf 'CTS title: %s (%s bytes; %s)\n' "$app" "$(stat -c %s "$app/eboot.bin")" "$(cat "$app/cts/build.txt")"
