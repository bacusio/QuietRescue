"""Strict bounded EBML length parsing; unknown length is never guessed."""
def vint(b,pos,identifier=False):
    if pos>=len(b) or b[pos]==0:raise ValueError('Invalid VINT')
    n=1
    while not b[pos]&(1<<(8-n)):
        n+=1
        if n>8:raise ValueError('Invalid VINT width')
    if pos+n>len(b):raise ValueError('Short VINT')
    value=int.from_bytes(b[pos:pos+n],'big')
    if not identifier:value&=(1<<(7*n))-1
    return value,n,not identifier and value==(1<<(7*n))-1
def mkv_length(b):
    if b[:4]!=b'\x1aE\xdf\xa3':return None
    try:
        size,n,unknown=vint(b,4)
        if unknown or size>65536:return None
        limit=4+n+size;pos=4+n;doctype=None
        while pos<limit:
            key,k,_=vint(b,pos,True);length,v,u=vint(b,pos+k);data=pos+k+v
            if u or data+length>limit or data+length>len(b):return None
            if key==0x4282:doctype=b[data:data+length]
            pos=data+length
        if doctype not in (b'matroska',b'webm'):return None
        pos=limit
        for _ in range(8):
            key,k,_=vint(b,pos,True);size,s,u=vint(b,pos+k);data=pos+k+s
            if key==0x18538067:return dict(doctype=doctype.decode(),declared_bytes=None if u else data+size)
            if u or size>65536:return None
            pos=data+size
    except (ValueError,IndexError):return None
    return None
