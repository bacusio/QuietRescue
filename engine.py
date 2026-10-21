"""Durable no-retry segmented imaging. No physical device write operation."""
import os,sys,json,time,hashlib,subprocess,threading,queue,shutil,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
BLOCK=1024**2
CHUNK=256*1024**2
FLOOR=5_000_000_000+32*1024**2

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,data):
    p=Path(p);t=p.with_suffix(p.suffix+'.tmp')
    with t.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def append(p,row):
    with Path(p).open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
def records(root):
    p=Path(root)/'map.jsonl'
    if not p.exists():return []
    data=p.read_bytes();lines=data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b'\n'):raise RuntimeError('映射尾部未完整保存，停止；不可將未知請求當未讀區域')
    return [json.loads(x) for x in lines]
def merge(ranges):
    out=[]
    for a,z in sorted((tuple(x) for x in ranges)):
        if a>=z:raise ValueError('Invalid range')
        if out and a<=out[-1][1]:out[-1][1]=max(z,out[-1][1])
        else:out.append([a,z])
    return out
def remaining(a,z,excluded):
    for x,y in merge(excluded):
        if y<=a:continue
        if x>=z:break
        if a<x:yield a,min(x,z)
        a=max(a,y)
        if a>=z:return
    if a<z:yield a,z
def contained(root,name):
    p=(Path(root)/name).resolve()
    if p.parent!=Path(root).resolve():raise ValueError('Invalid capture path')
    return p
def validate(plan,root):
    if plan['sector'] not in (512,4096):raise ValueError('Unsupported sector')
    a,z=plan['start'],plan['end']
    if not 0<=a<z<=plan['size'] or a%plan['sector'] or z%plan['sector']:raise ValueError('Unaligned scope')
    if plan['kind']=='disk':
        from platform_win import inventory,destination_disk
        d=next(x for x in inventory()['disks'] if x['Number']==plan['number'])
        if d['IsBoot'] or d['IsSystem']:raise ValueError('禁止讀取系統盤；請離線處理')
        if not plan['serial'] or d['SerialNumber'].strip()!=plan['serial'] or int(d['Size'])!=plan['size']:raise ValueError('硬盤身份改變')
        if destination_disk(root)==plan['number']:raise ValueError('來源與目的地是同一物理硬盤')
    elif plan['kind']=='file':
        p=Path(plan['source']).resolve()
        if str(p).startswith('\\\\') or not p.is_file():raise ValueError('Only regular local image files')
        if p.stat().st_size!=plan['size'] or p.stat().st_mtime_ns!=plan['mtime_ns']:raise ValueError('測試鏡像已改變')
        if p.parent==Path(root).resolve():raise ValueError('測試源不能位於輸出任務內')
    else:raise ValueError('Unknown source')

def worker(root):
    import base64
    p=load(Path(root)/'plan.json');d=None
    # Parent death must not leave a reader waiting for more requests.
    if os.name=='nt':
        import ctypes
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
        k.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        k.CloseHandle.argtypes=[ctypes.c_void_p]
        h=k.OpenProcess(0x100000,False,os.getppid())
        if not h:raise RuntimeError('Parent handle unavailable')
        def watch_parent():
            if k.WaitForSingleObject(h,0xFFFFFFFF)==0:os._exit(3)
        threading.Thread(target=watch_parent,daemon=True).start()
    try:
        if p['kind']=='disk':
            from platform_win import ReadDevice
            d=ReadDevice('\\\\.\\PhysicalDrive'+str(p['number']))
            serial,size=d.identity()
            if serial!=p['serial'] or size!=p['size']:raise ValueError('開啟後硬盤身份不符')
        else:
            d=open(p['source'],'rb');st=os.fstat(d.fileno())
            if st.st_size!=p['size'] or st.st_mtime_ns!=p['mtime_ns']:raise ValueError('Source file changed')
        print(json.dumps({'ready':True}),flush=True)
        for line in sys.stdin:
            a,n=json.loads(line);t=time.monotonic()
            if not p['start']<=a<a+n<=p['end'] or a%p['sector'] or n%p['sector'] or not 0<n<=BLOCK:raise ValueError('Invalid read')
            try:
                if p['kind']=='disk':b=d.read(a,n)
                else:d.seek(a);b=d.read(n)
                if len(b)!=n:raise OSError('Short read')
                print(json.dumps({'data':base64.b64encode(b).decode(),'seconds':time.monotonic()-t}),flush=True)
            except OSError as e:print(json.dumps({'error':str(e)}),flush=True);return
    except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
    finally:
        if d:d.close()

