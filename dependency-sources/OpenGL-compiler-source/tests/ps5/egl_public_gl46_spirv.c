// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>

#include "gl46_spirv_vert.inc"
#include "gl46_spirv_frag.inc"

#define WIDTH 1920
#define HEIGHT 1080

int ps5_egl_current_draw_status(unsigned *draw_calls);

static int
load_spirv(GLenum type, const void *binary, GLsizei size,
           PFNGLSPECIALIZESHADERPROC specialize, GLuint *result)
{
   GLuint shader = glCreateShader(type);
   GLint ok = GL_FALSE;

   glShaderBinary(1, &shader, GL_SHADER_BINARY_FORMAT_SPIR_V, binary, size);
   specialize(shader, "main", 0, NULL, NULL);
   glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
   if (!ok) {
      char log[1024];
      GLsizei length = 0;
      glGetShaderInfoLog(shader, sizeof(log), &length, log);
      printf("[ps5-egl-gl46-spirv] specialize type=0x%x log=%.*s\n",
             type, length, log);
      glDeleteShader(shader);
      return -1;
   }
   *result = shader;
   return 0;
}

int
main(void)
{
   const EGLint config_attribs[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_NONE,
   };
   const EGLint context_attribs[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE,
   };
   EGLDisplay display = EGL_NO_DISPLAY;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext context = EGL_NO_CONTEXT;
   EGLConfig config = NULL;
   EGLint count = 0;
   PFNGLSPECIALIZESHADERPROC specialize = NULL;
   GLuint vs = 0, fs = 0, program = 0, vao = 0;
   GLint major = 0, minor = 0, linked = GL_FALSE;
   GLint formats = 0, format = 0, spirv_extensions = 0;
   unsigned char pixel[4] = {0};
   unsigned draws = 0;
   int status = -1, current = 0, passed = 0;
   GLenum error = GL_NO_ERROR;

   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL) ||
       !eglBindAPI(EGL_OPENGL_API) ||
       !eglChooseConfig(display, config_attribs, &config, 1, &count) || count != 1)
      goto cleanup;
   surface = eglCreateWindowSurface(display, config, (EGLNativeWindowType)0, NULL);
   context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attribs);
   if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT ||
       !eglMakeCurrent(display, surface, surface, context) || !eglSwapInterval(display, 0))
      goto cleanup;
   current = 1;
   glGetIntegerv(GL_MAJOR_VERSION, &major);
   glGetIntegerv(GL_MINOR_VERSION, &minor);
   glGetIntegerv(GL_NUM_SHADER_BINARY_FORMATS, &formats);
   if (formats == 1)
      glGetIntegerv(GL_SHADER_BINARY_FORMATS, &format);
   glGetIntegerv(GL_NUM_SPIR_V_EXTENSIONS, &spirv_extensions);
   specialize = (PFNGLSPECIALIZESHADERPROC)eglGetProcAddress("glSpecializeShader");
   if (major != 4 || minor != 6 || formats != 1 ||
       format != GL_SHADER_BINARY_FORMAT_SPIR_V || !specialize ||
       load_spirv(GL_VERTEX_SHADER, gl46_spirv_vert_spv,
                  gl46_spirv_vert_spv_len, specialize, &vs) != 0 ||
       load_spirv(GL_FRAGMENT_SHADER, gl46_spirv_frag_spv,
                  gl46_spirv_frag_spv_len, specialize, &fs) != 0)
      goto cleanup;

   program = glCreateProgram();
   glAttachShader(program, vs);
   glAttachShader(program, fs);
   glLinkProgram(program);
   glGetProgramiv(program, GL_LINK_STATUS, &linked);
   if (!linked)
      goto cleanup;
   glUseProgram(program);
   glGenVertexArrays(1, &vao);
   glBindVertexArray(vao);
   glViewport(0, 0, WIDTH, HEIGHT);
   glClearColor(0, 0, 0, 1);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_TRIANGLES, 0, 3);
   glFinish();
   status = ps5_egl_current_draw_status(&draws);
   glReadPixels(WIDTH / 2, HEIGHT / 2, 1, 1, GL_RGBA,
                GL_UNSIGNED_BYTE, pixel);
   error = glGetError();
   passed = linked && pixel[0] < 32 && pixel[1] > 200 && pixel[2] < 32 &&
            status == 0 && draws == 2 && error == GL_NO_ERROR;
   printf("[ps5-egl-gl46-spirv] core=%d.%d formats=%d/0x%x extensions=%d "
          "linked=%d pixel=%02x%02x%02x%02x status=%d draws=%u "
          "error=0x%x result=%s\n",
          major, minor, formats, format, spirv_extensions, linked,
          pixel[0], pixel[1], pixel[2], pixel[3], status, draws, error,
          passed ? "pass" : "fail");

cleanup:
   if (vao) glDeleteVertexArrays(1, &vao);
   if (program) glDeleteProgram(program);
   if (fs) glDeleteShader(fs);
   if (vs) glDeleteShader(vs);
   if (current) eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
   if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
   if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
   if (display != EGL_NO_DISPLAY) eglTerminate(display);
   return passed ? 0 : 1;
}
