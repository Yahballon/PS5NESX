// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "private_array_fixture.h"

/* Test-only: scalar uint accesses, fixture-owned SSBO slot 2.
 * Each invocation gets two guard words around its private region. This is not
 * a production binding policy and does not lower ACO register spills. */
static bool private_buffer_intrinsic(nir_builder *b, nir_intrinsic_instr *intr, void *data) {
    const unsigned words=*(const unsigned *)data;
    bool store=intr->intrinsic==nir_intrinsic_store_scratch;
    if (!store && intr->intrinsic!=nir_intrinsic_load_scratch) return false;
    nir_def *value=store?intr->src[0].ssa:&intr->def;
    assert(value->bit_size==32 && value->num_components==1);
    assert(nir_intrinsic_align_mul(intr)>=4);
    b->cursor=nir_before_instr(&intr->instr);
    nir_def *id=private_invocation_index(b);
    nir_def *offset=nir_iadd(b,nir_iadd_imm(b,nir_imul_imm(b,id,(words+2)*4),4),
        intr->src[store?1:0].ssa);
    if (store)
        nir_store_ssbo(b,value,nir_imm_int(b,2),offset,
            .align_mul=4,.write_mask=1,.access=ACCESS_VOLATILE);
    else {
        nir_barrier(b,.memory_scope=SCOPE_INVOCATION,
            .memory_semantics=NIR_MEMORY_ACQ_REL,.memory_modes=nir_var_mem_ssbo);
        nir_def_rewrite_uses(value,nir_load_ssbo(b,1,32,nir_imm_int(b,2),offset,
            .align_mul=4,.access=ACCESS_VOLATILE));
    }
    nir_instr_remove(&intr->instr);
    return true;
}
static void private_buffer_lower(nir_shader *nir) {
    assert(nir->info.stage==MESA_SHADER_COMPUTE && nir->info.num_ssbos==2);
    assert(nir->info.workgroup_size[0] && nir->info.workgroup_size[1] &&
        nir->info.workgroup_size[2]);
    unsigned words=nir->scratch_size/4;
    assert(words>=4 && words<=1024 && !(words&(words-1)) && nir->scratch_size==words*4);
    assert(nir_shader_intrinsics_pass(nir,private_buffer_intrinsic,nir_metadata_control_flow,&words));
    nir->scratch_size=0;
    nir->info.num_ssbos=3;
    nir_validate_shader(nir,"bounded application-owned private buffer");
}
