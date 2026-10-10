// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* Adapted from Piglit's arb_compute_shader/execution/basic-ssbo.shader_test
 * at db0cf385b514bc107d0c66810689fe39b74d4474. Piglit's standard MIT license
 * applies to the adapted test logic; see tests/piglit/README.md. */

#include <stdint.h>
#include <stdio.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>

#define TAG "[ps5-piglit-basic-ssbo] "
#define SIZE 256

static GLuint
compile_compute(const char *source)
{
   GLuint shader = glCreateShader(GL_COMPUTE_SHADER);
   GLint compiled = GL_FALSE;
   glShaderSource(shader, 1, &source, NULL);
   glCompileShader(shader);
   glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
   if (!compiled) {
      char log[1024] = {0};
      glGetShaderInfoLog(shader, sizeof(log), NULL, log);
      printf(TAG "compile failed: %s\n", log);
      glDeleteShader(shader);
      return 0;
   }
   return shader;
}

int
main(void)
{
   static const char *source =
      "#version 430 core\n"
      "layout(local_size_x=256) in;\n"
      "layout(binding=0, offset=0) uniform atomic_uint counter;\n"
      "layout(std430, binding=0) buffer Data { uint u[256]; };\n"
      "uniform uint mode;\n"
      "void main(){uint i=gl_LocalInvocationIndex;"
      "if(mode==0u)u[i]=256u;else if(mode==1u)u[i]=i;"
      "else if(mode==2u){if(u[i]==256u)atomicCounterIncrement(counter);}"
      "else if(mode==3u){if(u[i]==i)atomicCounterIncrement(counter);}}\n";
   static const GLuint modes[] = {0, 3, 2, 1, 2, 3};
   static const GLuint expected[] = {0, 0, 256, 256, 256, 512};
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
   GLuint shader = 0, program = 0, buffers[2] = {0};
   GLint linked = GL_FALSE, mode_location = -1;
   GLuint counter = 0, words[SIZE] = {0};
   int current = 0, passed = 0;

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

   shader = compile_compute(source);
   if (!shader)
      goto cleanup;
   program = glCreateProgram();
   glAttachShader(program, shader);
   glLinkProgram(program);
   glGetProgramiv(program, GL_LINK_STATUS, &linked);
   if (!linked)
      goto cleanup;
   mode_location = glGetUniformLocation(program, "mode");
   glGenBuffers(2, buffers);
   glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[0]);
   glBufferData(GL_SHADER_STORAGE_BUFFER, sizeof(words), words, GL_DYNAMIC_COPY);
   glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, buffers[0]);
   glBindBuffer(GL_ATOMIC_COUNTER_BUFFER, buffers[1]);
   glBufferData(GL_ATOMIC_COUNTER_BUFFER, sizeof(counter), &counter, GL_DYNAMIC_COPY);
   glBindBufferBase(GL_ATOMIC_COUNTER_BUFFER, 0, buffers[1]);
   glUseProgram(program);

   for (unsigned step = 0; step < sizeof(modes) / sizeof(modes[0]); ++step) {
      glUniform1ui(mode_location, modes[step]);
      glDispatchCompute(1, 1, 1);
      glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT |
                      GL_ATOMIC_COUNTER_BARRIER_BIT |
                      GL_BUFFER_UPDATE_BARRIER_BIT);
      glBindBuffer(GL_ATOMIC_COUNTER_BUFFER, buffers[1]);
      glGetBufferSubData(GL_ATOMIC_COUNTER_BUFFER, 0, sizeof(counter), &counter);
      printf(TAG "step=%u mode=%u counter=%u expected=%u\n",
             step, modes[step], counter, expected[step]);
      if (counter != expected[step] || glGetError() != GL_NO_ERROR)
         goto cleanup;
   }
   glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[0]);
   glGetBufferSubData(GL_SHADER_STORAGE_BUFFER, 0, sizeof(words), words);
   for (unsigned i = 0; i < SIZE; ++i) {
      if (words[i] != i)
         goto cleanup;
   }
   passed = glGetError() == GL_NO_ERROR;

cleanup:
   if (current) {
      glFinish();
      glBindBufferBase(GL_ATOMIC_COUNTER_BUFFER, 0, 0);
      glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, 0);
      glDeleteBuffers(2, buffers);
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
