"""Decode saved movies only; no network protocols or source-device handles."""
import json,os,subprocess,time
from pathlib import Path
from image_recovery import sha
def validate_video(path,ffmpeg,stop):
    p=Path(path).resolve(strict=True);exe=Path(ffmpeg).resolve(strict=True);probe=exe.with_name('ffprobe.exe')
    if exe.name.lower()!='ffmpeg.exe' or not probe.is_file():raise ValueError('Choose ffmpeg.exe with adjacent ffprobe.exe')
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}}
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0);result=dict(validation='NOT_VALIDATED',path=str(p),bytes=p.stat().st_size,original_file_complete_proven=False)
    meta=subprocess.run([str(probe),'-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(p)],capture_output=True,env=env,timeout=60,creationflags=flags)
    if meta.returncode:result['validation']='PROBE_FAILED';return result
    data=json.loads(meta.stdout)
    if not any(s.get('codec_type')=='video' for s in data.get('streams',[])):result['validation']='NO_VIDEO_STREAM';return result
    result['duration_seconds']=data.get('format',{}).get('duration');result['sha256']=sha(p)
    log=p.with_suffix(p.suffix+'.decode.log');before=p.stat();child=None
    try:
        with log.open('wb') as errors:
            child=subprocess.Popen([str(exe),'-nostdin','-v','error','-xerror','-err_detect','explode','-protocol_whitelist','file,pipe','-i',str(p),'-map','0:v?','-map','0:a?','-f','null','-'],stdout=subprocess.DEVNULL,stderr=errors,env=env,creationflags=flags)
            start=time.monotonic()
            while child.poll() is None:
                if stop.is_set() or time.monotonic()-start>3600:
                    child.kill();child.wait(15);result['validation']='DECODE_STOPPED_OR_TIMED_OUT';return result
                time.sleep(.25)
        after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Movie changed during decode')
        result['validation']='FULL_AVAILABLE_STREAM_DECODE_PASS' if child.returncode==0 else 'DECODE_FAILED'
        result['decode_log']=str(log);return result
    finally:
        if child and child.poll() is None:child.kill();child.wait(15)
