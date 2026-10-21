def jpeg_length(data):
    """Return true EOI, skipping EXIF thumbnails and entropy stuffing; None means incomplete."""
    if len(data)<2:return None
    if data[:2]!=b'\xff\xd8':raise ValueError('Not JPEG')
    p=2;entropy=False
    while p<len(data):
        if entropy:
            q=data.find(b'\xff',p)
            if q<0:return None
            p=q
        if data[p]!=255:raise ValueError('Invalid JPEG marker')
        while p<len(data) and data[p]==255:p+=1
        if p>=len(data):return None
        marker=data[p];p+=1
        if entropy and (marker==0 or 0xd0<=marker<=0xd7):continue
        if marker==0xd9:return p
        if marker in [0,0xd8]:raise ValueError('Invalid JPEG marker sequence')
        if marker==1 or 0xd0<=marker<=0xd7:continue
        if p+2>len(data):return None
        length=int.from_bytes(data[p:p+2],'big')
        if length<2:raise ValueError('Invalid JPEG segment size')
        if p+length>len(data):return None
        p+=length;entropy=marker==0xda
    return None
