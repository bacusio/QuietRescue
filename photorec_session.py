"""Validate PhotoRec 7.2 saved sessions before headless saved-image resume.

Upstream phmain.c accepts /cmd resume; sessionp.c stores sector ranges and ends
the command with inter. Preserve the original and remove only that final token.
Never invoke bare /cmd resume: pass the staged image as a positional argument
first, so phmain.c does not enumerate physical disks when list_disk is empty.
"""
import re,json,hashlib
from pathlib import Path
from image_recovery import ascii_path,FORMATS

def checkpoint_session(job,state):
    """Select the last terminal attempt, never fall back to an older session."""
    job=Path(job).resolve(strict=True)
    attempt=state.get('resume_attempt')
    if not attempt:return job/'photorec.ses'
    path=Path(attempt)
    if path.is_symlink() or path.is_junction():raise ValueError('Reparse attempt rejected')
    path=path.resolve(strict=True)
    if path.parent!=job or not re.fullmatch(r'resume-[0-9a-f]{32}',path.name):
        raise ValueError('Resume attempt outside job')
    receipt=path/'resume.json'
    if receipt.is_symlink() or receipt.is_junction() or not receipt.is_file() or receipt.stat().st_size>1024*1024:
        raise ValueError('Invalid attempt receipt')
    info=json.loads(receipt.read_text(encoding='utf-8'))
    if info.get('status')!='STOPPED_ERROR' or info.get('worker_exit_confirmed') is not True:
        raise ValueError('Previous worker exit is unconfirmed; do not restart')
    if info.get('input_sha256')!=state.get('input_sha256'):
        raise ValueError('Attempt image identity changed')
    return path/'photorec.ses'

def validate_checkpoint(job, stop):
    """Read-only preflight; caller holds the job lock and staged-image lease.

    A stopped copy without a completed input hash is not a scan checkpoint.
    Never synthesize a new scan when PhotoRec has not saved its session.
    """
    job=Path(job)
    paths=[job,job/'recovery.json',job/'input.img']
    if any(p.is_symlink() or p.is_junction() for p in paths):
        raise ValueError('Reparse checkpoint rejected')
    manifest,stage=paths[1:]
    if not all(p.is_file() for p in paths[1:]):
        raise ValueError('Checkpoint incomplete; do not restart extraction automatically')
    if manifest.stat().st_size>1024*1024:
        raise ValueError('Checkpoint metadata exceeds limit')
    state=json.loads(manifest.read_text(encoding='utf-8'))
    if state.get('status')!='STOPPED_ERROR':
        raise ValueError('Only a stopped extraction can be resumed')
    session=checkpoint_session(job,state)
    if session.is_symlink() or session.is_junction() or not session.is_file():
        raise ValueError('Checkpoint incomplete; no fallback to older progress')
    if session.stat().st_size>1024*1024:raise ValueError('Checkpoint metadata exceeds limit')
    expected=state.get('input_sha256','')
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
        raise ValueError('Image copy was not verified before interruption')
    if stage.stat().st_size!=state.get('source_bytes'):
        raise ValueError('Staged image size changed')
    digest=hashlib.sha256()
    with stage.open('rb') as stream:
        while True:
            if stop.is_set():raise RuntimeError('Stopped during checkpoint verification')
            block=stream.read(8*1024**2)
            if not block:break
            digest.update(block)
    if digest.hexdigest()!=expected:raise ValueError('Staged image hash changed')
    original=session.read_bytes()
    normalized,info=normalize_session(original,stage)
    info['session_path']=str(session)
    return state,original,normalized,info

def resume_command(executable, stage, output):
    """Bind resume to an existing regular image before PhotoRec parses /cmd.

    Caller must validate the session with normalize_session, use its private
    working directory, and hold the image read-only lease during execution.
    Bare /cmd resume leaves list_disk empty and permits hd_parse().
    """
    stage=Path(stage)
    if stage.is_symlink() or stage.is_junction() or not stage.is_file():
        raise ValueError('Regular staged image required')
    return [str(executable), ascii_path(stage).replace('\\','/'),
            '/d', str(output), '/cmd', 'resume', '/log']

def normalize_session(data,stage):
    stage=Path(stage)
    if stage.is_symlink() or stage.is_junction() or not stage.is_file():raise ValueError('Regular staged image required')
    if len(data)>1024*1024:raise ValueError('Session exceeds limit')
    payload=data.split(b'\x00',1)[0]
    if any(data[len(payload):]):raise ValueError('Nonzero data after session padding')
    text=payload.decode('ascii',errors='strict');lines=text.splitlines()
    if len(lines)<3 or not re.fullmatch(r'#[0-9]+',lines[0]):raise ValueError('Invalid session header')
    device,sep,command=lines[1].partition(' ')
    expected=ascii_path(stage)
    if not sep or device.replace('\\','/').casefold()!=expected.replace('\\','/').casefold():raise ValueError('Session points outside staged image')
    tokens=command.split(',')
    # PhotoRec 7.2 emits order 255 for the whole-image pseudo-partition.
    # Keep accepting older order-0 saved-image sessions, never real partition tables.
    if tokens[-1]!='inter' or len(tokens)<2 or tokens[0]!='partition_none' or tokens[1] not in {'0','255'}:raise ValueError('Unsupported session layout')
    allowed=set(FORMATS)|{'partition_none','blocksize','fileopt','everything','enable','disable','options','paranoid','paranoid_no','paranoid_bf','keep_corrupted_file','keep_corrupted_file_no','mode_ext2','expert','lowmem','wholespace','freespace','search','inter','status=unformat','status=find_offset','status=ext2_on_bf','status=ext2_on_save_everything','status=ext2_on','status=ext2_off_save_everything','status=ext2_off_bf','status=ext2_off'}
    if any(t not in allowed and not re.fullmatch(r'[0-9]{1,20}',t) for t in tokens):raise ValueError('Unsupported session command')
    if tokens.count('search')!=1 or tokens.count('inter')!=1 or 'fileopt' not in tokens:raise ValueError('Incomplete session command')
    sectors=(stage.stat().st_size+511)//512;ranges=[];last=-1
    for line in lines[2:]:
        if not line:continue
        m=re.fullmatch(r'([0-9]{1,20})-([0-9]{1,20})',line)
        if not m:raise ValueError('Invalid session range')
        a,z=map(int,m.groups())
        if not 0<=a<=z<sectors or a<=last:raise ValueError('Overlapping or out-of-bounds session range')
        ranges.append((a,z));last=z
    if not ranges:raise ValueError('No resumable sectors')
    # A private session copy may enter the CLI, never the original untrusted text.
    result=(lines[0]+'\n'+expected.replace('\\','/')+' '+','.join(tokens[:-1])+',\n'+'\n'.join(f'{a}-{z}' for a,z in ranges)+'\n').encode('ascii')
    return result,dict(ranges=ranges,remaining_sectors=sum(z-a+1 for a,z in ranges),sector_bytes=512,interactive_token_removed=True)
