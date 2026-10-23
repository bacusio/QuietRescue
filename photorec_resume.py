"""Bounded saved-image session execution; never open a physical disk."""
import os,shutil,subprocess,time,uuid
from pathlib import Path
from image_recovery import FLOOR,ascii_path,find_photorec,save,require_scan_finished
from partition_scan import ReadOnlyLease
from photorec_session import validate_checkpoint,resume_command

def resume(job,stop,progress=lambda info:None):
    job=Path(job)
    if job.is_symlink() or job.is_junction():raise ValueError('Reparse job rejected')
    job=job.resolve(strict=True)
    lockpath=job/'resume.lock'
    if lockpath.is_symlink() or lockpath.is_junction():raise ValueError('Reparse lock rejected')
    with lockpath.open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        # Deny writes/deletion for the entire hash check and child execution.
        with ReadOnlyLease(job/'input.img'):
            state,original,normalized,info=validate_checkpoint(job,stop)
            exe=find_photorec()
            if stop.is_set():raise RuntimeError('Stopped')
            if shutil.disk_usage(job).free<FLOOR:raise RuntimeError('6GB free space reserve required')
            attempt=job/('resume-'+uuid.uuid4().hex);attempt.mkdir()
            safe=Path(ascii_path(attempt))
            # Never edit the original session or reuse a previous output directory.
            for name,data in [('original-session.ses',original),('photorec.ses',normalized)]:
                with (attempt/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            state.update(resume_attempt=str(attempt),status='RESUME_STARTING')
            save(job/'recovery.json',state)
            result=dict(status='RESUME_STARTING',output=str(attempt),checkpoint=info,
                        input_sha256=state['input_sha256'],worker_exit_confirmed=False,
                        original_image_deleted=False,complete_original_files_proven=False)
            def emit(status,**values):
                result.update(status=status,**values);save(attempt/'resume.json',result);progress(dict(result))
            child=None
            try:
                env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}}
                env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',__COMPAT_LAYER='RunAsInvoker')
                with (attempt/'stdout.log').open('xb') as output:
                    child=subprocess.Popen(resume_command(exe,job/'input.img',safe/'recovered'),cwd=safe,
                        env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    started=time.monotonic();last=0
                    while child.poll() is None:
                        if stop.is_set() or shutil.disk_usage(job).free<FLOOR or time.monotonic()-started>14400:
                            child.kill();child.wait(15);raise RuntimeError('Stopped by user, space or time protection')
                        if time.monotonic()-last>=2:
                            emit('RESUMING_SAVED_IMAGE',pid=child.pid,elapsed_seconds=round(time.monotonic()-started));last=time.monotonic()
                        time.sleep(.25)
                with (attempt/'stdout.log').open('rb') as f:
                    f.seek(max(0,f.seek(0,2)-65536));tail=f.read().lower()
                result['worker_exit_confirmed']=True
                if child.returncode or any(x in tail for x in (b'syntax error',b'unable to open',b'no such file',b'permission denied')):
                    raise RuntimeError('PhotoRec resume failed; retain session and inspect logs')
                require_scan_finished(attempt)
                files=[p for folder in attempt.glob('recovered.*') if folder.is_dir() for p in folder.iterdir() if p.is_file() and p.name not in {'report.xml','report.xml.bak'}]
                emit('EXTRACTION_COMPLETE_VALIDATION_REQUIRED',recovered_files=len(files),recovered_bytes=sum(p.stat().st_size for p in files))
                state.update(status=result['status']);save(job/'recovery.json',state)
                return result
            except Exception as exc:
                if child and child.poll() is None:child.kill();child.wait(15)
                emit('STOPPED_ERROR',error=str(exc),worker_exit_confirmed=bool(child is not None and child.poll() is not None))
                state.update(status='STOPPED_ERROR',error=str(exc));save(job/'recovery.json',state)
                raise
