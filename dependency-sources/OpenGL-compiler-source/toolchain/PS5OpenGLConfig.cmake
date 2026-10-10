# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

get_filename_component(PS5OpenGL_PREFIX
  "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

if(NOT TARGET PS5OpenGL::OpenGL)
  add_library(PS5OpenGL::OpenGL INTERFACE IMPORTED)
  set_target_properties(PS5OpenGL::OpenGL PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${PS5OpenGL_PREFIX}/include"
    INTERFACE_COMPILE_DEFINITIONS GL_GLEXT_PROTOTYPES=1
    INTERFACE_LINK_LIBRARIES
      "${PS5OpenGL_PREFIX}/lib/libPS5OpenGL.a;${PS5OpenGL_PREFIX}/lib/libSceAgc.so;${PS5OpenGL_PREFIX}/lib/libSceAgcDriver.so;SceVideoOut;kernel_web;SceSystemService"
    INTERFACE_LINK_OPTIONS "LINKER:-u,ps5_agc_gate2_run")
endif()

set(PS5OpenGL_FOUND TRUE)
