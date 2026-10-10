// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdint.h>
#include <stdio.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>

#define SIZE 64

int ps5_egl_current_draw_status(unsigned *draw_calls);

static GLuint
shader(GLenum type, const char *source)
{
   GLint ok = GL_FALSE;
   GLuint result = glCreateShader(type);

   glShaderSource(result, 1, &source, NULL);
   glCompileShader(result);
   glGetShaderiv(result, GL_COMPILE_STATUS, &ok);
   if (!ok) {
      char log[1024] = {0};
      GLsizei length = 0;
      glGetShaderInfoLog(result, sizeof(log), &length, log);
      printf("[ps5-egl-tessellation] shader=%x log=%.*s\n",
             type, length, log);
      glDeleteShader(result);
      return 0;
   }
   return result;
}

static GLuint
program(const char *const *sources, const GLenum *types, unsigned count)
{
   GLuint shaders[5] = {0};
   GLuint result = glCreateProgram();
   GLint ok = GL_FALSE;

   for (unsigned i = 0; i < count; ++i) {
      shaders[i] = shader(types[i], sources[i]);
      if (!shaders[i])
         goto done;
      glAttachShader(result, shaders[i]);
   }
   glLinkProgram(result);
   glGetProgramiv(result, GL_LINK_STATUS, &ok);
   if (!ok) {
      char log[1024] = {0};
      GLsizei length = 0;
      glGetProgramInfoLog(result, sizeof(log), &length, log);
      printf("[ps5-egl-tessellation] link=%.*s\n", length, log);
   }
done:
   for (unsigned i = 0; i < count; ++i)
      glDeleteShader(shaders[i]);
   if (!ok) {
      glDeleteProgram(result);
      result = 0;
   }
   return result;
}

