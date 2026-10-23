"""Recover decodable JPEG/PNG only from verified contiguous bytes, not holes."""
import io,hashlib,shutil
from pathlib import Path
from PIL import Image
from engine import good_blocks,FLOOR,save,records,merge,load,validate_saved_output
from jpeg_parser import jpeg_length
Image.MAX_IMAGE_PIXELS=80_000_000

def recover_photos(root):
    root=Path(root).resolve();validate_saved_output(load(root/'plan.json'),root);out=root/'photos';out.mkdir(exist_ok=True)
    buffer=b'';start=0;end=None;found=[];seen=set()
    for row,data in good_blocks(root):
        if end!=row['offset']:buffer=b'';start=row['offset']
        buffer+=data;end=row['offset']+len(data)
        while buffer:
            candidates=[(buffer.find(sig),sig) for sig in (b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')]
            candidates=[x for x in candidates if x[0]>=0]
            if not candidates:
                keep=min(8,len(buffer));start+=len(buffer)-keep;buffer=buffer[-keep:];break
            at,sig=min(candidates);start+=at;buffer=buffer[at:]
            try:
                if sig.startswith(b'\xff'):finish=jpeg_length(buffer)
                else:
                    finish=buffer.find(b'IEND\xaeB`\x82',len(sig))
                    finish=finish+8 if finish>=0 else None
            except ValueError:start+=1;buffer=buffer[1:];continue
            if finish is None:
                if len(buffer)>64*1024**2:start+=1;buffer=buffer[1:];continue
                break
            blob=buffer[:finish];digest=hashlib.sha256(blob).hexdigest()
            try:
                im=Image.open(io.BytesIO(blob));im.load()
                if im.width<64 or im.height<64:raise ValueError('tiny')
                if shutil.disk_usage(root).free-len(blob)<FLOOR:raise OSError('SPACE_LOW')
                ext='.jpg' if sig.startswith(b'\xff') else '.png';path=out/(digest+ext)
                if digest not in seen:
                    if not path.exists():path.write_bytes(blob)
                    found.append(dict(path=str(path),physical_offset=start,sha256=digest,width=im.width,height=im.height,original_name_known=False));seen.add(digest)
            except (ValueError,SyntaxError,Image.UnidentifiedImageError,Image.DecompressionBombError):pass
            except OSError as e:
                if str(e)=='SPACE_LOW':raise
            start+=finish;buffer=buffer[finish:]
    save(root/'photo-recovery.json',dict(files=found,source_reads=0,original_names_available=False));return found

def avoidance(root):
    root=Path(root).resolve();plan=load(root/'plan.json');validate_saved_output(plan,root)
    classified=[]
    labels={'FAILED':'OBSERVED_READ_ERROR_NOT_PROVEN_PHYSICAL_BAD',
        'REQUESTED':'UNCONFIRMED_REQUEST_DO_NOT_RETRY',
        'UNCONFIRMED':'UNCONFIRMED_REQUEST_DO_NOT_RETRY',
        'GUARD':'POLICY_GUARD_NOT_PROVEN_BAD'}
    for row in records(root):
        state=row.get('state')
        if state in labels and 'offset' in row:
            a=int(row['offset']);z=a+int(row['length'])
            classified.append((a,z,labels[state]))
        elif state=='GUARD':classified.append((int(row['start']),int(row['end']),labels[state]))
    for a,z in plan.get('guards',[]):classified.append((int(a),int(z),'IMPORTED_POLICY_GUARD_NOT_PROVEN_BAD'))
    for a,z in plan.get('attempted',[]):classified.append((int(a),int(z),'PREVIOUSLY_ATTEMPTED_NOT_PROVEN_BAD'))
    # Preserve evidence classes; only merge overlapping intervals of the same class.
    groups={}
    for a,z,label in classified:
        if a<z:groups.setdefault(label,[]).append((a,z))
    compact=[(a,z,label) for label,ranges in groups.items() for a,z in merge(ranges)]
    import csv
    path=root/'avoidance.csv'
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['start_byte','end_exclusive_byte','classification'])
        for a,z,label in sorted(compact):w.writerow([a,z,label])
    return path
