"""Discover and reconstruct declared MKV ranges across saved mapping files."""
import hashlib,json,os,time
from pathlib import Path
from container_headers import mkv_length
from saved_ranges import SavedRanges,BUFFER
from image_recovery import save,sha

def discover(index,stop,progress=lambda value:None):
    tail=b'';end=None;seen=set();found=[];scanned=0;last=0
    total=sum(r['end']-r['start'] for r in index.rows)
    for row in index.rows:
        index._verify(row,stop)
        if end!=row['start']:tail=b''
        cursor=row['start'];remaining=row['end']-cursor
        with Path(row['path']).open('rb') as stream:
            stream.seek(row['file_offset'])
            while remaining:
                if stop.is_set():raise RuntimeError('Stopped')
                block=stream.read(min(BUFFER,remaining))
                if not block:raise ValueError('Short image')
                data=tail+block;base=cursor-len(tail);pos=0
                while True:
                    at=data.find(b'\x1aE\xdf\xa3',pos)
                    if at<0:break
                    pos=at+4;origin=base+at
                    if origin in seen:continue
                    meta=mkv_length(data[at:at+131072])
                    if not meta:continue
                    seen.add(origin);entry=dict(start_byte=origin,**meta,saved_coverage_complete=False)
                    n=meta['declared_bytes']
                    if n and 0<n<=100_000_000_000:
                        try:index.parts(origin,n);entry['saved_coverage_complete']=True
                        except ValueError:entry['reason']='MISSING_SAVED_BYTES'
                    else:entry['reason']='UNKNOWN_OR_IMPLAUSIBLE_LENGTH'
                    found.append(entry)
                tail=data[-131072:];cursor+=len(block);remaining-=len(block);scanned+=len(block)
                if time.monotonic()-last>1:
                    progress(dict(status='SCANNING_SAVED_MKV_HEADERS',copied_bytes=scanned,total_bytes=total,candidates=len(found)));last=time.monotonic()
        index._unchanged(row);end=row['end']
    return found

def recover(jobs,destination,stop,progress=lambda value:None,ffmpeg=None,validate_destination=None):
    dest=Path(destination).resolve(strict=True)
    index=SavedRanges(jobs,cleanup_ledgers=sorted(dest.glob('lossless-cleanup-ledger*.json')),recovered_root=dest)
    if validate_destination:validate_destination(index.identity,dest)
    job_key=hashlib.sha256(json.dumps([index.identity,sorted(str(Path(p).resolve()) for p in jobs)],ensure_ascii=False).encode()).hexdigest()[:16]
    job=dest/('MappedVideos-'+job_key);job.mkdir(exist_ok=True)
    # A kernel-held lock automatically releases if the process exits.
    lock=(job/'active.lock').open('a+b')
    try:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _recover_locked(index,job,stop,progress,ffmpeg)
    finally:lock.close()

def _recover_locked(index,job,stop,progress,ffmpeg):
    fingerprint=hashlib.sha256(json.dumps(index.rows,sort_keys=True).encode()).hexdigest()
    manifest=job/'recovery.json'
    if manifest.exists():
        result=json.loads(manifest.read_text(encoding='utf-8'))
        if result.get('input_fingerprint')!=fingerprint:raise ValueError('Saved mapping changed; preserve this job and select a separate output folder for review')
        found=result.get('candidates')
    else:
        found=None
        result=dict(status='SCANNING',input_fingerprint=fingerprint,source_identity=index.identity,candidates=None,outputs=[],source_disk_reads=0,source_disk_writes=0,output=str(job))
        save(manifest,result)
    if found is None:
        found=discover(index,stop,progress);result.update(status='CANDIDATES_FOUND',candidates=found);save(manifest,result)
    for candidate in found:
        if not candidate['saved_coverage_complete']:continue
        if stop.is_set():raise RuntimeError('Stopped')
        path=job/f"Candidate-{candidate['start_byte']}.mkv"
        previous=next((r for r in result['outputs'] if r['start_byte']==candidate['start_byte']),None)
        if path.exists():
            if path.is_symlink():raise ValueError('Reparse output rejected')
            record=previous or json.loads(path.with_suffix(path.suffix+'.json').read_text(encoding='utf-8'))
            if record['start_byte']!=candidate['start_byte'] or record['bytes']!=candidate['declared_bytes'] or path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:raise ValueError('Existing restored movie changed')
        else:
            if previous:raise ValueError('Previously restored movie was moved or removed; no automatic recreation')
            record=index.export(candidate['start_byte'],candidate['declared_bytes'],path,stop,progress)
        validation=record.get('validation',{}).get('validation')
        if ffmpeg and validation not in {'FULL_AVAILABLE_STREAM_DECODE_PASS','DECODE_FAILED','PROBE_FAILED','NO_VIDEO_STREAM'}:
            from media_validation import validate_video
            progress(dict(status='VALIDATING_VIDEO',path=str(path)))
            record['validation']=validate_video(path,ffmpeg,stop)
        result['outputs']=[r for r in result['outputs'] if r['start_byte']!=candidate['start_byte']]
        result['outputs'].append(dict(record,path=str(path)));save(job/'recovery.json',result)
        if record.get('validation',{}).get('validation')=='DECODE_STOPPED_OR_TIMED_OUT':
            result['status']='VALIDATION_INTERRUPTED';save(job/'recovery.json',result);return result
    result['status']='RECONSTRUCTION_AND_VALIDATION_FINISHED' if ffmpeg else 'RECONSTRUCTION_COMPLETE_DECODE_VALIDATION_REQUIRED';save(job/'recovery.json',result)
    return result
