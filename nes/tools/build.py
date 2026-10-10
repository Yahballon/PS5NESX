"""(AI-assisted) PS5NES out-of-tree core build, native link and signed test package."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,shutil,subprocess,zipfile
project=Path(__file__).resolve().parents[2]
nes=project/'nes';out=nes/'build';out.mkdir(exist_ok=True)
core=nes/'third_party/fceumm';sdk=Path(os.environ['PS5_PAYLOAD_SDK'])
deps=Path(os.environ['PS5NES_DEPS']);nfs=Path(os.environ['LIBNFS_PREFIX']);z=Path(os.environ['LIBZ_PREFIX'])
native=project/'ps5/proto/native';wrapper=native/'tooling/prospero-clang18'
sources=subprocess.check_output(['make','-s','-f',str(nes/'tools/core-sources.mk'),'list'],cwd=core,text=True).splitlines()
incs=['-I'+str(core/'src'),'-I'+str(core/'src/drivers/libretro'),'-I'+str(core/'src/drivers/libretro/libretro-common/include')]
base=['-O2','-march=znver2','-ffunction-sections','-fdata-sections','-fno-stack-protector','-fno-plt']
cflags=['-target','x86_64-sie-ps5','-isysroot',str(sdk),'-isystem',str(sdk/'target/include'),'-std=gnu99',
        '-D__LIBRETRO__','-DPATH_MAX=1024','-DFCEU_VERSION_NUMERIC=9900','-DFRONTEND_SUPPORTS_RGB888',
        '-DINLINE=inline','-DHAVE_STDINT_H','-Wno-macro-redefined','-Wno-unused-result',*base,*incs]
objects=[]
def compile_c(name):
    path=core/name;obj=out/'obj/core'/Path(name).with_suffix('.o');obj.parent.mkdir(parents=True,exist_ok=True)
    if not obj.exists() or obj.stat().st_mtime < path.stat().st_mtime:
        subprocess.run(['clang-18',*cflags,'-c',str(path),'-o',str(obj)],check=True)
    return obj
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    objects=list(pool.map(compile_c,sources))
print(f'NES core: {len(objects)} PS5 objects (AI-assisted)',flush=True)
cpp=[*base,'-std=c++20','-fno-exceptions','-fno-rtti','-pthread','-DORBIS_NFS=1','-I'+str(nfs/'include'),
     '-I'+str(z/'include'),'-I'+str(nes/'src'),'-I'+str(project/'ps5/frontend'),
     '-I'+str(project/'ps5/coreorbis/orbis-shims/filesystem-elevation'),*incs]
cpp_sources=[nes/'src'/n for n in ['core_session.cpp','games.cpp','main.cpp','demo_renderer.cpp']]
cpp_sources += [project/'ps5/frontend/fe_nfs.cpp',project/'ps5/coreorbis/orbis-shims/filesystem-elevation/src/elevation.cpp']
cpp_sources += [native/'tooling/native'/f'{name}.cpp' for name in ['app_crt','app_cpp_runtime']]
for src in cpp_sources:
    obj=out/'obj'/f'{src.stem}.o';obj.parent.mkdir(exist_ok=True)
    subprocess.run(['sh',str(wrapper),*cpp,'-c',str(src),'-o',str(obj)],check=True);objects.append(obj)
stubs=sorted(str(p) for p in (sdk/'target/lib').glob('*.so') if p.name not in ('libScePosixForWebKit.so','libSceGLSlimVSH.so'))
pie=out/'llvm-pie.elf'
link=['ld.lld-18','-m','elf_x86_64','-pie','-z','max-page-size=0x4000','-mllvm','-emulated-tls',
      '--hash-style=gnu','-T',str(native/'tooling/native/ps5-pie.ld'),
      '-T',str(project/'ps5/coreorbis/orbis-shims/ehframe.ld'),'--eh-frame-hdr',
      '--version-script',str(native/'tooling/native/app-symbols.map'),'--no-dynamic-linker','-e','_start',
      '-o',str(pie),*(str(p) for p in objects),str(nfs/'lib/libnfs.a'),str(z/'lib/libz.a'),
      '--as-needed',*stubs,'-L'+str(sdk/'target/lib'),
      *(str(sdk/'target/lib'/f'lib{lib}.a') for lib in ['c++','c++abi','unwind','c']),'-lpthread']
subprocess.run(link,check=True)
exports=out/'orbis-exports.map'
subprocess.run(['python3',str(project/'ps5/genmap.py'),str(pie),str(sdk/'target/lib'),str(exports)],check=True)
subprocess.run(link+['--version-script',str(exports)],check=True)
tool=deps/'PS5_Vulkan/build/host/ps5-native-tool'
if not tool.exists():tool=native/'build/host/ps5-native-tool'
subprocess.run([str(tool),'link','--in',str(pie),'--out',str(out/'eboot.elf'),'--stub-dir',str(sdk/'target/lib'),
                '--module-sdk','0x02000009','--companion-sdk','0x08050001','--file-name','eboot.elf'],check=True)
subprocess.run(['python3',str(project/'ps5/tools/prepare_console_elf.py'),'--input',str(out/'eboot.elf'),
                '--output',str(out/'eboot-console-ready.elf')],check=True)
app=out/'package/PPSA99204';(app/'sce_module').mkdir(parents=True,exist_ok=True)
subprocess.run([str(tool),'self','--sign','--in',str(out/'eboot.elf'),'--out',str(app/'eboot.bin'),'--magic','0x1D3D154F'],check=True)
subprocess.run([str(tool),'self','--inspect','--file',str(app/'eboot.bin')],check=True)
shutil.copytree(nes/'sce_sys',app/'sce_sys',dirs_exist_ok=True)
shutil.copy2(deps/'PS5_Vulkan/runtime/libc.prx',app/'sce_module/libc.prx')
subprocess.run(['python3',str(deps/'filesystem-helper/tools/build-lapy-helper.py'),'PPSA99204',str(out/'filesystem-helper')],check=True)
for name in ['lapy.elf','lapy-manifest.json']:shutil.copy2(out/'filesystem-helper'/name,app/name)
licenses=app/'licenses';licenses.mkdir(exist_ok=True)
for path,name in [(core/'Copying','FCEUmm-GPL.txt'),(project/'COPYING.GPLv3','GPLv3.txt'),
                  (out/'filesystem-helper/Lapy-MIT.txt','Lapy-MIT.txt'),(deps/'libnfs/COPYING','libnfs.txt'),
                  (deps/'../..'/'ps5/build-vk/nfs-test-package/PPSA99203/licenses/zlib.txt','zlib.txt')]:
    if path.exists():shutil.copy2(path,licenses/name)
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=core,text=True).strip()
manifest={'ai_assisted':True,'name':'PS5NES v1 modded by YAHBALLON','title':'PPSA99204','core':'FCEUmm',
          'core_commit':commit,'core_source':'https://github.com/libretro/libretro-fceumm','console_tested':False,
          'files':{str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*')
                   if p.is_file() and p.name != 'build-manifest.json'}}
(app/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
shutil.copy2(nes/'TESTEN.txt',out/'package/TESTEN.txt')
bundle=out/'PS5NES-v1-modded-by-YAHBALLON.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in (out/'package').rglob('*'):
        if path.is_file():archive.write(path,path.relative_to(out/'package'))
print('PS5NES test package (AI-assisted):',bundle,flush=True)
