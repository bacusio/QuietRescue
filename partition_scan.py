"""Read-only TestDisk analysis of saved regular image files on Windows."""
import ctypes,os,subprocess,time,uuid,shutil,contextlib
from pathlib import Path
from image_recovery import ascii_path,find_photorec,sha,save,FLOOR
TESTDISK_SHA='025ea8936765169966fe497b8c46bd5ad16b98b189ee90d6854f063200c95f0c'
COMMANDS={'mbr':'partition_i386,analyse,search','gpt':'partition_gpt,analyse,search'}

class ReadOnlyLease:
    """Hold Windows share-read only: other handles cannot write or delete."""
    def __init__(self,path):self.path=Path(path);self.handle=None
    def __enter__(self):
        if os.name!='nt':raise RuntimeError('Windows read-only sharing is required')
        from ctypes import wintypes as w
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
        self.k.CreateFileW.restype=w.HANDLE
        self.k.CloseHandle.argtypes=[w.HANDLE];self.k.CloseHandle.restype=w.BOOL
        self.handle=self.k.CreateFileW(str(self.path),0x80000000,1,None,3,0,None)
        if self.handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        return self
    def __exit__(self,*args):
        if self.handle is not None:self.k.CloseHandle(self.handle);self.handle=None

def analyze(image,destination,stop,progress=lambda info:None,*,table='mbr'):
    if table not in COMMANDS:raise ValueError('Partition analysis mode must be mbr or gpt')
    if stop.is_set():raise RuntimeError('Stopped before image access')
    command=COMMANDS[table]
    original=Path(image)
    if original.is_symlink() or original.is_junction():raise ValueError('Reparse input rejected')
    source=original.resolve(strict=True);dest=Path(destination).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in {'.img','.bin','.dd','.raw','.partial'}:raise ValueError('Saved regular images only')
    exe=find_photorec().with_name('testdisk_win.exe')
    if sha(exe)!=TESTDISK_SHA:raise ValueError('Unverified TestDisk executable')
    ascii_path(dest)
    job=dest/('PartitionScan-'+uuid.uuid4().hex[:10]);job.mkdir();safe=Path(ascii_path(job))
    result=dict(status='STARTING',image=str(source),partition_mode=table,source_disk_reads=0,source_disk_writes=0,partition_table_written=False,coordinates='relative to saved image; not physical disk addresses',output=str(job))
    child=None;stage=None
    try:
        with ReadOnlyLease(source),contextlib.ExitStack() as staged_locks:
            before=sha(source)
            try:image_arg=ascii_path(source)
            except ValueError:
                if shutil.disk_usage(job).free-source.stat().st_size<FLOOR:
                    raise RuntimeError('需要足夠空間建立英文路徑暫存副本並保留6GB')
                stage=job/'input.partial';copied=0
                with source.open('rb') as src,stage.open('xb') as dst:
                    while True:
                        if stop.is_set():raise RuntimeError('Stopped during saved-image staging')
                        block=src.read(8*1024**2)
                        if not block:break
                        if shutil.disk_usage(job).free-len(block)<FLOOR:raise RuntimeError('Staging space protection')
                        dst.write(block);copied+=len(block)
                        progress(dict(status='COPYING_SAVED_IMAGE_FOR_TESTDISK',copied_bytes=copied))
                    dst.flush();os.fsync(dst.fileno())
                if sha(stage)!=before:raise RuntimeError('Staged image hash mismatch')
                complete_stage=job/'input.img';stage.rename(complete_stage);stage=complete_stage
                staged_locks.enter_context(ReadOnlyLease(stage))
                image_arg=ascii_path(stage);result['staged_input_verified']=True
            if stop.is_set():raise RuntimeError('Stopped before TestDisk launch')
            env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}}
            env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',__COMPAT_LAYER='RunAsInvoker')
            with (job/'stdout.log').open('wb') as output:
                # No write/delete/MBR commands and no user-supplied command text.
                child=subprocess.Popen([str(exe),'/log','/logname',str(safe/'testdisk.log'),'/cmd',image_arg,command],cwd=safe,stdout=output,stderr=subprocess.STDOUT,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
                start=time.monotonic();last=0
                while child.poll() is None:
                    if stop.is_set() or time.monotonic()-start>14400:
                        child.kill();child.wait(15);raise RuntimeError('Stopped; original image unchanged')
                    if time.monotonic()-last>2:
                        result.update(status='ANALYZING_SAVED_IMAGE',elapsed_seconds=round(time.monotonic()-start));save(job/'analysis.json',result);progress(dict(result));last=time.monotonic()
                    time.sleep(.25)
            text=(job/'stdout.log').read_bytes().lower()
            if child.returncode or any(x in text for x in (b'syntax error',b'unable to open',b'no such file',b'terminfo file')):raise RuntimeError('TestDisk failed; inspect '+str(job/'stdout.log'))
            after=sha(source)
            if before!=after:raise RuntimeError('IMAGE_CHANGED')
            result.update(status='ANALYSIS_COMPLETE_REVIEW_REQUIRED',sha256=before,input_unchanged=True)
            save(job/'analysis.json',result);progress(dict(result))
        if stage is not None:stage.unlink()
        return result
    except Exception as e:
        if child and child.poll() is None:child.kill();child.wait(15)
        result.update(status='STOPPED_ERROR',error=str(e));save(job/'analysis.json',result);raise
