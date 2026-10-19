#!/usr/bin/env python3
"""NESYX regression: PS5 process exit must be owned by system shell."""
from pathlib import Path
import json
r=Path(__file__).resolve().parents[1]
ui=(r/'ps5/frontend/fe_ps5.cpp').read_text()
main=(r/'nes/src/main_shelf.cpp').read_text()
crt=(r/'ps5/proto/native/tooling/native/app_crt.cpp').read_text()
app=json.loads((r/'app.json').read_text())
param=json.loads((r/'nes/sce_sys/param.json').read_text())
version=(r/'nes/src/ps5nes_build_version.h').read_text()
assert 'if (app.ExitRequested())' in ui
assert 'nesyx_exit_to_shell("CoverFlow exit confirmed")' in ui
assert '::exit(0)' not in ui
assert 'sceSystemServiceLoadExec("exit",nullptr)' in main
assert 'nesyx_exit_to_shell("frontend completed")' in main
assert 'extern "C" [[noreturn]] void catchReturnFromMain(int status)' in main
assert 'nesyx_exit_to_shell("CRT main return")' in main
assert 'for(;;)sceKernelUsleep(100000)' in main
assert '__attribute__((weak)) void catchReturnFromMain' in crt
assert 'catchReturnFromMain(status);' in crt
assert app['version']=='1.0.28' and app['releaseTag']=='ps5nesx-v1.0.28'
assert param['titleId']=='PPSA99204'
assert 'kVersion[] = "1.0.28"' in version
print("PASS: NESYX PS5 shell exit, no SIGSYS libc exit, CRT interception")
