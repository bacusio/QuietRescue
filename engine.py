"""Durable no-retry segmented imaging. No physical device write operation."""
import os,sys,json,time,hashlib,subprocess,threading,queue,shutil,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
BLOCK=1024**2
CHUNK=256*1024**2
FLOOR=5_000_000_000+32*1024**2
ENGINE_ID='QuietRescue segmented reader 1.2.0-review2'
PHYSICAL_READER_VALIDATED=False

class RescueError(RuntimeError):
    def __init__(self, message, failure_class, phase, winerror=None):
        super().__init__(message)
        self.failure_class=failure_class
        self.phase=phase
        self.winerror=winerror

def classify_error(error,phase):
    """Classify failures without turning startup or destination problems into bad sectors."""
    code=getattr(error,'winerror',None)
    if code is None:code=getattr(error,'errno',None)
    if code==1223:return 'UAC_CANCELLED'
    if isinstance(error,TimeoutError) or code==1460:return 'IO_TIMEOUT_UNCONFIRMED'
    if code==995:return 'IO_CANCELLED_UNCONFIRMED'
    if phase=='startup':
        if code==2:return 'ENGINE_START_FAILED'
        if code==5:return 'ADMIN_REQUIRED'
        if code in (21,55,1167,1117):return 'SOURCE_DISCONNECTED'
        return 'WORKER_START_FAILED'
    if phase=='destination_write':return 'DESTINATION_WRITE_FAILED'
    if phase=='destination_flush':return 'DESTINATION_FLUSH_FAILED'
    if code==23:return 'SOURCE_CRC_ERROR'
    if code in (21,55,1167,1117):return 'SOURCE_DISCONNECTED'
    if code==5:return 'SOURCE_ACCESS_DENIED'
    if phase=='read':return 'SOURCE_READ_ERROR'
    return 'INTERNAL_ERROR'

def error_payload(error,phase):
    return dict(error=str(error),failure_class=classify_error(error,phase),phase=phase,
        winerror=getattr(error,'winerror',None) or getattr(error,'errno',None))

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
    if int(plan.get('stage_bytes',0))<=0 or int(plan['stage_bytes'])%plan['sector']:raise ValueError('Invalid or unaligned stage budget')
    total_budget=int(plan.get('total_budget_bytes',z-a))
    if total_budget<=0 or total_budget>z-a or total_budget%plan['sector']:raise ValueError('Invalid or unaligned total plan budget')
    if plan['kind']=='disk':
        expected_policy=dict(read_only=True,retries=0,request_bytes=BLOCK,request_timeout_seconds=8,slow_read_stop_seconds=2,fault_guard_buffer_bytes=1024**3,free_space_reserve=FLOOR)
        if plan.get('policy')!=expected_policy:raise ValueError('讀取政策缺失或與固定引擎參數不符')
        from platform_win import inventory,destination_disk,destination_identity
        matches=[x for x in inventory()['disks'] if int(x['Number'])==int(plan['number'])]
        if len(matches)!=1:raise ValueError('來源實體磁碟不存在或無法唯一識別')
        d=matches[0]
        if d['IsBoot'] or d['IsSystem']:raise ValueError('禁止讀取系統盤；請離線處理')
        serial=str(d.get('SerialNumber') or '').strip()
        if not plan['serial'] or serial!=plan['serial'] or int(d['Size'])!=plan['size']:raise ValueError('硬盤身份改變')
        dest=destination_identity(root)
        if dest['number']==plan['number']:raise ValueError('來源與目的地是同一物理硬盤')
        expected=plan.get('destination_identity')
        if expected and expected!=dest:raise ValueError('目的實體硬盤身份改變；需要重新核對計劃')
    elif plan['kind']=='file':
        p=Path(plan['source']).resolve()
        if str(p).startswith('\\\\') or not p.is_file():raise ValueError('Only regular local image files')
        if p.stat().st_size!=plan['size'] or p.stat().st_mtime_ns!=plan['mtime_ns']:raise ValueError('測試鏡像已改變')
        if p.parent==Path(root).resolve():raise ValueError('測試源不能位於輸出任務內')
    else:raise ValueError('Unknown source')