static unsigned
matching(uint32_t color)
{
   static uint32_t pixels[SIZE * SIZE];
   unsigned result = 0;

   glReadPixels(0, 0, SIZE, SIZE, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
   for (unsigned i = 0; i < SIZE * SIZE; ++i)
      result += pixels[i] == color;
   return result;
}

/* Separate final-stage layer/viewport routing from upstream distance I/O.
 * Both texture layers and both viewport halves are checked after every draw. */
static int
layered_routing(const char *const *tess_sources)
{
   const GLenum types[] = {GL_VERTEX_SHADER, GL_TESS_CONTROL_SHADER,
      GL_TESS_EVALUATION_SHADER, GL_GEOMETRY_SHADER, GL_FRAGMENT_SHADER};
   GLuint texture = 0, fbo = 0;
   static uint32_t pixels[2 * SIZE * SIZE];
   int passed = 1;
   glGenTextures(1, &texture);
   glBindTexture(GL_TEXTURE_2D_ARRAY, texture);
   glTexImage3D(GL_TEXTURE_2D_ARRAY, 0, GL_RGBA8, SIZE, SIZE, 2, 0,
                GL_RGBA, GL_UNSIGNED_BYTE, NULL);
   glGenFramebuffers(1, &fbo);
   glBindFramebuffer(GL_FRAMEBUFFER, fbo);
   glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, texture, 0);
   if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
      passed = 0;
      goto done;
   }
   glViewportIndexedf(0, 0, 0, SIZE / 2, SIZE);
   glViewportIndexedf(1, SIZE / 2, 0, SIZE / 2, SIZE);
   glPatchParameteri(GL_PATCH_VERTICES, 3);
   for (unsigned distances = 0; distances < 2; ++distances) {
      for (unsigned layer = 0; layer < 2; ++layer) {
         for (unsigned viewport = 0; viewport < 2; ++viewport) {
            char geometry[1024];
            int length = snprintf(geometry, sizeof(geometry),
               "#version 330 core\n"
               "#extension GL_ARB_viewport_array : require\n"
               "%s"
               "layout(triangles) in;layout(triangle_strip,max_vertices=3) out;"
               "void main(){gl_Layer=%u;gl_ViewportIndex=%u;"
               "for(int i=0;i<3;++i){gl_Position=gl_in[i].gl_Position;"
               "%sEmitVertex();}EndPrimitive();}",
               distances ? "#extension GL_ARB_cull_distance : require\n" : "",
               layer, viewport,
               distances ? "gl_ClipDistance[0]=1.0;gl_CullDistance[0]=1.0;" : "");
            if (length < 0 || (size_t)length >= sizeof(geometry)) {
               passed = 0;
               goto done;
            }
            const char *sources[] = {tess_sources[0], tess_sources[1],
               tess_sources[2], geometry, tess_sources[3]};
            GLuint p = program(sources, types, 5);
            if (!p) { passed = 0; goto done; }
            glUseProgram(p);
            glClear(GL_COLOR_BUFFER_BIT);
            glDrawArrays(GL_PATCHES, 4, 3);
            glGetTexImage(GL_TEXTURE_2D_ARRAY, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
            unsigned green[4] = {0}, unexpected = 0;
            for (unsigned z = 0; z < 2; ++z)
               for (unsigned y = 0; y < SIZE; ++y)
                  for (unsigned x = 0; x < SIZE; ++x) {
                     uint32_t color = pixels[(z * SIZE + y) * SIZE + x];
                     green[z * 2 + (x >= SIZE / 2)] += color == UINT32_C(0xff00ff00);
                     unexpected += color != UINT32_C(0xff00ff00) && color != UINT32_C(0xff000000);
                  }
            int status = ps5_egl_current_draw_status(NULL);
            GLenum error = glGetError();
            int ok = !unexpected && !status && error == GL_NO_ERROR;
            for (unsigned q = 0; q < 4; ++q)
               ok &= q == layer * 2 + viewport ? green[q] > 100 : green[q] == 0;
            printf("[ps5-egl-tess-routing] distances=%u layer=%u viewport=%u "
                   "green=%u,%u,%u,%u unexpected=%u status=%d error=%x result=%s\n",
                   distances, layer, viewport, green[0], green[1], green[2], green[3],
                   unexpected, status, error, ok ? "pass" : "fail");
            passed &= ok;
            glUseProgram(0);
            glDeleteProgram(p);
         }
      }
   }
done:
   glBindFramebuffer(GL_FRAMEBUFFER, 0);
   glDeleteFramebuffers(1, &fbo);
   glDeleteTextures(1, &texture);
   return passed;
}

/* Keep every lane live with distinct buffer-texture data, and test a deliberate bad
 * lane as well as the all-correct case. No constant/uniform-only varyings. */
