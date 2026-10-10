#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build a compiler-only partial handoff using isolated Mesa host artifacts.

Generated outputs stay in build/mesa-host-frontend unless --export-header is
explicitly requested. PSBC archives are read-only; no default make integration.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
assert (ROOT / "tests/ps5/glsl_handoff").resolve() == HERE
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--export-header', action='store_true',
                    help='After all host checks pass, regenerate the selected native fixture header')
parser.add_argument('--private-arrays', action='store_true',
                    help='Parsed private-array checks in an isolated output directory')
cli_args = parser.parse_args()
private_defines = ['-DPS5_GLSL_PRIVATE_TEST=1'] if cli_args.private_arrays else []
BUILD = ROOT / 'build/mesa-host-frontend'
MESA = ROOT / 'third_party/mesa-26.2.0'
PSBC = ROOT / 'third_party/opengnm-psbc'
OUT = BUILD / ('handoff-private' if cli_args.private_arrays else 'handoff')
OUT.mkdir(exist_ok=True)
os.environ.update(TMPDIR=str(BUILD/'tmp'), XDG_CACHE_HOME=str(BUILD/'cache'), PYTHONDONTWRITEBYTECODE='1')
if (OUT/'result.log').exists():
    shutil.copy2(OUT/'result.log', OUT/'previous-result.log')

# Only audited serializer differences are permitted. No raw pointer-bearing
# spec metadata is accepted by the frontend; generated enum tables must match.
serialization=(MESA/'src/compiler/nir/nir_serialize.c').read_text()
for removed in ('   NIR_SERIALIZE_SHADER_SPEC = 1 << 3,\n',
                '   if (!strip && info.spec)\n      flags |= NIR_SERIALIZE_SHADER_SPEC;\n',
                '   if (!strip && info.spec)\n      blob_write_string(blob, info.spec);\n',
                '   char *spec = (flags & NIR_SERIALIZE_SHADER_SPEC) ? blob_read_string(blob) : NULL;\n',
                '   info.spec = spec ? ralloc_strdup(ctx.nir, spec) : NULL;\n'):
    assert serialization.count(removed)==1
    serialization=serialization.replace(removed,'')
assert serialization==(PSBC/'src/compiler/nir/nir_serialize.c').read_text()
for name in ('nir_intrinsics.h','nir_opcodes.h'):
    assert (BUILD/'src/compiler/nir'/name).read_bytes()==(PSBC/'src/compiler/nir'/name).read_bytes()
def tokens(path):
    return re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',path.read_text(),flags=re.S))
for name in ('src/compiler/nir/nir_shader_compiler_options.h','src/compiler/shader_info.h'):
    assert tokens(MESA/name)==tokens(PSBC/name)

# Enumerate every member, rejecting new declaration shapes instead of silently
# omitting options. Export values, not struct padding or process pointers.
options_source = (PSBC/'src/compiler/nir/nir_shader_compiler_options.h').read_text()
options_body = re.sub(r'/\*.*?\*/|//[^\n]*', '', options_source, flags=re.S)
options_body = options_body.split('typedef struct nir_shader_compiler_options {', 1)[1].split('}', 1)[0]
option_fields, callbacks = [], []
for declaration in options_body.split(';'):
    declaration = declaration.strip()
    if not declaration:
        continue
    callback = re.search(r'\(\*(\w+)\)', declaration)
    if callback:
        callbacks.append(callback[1])
        continue
    field = re.fullmatch(r'(\w+)\s+(\w+)(?:\[(\d+)\])?', declaration)
    if declaration == 'const void *cb_data':
        callbacks.append('cb_data')
    elif field and field[1] == 'nir_instr_filter_cb':
        callbacks.append(field[2])
    else:
        assert field, f'unaudited options declaration: {declaration}'
        option_fields.extend([f'{field[2]}[{i}]' for i in range(int(field[3]))]
                             if field[3] else [field[2]])
assert set(callbacks) == {'lower_to_scalar_filter', 'lower_mediump_io', 'lower_convert_alu_types',
                          'varying_expression_max_cost', 'varying_estimate_instr_cost',
                          'max_offset_shift', 'cb_data'}
(OUT/'options-values.inc').write_text(''.join(
    f'fprintf(values, "{field}=%llu\\n", (unsigned long long)opts.{field});\n'
    for field in option_fields))