def validate_saved_output(plan,root):
    """Verify only the healthy saved project destination; never touch source sectors."""
    if not Path(root).is_dir():raise ValueError('搶救資料夾不存在')
    if plan.get('kind')=='disk':
        from platform_win import destination_identity
        dest=destination_identity(root)
        expected=plan.get('destination_identity')
        if expected and dest!=expected:raise ValueError('任務目的實體硬盤改變；先核對已保存副本位置')
        if dest.get('serial')==plan.get('serial'):raise ValueError('任務資料夾位於來源實體硬盤，禁止寫入')

def validate_live_exclusions(plan):
    """Fail closed if a protected source range appeared after plan creation."""
    source=plan.get('imported_map_source')
    if plan.get('kind')!='disk' or not source:return
    source=Path(source).resolve()
    if not source.is_dir():raise ValueError('希捷最新跳過地圖路徑不存在；實體讀取保持封鎖')
    if str(source) not in sys.path:sys.path.insert(0,str(source))
    from stream_scan import exclusions
    bad,prior=exclusions();guards=merge(plan.get('guards',[]));attempted=merge(plan.get('attempted',[]))
    # Older v2 plans mixed attempted ranges and safety guards in one list. Preserve
    # that conservative interpretation while new plans keep the two meanings apart.
    if 'attempted' not in plan:
        baseline=guards
        live=merge(list(bad)+list(prior))
        for a,z in baseline:
            if list(remaining(a,z,live)):
                raise ValueError(f'希捷跳過地圖移除了已匯入保護範圍 [{a}, {z})；請離線核對地圖版本')
        for a,z in live:
            if list(remaining(a,z,baseline)):
                raise ValueError(f'希捷跳過地圖在計劃審核後新增保護範圍 [{a}, {z})；請重新建立並審核計劃')
        return
    for name,baseline,current in (('避讓',guards,bad),('已嘗試',attempted,prior)):
        for a,z in baseline:
            if list(remaining(a,z,current)):
                raise ValueError(f'希捷跳過地圖移除了已匯入{name}範圍 [{a}, {z})；請離線核對地圖版本')
        for a,z in current:
            if list(remaining(a,z,baseline)):
                raise ValueError(f'希捷跳過地圖在計劃審核後新增{name}範圍 [{a}, {z})；請重新建立並審核計劃')

def plan_digest(plan):
    """Hash every plan field; checkpoints evolve separately from this baseline."""
    raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def approval_path(root):return Path(root)/'approval.json'

def approve_physical_plan(root,approver):
    root=Path(root).resolve();plan=load(root/'plan.json');validate(plan,root);validate_live_exclusions(plan)
    if plan.get('kind')!='disk':raise ValueError('只有實體磁盤計劃需要這項審核')
    if not PHYSICAL_READER_VALIDATED:
        raise ValueError('實體讀取尚未開放：1.2 的原始磁碟 reader 未通過實機與 I/O 停止驗收；目前只可審閱計劃及測試健康鏡像檔。')
    if not approver or not plan.get('destination_identity'):
        raise ValueError('計劃缺少審核人或目的硬盤身份')
    approval=dict(schema_version=1,status='APPROVED',plan_id=plan['plan_id'],
        plan_sha256=plan_digest(plan),source=dict(number=plan['number'],serial=plan['serial'],size=plan['size']),
        destination=plan['destination_identity'],policy=plan['policy'],engine=ENGINE_ID,
        approved_by=approver,approved_at=datetime.now(timezone.utc).isoformat(),source_writes=0,retries=0)
    save(approval_path(root),approval);return approval

