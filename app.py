import sys,os,json,threading,queue,time,subprocess,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from PIL import Image,ImageTk
from engine import load,save,capture,verify,export_image,export_regions,validate,FLOOR
from platform_win import inventory,clean_env
from media import recover_photos,avoidance
BASE=Path(__file__).resolve().parent

class App:
    def __init__(self,window):
        self.w=window;window.title('QuietRescue 1.1 · 本地資料搶救');window.geometry('1100x820')
        self.root=None;self.busy=False;self.stop=threading.Event();self.events=queue.Queue();self.disks=[];self.photos=[];self.preview=None
        self.disk=tk.StringVar();self.dest=tk.StringVar();self.limit=tk.StringVar(value='1');self.start=tk.StringVar(value='0');self.end=tk.StringVar();self.state=tk.StringVar(value='尚未開始 · 不會自動讀取硬盤')
        ttk.Label(window,text='QuietRescue',font=('Microsoft JhengHei UI',24,'bold')).pack(anchor='w',padx=24,pady=(18,0))
        ttk.Label(window,text='來源只讀  /  斷點映射  /  已驗證副本還原',font=('Microsoft JhengHei UI',11)).pack(anchor='w',padx=26,pady=(4,14))
        tabs=ttk.Notebook(window);tabs.pack(fill='both',expand=True,padx=20,pady=8);self.tabs=tabs
        rescue=ttk.Frame(tabs,padding=16);gallery=ttk.Frame(tabs,padding=16);repair=ttk.Frame(tabs,padding=16)
        tabs.add(rescue,text='① 鏡像與續讀');tabs.add(gallery,text='② 還原與預覽');tabs.add(repair,text='③ 修復與避讓')
        ttk.Label(rescue,text='來源物理硬盤（系統盤不可選；E/G可能屬於同一硬盤）').pack(anchor='w')
        self.combo=ttk.Combobox(rescue,textvariable=self.disk,state='readonly',width=90);self.combo.pack(fill='x',pady=5);self.combo.bind('<<ComboboxSelected>>',self.select_disk)
        ttk.Button(rescue,text='刷新硬盤清單',command=self.refresh).pack(anchor='w',pady=4)
        line=ttk.Frame(rescue);line.pack(fill='x',pady=10);ttk.Label(line,text='保存位置').pack(side='left');ttk.Entry(line,textvariable=self.dest,width=70).pack(side='left',padx=8);ttk.Button(line,text='選擇資料夾',command=self.pick_dest).pack(side='left')
        line=ttk.Frame(rescue);line.pack(fill='x');
        for label,var,width in [('起點 bytes',self.start,18),('終點 bytes（不含）',self.end,18),('本次最多 GB',self.limit,8)]:
            ttk.Label(line,text=label).pack(side='left',padx=3);ttk.Entry(line,textvariable=var,width=width).pack(side='left')
        ttk.Label(rescue,text='保留至少5GB空間。每段256MiB；8秒超時或讀取超過2秒即停止。\n新增故障不自動重啟；再次續讀會跳過所有已請求位置及故障緩衝。',wraplength=900).pack(anchor='w',pady=12)
        line=ttk.Frame(rescue);line.pack(fill='x')
        for title,fn in [('建立並開始鏡像',self.new_disk),('開啟任務／續讀',self.open_job),('開始續讀',self.resume),('安全停止',self.stop.set),('測試鏡像檔',self.test_file)]:ttk.Button(line,text=title,command=fn).pack(side='left',padx=3)
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
        ttk.Button(repair,text='輸出不可分配區域 CSV 草案',command=lambda:self.job(lambda:str(avoidance(self.require_job())))).pack(anchor='w',pady=8)
        ttk.Button(repair,text='檔案系統修復 CHKDSK /f（需完整驗證備份）',command=self.repair).pack(anchor='w',pady=8)
        ttk.Label(repair,text='CHKDSK /f 只修正檔案系統結構，不等於修復物理壞道。\n有缺損的鏡像不通過寫入修復門檻。',wraplength=900).pack(anchor='w',pady=10)
        ttk.Label(window,textvariable=self.state,relief='sunken',padding=8).pack(fill='x')
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(200,self.poll)

    def note(self,text):
        self.log.configure(state='normal');self.log.insert('end',str(text)+'\n');self.log.see('end');self.log.configure(state='disabled')
    def job(self,fn):
        if self.busy:return messagebox.showinfo('忙碌中','請先等待目前操作完成或安全停止。')
        self.busy=True;self.stop.clear();self.state.set('處理中…')
        def work():
            try:self.events.put(('result',fn()))
            except Exception as e:self.events.put(('error',str(e)))
            finally:self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='progress':self.state.set(f"{value['status']} · 本次 {value.get('new_bytes',0)/1e9:.3f} GB · 源盤寫入 0")
            elif kind=='inventory':
                self.disks=[d for d in value['disks'] if not d['IsSystem'] and not d['IsBoot']];self.combo['values']=[f"Disk {d['Number']} | {d['FriendlyName']} | {d['Size']/1e9:.1f} GB | {d['SerialNumber']}" for d in self.disks]
                self.note('硬盤清單已刷新；尚未讀取磁區。')
            elif kind=='photos':
                self.photos=value;self.list.delete(0,'end')
                for x in value:self.list.insert('end',Path(x['path']).name)
            elif kind=='result':self.note(value);self.state.set('操作結束；請查看結果記錄')
            elif kind=='error':self.note('停止：'+value);self.state.set('操作停止：'+value);messagebox.showerror('操作停止',value)
            elif kind=='repair_ready':
                if value['complete']:self.w.after(100,self.confirm_repair)
                else:messagebox.showerror('修復未啟動','備份有缺損；禁止寫入修復')
            elif kind=='done':self.busy=False
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
        plan=dict(version=1,kind=kind,start=int(self.start.get()),end=int(self.end.get()),stage_bytes=n,guards=[],**kw)
        parent=Path(self.dest.get()).resolve()
        if not parent.is_dir() or not self.dest.get():raise ValueError('請選保存位置')
        # Validate before creating any destination files.
        validate(plan,parent)
        self.root=parent/('QuietRescue-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);self.root.mkdir();save(self.root/'plan.json',plan)
        self.note('任務：'+str(self.root));return plan
    def new_disk(self):
        if self.busy:return
        try:
            i=self.combo.current()
            if i<0:raise ValueError('請先刷新並選擇來源硬盤')
            d=self.disks[i]
            if not messagebox.askyesno('開始只讀鏡像',f"來源 Disk {d['Number']} / {d['SerialNumber']}\n目的地 {self.dest.get()}\n開始只讀搶救？"):return
            self.make_plan('disk',number=d['Number'],serial=d['SerialNumber'].strip(),size=int(d['Size']),sector=int(d['LogicalSectorSize']))
            self.resume()
        except Exception as e:messagebox.showerror('無法開始',str(e))
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
                plan=load(p);self.root=Path(p).parent;self.note('已開啟 '+str(self.root));self.state.set('任務已載入，尚未續讀')
                if (self.root/'photo-recovery.json').exists():self.events.put(('photos',load(self.root/'photo-recovery.json')['files']))
            except Exception as e:messagebox.showerror('無法開啟',str(e))
    def resume(self):
        if self.busy:return
        try:root=self.require_job()
        except Exception as e:return messagebox.showerror('未選任務',str(e))
        def run():
            capture(root,self.stop,lambda x:self.events.put(('progress',x)))
            report=verify(root)
            return {'status':load(root/'status.json'),'verification':{k:v for k,v in report.items() if k!='missing_ranges'},'missing_ranges_count':len(report['missing_ranges'])}
        self.job(run)
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
        self.job(run)
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
    def repair(self):
        if self.busy:return
        messagebox.showinfo('修復門檻','只有整個物理硬盤的完整、無缺損且當下雜湊驗證通過的副本，才允許繼續。修復會改動來源檔案系統；本程式不執行物理壞道重寫。')
        try:
            root=self.require_job();plan=load(root/'plan.json')
            if plan['kind']!='disk' or plan['start']!=0 or plan['end']!=plan['size']:raise ValueError('需要整盤完整備份；目前範圍不符合')
            validate(plan,root)
            # Long hash verification occurs off the UI thread. No write is launched here.
            self.job(lambda: self.events.put(('repair_ready',verify(root))))
        except Exception as e:messagebox.showerror('修復未啟動',str(e))
    def close(self):
        if self.busy:
            self.stop.set();messagebox.showinfo('正在安全停止','請等目前讀取／驗證結束後再關閉。');return
        self.video.close();self.w.destroy()

    def confirm_repair(self):
        try:
            root=self.require_job();plan=load(root/'plan.json');validate(plan,root)
            letter=simpledialog.askstring('選擇修復分區','輸入該來源硬盤上需要 CHKDSK /f 的單一盤符（例如 G）：')
            if letter is None:return
            letter=letter.strip().upper().rstrip(':')
            if len(letter)!=1 or not 'A'<=letter<='Z':raise ValueError('盤符無效')
            from platform_win import destination_disk
            if destination_disk(letter+':\\')!=plan['number']:raise ValueError('分區不屬於備份來源硬盤')
            typed=simpledialog.askstring('確認寫入修復',f"將對 {letter}: 執行 CHKDSK /f。這會改寫檔案系統，不能修復盤體。\n輸入來源序列號 {plan['serial']} 才會啟動：")
            if typed!=plan['serial']:return
            validate(plan,root)
            subprocess.Popen(['chkdsk.exe',letter+':','/f'],env=clean_env(),creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.note('CHKDSK 已另開視窗；需以其最終結果判定成功，關閉視窗不代表修復完成。')
        except Exception as e:messagebox.showerror('修復未啟動',str(e))

if __name__=='__main__':
    w=tk.Tk();ttk.Style().theme_use('clam');App(w);w.mainloop()
