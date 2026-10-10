// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* No-draw acceptance gate for the GFX10 merged VS+TCS AGC package. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ps5_agc_package.h"

#define WORK_BYTES 0x4000u

extern int sceAgcInit(uint32_t);
extern int sceAgcCreateShader(void **, void *, void *);
extern int64_t sceKernelGetDirectMemorySize(void);
extern int32_t sceKernelAllocateDirectMemory(int64_t, int64_t, size_t, size_t,
                                             int, int64_t *);
extern int32_t sceKernelMapDirectMemory(void **, size_t, int, int, int64_t,
                                       size_t);
extern int32_t sceKernelReleaseDirectMemory(int64_t, size_t);

static int
sections(const uint8_t *elf, size_t size, const uint8_t **header,
         size_t *header_size, const uint8_t **code, size_t *code_size)
{
   uint64_t table;
   uint16_t entry_size, count, names_index;

   if (size < 64 || memcmp(elf, "\177ELF", 4))
      return -1;
   memcpy(&table, elf + 40, 8);
   memcpy(&entry_size, elf + 58, 2);
   memcpy(&count, elf + 60, 2);
   memcpy(&names_index, elf + 62, 2);
   if (entry_size < 64 || names_index >= count || table > size ||
       count > (size - (size_t)table) / entry_size)
      return -1;

   const uint8_t *names_record = elf + table + names_index * entry_size;
   uint64_t names_at, names_size;
   memcpy(&names_at, names_record + 24, 8);
   memcpy(&names_size, names_record + 32, 8);
   if (names_at > size || names_size > size - (size_t)names_at)
      return -1;

   *header = *code = NULL;
   for (uint16_t i = 0; i < count; ++i) {
      const uint8_t *record = elf + table + i * entry_size;
      uint32_t name_at;
      uint64_t at, bytes;
      memcpy(&name_at, record, 4);
      memcpy(&at, record + 24, 8);
      memcpy(&bytes, record + 32, 8);
      if (name_at >= names_size || at > size || bytes > size - (size_t)at ||
          !memchr(elf + names_at + name_at, 0, names_size - name_at))
         return -1;
      const char *name = (const char *)elf + names_at + name_at;
      if (!strcmp(name, ".shader_header")) {
         *header = elf + at;
         *header_size = bytes;
      } else if (!strcmp(name, ".shader_text")) {
         *code = elf + at;
         *code_size = bytes;
      }
   }
   return *header && *code ? 0 : -1;
}

int
main(void)
{
   const uint32_t end_program = UINT32_C(0xbf810000);
   PsbcShaderOutput shader = {0};
   uint8_t *package = NULL, *memory = NULL;
   size_t package_size = 0, header_size = 0, code_size = 0;
   const uint8_t *header, *code;
   int64_t direct = 0;
   void *program = NULL;
   int result = 1, init_rc = -1, create_rc = -1;

   shader.machine_code = (void *)&end_program;
   shader.machine_code_size = sizeof(end_program);
   shader.metadata.version = PSBC_SHADER_METADATA_VERSION;
   shader.metadata.target = PSBC_TARGET_PS5;
   shader.metadata.source_stage = PSBC_STAGE_TESS_CTRL;
   shader.metadata.hardware_stage = PSBC_HW_STAGE_HULL;
   shader.metadata.unresolved_fields = PSBC_UNRESOLVED_PROGRAM_CHECKSUM;
   shader.metadata.shader_register_count = 2;
   shader.metadata.shader_registers[0].offset = 0x148;
   shader.metadata.shader_registers[1].offset = 0x10a;

   if (ps5_agc_package_build(&shader, 0, &package, &package_size) ||
       sections(package, package_size, &header, &header_size, &code,
                &code_size) || header[90] != 3)
      goto done;
   if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(),
                                     WORK_BYTES, 0x4000, 12, &direct) ||
       sceKernelMapDirectMemory((void **)&memory, WORK_BYTES, 0x33, 0, direct,
                                0x4000))
      goto done;
   memcpy(memory, header, header_size);
   memcpy(memory + 0x1000, code, code_size);
   init_rc = sceAgcInit(8);
   if (!init_rc)
      create_rc = sceAgcCreateShader(&program, memory, memory + 0x1000);
   result = init_rc || create_rc || !program;

done:
   printf("[ps5-tess-hull-package] init=%d create=%d selector=3 pgm=0148 result=%d\n",
          init_rc, create_rc, result);
   fflush(stdout);
   if (memory)
      sceKernelReleaseDirectMemory(direct, WORK_BYTES);
   free(package);
   return result;
}
