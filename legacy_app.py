import os,sys,threading,queue,traceback,webbrowser,urllib.parse,msvcrt
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from recorder import *
from processing import process_isolated
from transcription_runtime import refinement_settings,profile
from secret_store import has_key
from hotword_files import split_words, validate_words
from hotword_ui import HotwordEditor

def install_vault(vault):
    vault=Path(vault)
    if any(part.lower()=='.obsidian' for part in vault.parts):raise RuntimeError('请选择资料库根目录或专用资料目录，不要选择 .obsidian 配置文件夹。')
    vault.mkdir(parents=True,exist_ok=True)
    src=ROOT/'vault-template/.obsidian'
    for f in src.rglob('*'):
        if f.is_file():
            dest=vault/'.obsidian'/f.relative_to(src);dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copy2(f,dest)
    enabled=vault/'.obsidian/community-plugins.json'
    plugins=read(enabled) if enabled.exists() else []
    for name in ['media-transcript','experience-opener']:
        if name not in plugins:plugins.append(name)
    write(enabled,plugins)
    (vault/'办公室打开说明.md').write_text(OFFICE,encoding='utf-8')

class App:
    def __init__(self,root):
        self.root=root;self.cfg=config();self.events=queue.Queue();self.busy=False;self.active=None;self.paths={};self.last_poll=0;self.last_selection=None
        root.title('游戏体验记录器');root.geometry('850x655');root.minsize(810,600)
        root.option_add('*Font','{Microsoft YaHei UI} 10')
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',padding=8);style.configure('Title.TLabel',font=('Microsoft YaHei UI',20,'bold'));style.configure('State.TLabel',font=('Microsoft YaHei UI',13,'bold'),foreground='#166b51')
        frame=ttk.Frame(root,padding=22);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='游戏体验记录器',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='自然说出当时的想法。结束后整理，再回看与复盘。').pack(anchor='w',pady=(4,14))
        row=ttk.Frame(frame);row.pack(fill='x')
        ttk.Label(row,text='游戏名称').pack(side='left');self.game=tk.StringVar(value=self.cfg['game'])
        self.gamebox=ttk.Combobox(row,textvariable=self.game,values=list(self.cfg.get('games',{})));self.gamebox.pack(side='left',fill='x',expand=True,padx=8);self.gamebox.bind('<<ComboboxSelected>>',self.load_game)
        self.settings_btn=ttk.Button(row,text='首次设置 / 预设',command=self.settings);self.settings_btn.pack(side='right')
        self.service_btn=ttk.Button(row,text='转写服务',command=self.transcription_settings);self.service_btn.pack(side='right',padx=(0,6))
        self.summary=tk.StringVar();ttk.Label(frame,textvariable=self.summary,wraplength=650).pack(anchor='w',pady=(10,10));self.update_summary()
        self.status=tk.StringVar(value='待开始');ttk.Label(frame,textvariable=self.status,style='State.TLabel').pack(anchor='w')
        self.detail=tk.StringVar(value='整理 = 录后自动转写 + 生成同步回看文件。真实录制前请完成首次设置。')
        ttk.Label(frame,textvariable=self.detail,wraplength=790).pack(anchor='w',pady=(4,8))
        bar=ttk.Frame(frame);bar.pack(fill='x',pady=6)
        self.start_btn=ttk.Button(bar,text='开始体验',command=self.start);self.start_btn.pack(side='left',expand=True,fill='x',padx=(0,6))
        self.stop_btn=ttk.Button(bar,text='结束并整理',command=self.stop);self.stop_btn.pack(side='left',expand=True,fill='x')
        ttk.Label(frame,text='场次（选择后可回看、恢复或打包）').pack(anchor='w',pady=(12,6))
        self.tree=ttk.Treeview(frame,columns=('game','state'),show='headings',height=6);self.tree.heading('game',text='时间 / 游戏');self.tree.heading('state',text='状态');self.tree.column('game',width=475);self.tree.column('state',width=105);self.tree.pack(fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',self.selected_changed)
        buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=(10,0))
        self.review_btn=ttk.Button(buttons,text='打开同步回看',command=self.open_review);self.review_btn.pack(side='left',expand=True,fill='x',padx=2)
        self.retry_btn=ttk.Button(buttons,text='开始整理',command=self.retry);self.retry_btn.pack(side='left',expand=True,fill='x',padx=2)
        self.pack_btn=ttk.Button(buttons,text='打包带走',command=self.package);self.pack_btn.pack(side='left',expand=True,fill='x',padx=2)
        ttk.Button(buttons,text='资料文件夹',command=self.folder).pack(side='left',expand=True,fill='x',padx=2)
        extra=ttk.Frame(frame);extra.pack(fill='x',pady=(8,0))
        ttk.Button(extra,text='直接打开独立回看网页',command=self.browser_review).pack(side='left')
        ttk.Button(extra,text='查看原始录像',command=self.raw_video).pack(side='left',padx=8)
        ttk.Label(extra,text='整理时请稍候；可最小化窗口').pack(side='right')
        self.refresh();root.protocol('WM_DELETE_WINDOW',self.close);root.after(150,self.pump)
        if any(part.lower()=='.obsidian' for part in Path(self.cfg['vault']).parts):
            self.detail.set('保存位置选到了 Obsidian 内部配置文件夹。请点“首次设置 / 预设”，选择资料库根目录或专用资料目录。')
        self.background(self.recover)
    def update_summary(self):
        quality='准确率优先' if self.cfg.get('model')=='large-v3' else '标准转写'
        language={'zh':'中文','en':'英语','ja':'日语','':'自动语言'}.get(self.cfg['language'],self.cfg['language'])
        service=('Qwen 云端'+language+(' · 密钥已保存' if has_key() else ' · 待填写 API Key')) if self.cfg.get('transcription_provider')=='qwen' else quality+' · 离线'+language
        self.summary.set(f"{self.cfg['preset']} · {self.cfg['source']} · {service}\n保存到：{self.cfg['vault']}")
    def load_game(self,event=None):
        preset=self.cfg.get('games',{}).get(self.game.get())
        if preset and not self.busy and not self.active:self.cfg.update(preset);self.update_summary()
    def background(self,fn):
        if self.busy:return
        self.busy=True;self.controls()
        def work():
            try:fn()
            except Exception as e:
                with open(ROOT/'应用日志.txt','a',encoding='utf-8') as f:traceback.print_exc(file=f)
                self.events.put(('error',str(e)))
            finally:self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def controls(self):
        self.start_btn.configure(state='disabled' if self.busy or self.active else 'normal')
        self.stop_btn.configure(state='normal' if self.active and not self.busy else 'disabled')
        self.settings_btn.configure(state='disabled' if self.busy or self.active else 'normal')
        self.service_btn.configure(state='disabled' if self.busy or self.active else 'normal')
        self.gamebox.configure(state='disabled' if self.busy or self.active else 'normal')
        self.session_controls()
    def session_controls(self):
        try:state=self.selected().meta['state']
        except Exception:state=''
        label='重新转写（保留旧版）' if state=='可回看' else ('重试生成回看' if state=='失败' else '开始整理（转写 + 回看）')
        self.retry_btn.configure(text=label,state='normal' if state in ['失败','待整理','保存中','启动中','可回看'] and not self.busy and not self.active else 'disabled')
        self.review_btn.configure(state='normal' if state=='可回看' and not self.busy else 'disabled')
        self.pack_btn.configure(state='normal' if state=='可回看' and not self.busy and not self.active else 'disabled')
    def pump(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='detail':self.detail.set(data)
                elif kind=='state':self.status.set(data)
                elif kind=='error':self.status.set('失败');self.detail.set(data);messagebox.showerror('操作未完成',data)
                elif kind=='devices':self.settings_dialog(data)
                elif kind=='done':self.busy=False;self.refresh();self.controls()
        except queue.Empty:pass
        if self.active and not self.busy and time.time()-self.last_poll>5:
            self.last_poll=time.time();self.background(self.check_recording)
        self.root.after(150,self.pump)
    def check_recording(self):
        try:r=client(False);state=r.get_record_status()
        except Exception:
            self.last_poll=time.time()+20
            self.events.put(('state','录制连接中断'));self.events.put(('detail','暂时无法连接 OBS，录像可能仍在继续。正在重连；请勿重复开始。'));return
        if state.output_active:
            self.events.put(('state','录制中'))
            self.events.put(('detail','录制时长 '+state.output_timecode+' · 可最小化窗口继续玩'))
            if shutil.disk_usage(self.active.path).free<2*1024**3:
                self.active.stop();self.active.update(state='待整理',warning='磁盘空间不足，已停止录制');self.active=None
                self.events.put(('state','待整理'));self.events.put(('detail','剩余空间不足 2 GB，已保存录像。请释放空间后重试整理。'))
        else:
            s=self.active;self.active=None;s.update(state='失败',error='OBS 录制意外停止，原录像已保留。请选择恢复 / 重试整理。')
            self.events.put(('state','失败'));self.events.put(('detail',s.meta['error']))
    def refresh(self):
        selected=self.tree.selection();keep=selected[0] if selected else None
        self.tree.delete(*self.tree.get_children());self.paths={}
        base=Path(self.cfg['vault'])/'场次'
        if base.exists():
            for p in sorted(base.glob('*/session.json'),reverse=True):
                try:
                    m=read(p);key=m['id'];self.paths[key]=p.parent;display=('[测试] ' if m.get('test') else '')+p.parent.name;self.tree.insert('',tk.END,iid=key,values=(display,m['state']))
                except Exception:continue
        if keep in self.paths:self.tree.selection_set(keep)
        elif self.paths:
            ready=next((key for key,path in self.paths.items() if read(path/'session.json')['state']=='可回看'),None)
            self.tree.selection_set(ready or next(iter(self.paths)))
        self.session_controls()
    def selected(self):
        ids=self.tree.selection()
        if not ids:raise RuntimeError('请先选择一个场次。')
        return Session(self.paths[ids[0]])
    def selected_changed(self,event=None):
        self.session_controls()
        if self.active or self.busy:return
        selection=self.tree.selection()
        key=selection[0] if selection else None
        if key==self.last_selection:return
        self.last_selection=key
        try:
            m=self.selected().meta;self.status.set(m['state']);self.detail.set(m.get('error') or m.get('warning') or ('点击“开始整理”，自动转写口述并生成同步回看文件。' if m['state']=='待整理' else m['id']))
        except Exception:pass
    def recover(self):
        # Never start OBS just to recover or inspect an interrupted session.
        try:
            r=client(False)
            if r.get_record_status().output_active:
                p=Path(r.send('GetRecordDirectory').record_directory)
                if (p/'session.json').exists() and p.parent.parent.resolve()==Path(self.cfg['vault']).resolve():
                    if read(p/'session.json').get('test'):
                        self.events.put(('detail','后台正在验证合成样片；已有场次仍可整理和回看。'));return
                    self.active=Session(p);self.active.update(state='录制中');self.events.put(('state','录制中'));self.events.put(('detail','已接回尚未结束的录制。'))
                    return
        except Exception:pass
        for p in (Path(self.cfg['vault'])/'场次').glob('*/session.json'):
            s=Session(p.parent)
            if s.meta['state'] in ['录制中','启动中','保存中','转写中']:s.update(state='失败',error='上次操作中断。选择本场次并点击恢复 / 重试整理。')
    def start(self):
        if not self.cfg.get('configured'):self.settings();return
        if self.cfg.get('transcription_provider')=='qwen' and not has_key():self.transcription_settings();return
        if any(part.lower()=='.obsidian' for part in Path(self.cfg['vault']).parts):
            messagebox.showerror('保存位置需要调整','当前选中的是 Obsidian 内部配置文件夹。请在设置中选择资料库根目录，或新建专用资料目录。');self.settings();return
        self.cfg['game']=self.game.get().strip() or '自由探索';save_config(self.cfg)
        def work():
            self.events.put(('state','正在启动…'));self.active=Session.start(dict(self.cfg));self.events.put(('state','录制中'));self.events.put(('detail','已开始录制游戏画面和口述。'))
        self.background(work)
    def stop(self):
        if not self.active:return
        def work():
            s=self.active;self.events.put(('state','保存中'));s.stop();self.active=None;self.events.put(('state','转写中'));process_isolated(s,lambda t:self.events.put(('detail',t)));self.events.put(('state','可回看'))
        self.background(work)
    def retry(self):
        if self.active or self.busy:messagebox.showinfo('正在处理','当前操作尚未结束，请查看窗口中的进度。');return
        try:s=self.selected()
        except Exception as e:messagebox.showinfo('选择场次',str(e));return
        current=refinement_settings(self.cfg,s.meta)
        if current.get('transcription_provider')=='qwen' and not has_key():self.transcription_settings();return
        settings=current if s.meta['state']=='可回看' or profile(current)!=profile(s.meta['settings']) else None
        def work():
            try:
                r=client(False)
                if r.get_record_status().output_active and Path(r.send('GetRecordDirectory').record_directory).resolve()==s.path.resolve():raise RuntimeError('此场次仍在录制，请先结束录制。')
            except ConnectionError:pass
            except OSError:pass
            self.events.put(('state','转写中'));process_isolated(s,lambda t:self.events.put(('detail',t)),transcription_settings=settings);self.events.put(('state','可回看'))
        self.background(work)
    def open_review(self):
        try:
            s=self.selected()
            if s.meta['state']!='可回看':raise RuntimeError('请先完成整理。')
            self.detail.set('正在打开同步回看…')
            self.background(lambda:open_review(s,lambda t:self.events.put(('detail',t))))
        except Exception as e:messagebox.showerror('打开回看',str(e))
    def browser_review(self):
        try:
            s=self.selected();p=s.path/'独立回看.html'
            if not p.exists():raise RuntimeError('尚未生成回看网页，请先点击“开始整理”或“重试生成回看”。')
            os.startfile(p);self.detail.set('已请求浏览器打开所选场次的独立同步回看网页。')
        except Exception as e:messagebox.showinfo('打开独立回看',str(e))
    def raw_video(self):
        try:
            s=self.selected();files=list(s.path.glob('*.mkv'))
            if not files:raise RuntimeError('此场次还没有录像。可打开资料文件夹查看错误日志。')
            os.startfile(files[0]);self.detail.set('已请求默认播放器打开原始录像。')
        except Exception as e:messagebox.showinfo('查看原始录像',str(e))
    def package(self):
        if self.active or self.busy:return
        try:s=self.selected()
        except Exception as e:messagebox.showinfo('选择场次',str(e));return
        def work():
            self.events.put(('detail','正在打包与校验大文件，请稍候…'));p=s.package();self.events.put(('detail','已打包：'+p.name));os.startfile(p.parent)
        self.background(work)
    def folder(self):
        try:os.startfile(self.selected().path)
        except Exception:os.startfile(self.cfg['vault'])
    def close(self):
        if self.busy or self.active:
            self.root.iconify();self.detail.set('操作继续在后台进行。再次点击任务栏窗口可查看进度。');return
        self.root.destroy()
    def transcription_settings(self):
        from transcription_ui import show_settings
        return show_settings(self)
    def settings(self):
        if self.busy or self.active:return
        self.detail.set('读取可用窗口、显示器和麦克风…')
        def work():
            items=devices(progress=lambda text:self.events.put(('detail',text)))
            self.events.put(('devices',items))
        self.background(work)
    def settings_dialog(self,items):
        self.detail.set('设备已就绪，请选择录制窗口和麦克风。')
        win=tk.Toplevel(self.root);win.title('首次设置 / 游戏预设');win.geometry('840x690');win.minsize(810,660);win.transient(self.root);win.grab_set()
        body=ttk.Frame(win,padding=20);body.pack(fill='both',expand=True);body.columnconfigure(1,weight=1)
        values={};maps={}
        specs=[('vault','保存位置',None),('preset','技术预设',list(PRESETS)),('source','录制源',['游戏窗口','整个显示器']),('window','游戏窗口',[x['itemName'] for x in items['window']]),('monitor','显示器',[x['itemName'] for x in items['monitor']]),('mic','麦克风',[x['itemName'] for x in items['mic']]),('language','转写语言',['中文','英语','日语','自动识别']),('hotwords','专有词提示（可选）',None)]
        for n,(key,label,options) in enumerate(specs):
            ttk.Label(body,text=label).grid(row=n,column=0,sticky='nw' if key=='hotwords' else 'w',pady=7,padx=(0,14))
            selected=self.cfg.get(key,'')
            if key=='hotwords':
                widget=HotwordEditor(body,selected,game_name=self.game.get,directory=ROOT/'vocabularies',qwen=self.cfg.get('transcription_provider')=='qwen')
                values[key]=widget;widget.grid(row=n,column=1,columnspan=2,sticky='ew',pady=7)
                continue
            if key in items:
                maps[key]={x['itemName']:x['itemValue'] for x in items[key]};selected=next((label for label,val in maps[key].items() if val==selected),'')
            elif key=='language':
                maps[key]={'中文':'zh','英语':'en','日语':'ja','自动识别':''};selected=next((label for label,val in maps[key].items() if val==selected),'中文')
            var=tk.StringVar(value=selected);values[key]=var
            widget=ttk.Entry(body,textvariable=var) if options is None else ttk.Combobox(body,textvariable=var,values=options,state='readonly')
            widget.grid(row=n,column=1,sticky='ew',pady=7)
            if key=='vault':ttk.Button(body,text='选择…',command=lambda:values['vault'].set(filedialog.askdirectory(parent=win) or values['vault'].get())).grid(row=n,column=2,padx=4)
        ttk.Label(body,text='窗口列表只显示已打开的应用。游戏声音使用 Windows 默认输出设备。\n整个显示器会录下其中所有内容；窗口录制更适合保护其他应用内容。\n术语随当前游戏预设保存；下载的词库可先在上方校对，转写仍以原声为准。',wraplength=780).grid(row=8,column=0,columnspan=3,sticky='w',pady=14)
        def save():
            updated={k:(maps[k].get(v.get(),'') if k in maps else v.get()) for k,v in values.items()}
            try:updated['hotwords']='\n'.join(validate_words(split_words(updated['hotwords']),qwen=self.cfg.get('transcription_provider')=='qwen'))
            except ValueError as e:messagebox.showerror('专有词提示',str(e),parent=win);return
            if not Path(updated['vault']).is_absolute():messagebox.showerror('保存位置','请选择绝对路径。',parent=win);return
            if not updated['mic'] or not updated['window' if updated['source']=='游戏窗口' else 'monitor']:
                messagebox.showerror('录制设备','请选择录制源和麦克风。',parent=win);return
            try:install_vault(updated['vault'])
            except Exception as e:messagebox.showerror('保存位置',str(e),parent=win);return
            self.cfg.update(updated);self.cfg['configured']=True;self.cfg['game']=self.game.get().strip() or '自由探索'
            self.cfg.setdefault('games',{})[self.cfg['game']]={k:self.cfg[k] for k in ['preset','source','window','monitor','mic','language','hotwords']}
            save_config(self.cfg);self.update_summary();self.refresh();self.detail.set('设置已保存。确认游戏与麦克风就绪后开始体验。');win.destroy()
        ttk.Button(body,text='保存并记住此游戏预设',command=save).grid(row=9,column=0,columnspan=3,sticky='ew')
        return win

if __name__=='__main__':
    lock=open(ROOT/'app.lock','a+b');lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        r=tk.Tk();r.withdraw();messagebox.showinfo('游戏体验记录器','记录器已经运行，请打开任务栏中的窗口。');sys.exit(0)
    root=tk.Tk();app=App(root)
    if '--transcription-settings' in sys.argv:
        def open_service_when_idle():
            if app.busy:root.after(250,open_service_when_idle)
            elif not app.active:app.transcription_settings()
        root.after(500,open_service_when_idle)
    root.mainloop()
