"""Windows metadata queries and strictly read-only device access."""
import ctypes as C
from ctypes import wintypes as W
import json, os, subprocess, struct

def clean_env():
    return {k:v for k,v in os.environ.items() if k.upper() in
            {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}}

def powershell(script):
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
        capture_output=True,timeout=30,env=clean_env(),creationflags=0x08000000)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-1500:])
    return json.loads(p.stdout.decode('utf-8-sig'))

def inventory():
    data=powershell("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $d=@(Get-Disk | Select-Object Number,FriendlyName,SerialNumber,Size,LogicalSectorSize,IsBoot,IsSystem,BusType); $p=@(Get-Partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,Offset,Size); @{disks=$d;partitions=$p}|ConvertTo-Json -Depth 4 -Compress")
    for key in ('disks','partitions'):
        value=data.get(key,[])
        if value is None:data[key]=[]
        elif isinstance(value,dict):data[key]=[value]
    return data

K=C.WinDLL('kernel32',use_last_error=True)
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE]
K.DeviceIoControl.argtypes=[W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]
K.SetFilePointerEx.argtypes=[W.HANDLE,C.c_longlong,C.c_void_p,W.DWORD]
K.ReadFile.argtypes=[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]

class ReadDevice:
    def __init__(self,path,metadata=False):
        self.h=K.CreateFileW(path,0 if metadata else 0x80000000,3,None,3,0,None)
        if self.h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    def close(self):
        if self.h is not None:K.CloseHandle(self.h);self.h=None
    def ioctl(self,code,data=b'',size=4096):
        buf=C.create_string_buffer(size);n=W.DWORD()
        if not K.DeviceIoControl(self.h,code,data or None,len(data),buf,size,C.byref(n),None):raise C.WinError(C.get_last_error())
        return buf.raw[:n.value]
    def read(self,a,n):
        if not K.SetFilePointerEx(self.h,a,None,0):raise C.WinError(C.get_last_error())
        buf=C.create_string_buffer(n);count=W.DWORD()
        if not K.ReadFile(self.h,buf,n,C.byref(count),None):raise C.WinError(C.get_last_error())
        if count.value!=n:raise OSError('Short read')
        return buf.raw
    def identity(self):
        size=struct.unpack('<q',self.ioctl(0x7405C,size=8))[0]
        b=self.ioctl(0x2D1400,bytes(12));off=struct.unpack_from('<I',b,24)[0]
        serial=b[off:].split(b'\0')[0].decode('ascii','replace').strip() if off else ''
        return serial,size

def destination_disk(path):
    from pathlib import Path
    p=Path(path).resolve()
    if not p.drive or p.drive.startswith('\\'):raise ValueError('請選本機單一磁碟分區，不支援網路位置')
    d=ReadDevice('\\\\.\\'+p.drive,True)
    try:
        b=d.ioctl(0x560000,size=256)
        if struct.unpack_from('<I',b)[0]!=1:raise ValueError('不支援跨盤目的卷')
        return struct.unpack_from('<I',b,8)[0]
    finally:d.close()

def destination_identity(path):
    """Resolve a local destination volume to the physical disk identity."""
    number=destination_disk(path)
    matches=[x for x in inventory()['disks'] if int(x['Number'])==number]
    if len(matches)!=1:raise ValueError('無法唯一識別目的實體硬盤')
    d=matches[0]
    serial=str(d.get('SerialNumber') or '').strip()
    if not serial:raise ValueError('目的硬盤序列號缺失，不能建立救援任務')
    return dict(number=number,serial=serial,size=int(d['Size']))