ac=(PSBC/'src/amd/common/nir/ac_nir.c').read_text()
ac_start=ac.index('unsigned\nac_nir_varying_expression_max_cost(')
(OUT/'varying.inc').write_text(ac[ac_start:ac.index('\nbool\n',ac_start)])

def run(args, **kwargs):
    result = subprocess.run(args, cwd=BUILD, text=True, **kwargs)
    if result.returncode:
        if result.stdout: print(result.stdout)
        if result.stderr: print(result.stderr)
        raise SystemExit(f'Failed ({result.returncode}): {args[0]}')
    return result

driver = (ROOT/'src/gallium/ps5/ps5_screen.c').read_text()
start = driver.index('   unsigned textures = 0', driver.index('ps5_create_compute_state('))
end = driver.index('   if (!context->compute_descriptors)', start)
usage = driver.index('static bool\nps5_compute_texture_usage(')
defines = '\n'.join(line for line in driver.splitlines() if line.startswith((
    '#define PS5_COMPUTE_CONSTANT_SLOTS ', '#define PS5_COMPUTE_STORAGE_SLOTS ', '#define PS5_COMPUTE_IMAGE_SLOTS ')))
(OUT/'prepare.inc').write_text(defines + '\n#define PS5_COMPUTE_TEXTURE_SLOTS 16\n' +
    driver[usage:driver.index('/* Internal compute bring-up',usage)] +
    '\nbool handoff_prepare(nir_shader *nir) {\n' + driver[start:end] +
    'return true; cleanup: return false;\n}\n')

# Reuse the exact finalizer/helper bodies; omit unrelated link/cache/runtime code.
st = (MESA/'src/mesa/state_tracker/st_glsl_to_nir.cpp').read_text()
prefix = st[:st.index('static bool\ndef_is_64bit(')]
last = st[st.index('void\nst_nir_lower_samplers('):st.index('/**\n * Link a GLSL shader program.')]
(OUT/'finalize.cpp').write_text(prefix + last)
# The real finalizer references this real helper even when these fixtures need no merging.
statevars = (MESA/'src/mesa/program/prog_statevars.c').read_text()
size_start=statevars.index('unsigned\n_mesa_program_state_value_size(')
size_end=statevars.index('\n}\n',size_start)+3
opt_start=statevars.index('void\n_mesa_optimize_state_parameters(')
(OUT/'statevars.c').write_text('#include "program/prog_statevars.h"\n#include "program/prog_parameter.h"\n#include "main/mtypes.h"\n'+
    statevars[size_start:size_end]+statevars[opt_start:])

commands = json.loads((BUILD/'compile_commands.json').read_text())
def compile_like(suffix, source, dest, extra=()):
    entry = next(c for c in commands if c['file'].endswith(suffix))
    args = shlex.split(entry['command'])
    clean = [args[0]]
    i=1
    while i < len(args):
        arg=args[i]
        if arg in ('-o','-c','-MF','-MQ'):
            i += 2
            continue
        if arg not in ('-MD','-MMD'):
            clean.append(arg)
        i+=1
    clean += ['-ffunction-sections','-fdata-sections','-I'+str(PSBC/'libpsbc'),
              '-I'+str(MESA/'src/compiler/glsl'), '-I'+str(MESA/'src/mesa/state_tracker'),
              '-I'+str(OUT), *extra, '-c', str(source), '-o', str(dest)]
    run(clean)

compile_like('standalone.cpp', HERE/'handoff.cpp', OUT/'handoff.o', private_defines)
compile_like('standalone.cpp', OUT/'finalize.cpp', OUT/'finalize.o')
compile_like('gl_nir_linker.c', OUT/'statevars.c', OUT/'statevars.o')
compile_like('gl_nir_linker.c', HERE/'abi.c', OUT/'mesa-abi.o', ['-DABI_FUNCTION=mesa_abi'])
run(['clang-18','-std=gnu11','-DHAVE_FUNC_ATTRIBUTE_PACKED=1','-DHAVE_ENDIAN_H=1',
     '-DHAVE_PTHREAD=1','-DHAVE_STRUCT_TIMESPEC=1','-D_GNU_SOURCE','-DABI_FUNCTION=psbc_abi',
     '-I'+str(PSBC/'include/mesa'),'-I'+str(PSBC/'include'),'-I'+str(PSBC/'src'),
     '-c',str(HERE/'abi.c'),'-o',str(OUT/'psbc-abi.o')])