def require_physical_approval(root,plan=None):
    root=Path(root).resolve();plan=plan or load(root/'plan.json')
    if plan.get('kind')!='disk':return None
    p=approval_path(root)
    if not p.is_file():raise ValueError('實體讀取已封鎖：缺少審核紀錄。先建立計劃草案，檢視來源、目的、範圍與讀取政策，再明確批准。')
    approval=load(p)
    if approval.get('status')!='APPROVED' or approval.get('plan_id')!=plan.get('plan_id'):
        raise ValueError('實體讀取已封鎖：審核紀錄與計劃不匹配')
    if approval.get('plan_sha256')!=plan_digest(plan):
        raise ValueError('實體讀取已封鎖：計劃內容在審核後改變，需重新審核')
    if approval.get('source')!={k:plan.get(k) for k in ('number','serial','size')}:
        raise ValueError('實體讀取已封鎖：來源身分與審核紀錄不一致')
    if approval.get('destination')!=plan.get('destination_identity') or approval.get('policy')!=plan.get('policy'):
        raise ValueError('實體讀取已封鎖：目的地或讀取政策與審核紀錄不一致')
    return approval

def disk_mutex_name(plan):
    identity=str(plan.get('serial','')).strip()
    if not identity:raise ValueError('來源序列號缺失；不能取得唯一實體磁盤鎖')
    token=hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    return 'Global\\QuietRescue-Physical-'+token

def disk_reader_mutex_name(serial):
    identity=str(serial or '').strip()
    if not identity:raise ValueError('來源序列號缺失；不能取得唯一實體讀取鎖')
    token=hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    return 'Global\\QuietRescue-Reader-'+token

def acquire_disk_reader_mutex(serial):
    if os.name!='nt':return None
    import ctypes as C
    k=C.WinDLL('kernel32',use_last_error=True)
    k.CreateMutexW.argtypes=[C.c_void_p,C.c_int,C.c_wchar_p];k.CreateMutexW.restype=C.c_void_p
    k.WaitForSingleObject.argtypes=[C.c_void_p,C.c_ulong];k.WaitForSingleObject.restype=C.c_ulong
    k.ReleaseMutex.argtypes=[C.c_void_p];k.CloseHandle.argtypes=[C.c_void_p]
    h=k.CreateMutexW(None,False,disk_reader_mutex_name(serial))
    if not h:raise C.WinError(C.get_last_error())
    result=k.WaitForSingleObject(h,0)
    if result not in (0,128):
        k.CloseHandle(h)
        raise RuntimeError('同一來源實體磁碟已有讀取 worker；本工作未讀取來源')
    return k,h

def worker(root):
    import base64
    p=load(Path(root)/'plan.json');d=None;reader_mutex=None
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
            validate(p,root);require_physical_approval(root,p);validate_live_exclusions(p)
            reader_mutex=acquire_disk_reader_mutex(p['serial'])
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
            except OSError as e:print(json.dumps(error_payload(e,'read')),flush=True);return
    except Exception as e:print(json.dumps(error_payload(e,'startup')),flush=True)
    finally:
        try:
            if d:d.close()
        finally:
            if reader_mutex:
                reader_mutex[0].ReleaseMutex(reader_mutex[1]);reader_mutex[0].CloseHandle(reader_mutex[1])

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
            if not ready.get('ready'):raise RescueError(ready.get('error','Worker did not become ready'),ready.get('failure_class','WORKER_START_FAILED'),ready.get('phase','startup'),ready.get('winerror'))
        except BaseException:self.close();raise
    def reply(self,timeout):
        try:line=self.q.get(timeout=timeout)
        except queue.Empty:raise TimeoutError('READ_TIMEOUT')
        if not line:raise RuntimeError('Worker exited')
        return json.loads(line)
    def read(self,a,n):
        self.p.stdin.write(json.dumps([a,n])+'\n');self.p.stdin.flush();result=self.reply(8)
        if 'error' in result:raise RescueError(result['error'],result.get('failure_class','SOURCE_READ_ERROR'),result.get('phase','read'),result.get('winerror'))
        return result
    def close(self):
        if self.p.poll() is None:
            self.p.kill()
            # Keep the owning task and physical-disk locks until Windows confirms
            # that the child is gone. A hung kernel/USB request may delay this.
            self.p.wait()
        self.p.stdin.close();self.p.stdout.close()
        self.log.close()

