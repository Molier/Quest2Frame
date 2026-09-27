# SPDX-License-Identifier: GPL-3.0-only
"""Windows desktop wizard. Passwords are memory-only, never persisted."""
from pathlib import Path
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from bridge import APP, ROOT, Bridge, write_json, settings_text, artwork_candidates, suggested_title
from storage_ui import StoragePicker

class Wizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Quest → Frame'); self.geometry('960x790'); self.minsize(830, 680)
        self.events = queue.Queue(); self.busy = False; self.build = None; self.serial = None; self.package_list = []
        self.bridge = Bridge(lambda line: self.events.put(('log', line)))
        self.vars = {k: tk.StringVar(value=v) for k, v in {'host':'frame', 'port':'22', 'username':'steamos', 'password':'', 'title':'', 'steam_id':'', 'filter':'', 'scale':'100'}.items()}
        self.controllers = tk.BooleanVar(value=True); self.foveation = tk.BooleanVar(value=True); self.add_steam = tk.BooleanVar(value=True)
        self.auto_art = tk.BooleanVar(value=True); self.art_candidates = []
        config = APP / 'settings.json'
        if config.exists():
            try:
                for k,v in json.loads(config.read_text()).items():
                    if k in ('host','port','username'): self.vars[k].set(v)
            except (ValueError, OSError): pass
        style = ttk.Style(self); style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'))
        style.configure('Step.TLabel', font=('Segoe UI', 11, 'bold'))
        outer = ttk.Frame(self, padding=20); outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Quest → Frame', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Your games. Backed up, converted, and installed over USB.', padding=(0,3,0,14)).pack(anchor='w')
        ttk.Button(outer, text='About / licenses', command=lambda: messagebox.showinfo(
            'Quest to Frame — licenses',
            'Original project source: GPL-3.0-only. You may copy, modify, and redistribute it under GPL version 3.\n\n'
            'Provided WITHOUT ANY WARRANTY. Third-party tools and libraries retain their own licenses; game content and artwork are not covered.\n\n'
            f'Full license: {ROOT / "LICENSE"}\nDependency notices: {ROOT / "THIRD_PARTY_NOTICES.md"}'
        )).pack(anchor='w', pady=(0,8))
        self.status = tk.StringVar(value='0 · Configure Frame SSH, then connect your Quest.')
        ttk.Label(outer, textvariable=self.status, style='Step.TLabel').pack(anchor='w', pady=(0,12))
        self.tabs = ttk.Notebook(outer); self.tabs.pack(fill='both', expand=True)
        self.pages = []
        for label in ('0  Frame setup', '1  Select Quest game', '2  Convert', '3  Install on Frame'):
            page = ttk.Frame(self.tabs, padding=16); self.tabs.add(page, text=label); self.pages.append(page)
        self.setup_page(); self.quest_page(); self.convert_page(); self.install_page()
        self.progress = ttk.Progressbar(outer, mode='indeterminate'); self.progress.pack(fill='x', pady=(12,6))
        self.logbox = tk.Text(outer, height=9, font=('Consolas',9), wrap='word', state='disabled')
        self.logbox.pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)

    def field(self, parent, name, label, row, show=None):
        ttk.Label(parent,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=7)
        entry = ttk.Entry(parent,textvariable=self.vars[name],width=44,show=show or '')
        entry.grid(row=row,column=1,sticky='ew',pady=7)
        parent.columnconfigure(1,weight=1)
        return entry

    def setup_page(self):
        page=self.pages[0]
        self.field(page,'host','Frame hostname / IP',0)
        self.field(page,'port','SSH port',1)
        self.field(page,'username','SSH username',2)
        self.field(page,'password','SSH password (this session only)',3,show='•')
        ttk.Label(page,text='First connection: plug in Frame by USB to verify its SSH identity.\nAfterward, plug in Quest. Both headsets need developer/USB debugging enabled.',wraplength=720).grid(row=4,column=0,columnspan=2,sticky='w',pady=10)
        ttk.Button(page,text='Test SSH and save connection details',command=self.test_ssh).grid(row=5,column=0,columnspan=2,sticky='w')
        ttk.Button(page,text='Next: connect Quest →',command=lambda:self.tabs.select(1)).grid(row=6,column=0,columnspan=2,sticky='w',pady=10)

    def quest_page(self):
        page=self.pages[1]
        ttk.Label(page,text='Plug in Quest, unlock it, and accept the USB debugging prompt.').pack(anchor='w')
        ttk.Button(page,text='Scan Quest and list installed packages',command=self.scan).pack(anchor='w',pady=8)
        entry=ttk.Entry(page,textvariable=self.vars['filter']);entry.pack(fill='x')
        self.vars['filter'].trace_add('write',lambda *_:self.filter_packages())
        self.listbox=tk.Listbox(page,height=8,exportselection=False,selectmode='extended');self.listbox.pack(fill='both',expand=True,pady=8)
        ttk.Label(page,text='Ctrl-click or Shift-click to select multiple games. Filtering clears selection.').pack(anchor='w')
        controls=ttk.Frame(page);controls.pack(fill='x')
        ttk.Button(controls,text='Use selected game(s) →',command=self.select_game).pack(side='left')
        ttk.Button(controls,text='Select all visible',command=lambda:self.listbox.selection_set(0,'end')).pack(side='left',padx=8)
        ttk.Button(controls,text='Open batch / saved games…',command=self.open_batch).pack(side='left')

    def convert_page(self):
        page=self.pages[2]
        self.selected=tk.StringVar(value='Select a package on step 1, or reopen a previous conversion below.')
        ttk.Label(page,textvariable=self.selected,wraplength=750).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
        self.field(page,'title','Steam library title',1)
        self.field(page,'steam_id','Steam App ID for official art (optional)',2)
        ttk.Label(page,text='Resolution scale (%)').grid(row=3,column=0,sticky='w')
        ttk.Combobox(page,textvariable=self.vars['scale'],values=('50','67','75','85','100','125','150','175','200'),width=12).grid(row=3,column=1,sticky='w',pady=8)
        ttk.Label(page,text='100% = runtime recommendation. Higher values cost GPU performance. Restart to apply.').grid(row=4,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(page,text='Physical-controller compatibility (disable for hand-tracking games)',variable=self.controllers).grid(row=5,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Checkbutton(page,text='Disable unsupported Quest foveation',variable=self.foveation).grid(row=6,column=0,columnspan=2,sticky='w')
        ttk.Button(page,text='Back up Quest game and convert',command=self.convert).grid(row=7,column=0,columnspan=2,sticky='w',pady=12)
        ttk.Button(page,text='Open a previously converted game…',command=self.open_build).grid(row=8,column=0,columnspan=2,sticky='w')
        # Make room beneath the App ID field without shrinking existing controls.
        for widget in page.grid_slaves():
            row = int(widget.grid_info()['row'])
            if row >= 3: widget.grid_configure(row=row+1)
        ttk.Button(page,text='Find artwork',command=self.search_artwork).grid(row=2,column=2,padx=(8,0))
        self.art_matches = ttk.Combobox(page,state='readonly',width=55)
        self.art_matches.grid(row=3,column=0,columnspan=3,sticky='ew',pady=6)
        self.art_matches.set('Artwork candidates appear here — choose one to use its App ID')
        self.art_matches.bind('<<ComboboxSelected>>',self.choose_artwork)
        ttk.Checkbutton(page,text='Search Steam automatically (sends game title to Steam)',variable=self.auto_art).grid(row=10,column=0,columnspan=3,sticky='w',pady=6)

    def install_page(self):
        page=self.pages[3]
        self.storage_picker=StoragePicker(page,self);self.storage_picker.pack(fill='x',pady=(0,8))
        self.ready=tk.StringVar(value='Convert a game first. You will be prompted to switch headsets.')
        ttk.Label(page,textvariable=self.ready,wraplength=740,style='Step.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(page,text='Disconnect Quest. Connect Frame by USB, unlock it, and leave Wi-Fi on.\nThe SSH details from step 0 are used for setup; game files transfer over ADB.').pack(anchor='w')
        ttk.Checkbutton(page,text='Add to Steam with artwork (briefly closes and restarts Steam)',variable=self.add_steam).pack(anchor='w',pady=12)
        ttk.Button(page,text='Install on Frame',command=self.install).pack(anchor='w',pady=5)
        ttk.Button(page,text='Apply resolution / compatibility settings only',command=self.update_settings).pack(anchor='w',pady=5)
        ttk.Button(page,text='Add / repair Steam shortcut only',command=self.repair_shortcut).pack(anchor='w',pady=5)
        ttk.Button(page,text='Open game backups and conversions',command=lambda:os.startfile(ROOT/'games')).pack(anchor='w',pady=5)
        ttk.Label(page,text='Compatibility is game-dependent. DRM, online services, split APKs,\nand private Quest saves may not transfer. Original Quest files are never modified.',wraplength=720).pack(anchor='w',pady=10)

    def credentials(self):
        return {k:self.vars[k].get() for k in ('host','username','password','port')}

    def run_job(self, title, fn, done=None):
        if self.busy: messagebox.showinfo('Working','Wait for the current operation to finish.');return
        self.busy=True;self.status.set(title);self.progress.start()
        def worker():
            try: self.events.put(('done',(fn(),done)))
            except Exception as exc: self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def drain(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':
                    self.logbox.configure(state='normal');self.logbox.insert('end',value+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')
                else:
                    self.busy=False;self.progress.stop()
                    if kind=='error': self.status.set('Needs attention — see details below.');messagebox.showerror('Quest → Frame',value)
                    else:
                        result,done=value;self.status.set('Ready')
                        if done: done(result)
        except queue.Empty: pass
        self.after(100,self.drain)

    def test_ssh(self):
        credentials=self.credentials()
        def work():
            with self.bridge.connect(**credentials) as client:self.bridge.remote(client,'test -x "$HOME/.local/share/Steam/steamapps/common/Lepton/lepton"')
            write_json(APP/'settings.json',{k:v for k,v in credentials.items() if k!='password'})
        self.run_job('Verifying Frame SSH…',work,lambda _:self.status.set('SSH verified. Connect Quest and continue to step 1.'))

    def scan(self):
        def work():
            devices=self.bridge.quests()
            if len(devices)!=1: raise RuntimeError('Connect exactly one Quest and accept USB debugging. Found: '+str(len(devices)))
            return devices[0][0],self.bridge.packages(devices[0][0])
        def done(result):
            self.serial,self.package_list=result;self.filter_packages();self.status.set(f'{len(self.package_list)} installed packages. Select a game.')
        self.run_job('Scanning Quest…',work,done)

    def filter_packages(self):
        query=self.vars['filter'].get().lower();self.listbox.delete(0,'end')
        for package in self.package_list:
            if query in package.lower(): self.listbox.insert('end',package)

    def select_game(self):
        if self.busy:return
        indexes=self.listbox.curselection()
        if not indexes: messagebox.showinfo('Select a game','Choose an installed package first.');return
        if len(indexes)>1:
            self.show_batch([self.listbox.get(i) for i in indexes]);return
        self.package=self.listbox.get(indexes[0]);self.selected.set(self.package)
        self.vars['title'].set('Tetris Effect: Connected (Quest)' if self.package=='com.enhanceexperience.tetriseffect' else '')
        self.vars['steam_id'].set('')
        self.art_candidates=[];self.art_matches.configure(values=[]);self.art_matches.set('No artwork selected')
        self.tabs.select(2)
        if self.auto_art.get():self.search_artwork(query=self.vars['title'].get() or suggested_title(self.package))

    def show_batch(self,packages=(),path=None):
        if self.busy:return
        if getattr(self,'batch_window',None) and self.batch_window.winfo_exists():
            self.batch_window.lift();return
        from batch import BatchWindow
        try:self.batch_window=BatchWindow(self,packages,self.serial,path)
        except Exception as exc:messagebox.showerror('Batch queue',str(exc))

    def open_batch(self):
        if self.busy:return
        path=filedialog.askopenfilename(title='Open saved batch (Cancel to create an empty queue)',initialdir=ROOT/'games/batches',filetypes=[('Batch queue','*.json')])
        self.show_batch(path=path or None)

    def search_artwork(self, query=None):
        if self.busy:return
        query = query or self.vars['title'].get().strip()
        if not query:
            messagebox.showinfo('Artwork search','Enter a game title first.');return
        title_before=self.vars['title'].get();id_before=self.vars['steam_id'].get()
        self.art_candidates=[];self.art_matches.configure(values=[]);self.art_matches.set('Searching Steam…')
        def work():
            try:return artwork_candidates(query),None
            except Exception as exc:return [],str(exc)
        def done(result):
            if self.vars['title'].get()!=title_before or self.vars['steam_id'].get()!=id_before:
                self.art_matches.set('Details changed — click Find artwork to search again');return
            matches,error=result;self.art_candidates=matches
            self.art_matches.configure(values=[f"{m['title']} — App ID {m['id']}" for m in matches])
            if error:
                self.art_matches.set('Search unavailable — retry or enter an App ID manually')
                self.status.set('Artwork search failed; conversion is still available.')
                self.events.put(('log','Artwork search: '+error))
            elif matches:
                self.art_matches.set('Choose a candidate — verify the game and edition')
                self.status.set(f'{len(matches)} artwork candidates found. Choose one or keep your manual App ID.')
            else:
                self.art_matches.set('No matches — edit the title and search again')
                self.status.set('No artwork match. You can continue without artwork.')
        self.run_job('Searching Steam for artwork candidates…',work,done)

    def choose_artwork(self,event=None):
        index=self.art_matches.current()
        if self.busy or not 0<=index<len(self.art_candidates):return
        candidate=self.art_candidates[index]
        self.vars['steam_id'].set(candidate['id'])
        self.status.set('Artwork selected: '+candidate['title'])

    def options(self):
        options = dict(title=self.vars['title'].get(),scale=float(self.vars['scale'].get()),controllers=self.controllers.get(),foveation=self.foveation.get(),steam_id=self.vars['steam_id'].get())
        settings_text(options['scale'], options['controllers'], options['foveation'])
        return options

    def convert(self):
        if not self.serial or not hasattr(self,'package'):messagebox.showinfo('Select a game','Scan and select your Quest game first.');return
        try: options=self.options()
        except ValueError: messagebox.showerror('Invalid scale','Enter a number between 50 and 200.');return
        serial,package=self.serial,self.package
        self.run_job('Backing up and converting. Keep Quest connected…',lambda:self.bridge.convert(self.bridge.backup(serial,package),**options),self.build_ready)

    def build_ready(self,folder):
        self.build=Path(folder);game=json.loads((self.build/'game.json').read_text())
        for k in ('title','scale','steam_id'):self.vars[k].set(str(game[k]))
        self.controllers.set(game['controllers']);self.foveation.set(game['foveation'])
        self.ready.set(game['title']+' is ready. Plug in your Frame.');self.selected.set(game['package']);self.tabs.select(3)
        self.status.set('3 · Conversion ready. Switch from Quest to Frame, then Install.')
        self.art_candidates=[];self.art_matches.configure(values=[]);self.art_matches.set('Click Find artwork to search for this game')
        if self.auto_art.get() and not game.get('steam_id'):
            self.tabs.select(2)
            self.search_artwork(query=game['title'])

    def open_build(self):
        if self.busy:return
        path=filedialog.askopenfilename(title='Open converted game manifest',initialdir=ROOT/'games',filetypes=[('Game manifest','game.json')])
        if path:
            try:self.build_ready(Path(path).parent)
            except Exception as exc:messagebox.showerror('Invalid build',str(exc))

    def install(self):
        if not self.build:messagebox.showinfo('Convert first','Convert or reopen a game first.');return
        try:options=self.options()
        except ValueError:messagebox.showerror('Invalid scale','Enter a number between 50 and 200.');return
        try:storage_id=self.storage_picker.selected_id()
        except ValueError as exc:messagebox.showerror('Storage',str(exc));return
        credentials=self.credentials();folder=self.build;add=self.add_steam.get();art=self.vars['steam_id'].get()
        def work():
            game=json.loads((folder/'game.json').read_text())
            game.update({k:v for k,v in options.items() if k!='title' or v.strip()})
            write_json(folder/'game.json',game)
            with self.bridge.connect(**credentials) as client:return self.bridge.install(folder,client,add,art,storage_id)
        self.run_job('Installing on Frame…',work,lambda _:self.status.set('Installed. Launch the game from your Frame’s Steam library.'))

    def update_settings(self):
        if not self.build: return
        try:opts=self.options()
        except ValueError:messagebox.showerror('Invalid scale','Enter a number between 50 and 200.');return
        credentials=self.credentials();folder=self.build
        def work():
            with self.bridge.connect(**credentials) as client:self.bridge.update_settings(folder,client,opts['scale'],opts['controllers'],opts['foveation'])
        self.run_job('Updating game settings…',work,lambda _:self.status.set('Settings saved. Restart the game on Frame.'))

    def repair_shortcut(self):
        if not self.build:return
        credentials=self.credentials();folder=self.build;art_id=self.vars['steam_id'].get()
        def work():
            game=json.loads((folder/'game.json').read_text())
            deployment=json.loads((folder/'deployment.json').read_text())
            art=self.bridge.artwork(art_id,folder/'artwork') if art_id else {}
            with self.bridge.connect(**credentials) as client:
                self.bridge.add_shortcut(client,deployment.get('anchor',deployment['remote']),game['title'],deployment['appid'],art)
        self.run_job('Updating Steam shortcut…',work,lambda _:self.status.set('Steam shortcut and artwork updated.'))

    def close(self):
        if self.busy:messagebox.showinfo('Operation in progress','Wait for the current transfer/build to finish before closing.');return
        self.destroy()

if __name__=='__main__': Wizard().mainloop()
