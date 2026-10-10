// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* Visible OpenGL 4.6 demo: compute-driven SSBO animation and indirect cubes. */
#define _POSIX_C_SOURCE 200809L
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>

enum { INSTANCE_COUNT = 256, DEMO_SECONDS = 30 };

struct vertex {
   float position[3];
   float normal[3];
};

struct draw_arrays_indirect {
   uint32_t count, instance_count, first, base_instance;
};

static struct vertex vertices[36];

static int64_t
now_ns(void)
{
   struct timespec value;
   return clock_gettime(CLOCK_MONOTONIC, &value) == 0
             ? (int64_t)value.tv_sec * 1000000000 + value.tv_nsec
             : 0;
}

static int
check(int condition, const char *stage)
{
   if (!condition)
      printf("[ps5-gl46-demo] FAIL stage=%s gl=%x egl=%x\n", stage,
             glGetError(), eglGetError());
   return condition;
}

static GLuint
compile(GLenum type, const char *source)
{
   GLuint shader = glCreateShader(type);
   GLint ok = GL_FALSE;
   glShaderSource(shader, 1, &source, NULL);
   glCompileShader(shader);
   glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
   if (!ok) {
      char log[2048] = {0};
      GLsizei length = 0;
      glGetShaderInfoLog(shader, sizeof(log), &length, log);
      printf("[ps5-gl46-demo] shader=%x log=%.*s\n", type, length, log);
      glDeleteShader(shader);
      return 0;
   }
   return shader;
}

static GLuint
link_program(GLuint first, GLuint second)
{
   GLuint program = glCreateProgram();
   GLint ok = GL_FALSE;
   glAttachShader(program, first);
   if (second)
      glAttachShader(program, second);
   glLinkProgram(program);
   glGetProgramiv(program, GL_LINK_STATUS, &ok);
   if (!ok) {
      char log[2048] = {0};
      GLsizei length = 0;
      glGetProgramInfoLog(program, sizeof(log), &length, log);
      printf("[ps5-gl46-demo] link log=%.*s\n", length, log);
      glDeleteProgram(program);
      return 0;
   }
   return program;
}

static void
make_cube(void)
{
   static const float corners[8][3] = {
      {-1, -1, -1}, {1, -1, -1}, {1, 1, -1}, {-1, 1, -1},
      {-1, -1, 1},  {1, -1, 1},  {1, 1, 1},  {-1, 1, 1},
   };
   static const unsigned faces[6][4] = {
      {4, 5, 6, 7}, {5, 1, 2, 6}, {0, 4, 7, 3},
      {7, 6, 2, 3}, {0, 1, 5, 4}, {1, 0, 3, 2},
   };
   static const float normals[6][3] = {
      {0, 0, 1}, {1, 0, 0}, {-1, 0, 0},
      {0, 1, 0}, {0, -1, 0}, {0, 0, -1},
   };
   static const unsigned triangle[6] = {0, 1, 2, 0, 2, 3};
   for (unsigned face = 0; face < 6; ++face) {
      for (unsigned index = 0; index < 6; ++index) {
         struct vertex *vertex = &vertices[face * 6 + index];
         memcpy(vertex->position, corners[faces[face][triangle[index]]],
                sizeof(vertex->position));
         memcpy(vertex->normal, normals[face], sizeof(vertex->normal));
      }
   }
}