static int
wide_io(int patch)
{
   const GLenum limits[] = {GL_MAX_TESS_CONTROL_INPUT_COMPONENTS,
      GL_MAX_TESS_CONTROL_OUTPUT_COMPONENTS, GL_MAX_TESS_EVALUATION_INPUT_COMPONENTS,
      GL_MAX_TESS_EVALUATION_OUTPUT_COMPONENTS};
   for (unsigned i = 0; i < sizeof(limits) / sizeof(limits[0]); ++i) {
      GLint value = 0;
      glGetIntegerv(limits[i], &value);
      if (value < 128 || glGetError() != GL_NO_ERROR)
         return 0;
   }
   GLint patch_components = 0;
   glGetIntegerv(GL_MAX_TESS_PATCH_COMPONENTS, &patch_components);
   if (patch && (patch_components < 120 || glGetError() != GL_NO_ERROR))
      return 0;
   const char *sources[] = {
      "#version 430 core\n"
      "layout(binding=0) uniform samplerBuffer data;"
      "out vec4 v[32];void main(){for(int i=0;i<32;i++)"
      "v[i]=texelFetch(data,gl_VertexID*32+i);}",
      "#version 430 core\nlayout(vertices=3) out;"
      "in vec4 v[][32];out vec4 t[][32];"
      "void main(){for(int i=0;i<32;i++)"
      "t[gl_InvocationID][i]=v[gl_InvocationID][i]+vec4(1);"
      "gl_TessLevelOuter[0]=1;gl_TessLevelOuter[1]=1;"
      "gl_TessLevelOuter[2]=1;gl_TessLevelInner[0]=1;}",
      "#version 430 core\nlayout(triangles,equal_spacing,ccw) in;"
      "in vec4 t[][32];flat out vec4 e[31];"
      "void main(){bool ok=true;for(int j=0;j<3;j++)for(int i=0;i<32;i++)"
      "ok=ok&&all(equal(t[j][i],vec4(float(j*128+i*4+1))+vec4(0,1,2,3)));"
      "for(int i=0;i<31;i++)e[i]=t[0][i];if(!ok)e[30].w=-1;"
      "gl_Position=vec4(-0.8+1.6*gl_TessCoord.y,-0.8+1.6*gl_TessCoord.z,0,1);}",
      "#version 430 core\nflat in vec4 e[31];out vec4 color;"
      "void main(){bool ok=true;for(int i=0;i<31;i++)"
      "ok=ok&&all(equal(e[i],vec4(float(i*4+1))+vec4(0,1,2,3)));"
      "color=ok?vec4(0,1,0,1):vec4(1,0,0,1);}",
   };
   if (patch) {
      sources[1] = "#version 430 core\nlayout(vertices=3) out;"
         "in vec4 v[][32];patch out vec4 p[30];void main(){"
         "if(gl_InvocationID==0){for(int i=0;i<30;i++)p[i]=v[0][i]+vec4(1);"
         "gl_TessLevelOuter[0]=1;gl_TessLevelOuter[1]=1;"
         "gl_TessLevelOuter[2]=1;gl_TessLevelInner[0]=1;}}";
      sources[2] = "#version 430 core\nlayout(triangles,equal_spacing,ccw) in;"
         "patch in vec4 p[30];flat out vec4 e[31];void main(){"
         "for(int i=0;i<30;i++)e[i]=p[i];e[30]=vec4(121,122,123,124);"
         "gl_Position=vec4(-0.8+1.6*gl_TessCoord.y,-0.8+1.6*gl_TessCoord.z,0,1);}";
   }
   const GLenum types[] = {GL_VERTEX_SHADER, GL_TESS_CONTROL_SHADER,
                          GL_TESS_EVALUATION_SHADER, GL_FRAGMENT_SHADER};
   GLuint p = program(sources, types, 4), buffer = 0, texture = 0;
   float values[3 * 128];
   int passed = p != 0;
   if (!p)
      return 0;
   glGenBuffers(1, &buffer);
   glBindBuffer(GL_TEXTURE_BUFFER, buffer);
   glBufferData(GL_TEXTURE_BUFFER, sizeof(values), NULL, GL_STATIC_DRAW);
   glGenTextures(1, &texture);
   glActiveTexture(GL_TEXTURE0);
   glBindTexture(GL_TEXTURE_BUFFER, texture);
   glTexBuffer(GL_TEXTURE_BUFFER, GL_RGBA32F, buffer);
   glUseProgram(p);
   glViewport(0, 0, SIZE, SIZE);
   glPatchParameteri(GL_PATCH_VERTICES, 3);
   for (unsigned bad = 0; bad < 2; ++bad) {
      for (unsigned i = 0; i < 3 * 128; ++i)
         values[i] = (float)i;
      if (bad)
         values[patch ? 119 : 3 * 128 - 1] = -99;
      glBufferSubData(GL_TEXTURE_BUFFER, 0, sizeof(values), values);
      glClear(GL_COLOR_BUFFER_BIT);
      glDrawArrays(GL_PATCHES, 0, 3);
      unsigned green = matching(UINT32_C(0xff00ff00));
      unsigned red = matching(UINT32_C(0xff0000ff));
      int status = ps5_egl_current_draw_status(NULL);
      GLenum error = glGetError();
      int ok = !status && error == GL_NO_ERROR &&
               (bad ? red > 500 && green == 0 : green > 500 && red == 0);
      printf("[ps5-egl-tess-wide-io] patch=%d components=%u bad=%u green=%u red=%u "
             "status=%d error=%x result=%s\n", patch, patch ? 120 : 128, bad, green, red, status, error,
             ok ? "pass" : "fail");
      passed &= ok;
   }
   glBindTexture(GL_TEXTURE_BUFFER, 0);
   glDeleteTextures(1, &texture);
   glBindBuffer(GL_TEXTURE_BUFFER, 0);
   glDeleteBuffers(1, &buffer);
   glUseProgram(0);
   glDeleteProgram(p);
   return passed;
}

