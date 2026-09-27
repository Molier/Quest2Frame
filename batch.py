# SPDX-License-Identifier: GPL-3.0-only
"""Sequential, resumable multi-game work; no concurrent OVR Port workspaces."""
import json
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from bridge import ROOT, write_json, settings_text, valid_package, artwork_candidates
from storage_ui import StoragePicker

def run_batch(items, action, bridge, serial, credentials, add_steam, save, auto_art=False, storage_id='internal'):
    for index, item in enumerate(items, 1):
        bridge.log(f'Batch {index}/{len(items)}: {item["package"]} — {action}')
        item['error']=''
        try:
            item['status']='Working';save()
            if action=='convert':
                backup=item.get('backup')
                if not backup:
                    backup=str(bridge.backup(serial,item['package']))
                    item['backup']=backup;save()
                # Successful builds are reused, not reconverted on retry.
                if not item.get('build'):
                    item['build']=str(bridge.convert(backup,**item['options']))
                item['status']='Ready'
                if auto_art and not item['options']['steam_id']:
                    try:
                        game=json.loads((Path(item['build'])/'game.json').read_text())
                        item['candidates']=artwork_candidates(game['title'])
                        if not item['options']['title']:item['options']['title']=game['title']
                    except Exception as exc:bridge.log('Artwork search unavailable: '+str(exc))
            else:
                folder=Path(item['build'])
                game=json.loads((folder/'game.json').read_text())
                if game['package']!=item['package']:raise ValueError('Build/package mismatch')
                game.update({k:v for k,v in item['options'].items() if k!='title' or v.strip()})
                write_json(folder/'game.json',game)
                with bridge.connect(**credentials) as client:
                    bridge.install(folder,client,add_steam,item['options']['steam_id'],storage_id)
                item['status']='Installed'
        except Exception as exc:
            item['status']='Failed';item['error']=str(exc)
            bridge.log(f'FAILED {item["package"]}: {exc}')
        save()
    return items