def capture(root,stop,notify,reader_factory=Reader):
    import base64,msvcrt
    from contextlib import ExitStack
    root=Path(root).resolve();plan=load(root/'plan.json');validate(plan,root);require_physical_approval(root,plan);validate_live_exclusions(plan)
    if plan.get('kind')=='disk' and not PHYSICAL_READER_VALIDATED:
        raise ValueError('實體來源讀取被安全鎖定：目前 1.2 reader 未完成可丟棄設備驗收。')
    with ExitStack() as stack:
        lock=stack.enter_context((root/'active.lock').open('a+b'));lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        if plan['kind']=='disk':
            import ctypes as C
            k=C.WinDLL('kernel32',use_last_error=True)
            k.CreateMutexW.argtypes=[C.c_void_p,C.c_int,C.c_wchar_p];k.CreateMutexW.restype=C.c_void_p
            k.WaitForSingleObject.argtypes=[C.c_void_p,C.c_ulong];k.ReleaseMutex.argtypes=[C.c_void_p];k.CloseHandle.argtypes=[C.c_void_p]
            mutex=k.CreateMutexW(None,False,disk_mutex_name(plan))
            if not mutex:raise C.WinError(C.get_last_error())
            stack.callback(k.CloseHandle,mutex)
            if k.WaitForSingleObject(mutex,0) not in (0,128):raise RuntimeError('同一來源硬盤已有任務運行')
            stack.callback(k.ReleaseMutex,mutex)
            if plan.get('imported_map_source'):
                legacy=Path(plan['imported_map_source']).resolve()/'continuous.lock'
                shared=stack.enter_context(legacy.open('a+b'));shared.seek(0);msvcrt.locking(shared.fileno(),msvcrt.LK_NBLCK,1)
        rows=records(root)
        reconcile(root,rows)
        rows=records(root)
        excluded=[(x['offset'],x['offset']+x['length']) for x in rows if x['state'] in ('REQUESTED','GOOD','FAILED','UNCONFIRMED') and 'offset' in x]
        excluded += [(x['start'],x['end']) for x in rows if x['state']=='GUARD']+plan.get('guards',[])+plan.get('attempted',[])
        requested=merge([(x['offset'],x['offset']+x['length']) for x in rows if x['state']=='REQUESTED'])
        attempted=sum(max(0,min(z,plan['end'])-max(a,plan['start'])) for a,z in requested)
        total_budget=int(plan.get('total_budget_bytes',plan['end']-plan['start']))
        if not 0<=total_budget<=plan['end']-plan['start']:raise ValueError('Invalid total plan budget')
        total_good=sum(max(0,min(x['offset']+x['length'],plan['end'])-max(x['offset'],plan['start'])) for x in rows if x['state']=='GOOD')
        pass_index=0
        while True:
            if stop.is_set():
                status={'status':'STOPPED','source_writes':0,'retries':0,'new_bytes':0,'pass_index':pass_index,'total_attempted_bytes':attempted,'total_saved_bytes':total_good}
            elif attempted>=total_budget:
                status={'status':'PLAN_BUDGET_COMPLETE','source_writes':0,'retries':0,'new_bytes':0,'pass_index':pass_index,'total_attempted_bytes':attempted,'total_saved_bytes':total_good}
            else:
                status,excluded,attempted,total_good=_capture_pass(root,plan,stop,notify,reader_factory,excluded,attempted,total_good,pass_index,total_budget)
            pass_index+=1
            state=dict(status,plan_id=plan.get('plan_id'),total_budget_bytes=total_budget,pass_count=pass_index,
                destination_free_bytes=shutil.disk_usage(root).free,source_writes=0,retries=0)
            save(root/'status.json',state)
            save(root/'continuous-status.json',state)
            if not plan.get('continuous') or status['status']!='STAGE_COMPLETE':return status

