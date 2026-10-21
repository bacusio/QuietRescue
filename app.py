import sys,os,json,threading,queue,time,subprocess,uuid,getpass
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from engine import load,save,capture,verify,export_image,export_regions,validate,approve_physical_plan,require_physical_approval,FLOOR,PHYSICAL_READER_VALIDATED
from platform_win import inventory,clean_env,destination_identity
from media import recover_photos,avoidance
from maintenance import preview as partition_preview
BASE=Path(__file__).resolve().parent

class App:
    def __init__(self,window):
        self.w=window;window.title('QuietRescue 1.2 · 本地資料搶救');window.geometry('1100x820')
        self.root=None;self.busy=False;self.operation=None;self.operation_phase=None;self.stop=threading.Event();self.events=queue.Queue();self.disks=[];self.photos=[];self.preview=None
        self.disk=tk.StringVar();self.dest=tk.StringVar();self.limit=tk.StringVar(value='1');self.total_limit=tk.StringVar(value='100');self.continuous=tk.BooleanVar(value=True);self.start=tk.StringVar(value='0');self.end=tk.StringVar();self.state=tk.StringVar(value='尚未開始 · 不會自動讀取硬盤')
        ttk.Label(window,text='QuietRescue',font=('Microsoft JhengHei UI',24,'bold')).pack(anchor='w',padx=24,pady=(18,0))
        ttk.Label(window,text='來源只讀  /  斷點映射  /  已驗證副本還原',font=('Microsoft JhengHei UI',11)).pack(anchor='w',padx=26,pady=(4,14))
        tabs=ttk.Notebook(window);tabs.pack(fill='both',expand=True,padx=20,pady=8);self.tabs=tabs
        rescue=ttk.Frame(tabs,padding=16);gallery=ttk.Frame(tabs,padding=16);repair=ttk.Frame(tabs,padding=16)
        tabs.add(rescue,text='① 鏡像與續讀');tabs.add(gallery,text='② 還原與預覽');tabs.add(repair,text='③ 修復與避讓')
        ttk.Label(rescue,text='來源物理硬盤（系統盤不可選；同一物理盤只使用單一讀取 worker）').pack(anchor='w')
        self.combo=ttk.Combobox(rescue,textvariable=self.disk,state='readonly',width=90);self.combo.pack(fill='x',pady=5);self.combo.bind('<<ComboboxSelected>>',self.select_disk)
        ttk.Button(rescue,text='刷新硬盤清單',command=self.refresh).pack(anchor='w',pady=4)
        line=ttk.Frame(rescue);line.pack(fill='x',pady=10);ttk.Label(line,text='保存位置').pack(side='left');ttk.Entry(line,textvariable=self.dest,width=70).pack(side='left',padx=8);ttk.Button(line,text='選擇資料夾',command=self.pick_dest).pack(side='left')
        line=ttk.Frame(rescue);line.pack(fill='x');
        for label,var,width in [('起點 bytes',self.start,18),('終點 bytes（不含）',self.end,18),('本次最多 GB',self.limit,8)]:
            ttk.Label(line,text=label).pack(side='left',padx=3);ttk.Entry(line,textvariable=var,width=width).pack(side='left')
        line=ttk.Frame(rescue);line.pack(fill='x',pady=(6,0))
        ttk.Checkbutton(line,text='每批完成後自動續讀（遵守本計劃累計上限）',variable=self.continuous).pack(side='left')
        ttk.Label(line,text='累計上限 GB').pack(side='left',padx=(18,4));ttk.Entry(line,textvariable=self.total_limit,width=10).pack(side='left')
        ttk.Label(rescue,text='保留至少5GB空間。每批最多1MiB請求；8秒超時或讀取超過2秒即停止。\nCRC／超時／裝置掉線不自動重試；目的寫入失敗不記作來源壞區。1.2 實體 reader 尚未通過可丟棄設備驗收，實體讀取目前鎖定。',wraplength=900).pack(anchor='w',pady=12)
        line=ttk.Frame(rescue);line.pack(fill='x')
        for title,fn in [('建立未審核計劃草案',self.new_disk),('檢視並批准計劃',self.approve_plan),('開啟任務',self.open_job),('開始／續讀',self.resume),('安全停止',self.request_stop),('測試鏡像檔',self.test_file)]:ttk.Button(line,text=title,command=fn).pack(side='left',padx=3)
        self.log=tk.Text(rescue,height=15,wrap='word',state='disabled');self.log.pack(fill='both',expand=True,pady=12)
        line=ttk.Frame(gallery);line.pack(fill='x')
        for title,fn in [('驗證全部副本',lambda:self.job(lambda:verify(self.require_job()))),('還原照片',self.recover),('匯出完整 .img',self.export),('影片／更多格式 PhotoRec',self.photorec),('開啟還原資料夾',self.open_output)]:ttk.Button(line,text=title,command=fn).pack(side='left',padx=3)
        ttk.Label(gallery,text='照片從已驗證的連續資料提取；缺塊或碎片化影片不保證完整。PhotoRec可還原影片與更多格式，通常不保留原名。',wraplength=950).pack(anchor='w',pady=12)
        bar=ttk.Frame(gallery);bar.pack(fill='x',pady=4)
        ttk.Button(bar,text='匯出已驗證連續區段（可有缺損任務）',command=lambda:self.job(lambda:export_regions(self.require_job()))).pack(side='left')
        ttk.Button(bar,text='載入還原的照片／影片資料夾',command=self.load_media).pack(side='left',padx=8)
        ttk.Button(bar,text='開啟示範（不讀硬碟）',command=self.show_demo).pack(side='left',padx=8)
        body=ttk.Frame(gallery);body.pack(fill='both',expand=True);self.list=tk.Listbox(body,width=38);self.list.pack(side='left',fill='y');self.list.bind('<<ListboxSelect>>',self.show_photo);self.canvas=ttk.Label(body,text='還原後選擇照片，即可預覽');self.canvas.pack(side='left',expand=True,fill='both',padx=12)
        from video_preview import VideoPreview
        self.video=VideoPreview(self.canvas)
        controls=ttk.Frame(gallery);controls.pack(fill='x',pady=8)
        ttk.Button(controls,text='影片播放／暫停',command=self.video.pause).pack(side='left')
        ttk.Button(controls,text='使用系統播放器開啟',command=self.open_selected).pack(side='left',padx=8)
        ttk.Label(repair,text='修復前先保全資料',font=('Microsoft JhengHei UI',18,'bold')).pack(anchor='w')
        ttk.Label(repair,text='CRC、超時或慢讀只是故障證據，並非精確物理壞道邊界。\n重新分區只是在邏輯上避開範圍，不能修復盤體或保證資料永不消失。\n本工具不執行壞扇區寫入測試、不自動格式化或寫回分區表。',wraplength=900).pack(anchor='w',pady=16)
        ttk.Button(repair,text='輸出只讀避讓分區預覽（不寫入）',command=self.preview_partition).pack(anchor='w',pady=8)
        ttk.Button(repair,text='輸出不可分配區域 CSV 草案',command=lambda:self.job(lambda:str(avoidance(self.require_job())))).pack(anchor='w',pady=8)
        ttk.Button(repair,text='查看未開放的維護功能',command=self.repair).pack(anchor='w',pady=8)
        ttk.Label(repair,text='目前版本只產生診斷與避讓預覽；不執行 CHKDSK /f、壞扇區寫入修復、格式化或分區表寫回。',wraplength=900).pack(anchor='w',pady=10)
        ttk.Label(window,textvariable=self.state,relief='sunken',padding=8).pack(fill='x')
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(200,self.poll)

    def note(self,text):
        self.log.configure(state='normal');self.log.insert('end',str(text)+'\n');self.log.see('end');self.log.configure(state='disabled')
    def job(self,fn,operation='non-cancellable'):
        if self.busy:return messagebox.showinfo('忙碌中','請先等待目前操作完成或安全停止。')
        self.busy=True;self.operation=operation;self.operation_phase='preflight';self.stop.clear();self.state.set('處理中…')
        def work():
            try:self.events.put(('result',fn()))
            except Exception as e:self.events.put(('error',str(e)))
            finally:self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='progress':self.state.set(f"{value['status']} · 本次 {value.get('new_bytes',0)/1e9:.3f} GB · 源盤寫入 0")
            elif kind=='phase':self.operation_phase=value;self.state.set('目前階段：'+str(value))
            elif kind=='inventory':
                self.disks=[d for d in value['disks'] if not d['IsSystem'] and not d['IsBoot']]
                parts={}
                for p in value.get('partitions',[]):parts.setdefault(int(p['DiskNumber']),[]).append(p)
                labels=[]
                for d in self.disks:
                    ptxt=', '.join((str(p.get('DriveLetter') or '無盤符')+f"@{int(p['Offset'])}B/{int(p['Size'])}B") for p in parts.get(int(d['Number']),[])) or '無已掛載分區'
                    labels.append(f"Disk {d['Number']} | {d['FriendlyName']} | {d['Size']/1e9:.1f} GB | {d['SerialNumber']} | {ptxt}")
                self.combo['values']=labels
                self.note('硬盤清單已刷新；尚未讀取磁區。')
            elif kind=='photos':
                self.photos=value;self.list.delete(0,'end')
                for x in value:self.list.insert('end',Path(x['path']).name)
            elif kind=='result':self.note(value);self.state.set('操作結束；請查看結果記錄')
            elif kind=='error':self.note('停止：'+value);self.state.set('操作停止：'+value);messagebox.showerror('操作停止',value)
            elif kind=='done':self.busy=False;self.operation=None;self.operation_phase=None
        self.w.after(200,self.poll)
    def refresh(self):self.job(lambda:self.events.put(('inventory',inventory())))
    def select_disk(self,event=None):
        i=self.combo.current()
        if i>=0:self.end.set(str(self.disks[i]['Size']))
    def pick_dest(self):
        p=filedialog.askdirectory()
        if p:self.dest.set(p)
    def require_job(self):
        if not self.root:raise ValueError('請先建立或開啟搶救任務')
        return self.root
    def make_plan(self,kind,**kw):
        n=int(float(self.limit.get())*1e9)//4096*4096
        if n<=0:raise ValueError('GB上限必須大於0')
        start=int(self.start.get());end=int(self.end.get());scope=end-start
        total=int(float(self.total_limit.get())*1e9)//4096*4096
        total=min(total,scope)
        if total<=0:raise ValueError('累計GB上限必須大於0且不能超出範圍')
        plan=dict(version=3,plan_id=uuid.uuid4().hex,kind=kind,start=start,end=end,stage_bytes=n,total_budget_bytes=total,
            continuous=bool(self.continuous.get()) if kind=='disk' else False,guards=[],attempted=[],
            policy=dict(read_only=True,retries=0,request_bytes=1024**2,request_timeout_seconds=8,slow_read_stop_seconds=2,fault_guard_buffer_bytes=1024**3,free_space_reserve=FLOOR),**kw)
        parent=Path(self.dest.get()).resolve()
        if not parent.is_dir() or not self.dest.get():raise ValueError('請選保存位置')
        if kind=='disk':plan['destination_identity']=destination_identity(parent)
        # Validate before creating any destination files.
        validate(plan,parent)
        self.root=parent/('QuietRescue-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);self.root.mkdir();save(self.root/'plan.json',plan)
        self.note('未審核計劃草案：'+str(self.root));self.state.set('計劃草案已建立；實體來源尚未讀取');return plan
    def new_disk(self):
        if self.busy:return
        try:
            i=self.combo.current()
            if i<0:raise ValueError('請先刷新並選擇來源硬盤')
            d=self.disks[i]
            if not messagebox.askyesno('建立計劃草案',f"來源 Disk {d['Number']} / {d['SerialNumber']}\n目的地 {self.dest.get()}\n只建立未審核草案，不會開始讀取。繼續？"):return
            self.make_plan('disk',number=d['Number'],serial=d['SerialNumber'].strip(),size=int(d['Size']),sector=int(d['LogicalSectorSize']))
        except Exception as e:messagebox.showerror('無法開始',str(e))
    def approve_plan(self):
        if self.busy:return
        try:
            root=self.require_job();plan=load(root/'plan.json');validate(plan,root)
            if plan.get('kind')!='disk':raise ValueError('這不是實體磁碟計劃')
            if not PHYSICAL_READER_VALIDATED:
                raise ValueError('本次只可檢視計劃：1.2 實體 reader 尚未通過可丟棄設備與 I/O 停止驗收，因此不會批准或啟動來源讀取。')
            guards=plan.get('guards',[]);attempted=plan.get('attempted',[]);dest=plan['destination_identity']
            union=__import__('engine').merge(list(guards)+list(attempted));excluded_bytes=sum(z-a for a,z in union)
            summary=(f"來源：Disk {plan['number']} / {plan['serial']} / {plan['size']} bytes\n"
                f"目的：Disk {dest['number']} / {dest['serial']} / {dest['size']} bytes\n"
                f"讀取範圍：[ {plan['start']}, {plan['end']} )\n本輪上限：{plan['stage_bytes']} bytes\n"
                f"累計上限：{plan['total_budget_bytes']} bytes；自動續讀：{'是' if plan.get('continuous') else '否'}\n"
                f"匯入策略避讓：{len(guards)} 段；歷史已嘗試：{len(attempted)} 段；排除聯集 {excluded_bytes} bytes\n"
                f"政策：唯讀、程式重試 0 次、單請求 {plan['policy']['request_bytes']} bytes；保留至少 {FLOOR} bytes。\n\n"
                '批准會允許此固定計劃之後執行實體讀取。請確認來源與目的物理磁碟不同，且範圍正確。')
            if not messagebox.askyesno('審核實體讀取計劃',summary):return
            approval=approve_physical_plan(root,getpass.getuser())
            self.note(f"計劃已審核：{approval['plan_id']} · SHA-256 {approval['plan_sha256']}")
            self.state.set('計劃已批准；開始／續讀前仍會重新核對來源與目的身份')
        except Exception as e:messagebox.showerror('計劃未批准',str(e))
    def test_file(self):
        if self.busy:return
        p=filedialog.askopenfilename(title='選擇測試鏡像檔，不開啟物理硬盤')
        if not p:return
        try:
            st=Path(p).stat();self.start.set('0');self.end.set(str(st.st_size));self.make_plan('file',source=str(Path(p).resolve()),size=st.st_size,mtime_ns=st.st_mtime_ns,sector=512);self.resume()
        except Exception as e:messagebox.showerror('測試無法開始',str(e))
    def open_job(self):
        if self.busy:return
        p=filedialog.askopenfilename(title='選擇 QuietRescue plan.json',filetypes=[('任務','plan.json')])
        if p:
            try:
                plan=load(p);self.root=Path(p).parent;self.note('已開啟 '+str(self.root))
                try:
                    require_physical_approval(self.root,plan);self.state.set('任務已載入；計劃審核紀錄存在，續讀前會重新核對身份')
                except ValueError as e:
                    self.state.set('實體續讀封鎖：計劃未審核或審核已失效');self.note(str(e))
                if (self.root/'photo-recovery.json').exists():self.events.put(('photos',load(self.root/'photo-recovery.json')['files']))
            except Exception as e:messagebox.showerror('無法開啟',str(e))
    def resume(self):
        if self.busy:return
        try:
            root=self.require_job();plan=load(root/'plan.json');validate(plan,root);require_physical_approval(root,plan)
        except Exception as e:return messagebox.showerror('續讀未啟動',str(e))
        def run():
            self.events.put(('phase','source read'))
            capture(root,self.stop,lambda x:self.events.put(('progress',x)))
            self.events.put(('phase','saved-copy verification'))
            report=verify(root)
            return {'status':load(root/'status.json'),'verification':{k:v for k,v in report.items() if k!='missing_ranges'},'missing_ranges_count':len(report['missing_ranges'])}
        self.job(run,operation='rescue')
    def request_stop(self):
        if not self.busy:return self.state.set('目前沒有進行中的操作')
        if self.operation=='rescue' and self.operation_phase=='saved-copy verification':
            self.state.set('已保存副本校驗正在進行；本階段目前不支援中斷，請等待完成。');self.note('STOP_UNAVAILABLE：副本校驗不是來源讀取；目前繼續完成驗證。');return
        if self.operation not in ('rescue','external'):
            self.state.set('目前操作不支援中斷；請等待自然完成，工具不會假報已停妥。');self.note('STOP_UNAVAILABLE：目前為不可中斷的驗證／整理操作。');return
        self.stop.set();self.state.set('已提出安全停止；等待目前 I/O 完成並保存映射，未確認前請勿拔除硬盤或重開任務。');self.note('STOP_REQUESTED：停止後續請求；仍等待目前 I/O。')
    def recover(self):
        def run():
            found=recover_photos(self.require_job());self.events.put(('photos',found));return f'已還原 {len(found)} 張可解碼照片'
        self.job(run)
    def show_photo(self,event=None):
        if not self.list.curselection():return
        try:
            self.video.close()
            path=self.photos[self.list.curselection()[0]]['path']
            if Path(path).suffix.lower() in ('.mp4','.mkv','.avi','.mov','.mpg','.mpeg','.vob'):
                self.canvas.configure(image='',text='')
                try:self.video.open(path)
                except Exception as e:self.canvas.configure(text='內嵌預覽不支援此檔案或編碼。\n請按「使用系統播放器開啟」。');self.note(str(e))
                return
            im=Image.open(path);im.thumbnail((640,480));self.preview=ImageTk.PhotoImage(im);self.canvas.configure(image=self.preview,text='')
        except Exception as e:messagebox.showerror('無法預覽',str(e))
    def open_selected(self):
        if self.list.curselection():os.startfile(self.photos[self.list.curselection()[0]]['path'])
    def show_demo(self):
        self.tabs.select(1);self.photos=[dict(path=str(BASE/'demo/photo.jpg')),dict(path=str(BASE/'demo/video.avi'))]
        self.list.delete(0,'end')
        for x in self.photos:self.list.insert('end',Path(x['path']).name)
        self.list.selection_set(0);self.show_photo()
    def export(self):
        p=filedialog.asksaveasfilename(defaultextension='.img',filetypes=[('完整映像','.img')])
        if p:self.job(lambda:export_image(self.require_job(),p) or '完整映像已匯出')
    def photorec(self):
        if self.busy:return
        p=filedialog.askopenfilename(title='選擇完整鏡像或已驗證連續區段，PhotoRec只處理副本',filetypes=[('鏡像','*.img')])
        if not p:return
        if not Path(p).is_file():return
        dest=filedialog.askdirectory(title='選擇還原檔案保存位置')
        if not dest:return
        try:
            target_identity=destination_identity(dest)
            image_identity=destination_identity(Path(p).parent)
            if target_identity['serial']==image_identity['serial']:
                return messagebox.showerror('目的地不安全','PhotoRec輸出資料夾須位於鏡像所在物理盤以外的健康磁盤')
            if self.root:
                plan=load(self.root/'plan.json')
                if plan.get('kind')=='disk' and target_identity['serial']==plan.get('serial'):
                    return messagebox.showerror('禁止寫入來源','PhotoRec輸出不能位於來源實體硬盤')
        except Exception as e:return messagebox.showerror('無法確認目的磁盤',str(e))
        install=Path(sys.executable).parent if getattr(sys,'frozen',False) else BASE
        exe=install/'vendor/testdisk-7.2/photorec_win.exe'
        if not exe.exists():return messagebox.showerror('缺少工具','請依 docs/USAGE.zh-TW.md 安裝官方 PhotoRec 7.2 到 vendor/testdisk-7.2/')
        if self.root:
            plan=load(self.root/'plan.json')
            if plan['kind']=='disk':
                from platform_win import destination_disk
                if destination_disk(dest)==plan['number']:return messagebox.showerror('禁止寫入來源','還原資料必須保存到其他物理硬盤')
        def run():
            import shutil
            folder=Path(dest)/('PhotoRec-'+uuid.uuid4().hex[:8]);folder.mkdir()
            with (folder/'photorec.log').open('wb') as log:
                child=subprocess.Popen([str(exe),'/d',str(folder/'recovered'),'/cmd',str(Path(p).resolve()),'partition_none,search'],cwd=folder,stdout=log,stderr=log,env=clean_env(),creationflags=0x08000000)
                while child.poll() is None:
                    if self.stop.is_set() or shutil.disk_usage(folder).free<FLOOR+64*1024**2:
                        child.kill();child.wait(3);return 'PhotoRec 已停止；保留已輸出檔案：'+str(folder)
                    time.sleep(.5)
                if child.returncode:raise RuntimeError('PhotoRec 未成功完成，請看 '+str(folder/'photorec.log'))
            return 'PhotoRec 結束；請載入還原資料夾並檢查影片是否完整：'+str(folder)
        self.job(run,operation='external')
    def load_media(self):
        p=filedialog.askdirectory(title='選擇 PhotoRec 還原輸出或照片資料夾')
        if not p:return
        items=[]
        for path in Path(p).rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.jpg','.jpeg','.png','.mp4','.mkv','.avi','.mov','.mpg','.mpeg','.vob'):
                items.append(dict(path=str(path)))
                if len(items)>=5000:break
        self.events.put(('photos',items))
    def open_output(self):
        try:os.startfile(str(self.require_job()))
        except Exception as e:messagebox.showerror('未選任務',str(e))
    def preview_partition(self):
        if self.busy:return
        def run():
            path,report=partition_preview(self.require_job())
            return f"只讀避讓預覽已輸出：{path}\n不建分區、不判定候選區健康；候選段 {len(report['candidate_segments'])} 段。"
        self.job(run)
    def repair(self):
        messagebox.showinfo('維護功能未開放','本版本僅支援讀取診斷、映射驗證及避讓分區預覽。壞扇區寫入修復、CHKDSK /f、格式化和分區表寫回均未實作，也不會以按鈕冒充已支援。')
    def close(self):
        if self.busy:
            self.request_stop();messagebox.showinfo('操作仍在進行',self.state.get()+' 關閉前請等待工作結束。');return
        self.video.close();self.w.destroy()

if __name__=='__main__':
    w=tk.Tk();ttk.Style().theme_use('clam');App(w);w.mainloop()