class BatchWindow(tk.Toplevel):
    def __init__(self, parent, packages=(), serial=None, path=None):
        super().__init__(parent);self.parent=parent;self.serial=serial
        self.title('Quest → Frame — batch queue');self.geometry('1050x800');self.minsize(850,740)
        self.path=Path(path) if path else ROOT/'games/batches'/f'{uuid.uuid4().hex}.json'
        defaults=parent.options();self.items=[];self.active=None
        if path:
            data=json.loads(self.path.read_text());self.items=data['items'];self.serial=data.get('serial')
            for item in self.items:
                valid_package(item['package']);settings_text(item['options']['scale'])
                if item['status']=='Working':item['status']='Interrupted'
        else:
            for package in packages:
                opts=dict(defaults,title='',steam_id='')
                self.items.append(dict(package=package,options=opts,status='Queued',error='',backup='',build=''))
        box=ttk.Frame(self,padding=16);box.pack(fill='both',expand=True)
        ttk.Label(box,text='1. Configure games → 2. Back up & convert → 3. Switch to Frame → 4. Install',font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(box,text='Ctrl/Shift selects multiple rows. Settings below apply only to the highlighted editor game.').pack(anchor='w',pady=5)
        self.tree=ttk.Treeview(box,columns=('package','status'),show='headings',selectmode='extended',height=8)
        self.tree.heading('package',text='Quest package');self.tree.heading('status',text='Status')
        self.tree.column('package',width=630);self.tree.column('status',width=150)
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.selected)
        ttk.Button(box,text='Select all games',command=lambda:self.tree.selection_set(self.tree.get_children())).pack(anchor='w',pady=5)
        form=ttk.LabelFrame(box,text='Per-game settings — Save before switching games',padding=10);form.pack(fill='x')
        self.editing=tk.StringVar(value='Select a game to edit');ttk.Label(form,textvariable=self.editing).grid(row=0,column=0,columnspan=4,sticky='w')
        self.values={name:tk.StringVar() for name in ('title','scale','steam_id')}
        for row,(name,label) in enumerate((('title','Title (blank = APK title)'),('scale','Resolution 50–200%'),('steam_id','Steam artwork App ID')),1):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=5)
            ttk.Entry(form,textvariable=self.values[name],width=45).grid(row=row,column=1,sticky='ew',pady=3)
        form.columnconfigure(1,weight=1)
        self.controllers=tk.BooleanVar();self.foveation=tk.BooleanVar()
        ttk.Checkbutton(form,text='Physical controllers',variable=self.controllers).grid(row=1,column=2,padx=10)
        ttk.Checkbutton(form,text='Quest foveation fix',variable=self.foveation).grid(row=2,column=2,padx=10)
        ttk.Button(form,text='Save game settings',command=self.save_editor).grid(row=3,column=2,padx=10)
        ttk.Button(form,text='Find artwork by title',command=self.search_art).grid(row=4,column=0,pady=5)
        self.matches=ttk.Combobox(form,state='readonly',width=50);self.matches.grid(row=4,column=1,columnspan=2,sticky='ew')
        self.candidates=[];self.matches.bind('<<ComboboxSelected>>',self.choose_art)
        self.add_steam=tk.BooleanVar(value=parent.add_steam.get())
        self.storage_picker=StoragePicker(box,parent);self.storage_picker.pack(fill='x',pady=8)
        ttk.Checkbutton(box,text='Add each installed game to Steam (Steam restarts for each game)',variable=self.add_steam).pack(anchor='w',pady=8)
        buttons=ttk.Frame(box);buttons.pack(fill='x')
        ttk.Button(buttons,text='Back up & convert selected',command=lambda:self.start('convert')).pack(side='left',padx=3)
        ttk.Button(buttons,text='Install selected ready games',command=lambda:self.start('install')).pack(side='left',padx=3)
        ttk.Button(buttons,text='Add saved conversions…',command=self.add_builds).pack(side='left',padx=3)
        self.message=tk.StringVar(value='Keep Quest connected throughout the conversion batch.')
        ttk.Label(box,textvariable=self.message,wraplength=980).pack(anchor='w',pady=8)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();self.tree.selection_set(self.tree.get_children());self.save();self.poll_id=self.after(250,self.poll)

    def save(self):write_json(self.path,dict(serial=self.serial,items=self.items))
    def refresh(self):
        for index,item in enumerate(self.items):
            ident=str(index);values=(item['package'],item['status'])
            if self.tree.exists(ident):self.tree.item(ident,values=values)
            else:self.tree.insert('', 'end',iid=ident,values=values)
    def poll(self):self.refresh();self.poll_id=self.after(250,self.poll)
    def selected(self,event=None):
        if self.parent.busy:return
        selection=self.tree.selection()
        if not selection:return
        focus=self.tree.focus();ident=focus if focus in selection else selection[0]
        self.active=int(ident);item=self.items[self.active]
        self.editing.set(item['package'])
        for k,v in self.values.items():v.set(str(item['options'][k]))
        self.controllers.set(item['options']['controllers']);self.foveation.set(item['options']['foveation'])
        self.candidates=item.get('candidates',[])
        self.matches.configure(values=[f"{m['title']} — {m['id']}" for m in self.candidates])
        self.matches.set('Choose a candidate and Save' if self.candidates else 'Enter a title to search for artwork')
        self.message.set(item['error'] or item['status'])
    def save_editor(self):
        if self.parent.busy or self.active is None:return False
        try:
            opts={k:v.get().strip() for k,v in self.values.items()};opts['scale']=float(opts['scale'])
            settings_text(opts['scale'])
            if opts['steam_id'] and not opts['steam_id'].isdigit():raise ValueError('Steam App ID must be numeric')
            opts.update(controllers=self.controllers.get(),foveation=self.foveation.get())
        except ValueError as exc:messagebox.showerror('Invalid settings',str(exc),parent=self);return False
        self.items[self.active]['options']=opts;self.save();return True
    def search_art(self):
        if not self.save_editor():return
        title=self.values['title'].get().strip()
        if not title:self.message.set('Enter a title to search. Blank titles use APK labels during conversion.');return
        active=self.active
        def work():
            try:return artwork_candidates(title),None
            except Exception as exc:return [],str(exc)
        def done(result):
            matches,error=result
            if active!=self.active:return
            self.candidates=matches;self.matches.configure(values=[f"{m['title']} — {m['id']}" for m in matches])
            self.matches.set('Choose the matching edition' if matches else 'No matches')
            self.message.set(error or 'Choose a candidate, then Save game settings.')
        self.parent.run_job('Searching Steam artwork…',work,done)
    def choose_art(self,event=None):
        index=self.matches.current()
        if not self.parent.busy and 0<=index<len(self.candidates):self.values['steam_id'].set(self.candidates[index]['id'])
    def add_builds(self):
        if self.parent.busy:return
        paths=filedialog.askopenfilenames(parent=self,title='Select saved game manifests',initialdir=ROOT/'games',filetypes=[('Game manifests','game.json')])
        for path in paths:
            try:
                game=json.loads(Path(path).read_text());package=valid_package(game['package'])
                if any(i['package']==package for i in self.items):continue
                self.items.append(dict(package=package,options={k:game[k] for k in ('title','scale','steam_id','controllers','foveation')},build=str(Path(path).parent),backup=game['backup'],status='Ready',error=''))
            except Exception as exc:messagebox.showerror('Invalid manifest',str(exc),parent=self)
        self.refresh();self.save()
    def start(self,action):
        if self.parent.busy:return
        if self.active is not None and not self.save_editor():return
        items=[self.items[int(i)] for i in self.tree.selection()]
        items=[i for i in items if (not i.get('build') if action=='convert' else i.get('build') and i['status']!='Installed')]
        if not items:self.message.set('Select unconverted games or ready builds; completed items are skipped.');return
        credentials=self.parent.credentials();add=self.add_steam.get();auto_art=self.parent.auto_art.get()
        try:storage_id=self.storage_picker.selected_id()
        except ValueError as exc:messagebox.showerror('Storage',str(exc),parent=self);return
        def work():
            if action=='convert':
                if self.serial not in [s for s,_ in self.parent.bridge.quests()]:raise RuntimeError('Reconnect the original Quest and allow USB debugging.')
            return run_batch(items,action,self.parent.bridge,self.serial,credentials,add,self.save,auto_art,storage_id)
        def done(result):
            failed=sum(i['status']=='Failed' for i in result)
            self.refresh();self.selected()
            self.message.set(f'Batch finished: {len(result)-failed} completed, {failed} failed. '+('Switch to Frame, select ready games, then Install.' if action=='convert' else 'See the log for details.'))
        self.parent.run_job(f'Batch {action}: {len(items)} games. Keep the headset connected…',work,done)
    def close(self):
        if self.parent.busy:messagebox.showinfo('Working','Wait for the batch to finish.',parent=self);return
        if self.active is not None and not self.save_editor():return
        self.after_cancel(self.poll_id)
        self.destroy()
