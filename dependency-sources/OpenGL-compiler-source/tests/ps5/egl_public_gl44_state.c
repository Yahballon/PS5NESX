// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>

static GLuint
compile(GLenum type, const char *source)
{
   GLuint shader = glCreateShader(type);
   GLint ok = GL_FALSE;

   glShaderSource(shader, 1, &source, NULL);
   glCompileShader(shader);
   glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
   if (!ok) {
      char log[512] = {0};
      GLsizei length = 0;
      glGetShaderInfoLog(shader, sizeof(log), &length, log);
      printf("[ps5-egl-gl45-state] shader=%x log=%.*s\n", type, length, log);
      glDeleteShader(shader);
      return 0;
   }
   return shader;
}

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
   static const char *vertex_source =
      "#version 450 core\n"
      "layout(location=0) in vec3 p;"
      "layout(location=0,component=1) out float v;"
      "uniform int mode;"
      "void main(){int i=gl_VertexID;"
      "vec2 q=vec2(i==1?0.8:-0.8,i==2?0.8:-0.8);"
      "gl_Position=vec4(q+p.xy*0.001,mode==1?-0.5:0.0,1);"
      "gl_CullDistance[0]=mode==2?-1.0:1.0;v=1.0;}\n";
   static const char *fragment_source =
      "#version 450 core\n"
      "layout(location=0,component=1) in float v;"
      "layout(location=0) out vec4 c;"
      "uniform sampler2DMS ms;"
      "void main(){float d=dFdxFine(gl_FragCoord.x);"
      "c=v>0.0&&abs(d-1.0)<0.01&&textureSamples(ms)==4?"
      "vec4(0,1,0,1):vec4(1,0,0,1);}\n";
   static const uint32_t initial[] = {0x10203040, 0x50607080};
   static const uint32_t packed_vertices[3] = {0, 0, 0};
   const EGLint config_attrs[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_NONE,
   };
   const EGLint context_attrs[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 5,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE,
   };
   EGLDisplay display = EGL_NO_DISPLAY;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext context = EGL_NO_CONTEXT;
   EGLConfig config = NULL;
   EGLint count = 0;
   GLuint shaders[2] = {0}, program = 0, storage = 0, query_buffer = 0;
   GLuint vao = 0, packed_buffer = 0, dsa_buffer = 0;
   GLuint query = 0, texture = 0, ms_texture = 0;
   GLint linked = GL_FALSE, stride = 0;
   uint64_t query_value = 0;
   uint32_t pixel = 0, clip_pixel = 0, cull_pixel = 0;
   uint32_t *mapped = NULL;
   GLenum immutable_error = GL_NO_ERROR, error = GL_NO_ERROR;
   PFNGLCLIPCONTROLPROC clip_control = NULL;
   PFNGLTEXTUREBARRIERPROC texture_barrier = NULL;
   int storage_ok = 0, dsa_ok = 0, query_ok = 0, mirror_ok = 0, passed = 0;

   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL) ||
       !eglBindAPI(EGL_OPENGL_API) ||
       !eglChooseConfig(display, config_attrs, &config, 1, &count) || count != 1)
      goto done;
   surface = eglCreateWindowSurface(display, config, 0, NULL);
   context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
   if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT ||
       !eglMakeCurrent(display, surface, surface, context))
      goto done;

   glCreateBuffers(1, &dsa_buffer);
   glNamedBufferStorage(dsa_buffer, sizeof(initial), initial, GL_MAP_READ_BIT);
   const uint32_t *dsa = glMapNamedBufferRange(
      dsa_buffer, 0, sizeof(initial), GL_MAP_READ_BIT);
   dsa_ok = dsa && !memcmp(dsa, initial, sizeof(initial)) &&
            glUnmapNamedBuffer(dsa_buffer);

   glGetIntegerv(GL_MAX_VERTEX_ATTRIB_STRIDE, &stride);
   clip_control = (PFNGLCLIPCONTROLPROC)eglGetProcAddress("glClipControl");
   texture_barrier =
      (PFNGLTEXTUREBARRIERPROC)eglGetProcAddress("glTextureBarrier");
   if (!clip_control || !texture_barrier)
      goto done;
   shaders[0] = compile(GL_VERTEX_SHADER, vertex_source);
   shaders[1] = compile(GL_FRAGMENT_SHADER, fragment_source);
   if (!shaders[0] || !shaders[1])
      goto done;
   program = glCreateProgram();
   glAttachShader(program, shaders[0]);
   glAttachShader(program, shaders[1]);
   glLinkProgram(program);
   glGetProgramiv(program, GL_LINK_STATUS, &linked);

   glGenBuffers(1, &storage);
   glBindBuffer(GL_ARRAY_BUFFER, storage);
   glBufferStorage(GL_ARRAY_BUFFER, sizeof(initial), initial,
                   GL_MAP_READ_BIT | GL_MAP_WRITE_BIT | GL_MAP_PERSISTENT_BIT |
                   GL_MAP_COHERENT_BIT | GL_DYNAMIC_STORAGE_BIT);
   mapped = glMapBufferRange(GL_ARRAY_BUFFER, 0, sizeof(initial),
                             GL_MAP_READ_BIT | GL_MAP_WRITE_BIT |
                             GL_MAP_PERSISTENT_BIT | GL_MAP_COHERENT_BIT);
   if (mapped) {
      storage_ok = !memcmp(mapped, initial, sizeof(initial));
      mapped[1] ^= UINT32_C(0xffffffff);
   }
   glBufferData(GL_ARRAY_BUFFER, sizeof(initial), initial, GL_STATIC_DRAW);
   immutable_error = glGetError();

   glGenQueries(1, &query);
   glGenVertexArrays(1, &vao);
   glBindVertexArray(vao);
   glGenBuffers(1, &packed_buffer);
   glBindBuffer(GL_ARRAY_BUFFER, packed_buffer);
   glBufferData(GL_ARRAY_BUFFER, sizeof(packed_vertices), packed_vertices,
                GL_STATIC_DRAW);
   glVertexAttribPointer(0, 3, GL_UNSIGNED_INT_10F_11F_11F_REV, GL_FALSE,
                         sizeof(uint32_t), NULL);
   glEnableVertexAttribArray(0);
   glUseProgram(program);
   glUniform1i(glGetUniformLocation(program, "ms"), 0);
   glGenTextures(1, &ms_texture);
   glActiveTexture(GL_TEXTURE0);
   glBindTexture(GL_TEXTURE_2D_MULTISAMPLE, ms_texture);
   glTexImage2DMultisample(GL_TEXTURE_2D_MULTISAMPLE, 4, GL_RGBA8,
                           1, 1, GL_TRUE);
   glViewport(0, 0, 64, 64);
   glClearColor(0, 0, 0, 1);
   glBeginQuery(GL_TIME_ELAPSED, query);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_TRIANGLES, 0, 3);
   glEndQuery(GL_TIME_ELAPSED);
   glReadPixels(16, 16, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, &pixel);
   texture_barrier();
   glUniform1i(glGetUniformLocation(program, "mode"), 1);
   clip_control(GL_LOWER_LEFT, GL_ZERO_TO_ONE);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_TRIANGLES, 0, 3);
   glReadPixels(16, 16, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, &clip_pixel);
   glUniform1i(glGetUniformLocation(program, "mode"), 2);
   clip_control(GL_LOWER_LEFT, GL_NEGATIVE_ONE_TO_ONE);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_TRIANGLES, 0, 3);
   glReadPixels(16, 16, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, &cull_pixel);
   glGenBuffers(1, &query_buffer);
   glBindBuffer(GL_QUERY_BUFFER, query_buffer);
   glBufferData(GL_QUERY_BUFFER, sizeof(query_value), NULL, GL_DYNAMIC_READ);
   glGetQueryObjectui64v(query, GL_QUERY_RESULT, 0);
   glBindBuffer(GL_QUERY_BUFFER, 0);
   glBindBuffer(GL_COPY_READ_BUFFER, query_buffer);
   glGetBufferSubData(GL_COPY_READ_BUFFER, 0, sizeof(query_value), &query_value);
   query_ok = query_value != 0;

   glGenTextures(1, &texture);
   glBindTexture(GL_TEXTURE_2D, texture);
   glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_MIRROR_CLAMP_TO_EDGE);
   mirror_ok = glGetError() == GL_NO_ERROR;
   error = glGetError();
   passed = linked && stride >= 2048 && storage_ok && dsa_ok && query_ok && mirror_ok &&
            pixel == UINT32_C(0xff00ff00) &&
            clip_pixel == UINT32_C(0xff000000) &&
            cull_pixel == UINT32_C(0xff000000) &&
            immutable_error == GL_INVALID_OPERATION && error == GL_NO_ERROR &&
            has_extension("GL_ARB_buffer_storage") &&
            has_extension("GL_ARB_enhanced_layouts") &&
            has_extension("GL_ARB_query_buffer_object") &&
            has_extension("GL_ARB_texture_mirror_clamp_to_edge") &&
            has_extension("GL_ARB_vertex_type_10f_11f_11f_rev") &&
            has_extension("GL_ARB_ES3_1_compatibility") &&
            has_extension("GL_ARB_clip_control") &&
            has_extension("GL_ARB_cull_distance") &&
            has_extension("GL_ARB_derivative_control") &&
            has_extension("GL_ARB_shader_texture_image_samples") &&
            has_extension("GL_NV_texture_barrier");

