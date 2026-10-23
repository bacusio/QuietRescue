import sys,os,json,threading,queue,time,subprocess,uuid,getpass
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from PIL import Image,ImageTk
from engine import load,save,capture,verify,export_image,export_regions,validate,approve_physical_plan,require_physical_approval,FLOOR
from platform_win import inventory,clean_env,destination_identity
from media import recover_photos,avoidance
from maintenance import preview as partition_preview
from progress_view import STATE_COLORS,load_progress,matches_device,slider_byte_for_x
BASE=Path(__file__).resolve().parent

class App:
    def __init__(self,window):
        self.w=window;window.title('QuietRescue 1.2.2 · 本地資料搶救');window.geometry('1100x820')
        self.root=None;self.busy=False;self.operation=None;self.operation_phase=None;self.stop=threading.Event();self.events=queue.Queue();self.disks=[];self.photos=[];self.preview=None
        self.disk=tk.StringVar();self.dest=tk.StringVar();self.limit=tk.StringVar(value='1');self.total_limit=tk.StringVar(value='100');self.continuous=tk.BooleanVar(value=True);self.start=tk.StringVar(value='0');self.end=tk.StringVar();self.state=tk.StringVar(value='尚未開始 · 不會自動讀取硬盤')
        self.progress_path=tk.StringVar();self.progress_status=tk.StringVar(value='尚未載入進度檔；色帶不會讀取來源硬盤。')
        self.progress_data=None;self.progress_after=None;self.slider_drag=False;self.slider_size=0;self.slider_sector=512
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
        for variable in (self.start,self.end,self.limit):variable.trace_add('write',lambda *_:self.draw_progress_band())
        self.band=tk.Canvas(rescue,height=78,background='#f2f2f2',highlightthickness=1,highlightbackground='#aaa')
        self.band.pack(fill='x',pady=(10,2));self.band.bind('<Configure>',lambda _e:self.draw_progress_band())
        self.band.bind('<Button-1>',self.band_press);self.band.bind('<B1-Motion>',self.band_drag);self.band.bind('<ButtonRelease-1>',self.band_release)
        band_tools=ttk.Frame(rescue);band_tools.pack(fill='x')
        ttk.Button(band_tools,text='載入／同步進度 JSON',command=self.pick_progress).pack(side='left')
        ttk.Label(band_tools,textvariable=self.progress_status).pack(side='left',padx=10)
        ttk.Label(rescue,text='色帶按整碟 bytes 比例顯示；拖動游標會同步起點 bytes。灰色為尚未搶救區，更新只讀進度檔，不會讀取來源硬碟。',wraplength=950).pack(anchor='w',pady=(2,8))
        line=ttk.Frame(rescue);line.pack(fill='x',pady=(6,0))
        ttk.Checkbutton(line,text='每批完成後自動續讀（遵守本計劃累計上限）',variable=self.continuous).pack(side='left')
        ttk.Label(line,text='累計上限 GB').pack(side='left',padx=(18,4));ttk.Entry(line,textvariable=self.total_limit,width=10).pack(side='left')
        ttk.Label(rescue,text='實體讀取需先審核並明確批准計劃。來源唯讀；每批最多1MiB請求，8秒超時或讀取超過2秒即停止。\nCRC／超時／裝置掉線不自動重試；目的寫入失敗不記作來源壞區。請先保護資料；本 reader 尚未完成多型號故障硬碟驗收。',wraplength=900).pack(anchor='w',pady=12)
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
        ttk.Button(gallery,text='分析鏡像中的舊分區（只讀 TestDisk）',command=self.scan_partitions).pack(anchor='w',pady=4)
        ttk.Button(gallery,text='接續中斷的 PhotoRec 提取（保存鏡像）',command=self.resume_photorec).pack(anchor='w',pady=4)
        ttk.Button(gallery,text='跨任務尋找並還原完整 MKV（已保存鏡像）',command=self.recover_mapped_videos).pack(anchor='w',pady=4)
        ttk.Button(gallery,text='按 MFT 原檔名還原（已保存記錄／鏡像）',command=self.recover_named_record).pack(anchor='w',pady=4)
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
        if i>=0:
            self.end.set(str(self.disks[i]['Size']));self.slider_size=int(self.disks[i]['Size']);self.slider_sector=int(self.disks[i].get('LogicalSectorSize') or 512);self.draw_progress_band()
            self.validate_progress_source()
    def pick_progress(self):
        p=filedialog.askopenfilename(title='選取進度檔（只讀 JSON）',filetypes=[('進度 JSON','progress.json'),('JSON','*.json')])
        if not p:return
        self.progress_path.set(p)
        self.refresh_progress()
        if self.progress_after:self.w.after_cancel(self.progress_after)
        self.progress_after=self.w.after(5000,self.poll_progress_file)
    def poll_progress_file(self):
        self.progress_after=None
        if self.progress_path.get():
            self.refresh_progress()
            self.progress_after=self.w.after(5000,self.poll_progress_file)
    def refresh_progress(self):
        try:
            data=load_progress(self.progress_path.get());source=data.get('source') or {};size=int(source.get('size_bytes') or 0)
            self.progress_data=data;self.slider_size=size
            self.validate_progress_source();self.draw_progress_band()
        except Exception as e:
            self.progress_data=None;self.progress_status.set(f'進度檔讀取失敗：{e}');self.draw_progress_band()
    def validate_progress_source(self):
        data=self.progress_data
        if not data:return
        source=data.get('source') or {};i=self.combo.current()
        if i<0:
            self.progress_status.set(f"已載入 {source.get('serial','未知序號')} · {data.get('run',{}).get('status','未知狀態')} · 請選來源硬碟核對")
            return
        disk=self.disks[i];serial=str(disk.get('SerialNumber','')).strip();source_serial=str(source.get('serial','')).strip()
        source_size=int(source.get('size_bytes') or 0);disk_size=int(disk.get('Size') or 0)
        if not matches_device(data,serial,disk_size):
            self.slider_size=disk_size or source_size
            self.progress_status.set(f'來源不符（進度 {source_serial} / {source_size:,} bytes；所選 {serial} / {disk_size:,} bytes）；未套用色帶')
            return
        self.slider_size=disk_size or source_size
        self.progress_status.set(f"同步中 · {data.get('run',{}).get('status','未知狀態')} · 更新 {data.get('generated_at','未知時間')} · 每 5 秒重讀")
    def band_x_for_byte(self,value):
        w=max(2,self.band.winfo_width());left=10;right=w-10;cap=max(1,self.slider_size or int(((self.progress_data or {}).get('source') or {}).get('size_bytes') or 0))
        return left+(right-left)*max(0,min(cap,int(value)))/cap
    def draw_progress_band(self):
        if not hasattr(self,'band'):return
        c=self.band;c.delete('all');w=max(20,c.winfo_width());h=max(50,c.winfo_height());left=10;right=w-10;y0=24;y1=49
        c.create_text(left,8,anchor='nw',text='讀取進度色帶（全碟位置）',fill='#222',font=('Microsoft JhengHei UI',9))
        c.create_rectangle(left,y0,right,y1,fill='#d3d3d3',outline='#888')
        data=self.progress_data;cap=self.slider_size or int(((data or {}).get('source') or {}).get('size_bytes') or 0)
        if data and cap>0:
            i=self.combo.current();mismatch=i<0
            if i>=0:
                mismatch=not matches_device(data,self.disks[i].get('SerialNumber'),self.disks[i].get('Size'))
            if not mismatch:
                for r in data.get('ranges',[]):
                    try:a=int(r['start']);z=int(r['end']);color=STATE_COLORS[str(r['state'])]
                    except (KeyError,TypeError,ValueError):continue
                    if z<=a:continue
                    x1=left+(right-left)*max(0,min(cap,a))/cap;x2=left+(right-left)*max(0,min(cap,z))/cap
                    if x2>x1:c.create_rectangle(x1,y0,x2,y1,fill=color,outline=color)
                for o in data.get('overlays',[]):
                    try:a=int(o['start']);z=int(o['end']);kind=str(o.get('kind',''))
                    except (KeyError,TypeError,ValueError):continue
                    x1=left+(right-left)*max(0,min(cap,a))/cap;x2=left+(right-left)*max(0,min(cap,z))/cap
                    color={'draft':'#d18b26','historical_request':'#7040a0','policy':'#318aa6','unconfirmed':'#9361b4'}.get(kind)
                    if color and x2>x1:c.create_line(x1,y0-2,x2,y0-2,fill=color,width=3)
        try:pos=int(self.start.get() or 0)
        except ValueError:pos=0
        try:window_bytes=max(0,int(float(self.limit.get())*1e9))
        except (TypeError,ValueError):window_bytes=0
        try:end=int(self.end.get() or cap)
        except (TypeError,ValueError):end=cap
        if cap>0 and window_bytes>0:
            hi=min(cap,max(pos,min(end,pos+window_bytes)))
            xa=left+(right-left)*max(0,min(cap,pos))/cap;xb=left+(right-left)*hi/cap
            if xb>xa:c.create_rectangle(xa,y0,xb,y1,fill='#3b82c4',stipple='gray50',outline='#145b97',width=1)
        x=self.band_x_for_byte(pos);c.create_line(x,y0-5,x,y1+5,fill='#1769aa',width=3)
        c.create_polygon(x-5,y1+6,x+5,y1+6,x,y1+13,fill='#1769aa',outline='#104d7e')
        c.create_text(left,h-5,anchor='sw',text='綠 已保存   藍 已回報   紫 未確認   紅 故障   灰 未搶救   橙 避讓草案',fill='#333',font=('Microsoft JhengHei UI',8))
    def band_set_start(self,event):
        cap=self.slider_size or int(((self.progress_data or {}).get('source') or {}).get('size_bytes') or 0)
        if cap<=0:return
        try:current_end=int(self.end.get())
        except (TypeError,ValueError):current_end=cap
        value=slider_byte_for_x(event.x,self.band.winfo_width(),cap,sector=self.slider_sector,end=current_end)
        self.start.set(str(max(0,min(cap,value))))
    def band_press(self,event):self.slider_drag=True;self.band_set_start(event)
    def band_drag(self,event):
        if self.slider_drag:self.band_set_start(event)
    def band_release(self,event):
        if self.slider_drag:self.band_set_start(event)
        self.slider_drag=False
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
        p=filedialog.askopenfilename(title='選擇已保存鏡像；單一片段不代表完整影片',filetypes=[('鏡像','*.img *.bin *.dd *.raw *.partial')])
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
        from image_recovery import find_photorec,recover
        try:find_photorec()
        except Exception as e:return messagebox.showerror('缺少工具',str(e))
        if self.root:
            plan=load(self.root/'plan.json')
            if plan['kind']=='disk':
                from platform_win import destination_disk
                if destination_disk(dest)==plan['number']:return messagebox.showerror('禁止寫入來源','還原資料必須保存到其他物理硬盤')
        def run():
            def report(info):
                text=info['status']
                if 'copied_bytes' in info:text+=f" · 暫存 {info['copied_bytes']/1e9:.3f}/{info['source_bytes']/1e9:.3f} GB"
                if 'elapsed_seconds' in info:text+=f" · 搜尋 {info['elapsed_seconds']} 秒"
                self.events.put(('phase',text))
            result=recover(p,dest,self.stop,report)
            return f"提取 {result['recovered_files']} 個候選檔案，需驗證完整性：{result['output']}；原鏡像保留。"
        self.job(run,operation='external')
    def resume_photorec(self):
        if self.busy:return
        folder=filedialog.askdirectory(title='選擇含 recovery.json、input.img、photorec.ses 的中斷任務')
        if not folder:return
        try:
            target=destination_identity(folder)
            if not target.get('serial'):raise ValueError('無法確認保存磁盤識別碼')
            if self.root:
                plan=load(self.root/'plan.json')
                if plan.get('kind')=='disk' and target['serial']==plan.get('serial'):
                    raise ValueError('不能在來源實體硬盤上續作或寫入提取結果')
        except Exception as exc:return messagebox.showerror('無法安全續作',str(exc))
        from photorec_resume import resume
        def run():
            def report(info):
                text=info['status']
                if 'elapsed_seconds' in info:text+=f" · {info['elapsed_seconds']} 秒"
                self.events.put(('phase',text))
            self.events.put(('phase','正在核對暫存鏡像完整性；不讀取來源實體硬盤'))
            result=resume(folder,self.stop,report)
            return f"續作完成：{result['recovered_files']} 個候選檔案仍需驗證；保存於 {result['output']}。原鏡像與舊輸出保留。"
        self.job(run,operation='external')
    def recover_mapped_videos(self):
        if self.busy:return
        parent=filedialog.askdirectory(title='選擇同一來源硬盤的救援任務父資料夾')
        if not parent:return
        base=Path(parent);jobs=sorted({p.parent for pattern in ('map.jsonl','requests.jsonl','*/map.jsonl','*/requests.jsonl') for p in base.glob(pattern) if (p.parent/'plan.json').is_file()})
        if not jobs:return messagebox.showerror('沒有映射','所選資料夾及直屬子資料夾沒有 plan.json 與 map.jsonl／requests.jsonl。')
        destination=filedialog.askdirectory(title='選擇影片保存位置')
        if not destination:return
        import shutil
        ffmpeg=shutil.which('ffmpeg.exe')
        if not ffmpeg:ffmpeg=filedialog.askopenfilename(title='選擇 ffmpeg.exe 以驗證完整影片（同目錄需有 ffprobe.exe）',filetypes=[('FFmpeg','ffmpeg.exe')])
        if not ffmpeg:return
        def run():
            from mapped_videos import recover
            def check_destination(identity,target):
                if destination_identity(target)['serial']==identity[0]:raise ValueError('不能將結果寫入來源實體硬盤')
            last=[0]
            def report(info):
                if time.monotonic()-last[0]<1:return
                last[0]=time.monotonic();self.events.put(('phase',info['status']+f" · {info.get('copied_bytes',0)/1e9:.3f} GB"))
            result=recover(jobs,destination,self.stop,report,ffmpeg=ffmpeg,validate_destination=check_destination)
            passed=sum(x.get('validation',{}).get('validation')=='FULL_AVAILABLE_STREAM_DECODE_PASS' for x in result['outputs'])
            return f"拼接 {len(result['outputs'])} 個候選，{passed} 個完整解碼通過：{result['output']}。原名與原檔完整性仍需核對；鏡像保留。"
        self.job(run,operation='external')
    def recover_named_record(self):
        if self.busy:return
        record_path=filedialog.askopenfilename(title='選擇已保存的單筆 MFT FILE 記錄',filetypes=[('MFT 記錄','*.bin *.mft *.record')])
        if not record_path:return
        parent=filedialog.askdirectory(title='選擇已保存鏡像的任務父資料夾')
        if not parent:return
        base=Path(parent);jobs=sorted({p.parent for pattern in ('map.jsonl','requests.jsonl','*/map.jsonl','*/requests.jsonl') for p in base.glob(pattern) if (p.parent/'plan.json').is_file()})
        if not jobs:return messagebox.showerror('沒有映射','找不到保存鏡像的 plan.json 與映射。')
        destination=filedialog.askdirectory(title='選擇原檔名還原保存位置')
        if not destination:return
        start=simpledialog.askstring('分區實體起點','輸入分區起點 bytes（實體位址，不是分區相對位址）')
        if start is None:return
        cluster=simpledialog.askstring('叢集大小','輸入已確認的叢集大小 bytes')
        if cluster is None:return
        evidence=simpledialog.askstring('參數依據','填入分區／NTFS 開機記錄的核驗依據；推測參數不能證明檔案正確')
        if evidence is None:return
        try:
            start=int(start);cluster=int(cluster)
            if not evidence.strip():raise ValueError('需要參數依據')
        except ValueError as e:return messagebox.showerror('參數無效',str(e))
        def run():
            from saved_ranges import SavedRanges
            from named_recovery import recover_record
            target_root=Path(destination).resolve(strict=True)
            index=SavedRanges(jobs,cleanup_ledgers=sorted(target_root.glob('lossless-cleanup-ledger*.json')),recovered_root=target_root);p=Path(record_path)
            for location in (destination,p.parent):
                if destination_identity(location)['serial']==index.identity[0]:raise ValueError('不能從故障來源盤讀取記錄或寫入還原結果')
            if p.is_symlink() or not p.is_file() or not 512<=p.stat().st_size<=65536:raise ValueError('只接受已保存、最多64KiB的單筆MFT記錄')
            with p.open('rb') as stream:raw=stream.read(65537)
            if len(raw)>65536:raise ValueError('記錄超限')
            result=recover_record(index,raw,start,cluster,evidence,destination,self.stop,lambda info:self.events.put(('phase',f"按原名還原 · {info.get('copied_bytes',0):,} bytes")))
            return '已按 MFT 名稱匯出：'+result['original_filename_from_mft']+'；內容仍需解碼／結構驗證。未讀取故障盤，原鏡像保留。'
        self.job(run,operation='external')
    def scan_partitions(self):
        if self.busy:return
        image=filedialog.askopenfilename(title='選擇已保存鏡像，僅分析、不寫回分區表',filetypes=[('鏡像','*.img *.bin *.dd *.raw *.partial')])
        if not image:return
        destination=filedialog.askdirectory(title='選擇分析報告保存位置（建議英文路徑）')
        if not destination:return
        table=simpledialog.askstring('分區分析模式','輸入 GPT 或 MBR。4TB GPT 磁盤可選 GPT；此處只分析保存鏡像，不寫回。',initialvalue='GPT')
        if table is None:return
        table=table.strip().lower()
        if table not in {'gpt','mbr'}:return messagebox.showerror('模式無效','只接受 GPT 或 MBR。')
        try:
            identity=destination_identity(destination)
            if self.root:
                plan=load(self.root/'plan.json')
                if plan.get('kind')=='disk' and identity['serial']==plan.get('serial'):
                    raise ValueError('分析報告不能寫入故障來源實體硬盤')
        except Exception as e:return messagebox.showerror('目的地檢查失敗',str(e))
        def run():
            from partition_scan import analyze
            result=analyze(image,destination,self.stop,lambda info:self.events.put(('phase',f"舊分區分析 · {info.get('elapsed_seconds',0)} 秒 · 鏡像只讀")),table=table)
            return '舊分區分析完成，請查看 '+str(Path(result['output'])/'testdisk.log')+'；報告位址相對於鏡像，未寫回分區表。'
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
        if self.progress_after:
            try:self.w.after_cancel(self.progress_after)
            except tk.TclError:pass
        self.video.close();self.w.destroy()

if __name__=='__main__':
    w=tk.Tk();ttk.Style().theme_use('clam');App(w);w.mainloop()