run(['clang-18','-std=gnu11','-DHAVE_FUNC_ATTRIBUTE_PACKED=1','-DHAVE_ENDIAN_H=1',
     '-DHAVE_PTHREAD=1','-DHAVE_STRUCT_TIMESPEC=1','-D_GNU_SOURCE',
     '-I'+str(PSBC/'include/mesa'),'-I'+str(PSBC/'include'),'-I'+str(PSBC/'src'),
     '-I'+str(PSBC/'src/gallium/include'),'-I'+str(PSBC/'libpsbc'),'-I'+str(OUT), *private_defines,
     '-c',str(HERE/'backend.c'),'-o',str(OUT/'backend.o')])

link = shlex.split(run(['ninja','-t','commands','src/compiler/glsl/glsl_compiler'],capture_output=True).stdout.splitlines()[-1])
link[link.index('-o')+1] = str(OUT/'check')
main = next(i for i,arg in enumerate(link) if arg.endswith('/main.cpp.o'))
link[main:main+1] = [str(OUT/name) for name in ('handoff.o','finalize.o','statevars.o','mesa-abi.o')]
link += ['-Wl,--gc-sections']
archive_hash = hashlib.sha256((PSBC/'libpsbc.a').read_bytes()).hexdigest()
run(link)
run(['g++','-o',str(OUT/'backend'),str(OUT/'backend.o'),str(OUT/'psbc-abi.o'),str(PSBC/'libpsbc.a'),'-pthread','-lm'])
os.chdir(OUT)
logs=[]
for args in ([str(OUT/'backend'),'--contract'],[str(OUT/'check')],[str(OUT/'backend')]):
    result=subprocess.run(args,cwd=OUT,text=True,capture_output=True,timeout=60)
    logs.append(result.stdout+result.stderr)
    (OUT/'result.log').write_text(''.join(logs))
    print(logs[-1])
    if result.returncode: raise SystemExit(f'Failed ({result.returncode}): {args[0]}')
assert archive_hash == hashlib.sha256((PSBC/'libpsbc.a').read_bytes()).hexdigest()
assert driver==(ROOT/'src/gallium/ps5/ps5_screen.c').read_text(), 'Driver changed during this run'
(OUT/'inputs.json').write_text(json.dumps({'driver_sha256':hashlib.sha256(driver.encode()).hexdigest(),
    'driver_hash_encoding':'UTF-8 with normalized LF, as extracted',
    'psbc_sha256':archive_hash,'ubo_model':{'user_blocks':14,'combined_blocks':14},
    'boundary':'partial: gl_nir_link_glsl + selected ST passes + real st_finalize_nir + serialized transfer + extracted preparation',
    'harness_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'handoff.cpp',HERE/'backend.c',HERE/'abi.c',HERE/'run.py')},
    'frontend_finalizer_sha256':hashlib.sha256(st.encode()).hexdigest()},indent=2))


