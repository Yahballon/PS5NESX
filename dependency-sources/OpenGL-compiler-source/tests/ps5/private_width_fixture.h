// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "private_array_fixture.h"

static nir_builder private_width_fixture(unsigned bits) {
    assert(bits==8 || bits==16 || bits==32 || bits==64);
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE),"private-width-native");
    b.shader->info.workgroup_size[0]=2;
    b.shader->info.workgroup_size[1]=2;
    b.shader->info.workgroup_size[2]=4;
    b.shader->info.num_ssbos=2;
    b.shader->scratch_size=1024;
    nir_def *id=private_invocation_index(&b);
    nir_def *seed=nir_load_ssbo(&b,1,32,nir_imm_int(&b,1),
        nir_iadd_imm(&b,nir_imul_imm(&b,id,12),8),.align_mul=4);
    nir_def *value=bits==64
        ? nir_replicate(&b,nir_pack_64_2x32_split(&b,seed,
            nir_ixor(&b,seed,nir_imm_int(&b,UINT32_C(0xa5a55a5a)))),2)
        : nir_replicate(&b,nir_u2uN(&b,seed,bits),4);
    const unsigned components=bits==64?2:4;
    nir_def *offset=nir_imul_imm(&b,nir_iand_imm(&b,id,63),16);
    nir_store_scratch(&b,value,offset,.align_mul=bits/8,
        .write_mask=BITFIELD_MASK(components));
    nir_def *loaded=nir_load_scratch(&b,components,bits,offset,.align_mul=bits/8);
    nir_def *result=nir_bcsel(&b,nir_ball_iequal(&b,loaded,value),seed,nir_imm_int(&b,0));
    nir_store_ssbo(&b,result,nir_imm_int(&b,0),nir_imul_imm(&b,id,4),
        .align_mul=4,.write_mask=1);
    nir_validate_shader(b.shader,"private width before compiler lowering");
    return b;
}