class Reader:
    def __init__(self,root):
        from platform_win import clean_env
        self.log=(Path(root)/'worker.log').open('ab')
        env=clean_env()
        if getattr(sys,'frozen',False):
            # Keep the bootloader's validated worker context: do not spawn a second
            # extraction supervisor which could outlive a killed reader process.
            for key in ('_PYI_ARCHIVE_FILE','_PYI_APPLICATION_HOME_DIR','_PYI_PARENT_PROCESS_LEVEL'):
                if key in os.environ:env[key]=os.environ[key]
            command=[sys.executable,'--worker',str(root)]
        else:command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'worker',str(root)]
        self.p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,encoding='utf-8',env=env,creationflags=0x08000000)
        self.q=queue.Queue()
        def pump():
            for line in self.p.stdout:self.q.put(line)
            self.q.put('')
        threading.Thread(target=pump,daemon=True).start()
        try:
            ready=self.reply(30)
            if not ready.get('ready'):raise RuntimeError(str(ready))
        except BaseException:self.close();raise
    def reply(self,timeout):
        try:line=self.q.get(timeout=timeout)
        except queue.Empty:raise TimeoutError('READ_TIMEOUT')
        if not line:raise RuntimeError('Worker exited')
        return json.loads(line)
    def read(self,a,n):
        self.p.stdin.write(json.dumps([a,n])+'\n');self.p.stdin.flush();return self.reply(8)
    def close(self):
        if self.p.poll() is None:
            self.p.kill()
            try:self.p.wait(3)
            except subprocess.TimeoutExpired:raise RuntimeError('WORKER_EXIT_UNCONFIRMED: 不可續讀')
        self.p.stdin.close();self.p.stdout.close()
        self.log.close()

def capture(root,stop,notify,reader_factory=Reader):
    import base64,msvcrt
    root=Path(root).resolve();plan=load(root/'plan.json');validate(plan,root)
    from contextlib import ExitStack
    with ExitStack() as stack:
        lock=stack.enter_context((root/'active.lock').open('a+b'))
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        if plan['kind']=='disk':
            import ctypes as C
            k=C.WinDLL('kernel32',use_last_error=True)
            k.CreateMutexW.argtypes=[C.c_void_p,C.c_int,C.c_wchar_p];k.CreateMutexW.restype=C.c_void_p
            k.WaitForSingleObject.argtypes=[C.c_void_p,C.c_ulong];k.ReleaseMutex.argtypes=[C.c_void_p];k.CloseHandle.argtypes=[C.c_void_p]
            mutex=k.CreateMutexW(None,False,'Global\\QuietRescue-Disk-'+str(plan['number']))
            if not mutex:raise C.WinError(C.get_last_error())
            stack.callback(k.CloseHandle,mutex)
            if k.WaitForSingleObject(mutex,0) not in (0,128):raise RuntimeError('同一來源硬盤已有任務運行')
            stack.callback(k.ReleaseMutex,mutex)
        rows=records(root);excluded=[(x['offset'],x['offset']+x['length']) for x in rows if x['state']=='REQUESTED']
        excluded += [(x['start'],x['end']) for x in rows if x['state']=='GUARD']
        excluded += plan.get('guards',[])
        todo=list(remaining(plan['start'],plan['end'],excluded));new=0;reader=None
        status={'status':'RUNNING','source_writes':0,'retries':0,'pid':os.getpid()}
        try:
            for a,z in todo:
                while a<z:
                    if stop.is_set():status['status']='STOPPED';return status
                    n=min(BLOCK,z-a,plan['stage_bytes']-new)
                    if n<=0:status['status']='STAGE_COMPLETE';return status
                    if shutil.disk_usage(root).free-n<FLOOR:status['status']='SPACE_LOW';return status
                    if reader is None:reader=reader_factory(root)
                    append(root/'map.jsonl',dict(state='REQUESTED',offset=a,length=n))
                    try:
                        result=reader.read(a,n)
                        if 'error' in result:raise OSError(result['error'])
                        data=base64.b64decode(result['data'],validate=True)
                        if len(data)!=n:raise ValueError('Invalid returned data')
                    except (OSError,TimeoutError,RuntimeError,ValueError) as e:
                        reader.close();reader=None
                        append(root/'map.jsonl',dict(state='FAILED',offset=a,length=n,error=str(e)))
                        end=min(plan['end'],a+n+1024**3)
                        append(root/'map.jsonl',dict(state='GUARD',start=max(plan['start'],a-1024**3),end=end))
                        status.update(status='FAULT_STOP',offset=a,error=str(e));return
                    name=f'chunk-{a//CHUNK:012d}.bin';path=root/name
                    with path.open('ab') as f:
                        pos=f.tell();f.write(data);f.flush();os.fsync(f.fileno())
                    append(root/'map.jsonl',dict(state='GOOD',offset=a,length=n,file=name,file_offset=pos,sha256=hashlib.sha256(data).hexdigest()))
                    new+=n;status.update(new_bytes=new,offset=a)
                    notify(dict(status));a+=n
                    if result['seconds']>2:
                        append(root/'map.jsonl',dict(state='GUARD',start=max(plan['start'],a-n-1024**3),end=min(plan['end'],a+1024**3),reason='SLOW_READ'))
                        status.update(status='FAULT_STOP',error='SLOW_READ');return
            status['status']='SCOPE_READ_COMPLETE'
        except Exception as e:status.update(status='ERROR',error=str(e));raise
        finally:
            try:
                if reader:reader.close()
            finally:save(root/'status.json',status);notify(dict(status))
        return status

