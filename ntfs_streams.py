"""Parse data-run and timestamp evidence; never infer volume geometry."""
import datetime,struct
def timestamp(value):
    if not value:return None
    try:return (datetime.datetime(1601,1,1,tzinfo=datetime.timezone.utc)+datetime.timedelta(microseconds=value//10)).isoformat()
    except OverflowError:return None
def runs(data,start_vcn=0):
    out=[];pos=0;lcn=0;vcn=start_vcn
    while pos<len(data):
        head=data[pos];pos+=1
        if head==0:return out
        n=head&15;d=head>>4
        if not 1<=n<=8 or d>8 or pos+n+d>len(data):raise ValueError('Invalid mapping pair')
        length=int.from_bytes(data[pos:pos+n],'little');pos+=n
        if not length:raise ValueError('Empty run')
        if d:
            lcn+=int.from_bytes(data[pos:pos+d],'little',signed=True)
            if lcn<0:raise ValueError('Negative LCN')
        pos+=d
        out.append(dict(vcn=vcn,clusters=length,lcn=lcn if d else None,sparse=not bool(d)));vcn+=length
    raise ValueError('Unterminated mapping pairs')
def parse(raw):
    if len(raw)<512 or raw[:4]!=b'FILE':raise ValueError('Not a FILE record')
    u16=lambda at:struct.unpack_from('<H',raw,at)[0]
    u32=lambda at:struct.unpack_from('<I',raw,at)[0]
    size=u32(28);used=u32(24);attr=u16(20);usa=u16(4);count=u16(6)
    if size>len(raw) or size%512 or count!=size//512+1 or usa<8 or usa+count*2>size or not 48<=attr<used<=size:raise ValueError('Invalid record bounds')
    fixed=bytearray(raw[:size])
    for i in range(1,count):
        at=i*512-2
        if fixed[at:at+2]!=raw[usa:usa+2]:raise ValueError('Update sequence mismatch')
        fixed[at:at+2]=raw[usa+i*2:usa+i*2+2]
    result=dict(deleted=not bool(u16(22)&1),directory=bool(u16(22)&2),names=[],streams=[],times={},has_attribute_list=False,geometry_required=True)
    while attr+8<=used:
        kind,length=struct.unpack_from('<II',fixed,attr)
        if kind==0xffffffff:break
        if length<24 or attr+length>used:raise ValueError('Invalid attribute length')
        a=fixed[attr:attr+length];nonresident=a[8];flags=struct.unpack_from('<H',a,12)[0]
        if kind==0x20:result['has_attribute_list']=True
        if not nonresident:
            n,off=struct.unpack_from('<IH',a,16)
            if off<24 or off+n>length:raise ValueError('Resident value out of bounds')
            value=a[off:off+n]
            if kind==0x30:
                if len(value)<66:raise ValueError('Short FILE_NAME attribute')
                chars=value[64];namespace=value[65]
                if not chars or namespace>3 or 66+chars*2>len(value):raise ValueError('Invalid FILE_NAME bounds')
                name=bytes(value[66:66+chars*2]).decode('utf-16-le',errors='strict')
                result['names'].append(dict(name=name,namespace=namespace,parent_reference=struct.unpack_from('<Q',value,0)[0]))
            if kind==0x10 and len(value)>=32:
                result['times']={key:timestamp(struct.unpack_from('<Q',value,i*8)[0]) for i,key in enumerate(('created','modified','mft_changed','accessed'))}
            if kind==0x80 and a[9]==0:result['streams'].append(dict(resident=True,bytes=n,flags=flags,resident_value_offset=attr+off,resident_hex=bytes(value).hex()))
        elif kind==0x80 and a[9]==0:
            if length<64:raise ValueError('Short nonresident header')
            start,last=struct.unpack_from('<QQ',a,16);off=struct.unpack_from('<H',a,32)[0]
            if off<64 or off>=length:raise ValueError('Bad run offset')
            mapped=runs(a[off:],start)
            if mapped and mapped[-1]['vcn']+mapped[-1]['clusters']!=last+1:raise ValueError('VCN extent mismatch')
            allocated,total,initialized=struct.unpack_from('<QQQ',a,40)
            result['streams'].append(dict(resident=False,start_vcn=start,last_vcn=last,bytes=total,initialized_bytes=initialized,allocated_bytes=allocated,flags=flags,runs=mapped,unsupported_encoding=bool(flags&0xc001)))
        attr+=length
    return result