int
main(void)
{
   static const char *compute_source =
      "#version 460 core\n"
      "layout(local_size_x=64) in;"
      "layout(std430,binding=0) buffer Instances { vec4 state[]; };"
      "uniform float u_time;"
      "void main(){uint id=gl_GlobalInvocationID.x;if(id>=256u)return;"
      "uint x=id%8u,y=(id/8u)%8u,z=id/64u;"
      "float f=float(id),a=u_time*(0.7+float(z)*0.12)+f*0.17;"
      "vec3 p=vec3((float(x)-3.5)*1.25,(float(y)-3.5)*1.05+sin(a)*0.35,"
      "-7.0-float(z)*2.35);"
      "state[id*2u]=vec4(p,0.34+0.07*sin(a*1.7));"
      "state[id*2u+1u]=vec4(sin(a),cos(a),fract(f*0.618+u_time*0.04),1.0);}\n";
   static const char *vertex_source =
      "#version 460 core\n"
      "layout(location=0) in vec3 in_position;"
      "layout(location=1) in vec3 in_normal;"
      "layout(std430,binding=0) readonly buffer Instances { vec4 state[]; };"
      "uniform float u_aspect;out vec3 v_normal;out vec3 v_color;"
      "vec3 rotate(vec3 p,vec2 r){vec3 y=vec3(r.y*p.x+r.x*p.z,p.y,-r.x*p.x+r.y*p.z);"
      "return vec3(y.x,r.y*y.y-r.x*y.z,r.x*y.y+r.y*y.z);}"
      "void main(){uint id=uint(gl_InstanceID);vec4 place=state[id*2u];"
      "vec4 spin=state[id*2u+1u];vec3 world=rotate(in_position,spin.xy)*place.w+place.xyz;"
      "v_normal=rotate(in_normal,spin.xy);float h=spin.z;"
      "v_color=0.3+0.7*abs(vec3(sin(h*6.283),sin((h+0.333)*6.283),sin((h+0.667)*6.283)));"
      "gl_Position=vec4(world.x*1.65/u_aspect,world.y*1.65,"
      "-1.002002*world.z-0.2002002,-world.z);}\n";
   static const char *fragment_source =
      "#version 460 core\n"
      "in vec3 v_normal;in vec3 v_color;layout(location=0) out vec4 color;"
      "void main(){vec3 n=normalize(v_normal);vec3 light=normalize(vec3(0.4,0.7,1.0));"
      "float diffuse=max(dot(n,light),0.0);float rim=pow(1.0-max(n.z,0.0),2.0);"
      "color=vec4(v_color*(0.18+0.82*diffuse)+rim*0.12,1.0);}\n";
   static const struct draw_arrays_indirect command = {
      36, INSTANCE_COUNT, 0, 0,
   };
   static const EGLint config_attributes[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_DEPTH_SIZE, 24, EGL_NONE,
   };
   static const EGLint context_attributes[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE,
   };

   EGLDisplay display = EGL_NO_DISPLAY;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext context = EGL_NO_CONTEXT;
   EGLConfig config = NULL;
   EGLint config_count = 0, width = 0, height = 0;
   GLuint shaders[3] = {0};
   GLuint draw_program = 0, compute_program = 0;
   GLuint vao = 0, vertex_buffer = 0, instance_buffer = 0, indirect_buffer = 0;
   GLint compute_time = -1, draw_aspect = -1;
   int current = 0, passed = 0, clean = 1;
   unsigned frames = 0;

   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (!check(display != EGL_NO_DISPLAY && eglInitialize(display, NULL, NULL) &&
              eglBindAPI(EGL_OPENGL_API) &&
              eglChooseConfig(display, config_attributes, &config, 1,
                              &config_count) && config_count == 1,
              "EGL init"))
      goto cleanup;
   surface = eglCreateWindowSurface(display, config, 0, NULL);
   context = eglCreateContext(display, config, EGL_NO_CONTEXT,
                              context_attributes);
   if (!check(surface != EGL_NO_SURFACE && context != EGL_NO_CONTEXT &&
              eglMakeCurrent(display, surface, surface, context), "EGL current"))
      goto cleanup;
   current = 1;
   if (!check(eglQuerySurface(display, surface, EGL_WIDTH, &width) &&
              eglQuerySurface(display, surface, EGL_HEIGHT, &height) &&
              width > 0 && height > 0, "surface dimensions"))
      goto cleanup;

   GLint major = 0, minor = 0;
   glGetIntegerv(GL_MAJOR_VERSION, &major);
   glGetIntegerv(GL_MINOR_VERSION, &minor);
   if (!check(major > 4 || (major == 4 && minor >= 6), "OpenGL 4.6 context"))
      goto cleanup;

   shaders[0] = compile(GL_COMPUTE_SHADER, compute_source);
   shaders[1] = compile(GL_VERTEX_SHADER, vertex_source);
   shaders[2] = compile(GL_FRAGMENT_SHADER, fragment_source);
   if (!shaders[0] || !shaders[1] || !shaders[2])
      goto cleanup;
   compute_program = link_program(shaders[0], 0);
   draw_program = link_program(shaders[1], shaders[2]);
   if (!compute_program || !draw_program)
      goto cleanup;
   compute_time = glGetUniformLocation(compute_program, "u_time");
   draw_aspect = glGetUniformLocation(draw_program, "u_aspect");
   if (!check(compute_time >= 0 && draw_aspect >= 0, "uniforms"))
      goto cleanup;

   make_cube();
   glCreateBuffers(1, &vertex_buffer);
   glNamedBufferStorage(vertex_buffer, sizeof(vertices), vertices, 0);
   glCreateBuffers(1, &instance_buffer);
   glNamedBufferStorage(instance_buffer,
                        INSTANCE_COUNT * 2 * 4 * sizeof(float), NULL, 0);
   glCreateBuffers(1, &indirect_buffer);
   glNamedBufferStorage(indirect_buffer, sizeof(command), &command, 0);
   glCreateVertexArrays(1, &vao);
   glVertexArrayVertexBuffer(vao, 0, vertex_buffer, 0, sizeof(struct vertex));
   glEnableVertexArrayAttrib(vao, 0);
   glEnableVertexArrayAttrib(vao, 1);
   glVertexArrayAttribFormat(vao, 0, 3, GL_FLOAT, GL_FALSE,
                             offsetof(struct vertex, position));
   glVertexArrayAttribFormat(vao, 1, 3, GL_FLOAT, GL_FALSE,
                             offsetof(struct vertex, normal));
   glVertexArrayAttribBinding(vao, 0, 0);
   glVertexArrayAttribBinding(vao, 1, 0);
   glBindVertexArray(vao);
   glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, instance_buffer);
   glBindBuffer(GL_DRAW_INDIRECT_BUFFER, indirect_buffer);
   glProgramUniform1f(draw_program, draw_aspect, (float)width / (float)height);
   glViewport(0, 0, width, height);
   glEnable(GL_DEPTH_TEST);
   glDepthFunc(GL_LESS);
   glDisable(GL_CULL_FACE);
   glDisable(GL_BLEND);
   glDisable(GL_DITHER);
   eglSwapInterval(display, 1);
   if (!check(glGetError() == GL_NO_ERROR, "resource setup"))
      goto cleanup;

   printf("[ps5-gl46-demo] ready GL=%s GLSL=%s size=%dx%d instances=%u seconds=%u\n",
          glGetString(GL_VERSION), glGetString(GL_SHADING_LANGUAGE_VERSION),
          width, height, INSTANCE_COUNT, DEMO_SECONDS);
   const int64_t start = now_ns();
   while (now_ns() - start < (int64_t)DEMO_SECONDS * 1000000000) {
      const float seconds = (float)(now_ns() - start) / 1000000000.0f;
      glUseProgram(compute_program);
      glUniform1f(compute_time, seconds);
      glDispatchCompute(INSTANCE_COUNT / 64, 1, 1);
      glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT);

      glClearColor(0.008f, 0.015f, 0.035f, 1.0f);
      glClearDepth(1.0);
      glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
      glUseProgram(draw_program);
      glDrawArraysIndirect(GL_TRIANGLES, NULL);
      if (!check(eglSwapBuffers(display, surface), "present"))
         goto cleanup;
      ++frames;
      if ((frames & 255u) == 0 && !check(glGetError() == GL_NO_ERROR,
                                         "frame errors"))
         goto cleanup;
   }
   passed = check(frames > 0 && glGetError() == GL_NO_ERROR,
                  "completed animation");

