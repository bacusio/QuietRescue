"""Bounded-memory, hash-checked reads across saved QuietRescue jobs.

Only GOOD blocks are used. A missing range raises; never fill gaps with zeros.
Source serial and size must agree across all imported jobs.
"""
import hashlib,json,os,uuid
from pathlib import Path
from image_recovery import save
RAW={'.bin','.img','.dd','.partial','.raw'}
BUFFER=8*1024**2

class SavedRanges:
    def __init__(self,jobs,cleanup_ledgers=(),recovered_root=None):
        self.rows=[];self.identity=None;self.checked={}
        replacements={}
        for ledger in cleanup_ledgers:
            lp=Path(ledger)
            if recovered_root is None or lp.is_symlink() or lp.is_junction() or lp.stat().st_size>10*1024**2:raise ValueError('Invalid cleanup ledger')
            allowed=Path(recovered_root).resolve(strict=True)
            if not lp.resolve().is_relative_to(allowed):raise ValueError('Ledger outside selected recovery folder')
            contents=json.loads(lp.read_text(encoding='utf-8'))
            if contents.get('status')!='COMPLETE':raise ValueError('Cleanup ledger is not complete')
            for entry in contents['files']:
                original=str(Path(entry['path']).resolve())
                video=Path(entry['reconstruction_video'])
                if video.is_symlink() or video.is_junction():raise ValueError('Reparse replacement rejected')
                video=video.resolve(strict=True)
                if not video.is_relative_to(allowed) or video.suffix.lower()!='.mkv':raise ValueError('Replacement outside selected recovery folder')
                if type(entry['video_offset'])!=int or type(entry['bytes'])!=int or entry['video_offset']<0 or entry['bytes']<=0 or entry['video_offset']+entry['bytes']>video.stat().st_size:raise ValueError('Invalid replacement bounds')
                if len(entry['video_sha256'])!=64:raise ValueError('Missing replacement hash')
                replacement=dict(entry,video_path=str(video))
                if original in replacements and replacements[original]!=replacement:raise ValueError('Conflicting cleanup receipts')
                replacements[original]=replacement
        for directory in jobs:
            root=Path(directory).resolve(strict=True)
            plan=json.loads((root/'plan.json').read_text(encoding='utf-8-sig'))
            serial=plan.get('serial',plan.get('source_serial'));size=plan.get('size',plan.get('source_size'))
            if not serial or not isinstance(size,int) or size<=0:raise ValueError('Missing physical-source identity')
            identity=(serial,size)
            if self.identity and self.identity!=identity:raise ValueError('Different source disks cannot be merged')
            self.identity=identity
            mapfile=root/'map.jsonl'
            if not mapfile.exists():mapfile=root/'requests.jsonl'
            with mapfile.open(encoding='utf-8-sig') as stream:
                for line in stream:
                    try:r=json.loads(line)
                    except ValueError:raise ValueError('Incomplete mapping; review before importing')
                    if r.get('state')!='GOOD':continue
                    raw=Path(r.get('file',r.get('path','')))
                    p=raw if raw.is_absolute() else root/raw
                    if p.is_symlink() or p.is_junction():raise ValueError('Reparse image rejected')
                    p=p.resolve()
                    if not p.is_relative_to(root) or p.suffix.lower() not in RAW:raise ValueError('Image outside selected job')
                    a=int(r['offset']);n=int(r['length']);off=int(r['file_offset']);extra={}
                    if not p.is_file():
                        replacement=replacements.get(str(p))
                        if replacement is None:continue
                        if off<0 or off+n>replacement['bytes']:raise ValueError('Block outside original cleanup extent')
                        extra=dict(container_sha256=replacement['video_sha256'],replaced_original=str(p))
                        p=Path(replacement['video_path']);off+=replacement['video_offset']
                    st=p.stat()
                    if a<0 or n<=0 or a+n>size or off<0 or off+n>st.st_size:raise ValueError('Invalid mapped bounds')
                    if len(r['sha256'])!=64:raise ValueError('Missing block hash')
                    self.rows.append(dict(start=a,end=a+n,path=str(p),file_offset=off,sha256=r['sha256'],stat=(st.st_size,st.st_mtime_ns),**extra))
        self.rows.sort(key=lambda r:(r['start'],r['end']))
        unique={}
        for r in self.rows:
            k=(r['start'],r['end'])
            if k in unique and unique[k]['sha256']!=r['sha256']:raise ValueError('Conflicting saved GOOD blocks')
            unique.setdefault(k,r)
        self.rows=list(unique.values())
        for left,right in zip(self.rows,self.rows[1:]):
            if right['start']<left['end']:raise ValueError('Overlapping mappings require explicit reconciliation')

    def _unchanged(self,row):
        st=Path(row['path']).stat()
        if (st.st_size,st.st_mtime_ns)!=row['stat']:raise ValueError('Saved image changed')

    def _verify(self,row,stop):
        self._unchanged(row);key=(row['path'],row['file_offset'],row['end']-row['start'],row['sha256'])
        if row.get('container_sha256'):
            container_key=('container',row['path'],row['container_sha256'])
            if container_key not in self.checked:
                container=hashlib.sha256()
                with Path(row['path']).open('rb') as stream:
                    while True:
                        if stop.is_set():raise RuntimeError('Stopped')
                        data=stream.read(BUFFER)
                        if not data:break
                        container.update(data)
                self._unchanged(row)
                if container.hexdigest()!=row['container_sha256']:raise ValueError('Replacement movie hash mismatch')
                self.checked[container_key]=True
        if key in self.checked:return
        h=hashlib.sha256();remaining=row['end']-row['start']
        with Path(row['path']).open('rb') as f:
            f.seek(row['file_offset'])
            while remaining:
                if stop.is_set():raise RuntimeError('Stopped')
                b=f.read(min(BUFFER,remaining))
                if not b:raise ValueError('Short saved block')
                h.update(b);remaining-=len(b)
        self._unchanged(row)
        if h.hexdigest()!=row['sha256']:raise ValueError('Saved block hash mismatch')
        self.checked[key]=True

    def parts(self,start,length):
        if start<0 or length<=0:raise ValueError('Invalid requested range')
        cursor=start;end=start+length;result=[]
        while cursor<end:
            choices=[r for r in self.rows if r['start']<=cursor<r['end']]
            if not choices:raise ValueError('Missing saved bytes at '+str(cursor))
            row=max(choices,key=lambda r:r['end']);n=min(end,row['end'])-cursor
            result.append((row,cursor-row['start'],n));cursor+=n
        return result

    def export(self,start,length,target,stop,progress=lambda info:None):
        import shutil
        if Path(target).is_symlink() or Path(target).is_junction():raise ValueError('Reparse output rejected')
        output=Path(target).resolve();part=output.with_suffix(output.suffix+'.partial')
        checkpoint=part.with_suffix(part.suffix+'.checkpoint.json')
        receipt=output.with_suffix(output.suffix+'.json')
        if output.exists() or output.is_symlink():raise FileExistsError(output)
        rows=self.parts(start,length)  # Reject holes before creating any output.
        if any(output==Path(r['path']) for r in self.rows):raise ValueError('Cannot overwrite input')
        binding=hashlib.sha256(json.dumps(dict(identity=self.identity,start=start,length=length,rows=rows),sort_keys=True).encode()).hexdigest()
        h=hashlib.sha256();copied=0;mapping=[]
        if part.is_symlink() or part.is_junction() or checkpoint.is_symlink() or checkpoint.is_junction():raise ValueError('Reparse output rejected')
        resuming=part.exists() and checkpoint.exists()
        if part.exists()!=checkpoint.exists():raise FileExistsError('Unrecognized partial export')
        if resuming:
            state=json.loads(checkpoint.read_text(encoding='utf-8'))
            if (state.get('version')!=1 or state.get('binding')!=binding or
                type(state.get('copied')) is not int or not 0<=state['copied']<=length or
                not isinstance(state.get('sha256'),str) or len(state['sha256'])!=64):
                raise ValueError('Partial export checkpoint does not match inputs')
            copied=state['copied']
            if part.stat().st_size<copied:raise ValueError('Partial export shorter than checkpoint')
            # Authenticate every source block before changing the partial file.
            for row,_,_ in rows:self._verify(row,stop)
            with part.open('rb') as src:
                remaining=copied
                while remaining:
                    if stop.is_set():raise RuntimeError('Stopped')
                    b=src.read(min(BUFFER,remaining))
                    if not b:raise ValueError('Partial export truncated')
                    h.update(b);remaining-=len(b)
            if h.hexdigest()!=state['sha256']:raise ValueError('Partial export prefix changed')
        elif receipt.exists() or receipt.is_symlink():
            raise FileExistsError(receipt)
        if shutil.disk_usage(output.parent).free-(length-copied)<6_000_000_000:raise RuntimeError('Output space low')

        def persist():
            state=dict(version=1,binding=binding,copied=copied,sha256=h.hexdigest())
            temp=checkpoint.with_name(checkpoint.name+'.'+uuid.uuid4().hex+'.tmp')
            with temp.open('x',encoding='utf-8') as stream:
                json.dump(state,stream);stream.flush();os.fsync(stream.fileno())
            temp.replace(checkpoint)

        with part.open('r+b' if resuming else 'xb') as dst:
            if resuming:dst.truncate(copied);dst.seek(copied)
            else:persist()
            position=0;resume_bytes=copied
            for row,within,n in rows:
                skip=min(max(resume_bytes-position,0),n);position+=n
                if skip==n:
                    mapping.append(dict(path=row['path'],file_offset=row['file_offset']+within,bytes=n,block_sha256=row['sha256']))
                    continue
                self._verify(row,stop)
                with Path(row['path']).open('rb') as src:
                    src.seek(row['file_offset']+within+skip);remaining=n-skip
                    while remaining:
                        if stop.is_set():raise RuntimeError('Stopped')
                        b=src.read(min(BUFFER,remaining))
                        if not b:raise ValueError('Saved input truncated')
                        if shutil.disk_usage(output.parent).free-len(b)<6_000_000_000:raise RuntimeError('Output space low')
                        dst.write(b);h.update(b);remaining-=len(b);copied+=len(b)
                        dst.flush();os.fsync(dst.fileno());persist()
                        progress(dict(status='EXPORTING_VERIFIED_RANGE',copied_bytes=copied,total_bytes=length))
                self._unchanged(row)
                mapping.append(dict(path=row['path'],file_offset=row['file_offset']+within,bytes=n,block_sha256=row['sha256']))
            dst.flush();os.fsync(dst.fileno())
        result=dict(status='EXPORTED_CONTENT_VALIDATION_REQUIRED',source_identity=self.identity,start_byte=start,end_exclusive_byte=start+length,bytes=copied,sha256=h.hexdigest(),spans=mapping,source_disk_reads=0,source_disk_writes=0,original_name_proven=False)
        if receipt.exists():
            if json.loads(receipt.read_text(encoding='utf-8'))!=json.loads(json.dumps(result)):raise ValueError('Export receipt changed')
        else:save(receipt,result)
        part.rename(output)
        checkpoint.unlink()
        return result
