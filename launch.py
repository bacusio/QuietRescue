"""Normal Windows UAC launch. No disk is opened automatically."""
import ctypes,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parent
pythonw=Path(sys.executable).with_name('pythonw.exe')
if not pythonw.exists():pythonw=Path(sys.executable)
shell=ctypes.WinDLL('shell32',use_last_error=True)
shell.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
shell.ShellExecuteW.restype=ctypes.c_ssize_t
result=shell.ShellExecuteW(None,'runas',str(pythonw),subprocess.list2cmdline(['-I','-B',str(base/'app.py')]),str(base),1)
if result<=32:
    ctypes.windll.user32.MessageBoxW(None,'Launch was cancelled or failed. No scan was started.','QuietRescue',0)
    raise SystemExit(1)