cleanup:
   if (current) {
      glUseProgram(0);
      if (indirect_buffer)
         glDeleteBuffers(1, &indirect_buffer);
      if (instance_buffer)
         glDeleteBuffers(1, &instance_buffer);
      if (vertex_buffer)
         glDeleteBuffers(1, &vertex_buffer);
      if (vao)
         glDeleteVertexArrays(1, &vao);
      if (compute_program)
         glDeleteProgram(compute_program);
      if (draw_program)
         glDeleteProgram(draw_program);
      for (unsigned index = 0; index < 3; ++index)
         if (shaders[index])
            glDeleteShader(shaders[index]);
      clean &= glGetError() == GL_NO_ERROR;
   }
   if (display != EGL_NO_DISPLAY) {
      clean &= eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE,
                              EGL_NO_CONTEXT);
      if (surface != EGL_NO_SURFACE)
         clean &= eglDestroySurface(display, surface);
      if (context != EGL_NO_CONTEXT)
         clean &= eglDestroyContext(display, context);
      clean &= eglTerminate(display);
   }
   clean &= eglGetError() == EGL_SUCCESS;
   printf("[ps5-gl46-demo] frames=%u cleanup=%u result=%s\n", frames, clean,
          passed && clean ? "PASS" : "FAIL");
   return passed && clean ? 0 : 1;
}