def good_blocks(root):
    seen=[]
    for r in records(root):
        if r['state']!='GOOD':continue
        a=r['offset'];z=a+r['length']
        if any(a<y and x<z for x,y in seen):raise ValueError('Overlapping GOOD records')
        seen.append((a,z))
        with contained(root,r['file']).open('rb') as f:f.seek(r['file_offset']);b=f.read(r['length'])
        if len(b)!=r['length'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('副本雜湊不符')
        yield r,b

def verify(root):
    p=load(Path(root)/'plan.json');ranges=[];size=0
    for r,b in good_blocks(root):ranges.append((r['offset'],r['offset']+len(b)));size+=len(b)
    gaps=list(remaining(p['start'],p['end'],ranges))
    out=dict(verified_bytes=size,missing_ranges=gaps,complete=not gaps,scope_start=p['start'],scope_end=p['end'])
    save(Path(root)/'verification.json',out);return out

def export_image(root,target):
    root=Path(root);target=Path(target)
    report=verify(root)
    if not report['complete']:raise ValueError('鏡像有缺損，不能匯出成完整映像；請保留分段及映射')
    if shutil.disk_usage(target.parent).free-report['verified_bytes']<FLOOR:raise ValueError('匯出空間不足')
    partial=target.with_suffix(target.suffix+'.partial')
    if target.exists():raise FileExistsError(target)
    with partial.open('xb') as f:
        for r,b in good_blocks(root):
            if shutil.disk_usage(target.parent).free-len(b)<FLOOR:raise ValueError('SPACE_LOW')
            f.seek(r['offset']-report['scope_start']);f.write(b)
        f.flush();os.fsync(f.fileno())
    partial.rename(target)
    save(target.with_suffix(target.suffix+'.json'),report)

def export_regions(root):
    root=Path(root);out=root/('regions-'+uuid.uuid4().hex[:8]);out.mkdir();regions=[];stream=None;end=None
    try:
        for row,b in good_blocks(root):
            if shutil.disk_usage(root).free-len(b)<FLOOR:raise ValueError('SPACE_LOW')
            if end!=row['offset']:
                if stream:stream.flush();os.fsync(stream.fileno());stream.close()
                path=out/f"range-{row['offset']}.img";stream=path.open('xb')
                regions.append(dict(path=str(path),physical_start=row['offset'],bytes=0,whole_disk=False))
            stream.write(b);regions[-1]['bytes']+=len(b);end=row['offset']+len(b)
        if stream:stream.flush();os.fsync(stream.fileno())
    finally:
        if stream:stream.close()
    save(out/'regions.json',regions);return regions

if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='worker':worker(Path(sys.argv[2]))
