"""PhotoRec extraction of regular saved images; never opens a physical device."""
import ctypes, hashlib, json, os, shutil, subprocess, sys, time, uuid
from pathlib import Path

PHOTO_SHA='d75b9a6ff60f91479085a578aca518abb1cd7405f24506a61afa2f7e222147bf'
FLOOR=6_000_000_000
FORMATS=('jpg','png','tif','bmp','gif','mov','mkv','riff','mpg','pdf','zip','rar','7z','doc')
SCRIPT='partition_none,fileopt,everything,disable,'+','.join(x+',enable' for x in FORMATS)+',search'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    return h.hexdigest()

def find_photorec():
    roots=[Path(sys.executable).parent,Path(__file__).resolve().parent]
    for root in roots:
        p=root/'vendor/testdisk-7.2/photorec_win.exe'
        if p.is_file() and sha(p)==PHOTO_SHA and (p.parent/'63/cygwin').is_file():return p
    raise RuntimeError('缺少已驗證 PhotoRec 7.2；請使用包含 vendor 的完整安裝包。')

def ascii_path(path):
    p=str(Path(path).resolve())
    if p.isascii() and ' ' not in p:return p
    if os.name=='nt':
        api=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        api.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint];api.restype=ctypes.c_uint
        buf=ctypes.create_unicode_buffer(32768);n=api(p,buf,len(buf))
        if 0<n<len(buf) and buf.value.isascii() and ' ' not in buf.value:return buf.value
    raise ValueError('PhotoRec 無法可靠解析此路徑；請選不含空格的英文保存路徑，例如 R:\\QuietRescue。原鏡像路徑可含中文。')

def save(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    temp.replace(path)

def require_scan_finished(job):
    """PhotoRec phrecn.c removes its session only after final PSTATUS_OK.

    Exit code zero also occurs on some stopped paths; never discard the staged
    image or report completion while a checkpoint remains, even an empty one.
    """
    session=Path(job)/'photorec.ses'
    if session.exists() or session.is_symlink():
        raise RuntimeError('PhotoRec 保留了斷點；尚未證明掃描完成，鏡像與提取內容保留')

def recover(image,destination,stop,progress=lambda info:None):
    original=Path(image)
    if original.is_symlink() or original.is_junction():raise ValueError('不接受重解析來源')
    source=original.resolve(strict=True);dest=Path(destination).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in {'.img','.bin','.dd','.raw','.partial'}:
        raise ValueError('只接受已保存的 .img/.bin/.dd/.raw/.partial 普通檔案')
    if source.is_symlink() or source.is_junction():raise ValueError('不接受重解析來源')
    exe=find_photorec();ascii_path(dest)
    before=source.stat()
    if shutil.disk_usage(dest).free-before.st_size<FLOOR:raise RuntimeError('空間不足以建立暫存鏡像並保留 6GB')
    job=dest/('PhotoRec-'+uuid.uuid4().hex[:10]);job.mkdir()
    stage=job/'input.img';log=job/'photorec.log';manifest=job/'recovery.json'
    result=dict(status='COPYING_LOCAL_IMAGE',source=str(source),source_bytes=before.st_size,source_disk_reads=0,source_disk_writes=0,original_image_deleted=False,original_filename_known=False,complete_original_files_proven=False)
    def emit(state,**values):
        result.update(status=state,**values);save(manifest,result);progress(dict(result))
    child=None
    try:
        copied=0;h=hashlib.sha256();last=0
        with source.open('rb') as src,stage.open('xb') as dst:
            for data in iter(lambda:src.read(8*1024**2),b''):
                if stop.is_set():raise RuntimeError('使用者停止；保留原鏡像')
                if shutil.disk_usage(dest).free-len(data)<FLOOR:raise RuntimeError('空間保護停止')
                dst.write(data);h.update(data);copied+=len(data)
                if time.monotonic()-last>=1:emit('COPYING_LOCAL_IMAGE',copied_bytes=copied);last=time.monotonic()
            dst.flush();os.fsync(dst.fileno())
        after=source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('鏡像在提取期間被修改')
        if sha(stage)!=h.hexdigest():raise RuntimeError('暫存鏡像雜湊不一致')
        result['input_sha256']=h.hexdigest()
        safe=Path(ascii_path(job))
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}}
        env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',__COMPAT_LAYER='RunAsInvoker')
        from partition_scan import ReadOnlyLease
        with ReadOnlyLease(stage),log.open('wb') as output:
            child=subprocess.Popen([str(exe),(safe/'input.img').as_posix(),'/d',str(safe/'recovered'),'/cmd',(safe/'input.img').as_posix(),SCRIPT],cwd=safe,stdout=output,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            last=0;started=time.monotonic()
            while child.poll() is None:
                if stop.is_set() or shutil.disk_usage(dest).free<FLOOR or time.monotonic()-started>14400:
                    child.kill();child.wait(timeout=15);raise RuntimeError('停止／空間或時間保護；已提取結果保留')
                if time.monotonic()-last>=2:
                    emit('PHOTOREC_RUNNING',elapsed_seconds=round(time.monotonic()-started),log_bytes=log.stat().st_size);last=time.monotonic()
                time.sleep(.25)
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-65536));tail=f.read().lower()
        if child.returncode or any(x in tail for x in (b'syntax error',b'unable to open',b'no such file',b'permission denied')):
            raise RuntimeError('PhotoRec 未成功完成，請查看 '+str(log))
        require_scan_finished(job)
        files=[p for folder in job.glob('recovered.*') if folder.is_dir() for p in folder.iterdir() if p.is_file() and p.name not in {'report.xml','report.xml.bak'}]
        # Saved-output checks only. A structural pass never authorizes image deletion.
        from document_validation import validate_document
        documents=[]
        for p in files:
            if stop.is_set():raise RuntimeError('使用者停止；提取結果保留')
            if p.suffix.lower() in {'.doc','.docx','.xlsx','.pptx','.pdf'}:
                emit('VALIDATING_SAVED_DOCUMENT',path=str(p))
                documents.append(validate_document(p, parse_pdf=False))
                save(job/'document-validation.json',dict(files=documents,original_file_complete_proven=False))
        result['documents_checked']=len(documents)
        emit('EXTRACTION_COMPLETE_VALIDATION_REQUIRED',recovered_files=len(files),recovered_bytes=sum(p.stat().st_size for p in files),output=str(job))
        # Only our disposable copy, never the user's original image.
        stage.unlink()
        return result
    except Exception as e:
        if child and child.poll() is None:child.kill();child.wait(timeout=15)
        emit('STOPPED_ERROR',error=str(e));raise
