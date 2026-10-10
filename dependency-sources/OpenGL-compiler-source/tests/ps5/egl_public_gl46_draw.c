// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>

#define WIDTH 1920
#define HEIGHT 1080

int ps5_egl_current_draw_status(unsigned *draw_calls);

static GLuint
shader(GLenum type, const char *source)
{
   GLuint object = glCreateShader(type);
   GLint ok = GL_FALSE;

   glShaderSource(object, 1, &source, NULL);
   glCompileShader(object);
   glGetShaderiv(object, GL_COMPILE_STATUS, &ok);
   if (!ok) {
      char log[1024];
      GLsizei length = 0;
      glGetShaderInfoLog(object, sizeof(log), &length, log);
      printf("[ps5-egl-gl46-draw] compile type=0x%x log=%.*s\n",
             type, length, log);
      glDeleteShader(object);
      return 0;
   }
   return object;
}

int
main(void)
{
   static const char *vs_source =
      "#version 460\n"
      "layout(location=0) in vec2 p;\n"
      "flat out int id;\n"
      "void main() {\n"
      " bool ok = allInvocations(true) && anyInvocation(true) &&\n"
      "           allInvocationsEqual(gl_DrawID == 0) &&\n"
      "           gl_BaseVertex == 0 && gl_BaseInstance == 0;\n"
      " id = ok ? gl_DrawID : -1;\n"
      " float x = gl_DrawID == 0 ? -0.4 : 0.4;\n"
      " gl_Position = vec4(p + vec2(x, 0.0), 0.0, 1.0);\n"
      "}\n";
   static const char *fs_source =
      "#version 460\n"
      "layout(binding=0) uniform sampler2D image;\n"
      "flat in int id; layout(location=0) out vec4 color;\n"
      "void main() { color = texture(image, vec2(0.5)) *\n"
      " (id == 0 ? vec4(1,0,0,1) : id == 1 ? vec4(0,1,0,1) : vec4(0,0,1,1)); }\n";
   static const float vertices[] = {
      -0.25f, -0.3f, 0.25f, -0.3f, 0.0f, 0.3f,
   };
   static const GLuint indirect[] = {3, 1, 0, 0, 3, 1, 0, 0};
   static const GLuint draw_count = 2;
   static const unsigned char white[] = {255, 255, 255, 255};
   const EGLint config_attribs[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_DEPTH_SIZE, 32, EGL_NONE,
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
   GLuint vs = 0, fs = 0, program = 0, vao = 0, vbo = 0;
   GLuint indirect_buffer = 0, count_buffer = 0, texture = 0;
   PFNGLMULTIDRAWARRAYSINDIRECTCOUNTPROC multi_draw_count;
   PFNGLPOLYGONOFFSETCLAMPPROC polygon_offset_clamp;
   GLint linked = GL_FALSE, major = 0, minor = 0;
   GLfloat anisotropy = 0.0f, max_anisotropy = 0.0f;
   unsigned char left[4] = {0}, right[4] = {0};
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
   multi_draw_count = (PFNGLMULTIDRAWARRAYSINDIRECTCOUNTPROC)
      eglGetProcAddress("glMultiDrawArraysIndirectCount");
   polygon_offset_clamp = (PFNGLPOLYGONOFFSETCLAMPPROC)
      eglGetProcAddress("glPolygonOffsetClamp");
   if (major != 4 || minor != 6 || !multi_draw_count || !polygon_offset_clamp)
      goto cleanup;

   vs = shader(GL_VERTEX_SHADER, vs_source);
   fs = shader(GL_FRAGMENT_SHADER, fs_source);
   if (!vs || !fs)
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
   glGenBuffers(1, &vbo);
   glBindBuffer(GL_ARRAY_BUFFER, vbo);
   glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
   glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL);
   glEnableVertexAttribArray(0);
   glGenBuffers(1, &indirect_buffer);
   glBindBuffer(GL_DRAW_INDIRECT_BUFFER, indirect_buffer);
   glBufferData(GL_DRAW_INDIRECT_BUFFER, sizeof(indirect), indirect, GL_STATIC_DRAW);
   glGenBuffers(1, &count_buffer);
   glBindBuffer(GL_PARAMETER_BUFFER_ARB, count_buffer);
   glBufferData(GL_PARAMETER_BUFFER_ARB, sizeof(draw_count), &draw_count, GL_STATIC_DRAW);

   glGenTextures(1, &texture);
   glBindTexture(GL_TEXTURE_2D, texture);
   glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 1, 1, 0, GL_RGBA,
                GL_UNSIGNED_BYTE, white);
   glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
   glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
   glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY, 16.0f);
   glGetTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY, &anisotropy);
   glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY, &max_anisotropy);

   glViewport(0, 0, WIDTH, HEIGHT);
   glClearColor(0, 0, 0, 1);
   glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
   glEnable(GL_POLYGON_OFFSET_FILL);
   polygon_offset_clamp(1.0f, 1.0f, 0.25f);
   multi_draw_count(GL_TRIANGLES, NULL, 0, 2, sizeof(GLuint) * 4);
   glFinish();
   status = ps5_egl_current_draw_status(&draws);
   glReadPixels((int)(WIDTH * 0.3f), HEIGHT / 2, 1, 1, GL_RGBA,
                GL_UNSIGNED_BYTE, left);
   glReadPixels((int)(WIDTH * 0.7f), HEIGHT / 2, 1, 1, GL_RGBA,
                GL_UNSIGNED_BYTE, right);
   error = glGetError();
   passed = linked && anisotropy == 16.0f && max_anisotropy >= 16.0f &&
            left[0] > 200 && left[1] < 32 && right[0] < 32 && right[1] > 200 &&
            status == 0 && draws == 3 && error == GL_NO_ERROR;
   printf("[ps5-egl-gl46-draw] core=%d.%d linked=%d aniso=%.1f/%.1f "
          "pixels=%02x%02x%02x%02x/%02x%02x%02x%02x "
          "status=%d draws=%u error=0x%x result=%s\n",
          major, minor, linked, anisotropy, max_anisotropy,
          left[0], left[1], left[2], left[3], right[0], right[1], right[2], right[3],
          status, draws, error, passed ? "pass" : "fail");

cleanup:
   if (texture) glDeleteTextures(1, &texture);
   if (count_buffer) glDeleteBuffers(1, &count_buffer);
   if (indirect_buffer) glDeleteBuffers(1, &indirect_buffer);
   if (vbo) glDeleteBuffers(1, &vbo);
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
