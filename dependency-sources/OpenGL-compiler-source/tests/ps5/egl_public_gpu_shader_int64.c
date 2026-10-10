// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* Representative BC4 copy shader reduced to one block, with exact operations. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>

#define TAG "[ps5-gpu-shader-int64] "

static int
has_extension(const char *name)
{
   GLint count = 0;
   glGetIntegerv(GL_NUM_EXTENSIONS, &count);
   for (GLint i = 0; i < count; ++i) {
      const char *extension = (const char *)glGetStringi(GL_EXTENSIONS, i);
      if (extension && !strcmp(extension, name))
         return 1;
   }
   return 0;
}

int
main(void)
{
   static const char *source =
      "#version 430 core\n"
      "#extension GL_ARB_gpu_shader_int64 : require\n"
      "layout(local_size_x=4,local_size_y=4) in;\n"
      "layout(binding=0,rg32ui) readonly uniform uimage3D bc4_input;\n"
      "layout(binding=1,rgba8ui) writeonly uniform uimage3D bc4_output;\n"
      "uint decompress(uint64_t bits,uvec2 p){\n"
      " uint shift=16u+3u*(4u*p.y+p.x);\n"
      " uint code=uint(bits>>shift)&7u;\n"
      " uint r0=uint(bits)&255u,r1=uint(bits>>8)&255u;\n"
      " if(code==0u)return r0;if(code==1u)return r1;\n"
      " if(r0>r1)return ((8u-code)*r0+(code-1u)*r1)/7u;\n"
      " if(code==6u)return 0u;if(code==7u)return 255u;\n"
      " return ((6u-code)*r0+(code-1u)*r1)/5u;}\n"
      "void main(){uvec2 p=imageLoad(bc4_input,ivec3(gl_WorkGroupID)).rg;\n"
      " uint r=decompress(packUint2x32(p),gl_LocalInvocationID.xy);\n"
      " imageStore(bc4_output,ivec3(gl_GlobalInvocationID),uvec4(r,0,0,255));}\n";
   const EGLint config_attrs[] = {
      EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_NONE,
   };
   const EGLint surface_attrs[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE};
   const EGLint context_attrs[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE,
   };
   EGLDisplay display = EGL_NO_DISPLAY;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext context = EGL_NO_CONTEXT;
   EGLConfig config = NULL;
   EGLint count = 0;
   GLuint shader = 0, program = 0, textures[2] = {0};
   uint32_t packed[2] = {0x0000140a, 0};
   uint8_t pixels[4 * 4 * 4] = {0};
   GLint status = GL_FALSE;
   int current = 0, passed = 0;

   setvbuf(stdout, NULL, _IONBF, 0);
   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL) ||
       !eglBindAPI(EGL_OPENGL_API) ||
       !eglChooseConfig(display, config_attrs, &config, 1, &count) || count != 1)
      goto cleanup;
   surface = eglCreatePbufferSurface(display, config, surface_attrs);
   context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
   if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT ||
       !eglMakeCurrent(display, surface, surface, context))
      goto cleanup;
   current = 1;
   if (!has_extension("GL_ARB_gpu_shader_int64")) {
      puts(TAG "extension missing");
      goto cleanup;
   }

   shader = glCreateShader(GL_COMPUTE_SHADER);
   glShaderSource(shader, 1, &source, NULL);
   glCompileShader(shader);
   glGetShaderiv(shader, GL_COMPILE_STATUS, &status);
   if (!status) {
      char log[4096] = {0};
      glGetShaderInfoLog(shader, sizeof(log), NULL, log);
      printf(TAG "compile failed: %s\n", log);
      goto cleanup;
   }
   program = glCreateProgram();
   glAttachShader(program, shader);
   glLinkProgram(program);
   glGetProgramiv(program, GL_LINK_STATUS, &status);
   if (!status)
      goto cleanup;

   glGenTextures(2, textures);
   glBindTexture(GL_TEXTURE_3D, textures[0]);
   glTexStorage3D(GL_TEXTURE_3D, 1, GL_RG32UI, 1, 1, 1);
   glTexSubImage3D(GL_TEXTURE_3D, 0, 0, 0, 0, 1, 1, 1,
                   GL_RG_INTEGER, GL_UNSIGNED_INT, packed);
   glBindTexture(GL_TEXTURE_3D, textures[1]);
   glTexStorage3D(GL_TEXTURE_3D, 1, GL_RGBA8UI, 4, 4, 1);
   glBindImageTexture(0, textures[0], 0, GL_TRUE, 0, GL_READ_ONLY, GL_RG32UI);
   glBindImageTexture(1, textures[1], 0, GL_TRUE, 0, GL_WRITE_ONLY, GL_RGBA8UI);
   glUseProgram(program);
   glDispatchCompute(1, 1, 1);
   glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT | GL_TEXTURE_UPDATE_BARRIER_BIT);
   glBindTexture(GL_TEXTURE_3D, textures[1]);
   glGetTexImage(GL_TEXTURE_3D, 0, GL_RGBA_INTEGER, GL_UNSIGNED_BYTE, pixels);
   glFinish();
   if (glGetError() != GL_NO_ERROR)
      goto cleanup;
   passed = 1;
   for (unsigned i = 0; i < 16; ++i) {
      const uint8_t *pixel = &pixels[4 * i];
      if (pixel[0] != 10 || pixel[1] || pixel[2] || pixel[3] != 255) {
         printf(TAG "pixel=%u rgba=%u,%u,%u,%u\n", i,
                pixel[0], pixel[1], pixel[2], pixel[3]);
         passed = 0;
         break;
      }
   }

cleanup:
   if (current) {
      glFinish();
      glBindImageTexture(0, 0, 0, GL_FALSE, 0, GL_READ_ONLY, GL_R8);
      glBindImageTexture(1, 0, 0, GL_FALSE, 0, GL_READ_ONLY, GL_R8);
      glDeleteTextures(2, textures);
      if (program) glDeleteProgram(program);
      if (shader) glDeleteShader(shader);
      eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
   }
   if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
   if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
   if (display != EGL_NO_DISPLAY) eglTerminate(display);
   printf(TAG "result=%s\n", passed ? "PASS" : "FAIL");
   return passed ? 0 : 1;
}
