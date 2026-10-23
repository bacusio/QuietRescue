"""Build on Windows using the virtual environment from build-requirements.txt."""
import sys,subprocess,os,shutil,argparse,re
from pathlib import Path
if os.name!='nt':raise SystemExit('Build on Windows x64 with Python 3.12 x64.')
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--variant',default='',help='Build to a separate dist-VARIANT directory without replacing an in-use executable')
args=parser.parse_args()
if args.variant and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,48}',args.variant):
    parser.error('variant must contain only lowercase letters, digits and hyphens')
destination=root/('dist-'+args.variant if args.variant else 'dist')
keep={'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','SYSTEMDRIVE'}
env={k:v for k,v in os.environ.items() if k.upper() in keep}
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--hide-console','hide-early','--uac-admin','--name','QuietRescue','--icon',str(root/'icon.ico'),'--add-data',str(root/'demo')+':demo','--distpath',str(destination),'--workpath',str(root/'build'),'--specpath',str(root/'build'),str(root/'entry.py')],check=True,cwd=root,env=env)
shutil.copytree(root/'vendor',destination/'vendor',dirs_exist_ok=True)
shutil.copytree(root/'licenses',destination/'licenses',dirs_exist_ok=True)
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',destination/'THIRD_PARTY_NOTICES.md')
shutil.copy2(root/'docs/USAGE.zh-TW.md',destination/'使用說明.md')
