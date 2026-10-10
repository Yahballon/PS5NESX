// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <assert.h>
#include "compiler/nir/nir_builder.h"
#include "psbc_compile.h"

/* Test-only bounded register lowering; production compiler unchanged. */
static nir_def *private_invocation_index(nir_builder *b) {
    nir_def *local=nir_load_local_invocation_id(b);
    nir_def *group=nir_load_workgroup_id(b);
    nir_def *grid=nir_load_num_workgroups(b);
    const uint16_t *size=b->shader->info.workgroup_size;
    nir_def *local_index=nir_iadd(b,nir_channel(b,local,0),
        nir_imul_imm(b,nir_iadd(b,nir_channel(b,local,1),
            nir_imul_imm(b,nir_channel(b,local,2),size[1])),size[0]));
    nir_def *group_index=nir_iadd(b,nir_channel(b,group,0),
        nir_imul(b,nir_channel(b,grid,0),nir_iadd(b,nir_channel(b,group,1),
            nir_imul(b,nir_channel(b,grid,1),nir_channel(b,group,2)))));
    return nir_iadd(b,local_index,nir_imul_imm(b,group_index,size[0]*size[1]*size[2]));
}
static nir_builder private_array_fixture_shape(unsigned words, const uint16_t size[3]) {
    assert(words>=4 && words<=1024 && !(words&(words-1)));
    assert(size[0] && size[1] && size[2] &&
        (uint64_t)size[0]*size[1]*size[2]<=1024);
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE), "private-array-lowering");
    for (unsigned i=0;i<3;++i) b.shader->info.workgroup_size[i]=size[i];
    b.shader->info.num_ssbos=2;
    b.shader->scratch_size=words*4;
    nir_def *id=private_invocation_index(&b);
    nir_def *input=nir_load_ssbo(&b,3,32,nir_imm_int(&b,1),
        nir_imul_imm(&b,id,12),.align_mul=4);
    nir_def *write_index=nir_iand_imm(&b,nir_channel(&b,input,0),words-1);
    nir_def *read_index=nir_iand_imm(&b,nir_channel(&b,input,1),words-1);
    nir_def *seed=nir_channel(&b,input,2);
    /* Initialize every word, then overwrite/read independently supplied indices.
     * Unlike store(x,i); load(i), the result must select among live values. */
    for (unsigned i=0; i<words; ++i)
        nir_store_scratch(&b,nir_ixor(&b,seed,nir_imm_int(&b,17+37*i)),nir_imm_int(&b,i*4),
            .align_mul=4,.write_mask=1);
    nir_store_scratch(&b,nir_iadd_imm(&b,seed,991),nir_imul_imm(&b,write_index,4),
        .align_mul=4,.write_mask=1);
    nir_def *value=nir_load_scratch(&b,1,32,nir_imul_imm(&b,read_index,4),.align_mul=4);
    nir_store_ssbo(&b,value,nir_imm_int(&b,0),nir_imul_imm(&b,id,4),
        .align_mul=4,.write_mask=1);
    nir_validate_shader(b.shader,"private array before lowering");
    return b;
}
static nir_builder private_array_fixture(unsigned words) {
    const uint16_t size[3]={16,1,1};
    return private_array_fixture_shape(words,size);
}
static void private_array_lower(nir_shader *nir) {
    assert(nir->scratch_size<=128);
    nir_lower_scratch_to_var(nir);
    nir_lower_indirect_derefs_to_if_else_trees(nir,nir_var_function_temp,32);
    nir_lower_vars_to_ssa(nir);
    nir_validate_shader(nir,"private array after lowering");
}
