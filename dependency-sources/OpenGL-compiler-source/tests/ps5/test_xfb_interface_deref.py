#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise Mesa's real XFB name resolver on structs and interface blocks."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'third_party/mesa-26.2.0/src/compiler/glsl/gl_nir_lower_xfb_varying.c').read_text()
def function(marker):
    start = source.index(marker)
    return source[start:source.index('\n}', start) + 2]
code = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "psbc_compile.h"
''' + function('static char*\nget_field_name(') + '\n' + function('static bool\nget_deref(') + r'''
int main(void) {
 psbc_init();
 nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_VERTEX,
      psbc_get_nir_options(PSBC_STAGE_VERTEX), "xfb-interface");
 struct glsl_struct_field field={.name="attrib",.type=glsl_array_type(glsl_vec4_type(),16,0)};
 const struct glsl_type *types[2]={
   glsl_struct_type(&field,1,"StructData",false),
   glsl_interface_type(&field,1,GLSL_INTERFACE_PACKING_PACKED,false,"StageData")};
 for(unsigned t=0;t<2;++t) for(unsigned index=0;index<16;++index) {
   nir_variable *var=nir_variable_create(b.shader,nir_var_shader_out,types[t],"vs_out");
   char name[64]; snprintf(name,sizeof(name),"StageData.attrib[%u]",index);
   nir_deref_instr *deref=NULL; const struct glsl_type *type=NULL;
   assert(get_deref(&b,name,var,&deref,&type));
   assert(type==glsl_vec4_type() && deref->deref_type==nir_deref_type_array);
   assert(nir_src_as_uint(deref->arr.index)==index);
 }
 for(unsigned outer=0;outer<3;++outer) for(unsigned index=0;index<16;++index) {
   const struct glsl_type *member=field.type;
   nir_variable *var=nir_variable_create(b.shader,nir_var_shader_out,
      outer ? glsl_array_type(member,3,0) : member,"attrib");
   var->data.from_named_ifc_block=1;
   var->interface_type=outer ? glsl_array_type(types[1],3,0) : types[1];
   char name[64];
   if(outer) snprintf(name,sizeof(name),"StageData[%u].attrib[%u]",outer,index);
   else snprintf(name,sizeof(name),"StageData.attrib[%u]",index);
   nir_deref_instr *deref=NULL; const struct glsl_type *type=NULL;
   assert(get_deref(&b,name,var,&deref,&type));
   assert(type==glsl_vec4_type() && deref->deref_type==nir_deref_type_array);
   assert(nir_src_as_uint(deref->arr.index)==index);
   nir_deref_instr *parent=nir_src_as_deref(deref->parent);
   if(outer) {
      assert(parent->deref_type==nir_deref_type_array);
      assert(nir_src_as_uint(parent->arr.index)==outer);
      parent=nir_src_as_deref(parent->parent);
   }
   assert(parent->deref_type==nir_deref_type_var && parent->var==var);
 }
 ralloc_free(b.shader); psbc_shutdown();
}
'''
with tempfile.TemporaryDirectory() as directory:
    exe = str(Path(directory) / 'check')
    obj = exe + '.o'
    psbc = root / 'third_party/opengnm-psbc'
    subprocess.run(['clang-18', '-std=gnu11', '-Wall', '-Werror',
                    '-DHAVE_ENDIAN_H=1', '-DHAVE_FUNC_ATTRIBUTE_PACKED=1',
                    '-DHAVE_PTHREAD=1', '-DHAVE_STRUCT_TIMESPEC=1', '-D_GNU_SOURCE',
                    *['-I'+str(psbc/p) for p in ('include/mesa','include','src','src/gallium/include','libpsbc')],
                    '-x','c','-c','-o',obj,'-'], input=code,text=True,check=True)
    subprocess.run(['g++','-o',exe,obj,str(psbc/'libpsbc.a'),'-pthread','-lm'],check=True)
    subprocess.run([exe],check=True)
print('PASS: struct, interface and lowered interface/array XFB members, all 16 indices')
