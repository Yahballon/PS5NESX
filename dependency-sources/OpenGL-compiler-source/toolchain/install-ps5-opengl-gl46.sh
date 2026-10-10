#!/usr/bin/env bash
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

# Canonical OpenGL 4.6 installer. The delegated implementation retains legacy
# Core33 package aliases so existing OpenGL 3.3 consumers remain source-compatible.

set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$root/toolchain/install-ps5-opengl-core33.sh" \
    "${1:?usage: $0 <install-prefix>}"