def _capture_pass(root,plan,stop,notify,reader_factory,excluded,attempted,total_good,pass_index,total_budget):
    import base64
    todo=list(remaining(plan['start'],plan['end'],excluded));new=0;reader=None
    status={'status':'RUNNING','source_writes':0,'retries':0,'pid':os.getpid(),'pass_index':pass_index,'total_attempted_bytes':attempted,'total_saved_bytes':total_good}
    try:
        if not todo:status['status']='ELIGIBLE_SCOPE_COMPLETE';return status,excluded,attempted,total_good
        for a,z in todo:
            while a<z:
                if stop.is_set():status['status']='STOPPED';return status,excluded,attempted,total_good
                validate_live_exclusions(plan)
                budget_left=total_budget-attempted
                n=min(BLOCK,z-a,plan['stage_bytes']-new,budget_left)
                n=n//plan['sector']*plan['sector']
                if n<=0:
                    status['status']='PLAN_BUDGET_COMPLETE';return status,excluded,attempted,total_good
                if shutil.disk_usage(root).free-n<FLOOR:
                    status['status']='SPACE_LOW';return status,excluded,attempted,total_good
                name=f'chunk-{a//CHUNK:012d}.bin';path=contained(root,name)
                file_offset=path.stat().st_size if path.exists() else 0
                request_id=uuid.uuid4().hex
                try:
                    if reader is None:reader=reader_factory(root)
                except Exception as e:
                    category=classify_error(e,'startup')
                    status.update(status=category,failure_class=category,error=str(e),source_request_issued=False)
                    return status,excluded,attempted,total_good
                append(root/'map.jsonl',dict(state='REQUESTED',request_id=request_id,offset=a,length=n,file=name,file_offset=file_offset));excluded.append((a,a+n));attempted+=n
                try:
                    result=reader.read(a,n)
                    if 'error' in result:raise OSError(result['error'])
                    data=base64.b64decode(result['data'],validate=True)
                    if len(data)!=n:raise ValueError('Invalid returned data')
                except (OSError,TimeoutError,RuntimeError,ValueError) as e:
                    category=getattr(e,'failure_class',None) or classify_error(e,'read')
                    status.update(status='STOPPING_WAIT_FOR_IO',offset=a,error=str(e),failure_class=category,total_attempted_bytes=attempted);notify(dict(status))
                    try:reader.close()
                    except Exception as close_error:
                        status.update(status='DRIVER_CANCEL_UNCONFIRMED',close_error=str(close_error));return status,excluded,attempted,total_good
                    reader=None
                    if category in ('IO_TIMEOUT_UNCONFIRMED','IO_CANCELLED_UNCONFIRMED'):
                        append(root/'map.jsonl',dict(state='UNCONFIRMED',request_id=request_id,offset=a,length=n,error=str(e),failure_class=category))
                        status.update(status=category,offset=a,error=str(e));return status,excluded,attempted,total_good
                    if category in ('SOURCE_CRC_ERROR','SOURCE_READ_ERROR'):
                        append(root/'map.jsonl',dict(state='FAILED',request_id=request_id,offset=a,length=n,error=str(e),failure_class=category))
                        guard=int(plan['policy']['fault_guard_buffer_bytes']);guard_end=min(plan['end'],a+n+guard);guard_start=max(plan['start'],a-guard)
                        append(root/'map.jsonl',dict(state='GUARD',start=guard_start,end=guard_end,reason=category));excluded.append((guard_start,guard_end))
                        status.update(status='FAULT_STOP',offset=a,error=str(e));return status,excluded,attempted,total_good
                    if category=='SOURCE_DISCONNECTED':
                        append(root/'map.jsonl',dict(state='UNCONFIRMED',request_id=request_id,offset=a,length=n,error=str(e),failure_class=category))
                        status.update(status=category,offset=a,error=str(e));return status,excluded,attempted,total_good
                    append(root/'map.jsonl',dict(state='UNCONFIRMED',request_id=request_id,offset=a,length=n,error=str(e),failure_class=category))
                    status.update(status=category,offset=a,error=str(e));return status,excluded,attempted,total_good
                digest=hashlib.sha256(data).hexdigest()
                append(root/'map.jsonl',dict(state='RECEIVED',request_id=request_id,offset=a,length=n,file=name,file_offset=file_offset,sha256=digest))
                try:
                    mode='r+b' if path.exists() else 'w+b'
                    with path.open(mode) as f:
                        f.seek(file_offset)
                        if f.write(data)!=len(data):raise OSError('Short destination write')
                        phase='destination_flush';f.flush();os.fsync(f.fileno())
                except OSError as e:
                    category=classify_error(e,locals().get('phase','destination_write'))
                    status.update(status=category,failure_class=category,error=str(e),offset=a)
                    append(root/'map.jsonl',dict(state='UNCONFIRMED',request_id=request_id,offset=a,length=n,error=str(e),failure_class=category))
                    return status,excluded,attempted,total_good
                append(root/'map.jsonl',dict(state='GOOD',request_id=request_id,offset=a,length=n,file=name,file_offset=file_offset,sha256=digest))
                new+=n;total_good+=n;status.update(new_bytes=new,offset=a,total_attempted_bytes=attempted,total_saved_bytes=total_good)
                notify(dict(status));a+=n
                if result['seconds']>2:
                    guard_start=max(plan['start'],a-n-1024**3);guard_end=min(plan['end'],a+1024**3)
                    append(root/'map.jsonl',dict(state='GUARD',start=guard_start,end=guard_end,reason='SLOW_READ'));excluded.append((guard_start,guard_end))
                    status.update(status='FAULT_STOP',error='SLOW_READ');return status,excluded,attempted,total_good
                if new>=plan['stage_bytes']:
                    status['status']='STAGE_COMPLETE';return status,excluded,attempted,total_good
        status['status']='ELIGIBLE_SCOPE_COMPLETE'
        return status,excluded,attempted,total_good
    except Exception as e:
        status.update(status='ERROR',error=str(e));raise
    finally:
        try:
            if reader:reader.close()
        finally:
            save(root/'status.json',status);notify(dict(status))

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

