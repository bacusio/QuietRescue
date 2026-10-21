"""Native Windows MCI preview; unsupported codecs fall back to the system player."""
import ctypes,uuid
class VideoPreview:
    def __init__(self,widget):
        self.widget=widget;self.alias='qr'+uuid.uuid4().hex;self.opened=False
        self.winmm=ctypes.WinDLL('winmm')
        self.winmm.mciSendStringW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p]
        self.winmm.mciGetErrorStringW.argtypes=[ctypes.c_uint,ctypes.c_wchar_p,ctypes.c_uint]
    def command(self,text):
        out=ctypes.create_unicode_buffer(1024)
        code=self.winmm.mciSendStringW(text,out,len(out),None)
        if code:
            self.winmm.mciGetErrorStringW(code,out,len(out))
            raise RuntimeError(out.value)
        return out.value
    def close(self):
        if self.opened:
            try:self.command('close '+self.alias)
            finally:self.opened=False
    def open(self,path):
        from pathlib import Path
        self.close();path=Path(path).resolve()
        if '"' in str(path) or not path.is_file():raise ValueError('Invalid local video')
        self.widget.update_idletasks()
        kind='avivideo' if path.suffix.lower()=='.avi' else 'mpegvideo'
        self.command(f'open "{path}" type {kind} alias {self.alias} style child parent {self.widget.winfo_id()}')
        self.opened=True
        try:
            self.command(f'set {self.alias} time format milliseconds')
            self.command(f'put {self.alias} window at 0 0 {max(320,self.widget.winfo_width())} {max(200,self.widget.winfo_height())}')
            self.command(f'play {self.alias} from 0')
        except Exception:self.close();raise
    def pause(self):
        if self.opened:
            mode=self.command('status '+self.alias+' mode')
            if mode=='stopped':self.command('play '+self.alias+' from 0')
            else:self.command(('resume ' if mode=='paused' else 'pause ')+self.alias)
    def position(self):return int(self.command('status '+self.alias+' position'))