done:
   printf("[ps5-egl-gl45-state] gl=%s glsl=%s stride=%d linked=%d storage=%d dsa=%d "
          "immutable=0x%x query=%llu mirror=%d pixel=%08x clip=%08x "
          "cull=%08x error=0x%x result=%s\n",
          glGetString(GL_VERSION), glGetString(GL_SHADING_LANGUAGE_VERSION),
          stride, linked, storage_ok, dsa_ok, immutable_error,
          (unsigned long long)query_value, mirror_ok, pixel, clip_pixel,
          cull_pixel, error,
          passed ? "pass" : "fail");
   if (mapped) {
      glBindBuffer(GL_ARRAY_BUFFER, storage);
      glUnmapBuffer(GL_ARRAY_BUFFER);
   }
   if (texture)
      glDeleteTextures(1, &texture);
   if (dsa_buffer)
      glDeleteBuffers(1, &dsa_buffer);
   if (ms_texture)
      glDeleteTextures(1, &ms_texture);
   if (query)
      glDeleteQueries(1, &query);
   glDeleteBuffers(1, &packed_buffer);
   glDeleteVertexArrays(1, &vao);
   glDeleteBuffers(1, &query_buffer);
   glDeleteBuffers(1, &storage);
   glDeleteProgram(program);
   glDeleteShader(shaders[0]);
   glDeleteShader(shaders[1]);
   if (display != EGL_NO_DISPLAY)
      eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
   if (context != EGL_NO_CONTEXT)
      eglDestroyContext(display, context);
   if (surface != EGL_NO_SURFACE)
      eglDestroySurface(display, surface);
   if (display != EGL_NO_DISPLAY)
      eglTerminate(display);
   return passed ? 0 : 1;
}