def reconcile(root,rows=None):
    """Recover only data already received and durably mapped; never reread a source."""
    root=Path(root).resolve();rows=records(root) if rows is None else rows
    good_ids={r.get('request_id') for r in rows if r['state']=='GOOD' and r.get('request_id')}
    unresolved={r.get('request_id') for r in rows if r['state']=='UNCONFIRMED' and r.get('request_id')}
    received={r.get('request_id'):r for r in rows if r['state']=='RECEIVED' and r.get('request_id')}
    for request in rows:
        rid=request.get('request_id')
        if request['state']!='REQUESTED' or not rid or rid in good_ids or rid in unresolved:continue
        receipt=received.get(rid)
        if not receipt:continue
        try:
            path=contained(root,receipt['file'])
            with path.open('rb') as f:f.seek(int(receipt['file_offset']));data=f.read(int(receipt['length']))
            if len(data)!=int(receipt['length']) or hashlib.sha256(data).hexdigest()!=receipt['sha256']:
                raise ValueError('saved bytes do not match received hash')
            append(root/'map.jsonl',dict(state='GOOD',request_id=rid,offset=receipt['offset'],length=receipt['length'],file=receipt['file'],file_offset=receipt['file_offset'],sha256=receipt['sha256'],reconciled=True))
            good_ids.add(rid)
        except (OSError,KeyError,ValueError) as e:
            append(root/'map.jsonl',dict(state='UNCONFIRMED',request_id=rid,offset=request['offset'],length=request['length'],failure_class='DESTINATION_RECONCILIATION_REQUIRED',error=str(e)))
            unresolved.add(rid)

def verify(root):
    root=Path(root).resolve();p=load(root/'plan.json');validate_saved_output(p,root);ranges=[];size=0
    for r,b in good_blocks(root):ranges.append((r['offset'],r['offset']+len(b)));size+=len(b)
    gaps=list(remaining(p['start'],p['end'],ranges))
    out=dict(verified_bytes=size,missing_ranges=gaps,complete=not gaps,scope_start=p['start'],scope_end=p['end'])
    save(Path(root)/'verification.json',out);return out

def export_image(root,target):
    root=Path(root).resolve();target=Path(target).resolve()
    plan=load(root/'plan.json');validate_saved_output(plan,root)
    if plan.get('kind')=='disk':
        from platform_win import destination_identity
        if destination_identity(target.parent)['serial']==plan['serial']:
            raise ValueError('匯出映像不能寫回來源實體硬盤')
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
    root=Path(root).resolve();validate_saved_output(load(root/'plan.json'),root);out=root/('regions-'+uuid.uuid4().hex[:8]);out.mkdir();regions=[];stream=None;end=None
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