def export_header(target_abi):
    """Fixed, audited fixtures only; this is not a general NIR file format."""
    def sha(data):
        return hashlib.sha256(data).hexdigest()

    abi_values = [int(x) for x in (OUT/'abi-values.txt').read_text().split()]
    abi_body = (HERE/'abi.c').read_text().split('static const size_t values[]={', 1)[1].split('};', 1)[0]
    abi_exprs = [x.strip() for x in re.split(r',\s*(?![^()]*\))', abi_body)]
    assert abi_exprs.pop() == '0' and len(abi_exprs) == len(abi_values) == 22
    values = dict(line.split('=') for line in (OUT/'options-values.txt').read_text().splitlines())
    assert list(values) == option_fields
    values = {k: int(v) for k, v in values.items()}
    layout = [list(map(int, line.split())) for line in (OUT/'fixtures.txt').read_text().splitlines()]
    assert len(layout) == 3 and [row[0] for row in layout] == [0, 1, 2]
    if cli_args.private_arrays:
        assert layout[0][1:] == [0, 0]
    else:
        assert 0 <= layout[0][1] < layout[0][2] <= 64
    assert layout[1][1:] == layout[2][1:] == [0, 0]
    suffix = '-prepared' if cli_args.private_arrays else ''
    blobs = [(OUT/f'fixture-{i}{suffix}.nir').read_bytes() for i in range(3)]
    literals = [(OUT/f'fixture-{i}.comp').read_text() for i in range(3)]
    ssbo_bindings = [list(map(int,(OUT/f'fixture-{i}-ssbo.txt').read_text().split())) for i in range(3)]
    assert all(sorted(bindings)==([0,1] if cli_args.private_arrays else [0]) for bindings in ssbo_bindings)
    assert all(0 < len(blob) <= 1048576 for blob in blobs)
    metadata_version = int(re.search(r'#define PSBC_SHADER_METADATA_VERSION (\d+)u',
                                    (PSBC/'libpsbc/psbc_compile.h').read_text())[1])
    # Preserve exact audited source identities, not only a repository HEAD which
    # may omit local patches. LF normalization matches the extraction above.
    paths = [HERE/name for name in ('configure.sh', 'run.py', 'handoff.cpp', 'backend.c', 'abi.c',
                                   'check_target_abi.py')]
    paths += [ROOT/'src/gallium/ps5/ps5_screen.c', PSBC/'libpsbc/psbc_compile.h',
              PSBC/'libpsbc/psbc_compile.c', PSBC/'src/amd/common/nir/ac_nir.c',
              MESA/'src/mesa/state_tracker/st_glsl_to_nir.cpp',
              MESA/'src/mesa/program/prog_statevars.c']
    for tree in (MESA, PSBC):
        paths += [tree/name for name in ('src/compiler/nir/nir_serialize.c',
                  'src/compiler/nir/nir_shader_compiler_options.h', 'src/compiler/shader_info.h',
                  'src/compiler/nir/nir_lower_uniforms_to_ubo.c')]
    paths += [MESA/'src/compiler/glsl'/name for name in
              ('standalone.cpp', 'standalone_scaffolding.cpp', 'gl_nir_linker.c')]
    paths += [PSBC/'src/compiler/nir'/name for name in ('nir_intrinsics.h', 'nir_opcodes.h')]
    receipt = {
        'schema': 1, 'encoding': 'source hashes use UTF-8 normalized LF; blobs use raw bytes',
        'scope': ('parsed GLSL + selected ST passes' +
                  (' + extracted driver preparation' if cli_args.private_arrays else '') +
                  '; not st_link_shader or a stable NIR format'),
        'metadata_version': metadata_version,
        'target_abi': target_abi,
        'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_text().encode()) for p in paths},
        'serialization_audited_sha256': sha(serialization.encode()),
        'frontend_generated_sha256': {name: sha((BUILD/'src/compiler/nir'/name).read_bytes())
                                      for name in ('nir_intrinsics.h', 'nir_opcodes.h')},
        'options_values': values,
        'options_values_sha256': sha(json.dumps(values, sort_keys=True).encode()),
        'abi': dict(zip(abi_exprs, abi_values)),
        'fixtures': [{'source': literal, 'source_sha256': sha(literal.encode()),
                      'blob_sha256': sha(blob), 'bytes': len(blob), 'ssbo_bindings': ssbo_bindings[i],
                      'addend_offset': layout[i][1], 'default_bytes': layout[i][2]}
                     for i, (literal, blob) in enumerate(zip(literals, blobs))]
    }
    receipt_text = json.dumps(receipt, sort_keys=True, indent=2)
    receipt_hash = sha(receipt_text.encode())
    lines = [
        '// PS5 OpenGL - OpenGL implementation for PlayStation 5.',
        '// Copyright (C) 2026 BlackBearReloaded',
        '// SPDX-License-Identifier: GPL-3.0-or-later',
        '/* Generated fixed test data; do not edit. No portable NIR-format claim.',
        ' * Regenerate explicitly from repository root (WSL):',
        ' * bash tests/ps5/glsl_handoff/configure.sh  # only if not configured',
        ' * ninja -C build/mesa-host-frontend -j6 src/compiler/glsl/glsl_compiler',
        ' * python3 tests/ps5/glsl_handoff/run.py --export-header' +
        (' --private-arrays' if cli_args.private_arrays else ''),
        ' * Normal builds consume this checked-in header, never the exporter.',
        ' * Source/options/serializer audit: receipt below. ABI static assertions',
        ' * do not replace the independent target-vs-host bitfield/layout probe.',
        ' */',
        '#ifndef PS5_' + ('PRIVATE' if cli_args.private_arrays else 'COMPUTE') + '_GLSL_FIXTURES_H',
        '#define PS5_' + ('PRIVATE' if cli_args.private_arrays else 'COMPUTE') + '_GLSL_FIXTURES_H',
        '#include <stddef.h>',
        '#include <stdint.h>',
        '#include <stdbool.h>',
        '#include "compiler/nir/nir.h"',
        '#include "psbc_compile.h"',
        '/* PS5_GLSL_RECEIPT_BEGIN',
        receipt_text,
        'PS5_GLSL_RECEIPT_END */',
        f'#define PS5_GLSL_RECEIPT_SHA256 "{receipt_hash}"',
        f'#define PS5_GLSL_DEFAULT_BYTES {layout[0][2]}u',
        f'#define PS5_GLSL_ADDEND_OFFSET {layout[0][1]}u',
        *(['_Static_assert(PS5_GLSL_DEFAULT_BYTES == 0, "private GLSL has no defaults");']
          if cli_args.private_arrays else [
        '_Static_assert(PS5_GLSL_DEFAULT_BYTES > 0 && PS5_GLSL_DEFAULT_BYTES <= 64 &&',
        '               !(PS5_GLSL_DEFAULT_BYTES % 4) && !(PS5_GLSL_ADDEND_OFFSET % 4) &&',
        '               PS5_GLSL_ADDEND_OFFSET + 4 <= PS5_GLSL_DEFAULT_BYTES, "GLSL default layout");']),
        f'_Static_assert(PSBC_SHADER_METADATA_VERSION == {metadata_version}u, "regenerate GLSL fixtures");',
    ]
    for expression, value in zip(abi_exprs, abi_values):
        lines.append(f'_Static_assert({expression} == {value}u, "GLSL fixture ABI: {expression}");')
    lines += [
        'extern unsigned ac_nir_varying_expression_max_cost(struct nir_shader *, struct nir_shader *);',
        'static bool ps5_glsl_options_match(const nir_shader_compiler_options *o) {',
        '   if (!o) return false;'
    ]
    for field, value in values.items():
        lines.append(f'   if ((uint64_t)o->{field} != UINT64_C({value})) return false;')
    for field in callbacks:
        expected = 'ac_nir_varying_expression_max_cost' if field == 'varying_expression_max_cost' else 'NULL'
        lines.append(f'   if (o->{field} != {expected}) return false;')
    lines += ['   return true;', '}']
    if cli_args.private_arrays:
        lines += ['static const unsigned ps5_glsl_ssbo_bindings[3][2] = {',
                  *[f'   {{{bindings[0]}, {bindings[1]}}},' for bindings in ssbo_bindings], '};']
    for i, blob in enumerate(blobs):
        lines.append(f'static const uint8_t ps5_glsl_blob_{i}[] = {{')
        for start in range(0, len(blob), 16):
            lines.append('   ' + ', '.join(f'0x{b:02x}' for b in blob[start:start+16]) + ',')
        lines += ['};', f'_Static_assert(sizeof(ps5_glsl_blob_{i}) == {len(blob)}u && '
                  f'sizeof(ps5_glsl_blob_{i}) <= 1048576u, "GLSL blob bound");']
    lines += [
        'static const struct { const uint8_t *data; size_t size; } ps5_glsl_fixtures[] = {',
        *[f'   {{ps5_glsl_blob_{i}, sizeof(ps5_glsl_blob_{i})}},' for i in range(3)],
        '};', '#endif', ''
    ]
    destination = ROOT/'tests/ps5'/('private_glsl_fixtures.h' if cli_args.private_arrays else 'compute_glsl_fixtures.h')
    destination.write_text('\n'.join(lines))
    print(f'Exported {destination.relative_to(ROOT)}; receipt sha256={receipt_hash}')


if cli_args.export_header:
    # Compile-only target gate is opt-in; normal host runs need no PS5 SDK.
    gate = subprocess.run([sys.executable, str(HERE/'check_target_abi.py')],
                          cwd=ROOT, text=True, capture_output=True, timeout=240)
    (OUT/'target-abi.log').write_text(gate.stdout + gate.stderr)
    print(gate.stdout + gate.stderr)
    if gate.returncode:
        raise SystemExit('Target ABI gate failed; header not exported')
    witness = re.search(r'PASS host/native \.psbc_glsl_abi: (\d+) identical bytes; sha256=([0-9a-f]{64})',
                        gate.stdout)
    assert witness, 'missing target ABI witness; header not exported'
    export_header({'bytes': int(witness[1]), 'sha256': witness[2], 'compile_only': True})
