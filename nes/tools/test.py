"""(AI-assisted) Run the actual NES host with a generated original machine-code fixture."""
from pathlib import Path
import concurrent.futures,subprocess,tempfile,zipfile,struct
project=Path(__file__).resolve().parents[2];nes=project/'nes';core=nes/'third_party/fceumm'
out=nes/'build/host-test';out.mkdir(parents=True,exist_ok=True)
sources=subprocess.check_output(['make','-s','-f',str(nes/'tools/core-sources.mk'),'list'],cwd=core,text=True).splitlines()
incs=['-I'+str(core/'src'),'-I'+str(core/'src/drivers/libretro'),'-I'+str(core/'src/drivers/libretro/libretro-common/include')]
flags=['-O1','-g','-std=gnu99','-D__LIBRETRO__','-DPATH_MAX=1024','-DFCEU_VERSION_NUMERIC=9900',
       '-DFRONTEND_SUPPORTS_RGB888','-DINLINE=inline','-DHAVE_STDINT_H','-Wno-macro-redefined',*incs]
def compile(name):
    src=core/name;obj=out/Path(name).with_suffix('.o');obj.parent.mkdir(parents=True,exist_ok=True)
    if not obj.exists() or obj.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(['clang-18',*flags,'-c',str(src),'-o',str(obj)],check=True,stdout=subprocess.DEVNULL)
    return obj
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(compile,sources))
exe=out/'integration'
subprocess.run(['clang++-18','-std=c++20','-O1','-g',*incs,'-I'+str(nes/'src'),'-I'+str(project/'ps5/frontend'),
                str(nes/'tools/test_session.cpp'),str(nes/'src/core_session.cpp'),str(nes/'src/games.cpp'),
                str(project/'ps5/frontend/fe_nfs.cpp'),*(str(o) for o in objects),'-lz','-pthread','-lm','-o',str(exe)],check=True)
# Original 6502 test: initialize PPU/pulse channel, poll the A button into battery SRAM.
program=bytearray([0x78,0xd8,0xa2,0xff,0x9a])
def write(address,value):program.extend([0xa9,value,0x8d,address&255,address>>8])
write(0x2000,0);write(0x2001,0);write(0x2006,0x3f);write(0x2006,0);write(0x2007,0x21);write(0x2001,8)
write(0x4015,1);write(0x4000,0xbf);write(0x4002,0x40);write(0x4003,8)
loop=0x8000+len(program);write(0x4016,1);write(0x4016,0)
program.extend([0xad,0x16,0x40,0x29,1,0x8d,0,0x60,0x4c,loop&255,loop>>8])
prg=bytearray([0xea]*16384);prg[:len(program)]=program
for vector in (16378,16380,16382):prg[vector:vector+2]=struct.pack('<H',0x8000)
rom=b'NES\x1a'+bytes([1,1,2,0])+bytes(8)+prg+bytes(8192)
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);roms=root/'games';saves=root/'saves';roms.mkdir();saves.mkdir()
    (roms/'input.nes').write_bytes(rom)
    with zipfile.ZipFile(roms/'input.zip','w',zipfile.ZIP_DEFLATED) as z:z.writestr('game.nes',rom)
    (roms/'bad.zip').write_bytes(b'invalid zip')
    with zipfile.ZipFile(roms/'multiple.zip','w') as z:z.writestr('one.nes',rom);z.writestr('two.nes',rom)
    with zipfile.ZipFile(roms/'corrupt.zip','w') as z:z.writestr('one.nes',rom)
    corrupt=bytearray((roms/'corrupt.zip').read_bytes());corrupt[100]^=1;(roms/'corrupt.zip').write_bytes(corrupt)
    subprocess.run([str(exe),str(roms),str(saves)],check=True,timeout=30)
video=out/'video-test'
subprocess.run(['clang++-18','-std=c++20','-O1','-I'+str(nes/'src'),str(nes/'tools/test_video.cpp'),
                str(nes/'src/demo_renderer.cpp'),'-o',str(video)],check=True)
subprocess.run([str(video)],check=True,timeout=10)
