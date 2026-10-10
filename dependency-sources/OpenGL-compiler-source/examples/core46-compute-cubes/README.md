# OpenGL 4.6 compute cubes

A visible 30-second animation of 256 cubes driven entirely through public
OpenGL/EGL interfaces. A GLSL 4.60 compute shader writes per-instance state to
an SSBO; the graphics pipeline consumes it after an explicit memory barrier and
renders the scene with one indirect instanced draw per frame. Resources use the
OpenGL direct-state-access API.

Build the native `PPSA99005` folder with the frozen SDK:

```sh
PS5_OPENGL_PREFIX=/path/to/ps5-opengl-sdk-0.3.0/sdk \
  make gl46-demo
```

Deploy and launch the generated folder through the native-title protocol. A
successful natural completion logs `[ps5-gl46-demo] ... result=PASS`.
