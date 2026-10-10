#!/usr/bin/env bash
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
build="$root/build/mesa-host-frontend"
mkdir -p "$build/tmp" "$build/cache"
export TMPDIR="$build/tmp" XDG_CACHE_HOME="$build/cache" PYTHONDONTWRITEBYTECODE=1
export CC=clang-18 CXX=clang++-18
meson setup "$build" "$root/third_party/mesa-26.2.0" --wrap-mode=nodownload \
  --buildtype=debugoptimized -Db_ndebug=false -Dplatforms= \
  -Dgallium-drivers=softpipe -Dvulkan-drivers= -Dopengl=true \
  -Degl=disabled -Dgbm=disabled -Dgles1=disabled -Dgles2=disabled \
  -Dglx=disabled -Dllvm=disabled -Dzlib=disabled -Dzstd=disabled \
  -Dshader-cache=disabled -Dxmlconfig=disabled -Dexpat=disabled \
  -Dlibunwind=disabled -Dvalgrind=disabled -Dvideo-codecs= \
  -Dbuild-tests=false -Dtools= -Dgallium-va=disabled -Dgallium-rusticl=false
