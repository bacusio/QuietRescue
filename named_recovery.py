"""Restore an MFT nonresident stream from verified saved ranges only.

Volume geometry must be supplied with evidence; this module never guesses it.
Names are metadata, never trusted output paths. Full decoding remains required.
"""
import re,hashlib,os,shutil
from pathlib import Path
from ntfs_streams import parse
from saved_ranges import SavedRanges

def safe_name(names):
    ordered=sorted(names,key=lambda n:n['namespace']==2)
    for item in ordered:
        name=item['name']
        if (name in {'.','..'} or name.endswith((' ','.')) or
            re.search(r'[\x00-\x1f<>:"/\\|?*]',name) or
            re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.I)):
            continue
        if len(name.encode('utf-16-le'))<=240:return name
    raise ValueError('No safe original filename; preserve record for review')

class StreamView(SavedRanges):
    def __init__(self,index,extents):
        self.rows=index.rows;self.identity=index.identity;self.checked=index.checked
        self.index=index;self.extents=extents
    def parts(self,start,length):
        end=start+length;out=[];cursor=start
        for logical,physical,n in self.extents:
            lo=max(cursor,logical);hi=min(end,logical+n)
            if lo<hi:
                if lo!=cursor:raise ValueError('Missing logical file bytes')
                out.extend(self.index.parts(physical+lo-logical,hi-lo));cursor=hi
        if cursor!=end:raise ValueError('Missing logical file bytes')
        return out

def recover_record(index,raw,volume_start,cluster_bytes,geometry_evidence,destination,stop,progress=lambda x:None):
    if len(raw)>65536:raise ValueError('MFT record exceeds inspection limit')
    if not isinstance(geometry_evidence,str) or not geometry_evidence.strip():raise ValueError('Geometry evidence required')
    if type(volume_start)!=int or volume_start<0 or volume_start%512:raise ValueError('Invalid volume start')
    if cluster_bytes not in {512,1024,2048,4096,8192,16384,32768,65536}:raise ValueError('Invalid cluster size')
    record=parse(raw)
    if record['directory'] or record['has_attribute_list']:raise ValueError('Directory or extension records require reconciliation')
    if len(record['streams'])!=1:raise ValueError('Ambiguous unnamed stream')
    stream=record['streams'][0]
    name=safe_name(record['names']);root=Path(destination).resolve(strict=True)
    target=root/name;receipt=target.with_suffix(target.suffix+'.mft.json')
    if receipt.exists() or receipt.is_symlink():raise FileExistsError(receipt)
    if stream['resident']:
        if stream['flags']:raise ValueError('Unsupported resident attribute flags')
        data=bytes.fromhex(stream['resident_hex'])
        if len(data)!=stream['bytes']:raise ValueError('Resident value length mismatch')
        part=target.with_suffix(target.suffix+'.partial')
        if target.exists() or target.is_symlink() or part.exists() or part.is_symlink():raise FileExistsError(target)
        if stop.is_set():raise RuntimeError('Stopped')
        if shutil.disk_usage(root).free-len(data)<6_000_000_000:raise RuntimeError('Output space low')
        result=dict(status='EXPORTED_CONTENT_VALIDATION_REQUIRED',resident=True,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),record_sha256=hashlib.sha256(raw).hexdigest(),original_filename_from_mft=name,mft_times=record['times'],geometry_required=False,source_disk_reads=0,source_disk_writes=0,complete_original_file_proven=False,record_source_identity_proven=False)
        with part.open('xb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
        if stop.is_set():raise RuntimeError('Stopped; partial retained')
        from image_recovery import save
        save(receipt,result)
        part.rename(target)
        progress(dict(status='EXPORTED_RESIDENT_RECORD',copied_bytes=len(data),total_bytes=len(data)))
        return result
    if stream['unsupported_encoding'] or stream['start_vcn']!=0 or stream['initialized_bytes']<stream['bytes']:raise ValueError('Unsupported or incomplete stream')
    length=stream['bytes'];extents=[];cursor=0
    for run in stream['runs']:
        if cursor>=length:break
        if run['sparse'] or run['vcn']*cluster_bytes!=cursor:raise ValueError('Sparse or missing extent')
        n=min(length-cursor,run['clusters']*cluster_bytes)
        physical=volume_start+run['lcn']*cluster_bytes
        if physical+n>index.identity[1]:raise ValueError('Extent beyond source disk')
        index.parts(physical,n) # Reject missing saved bytes before output is created.
        extents.append((cursor,physical,n));cursor+=n
    if cursor!=length or not length:raise ValueError('Incomplete stream length')
    result=StreamView(index,extents).export(0,length,root/name,stop,progress)
    result.update(original_filename_from_mft=name,geometry_evidence=geometry_evidence,volume_start=volume_start,cluster_bytes=cluster_bytes,mft_times=record['times'],complete_original_file_proven=False)
    from image_recovery import save
    save((root/name).with_suffix((root/name).suffix+'.mft.json'),result)
    return result
