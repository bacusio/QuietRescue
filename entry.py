"""Frozen application entry, worker dispatch and synthetic acceptance mode."""
import sys,os,ctypes,json,threading,queue,time,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
if len(sys.argv)>1 and sys.argv[1]=='--worker':
    from engine import worker
    worker(Path(sys.argv[2]));raise SystemExit

def main():
    import tkinter as tk
    from tkinter import ttk
    from app import App
    w=tk.Tk();ttk.Style().theme_use('clam');app=App(w)
    if '--acceptance' in sys.argv:
        target=Path(sys.argv[sys.argv.index('--acceptance')+1]).resolve()
        target.mkdir(exist_ok=False,parents=True)
        from engine import save,load,capture,verify,records,BLOCK,export_image
        from media import recover_photos
        from PIL import Image
        result=dict(status='RUNNING',admin=bool(ctypes.windll.shell32.IsUserAnAdmin()),frozen=bool(getattr(sys,'frozen',False)),source_disk_reads=0,source_disk_writes=0)
        save(target/'acceptance.json',result)
        events=queue.Queue()
        def run():
            try:
                source=target/'synthetic.img';photo=(ROOT/'demo/photo.jpg').read_bytes()
                source.write_bytes(photo+bytes(2*BLOCK-len(photo)))
                job=target/'job';job.mkdir();st=source.stat()
                plan=dict(kind='file',source=str(source),size=st.st_size,mtime_ns=st.st_mtime_ns,sector=512,start=0,end=st.st_size,stage_bytes=BLOCK,guards=[])
                save(job/'plan.json',plan)
                capture(job,threading.Event(),lambda x:None)
                first=verify(job);assert first['verified_bytes']==BLOCK and not first['complete']
                capture(job,threading.Event(),lambda x:None)
                second=verify(job);assert second['verified_bytes']==2*BLOCK and second['complete']
                req=[(r['offset'],r['length']) for r in records(job) if r['state']=='REQUESTED']
                assert len(req)==len(set(req))==2
                export_image(job,target/'roundtrip.img');assert source.read_bytes()==(target/'roundtrip.img').read_bytes()
                found=recover_photos(job);assert len(found)==1 and Path(found[0]['path']).read_bytes()==photo
                result.update(resume_verified=True,unique_requests=len(req),verified_bytes=second['verified_bytes'],photo_bytes_equal=True)
                events.put(('ready',(job,found)))
            except Exception as e:result.update(status='FAILED',error=str(e));save(target/'acceptance.json',result);events.put(('error',str(e)))
        def poll():
            while not events.empty():
                kind,value=events.get()
                if kind=='error':app.note(value);return
                job,found=value;app.root=job;app.show_demo();app.photos=found+[dict(path=str(ROOT/'demo/video.avi'))]
                app.list.delete(0,'end')
                for x in app.photos:app.list.insert('end',Path(x['path']).name)
                app.list.selection_clear(0,'end');app.list.selection_set(0);app.show_photo();w.update_idletasks()
                result['photo_preview']=app.preview is not None
                save(target/'acceptance.json',result)
                def video():
                    try:
                        app.list.selection_clear(0,'end');app.list.selection_set(1);app.show_photo()
                        assert app.video.opened,'Embedded video did not open'
                        before=app.video.position()
                        def finish():
                            try:
                                after=app.video.position();assert after>before
                                result.update(status='PASSED',video_position_start_ms=before,video_position_after_ms=after,video_playback=True)
                                app.note('EXE acceptance passed: UAC token, checkpoint resume, byte-identical photo, advancing native video playback. No physical disk read.')
                            except Exception as e:result.update(status='FAILED',error=str(e))
                            save(target/'acceptance.json',result)
                        w.after(1200,finish)
                    except Exception as e:result.update(status='FAILED',error=str(e));save(target/'acceptance.json',result)
                w.after(1800,video)
            w.after(200,poll)
        w.after(200,poll);threading.Thread(target=run,daemon=True).start()
    w.mainloop()
if __name__=='__main__':main()
