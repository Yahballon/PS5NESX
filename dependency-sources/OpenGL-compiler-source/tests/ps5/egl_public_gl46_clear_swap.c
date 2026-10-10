// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdint.h>
#include <stdio.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GL/gl.h>

int ps5_egl_current_draw_status(unsigned *draw_calls);

int
main(void)
{
   static const EGLint config_attributes[] = {
      EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
      EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
      EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_NONE,
   };
   static const EGLint context_attributes[] = {
      EGL_CONTEXT_MAJOR_VERSION_KHR, 4,
      EGL_CONTEXT_MINOR_VERSION_KHR, 6,
      EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
      EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT_KHR,
      EGL_NONE,
   };
   static const uint8_t expected[3][4] = {
      {0, 0, 255, 255}, {255, 0, 0, 255}, {0, 255, 0, 255},
   };
   EGLDisplay display = EGL_NO_DISPLAY;
   EGLConfig config = NULL;
   EGLSurface surface = EGL_NO_SURFACE;
   EGLContext root = EGL_NO_CONTEXT, renderer = EGL_NO_CONTEXT;
   EGLint major = 0, minor = 0, count = 0;
   unsigned draw_calls = 0;
   int passed = 1, made_current = 0;

   display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
   if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor) ||
       !eglBindAPI(EGL_OPENGL_API) ||
       !eglChooseConfig(display, config_attributes, &config, 1, &count) ||
       count != 1)
      passed = 0;
   if (passed)
      root = eglCreateContext(display, config, EGL_NO_CONTEXT,
                              context_attributes);
   if (root == EGL_NO_CONTEXT ||
       !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, root))
      passed = 0;
   if (passed) {
      renderer = eglCreateContext(display, config, root, context_attributes);
      surface = eglCreateWindowSurface(display, config,
                                       (EGLNativeWindowType)0, NULL);
   }
   if (renderer == EGL_NO_CONTEXT || surface == EGL_NO_SURFACE ||
       !eglMakeCurrent(display, surface, surface, renderer))
      passed = 0;
   else
      made_current = 1;

   if (passed) {
      printf("[ps5-egl-gl46-clear-swap] version=%s glsl=%s\n",
             glGetString(GL_VERSION), glGetString(GL_SHADING_LANGUAGE_VERSION));
      for (unsigned frame = 0, color = 0; frame < 6; ++frame) {
         uint8_t pixel[4] = {0};
         GLenum gl_error = GL_NO_ERROR;

         if (frame == 0 || frame >= 3) {
            color = frame == 0 ? 0 : frame - 2;
            if (color == 3)
               color = 0;
            glClearColor(expected[color][0] / 255.0f,
                         expected[color][1] / 255.0f,
                         expected[color][2] / 255.0f, 1.0f);
            glClear(GL_COLOR_BUFFER_BIT);
            glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
            gl_error = glGetError();
            for (unsigned channel = 0; channel < 4; ++channel)
               passed &= pixel[channel] == expected[color][channel];
         }
         EGLBoolean swapped = eglSwapBuffers(display, surface);
         EGLint swap_error = eglGetError();
         printf("[ps5-egl-gl46-clear-swap] frame=%u clear=%u pixel=%u/%u/%u/%u "
                "gl=%04x swap=%u egl=%04x\n",
                frame, frame == 0 || frame >= 3,
                pixel[0], pixel[1], pixel[2], pixel[3], gl_error,
                swapped, swap_error);
         passed &= gl_error == GL_NO_ERROR && swapped == EGL_TRUE &&
                   swap_error == EGL_SUCCESS;
      }
      passed &= ps5_egl_current_draw_status(&draw_calls) == 0;
   }

   if (made_current)
      passed &= eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE,
                               EGL_NO_CONTEXT);
   if (renderer != EGL_NO_CONTEXT)
      passed &= eglDestroyContext(display, renderer);
   if (root != EGL_NO_CONTEXT)
      passed &= eglDestroyContext(display, root);
   if (surface != EGL_NO_SURFACE)
      passed &= eglDestroySurface(display, surface);
   if (display != EGL_NO_DISPLAY)
      passed &= eglTerminate(display);
   passed &= eglGetError() == EGL_SUCCESS;
   passed &= draw_calls == 4;
   printf("[ps5-egl-gl46-clear-swap] egl=%d.%d app-draws=0 driver-draws=%u result=%d\n",
          major, minor, draw_calls, passed ? 0 : 1);
   return passed ? 0 : 1;
}