int
main(void)
{
   static const char *vs =
      "#version 330 core\n"
      "void main(){"
      "float x=gl_VertexID==1?0.8:-0.8;"
      "float y=gl_VertexID==2?0.8:-0.8;"
      "gl_Position=vec4(x,y,0.5,1.0);}\n";
   static const char *tess_vs =
      "#version 330 core\n"
      "void main(){"
      "int id=gl_VertexID-4;"
      "float x=(id&1)!=0?0.8:-0.8;"
      "float y=(id&2)!=0?0.8:-0.8;"
      "gl_Position=vec4(x,y,0.5,1.0);}\n";
   static const char *tcs =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(vertices=3) out;"
      "void main(){"
      "gl_out[gl_InvocationID].gl_Position=gl_in[gl_InvocationID].gl_Position;"
      "if(gl_InvocationID==0){"
      "gl_TessLevelOuter[0]=2.0;gl_TessLevelOuter[1]=2.0;"
      "gl_TessLevelOuter[2]=2.0;gl_TessLevelOuter[3]=2.0;"
      "gl_TessLevelInner[0]=2.0;gl_TessLevelInner[1]=2.0;}}\n";
   static const char *tes =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(triangles,equal_spacing,ccw) in;"
      "void main(){gl_Position="
      "gl_in[0].gl_Position*gl_TessCoord.x+"
      "gl_in[1].gl_Position*gl_TessCoord.y+"
      "gl_in[2].gl_Position*gl_TessCoord.z;}\n";
   static const char *green =
      "#version 330 core\n"
      "out vec4 c;void main(){c=vec4(0,1,0,1);}\n";
   static const char *blue =
      "#version 330 core\n"
      "out vec4 c;void main(){c=vec4(0,0,1,1);}\n";
   static const char *quad_tcs =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(vertices=4) out;"
      "void main(){"
      "gl_out[gl_InvocationID].gl_Position=gl_in[gl_InvocationID].gl_Position;"
      "if(gl_InvocationID==0){"
      "gl_TessLevelOuter[0]=2.0;gl_TessLevelOuter[1]=2.0;"
      "gl_TessLevelOuter[2]=2.0;gl_TessLevelOuter[3]=2.0;"
      "gl_TessLevelInner[0]=2.0;gl_TessLevelInner[1]=2.0;}}\n";
   static const char *quad_tes =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(quads,fractional_even_spacing,cw) in;"
      "void main(){vec2 p=gl_TessCoord.xy;gl_Position="
      "mix(mix(gl_in[0].gl_Position,gl_in[1].gl_Position,p.x),"
      "mix(gl_in[2].gl_Position,gl_in[3].gl_Position,p.x),p.y);}\n";
   static const char *line_tcs =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(vertices=2) out;"
      "void main(){"
      "gl_out[gl_InvocationID].gl_Position=gl_in[gl_InvocationID].gl_Position;"
      "if(gl_InvocationID==0){gl_TessLevelOuter[0]=4.0;"
      "gl_TessLevelOuter[1]=4.0;}}\n";
   static const char *line_tes =
      "#version 330 core\n"
      "#extension GL_ARB_tessellation_shader : require\n"
      "layout(isolines,equal_spacing) in;"
      "void main(){gl_Position=mix(gl_in[0].gl_Position,"
      "gl_in[1].gl_Position,gl_TessCoord.x);}\n";
   static const char *yellow =
      "#version 330 core\n"
      "out vec4 c;void main(){c=vec4(1,1,0,1);}\n";
   static const char *magenta =
      "#version 330 core\n"
      "out vec4 c;void main(){c=vec4(1,0,1,1);}\n";
   const char *tess_sources[] = {tess_vs, tcs, tes, green};
   const GLenum tess_types[] = {GL_VERTEX_SHADER, GL_TESS_CONTROL_SHADER,
                                GL_TESS_EVALUATION_SHADER,
                                GL_FRAGMENT_SHADER};
   const char *plain_sources[] = {vs, blue};
   const GLenum plain_types[] = {GL_VERTEX_SHADER, GL_FRAGMENT_SHADER};
   const char *quad_sources[] = {tess_vs, quad_tcs, quad_tes, yellow};
   const char *line_sources[] = {tess_vs, line_tcs, line_tes, magenta};
   const EGLint config_attrs[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_NONE,
   };
   const EGLint context_attrs[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE,
   };
   EGLDisplay display = EGL_NO_DISPLAY;
   EGLConfig config = NULL;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext context = EGL_NO_CONTEXT;
   EGLint count = 0;
   GLuint programs[4] = {0};
   GLuint vao = 0;
   unsigned green_count = 0, yellow_count = 0, magenta_count = 0;
   unsigned blue_count = 0, draws = 0;
   int status = -1, passed = 0;

   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL) ||
       !eglBindAPI(EGL_OPENGL_API) ||
       !eglChooseConfig(display, config_attrs, &config, 1, &count) ||
       count != 1)
      goto done;
   surface = eglCreateWindowSurface(display, config, 0, NULL);
   context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
   if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT ||
       !eglMakeCurrent(display, surface, surface, context))
      goto done;
   programs[0] = program(tess_sources, tess_types, 4);
   programs[1] = program(plain_sources, plain_types, 2);
   programs[2] = program(quad_sources, tess_types, 4);
   programs[3] = program(line_sources, tess_types, 4);
   if (!programs[0] || !programs[1] || !programs[2] || !programs[3])
      goto done;
   glGenVertexArrays(1, &vao);
   glBindVertexArray(vao);
   glViewport(0, 0, SIZE, SIZE);
   glPatchParameteri(GL_PATCH_VERTICES, 4);
   glUseProgram(programs[0]);
   glClearColor(0, 0, 0, 1);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_PATCHES, 4, 4);
   green_count = matching(UINT32_C(0xff00ff00));
   glUseProgram(programs[2]);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_PATCHES, 4, 4);
   yellow_count = matching(UINT32_C(0xff00ffff));
   glUseProgram(programs[3]);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_PATCHES, 4, 4);
   magenta_count = matching(UINT32_C(0xffff00ff));
   glUseProgram(programs[1]);
   glClear(GL_COLOR_BUFFER_BIT);
   glDrawArrays(GL_TRIANGLES, 0, 3);
   blue_count = matching(UINT32_C(0xffff0000));
   status = ps5_egl_current_draw_status(&draws);
   passed = glGetError() == GL_NO_ERROR && status == 0 && draws == 8 &&
            green_count > 500 && yellow_count > 1000 &&
            magenta_count > 20 && blue_count > 500;
   if (passed)
      passed = layered_routing(tess_sources);
   if (passed)
      passed = wide_io(0) && wide_io(1);

done:
   printf("[ps5-egl-tessellation] green=%u yellow=%u magenta=%u blue=%u "
          "draws=%u status=%d result=%s\n", green_count, yellow_count,
          magenta_count, blue_count, draws, status,
          passed ? "pass" : "fail");
   glDeleteVertexArrays(1, &vao);
   glDeleteProgram(programs[0]);
   glDeleteProgram(programs[1]);
   glDeleteProgram(programs[2]);
   glDeleteProgram(programs[3]);
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
