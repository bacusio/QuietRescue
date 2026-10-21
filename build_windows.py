"""Build on Windows using the virtual environment from build-requirements.txt."""
import sys,subprocess,os
from pathlib import Path
if os.name!='nt':raise SystemExit('Build on Windows x64 with Python 3.12 x64.')
root=Path(__file__).resolve().parent
keep={'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}
env={k:v for k,v in os.environ.items() if k.upper() in keep}
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--hide-console','hide-early','--uac-admin','--name','QuietRescue','--icon',str(root/'icon.ico'),'--add-data',str(root/'demo')+':demo','--distpath',str(root/'dist'),'--workpath',str(root/'build'),'--specpath',str(root/'build'),str(root/'entry.py')],check=True,cwd=root,env=env)
