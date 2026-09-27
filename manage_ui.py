# SPDX-License-Identifier: GPL-3.0-only
import tkinter as tk
from tkinter import ttk, messagebox

class InstalledGames(tk.Toplevel):
    def __init__(self,wizard):
        super().__init__(wizard);self.wizard=wizard;self.games={}
        self.title('Quest2Frame · Installed games');self.geometry('1100x620');self.minsize(900,500)
        box=ttk.Frame(self,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='On your Frame',style='Title.TLabel').pack(anchor='w')
        ttk.Label(box,text='Manage games installed by Quest2Frame. Uses SSH; no USB required after initial verification.',style='Muted.TLabel').pack(anchor='w',pady=(5,8))
        ttk.Button(box,text='Refresh installed games',command=self.refresh).pack(anchor='w',pady=10)
        table=ttk.Frame(box);table.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(table,columns=('game','location','state'),show='headings',selectmode='browse')
        for name,width in [('game',370),('location',150),('state',350)]:
            self.tree.heading(name,text=name.title());self.tree.column(name,width=width)
        scrollbar=ttk.Scrollbar(table,command=self.tree.yview);scrollbar.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set);self.tree.pack(fill='both',expand=True)
        self.keep=tk.BooleanVar(value=True)
        ttk.Checkbutton(box,text='Preserve saves / Lepton data in a recovery folder (uses space; manual restore)',variable=self.keep).pack(anchor='w',pady=10)
        ttk.Button(box,text='Uninstall selected game…',command=self.uninstall).pack(anchor='w')
        self.message=tk.StringVar(value='Refresh to detect internal and SD-card installations.')
        ttk.Label(box,textvariable=self.message,wraplength=920).pack(anchor='w',pady=10)
        self.protocol('WM_DELETE_WINDOW',self.close)
    def refresh(self):
        if self.wizard.busy:return
        credentials=self.wizard.credentials()
        def work():
            with self.wizard.bridge.connect(**credentials) as client:return self.wizard.bridge.installed_games(client)
        def done(games):
            self.tree.delete(*self.tree.get_children());self.games={}
            for index,game in enumerate(games):
                ident=str(index);self.games[ident]=game
                self.tree.insert('','end',iid=ident,values=(game['package'],'SD / removable' if game.get('storage_uuid') else 'Internal / unknown' if game.get('error') else 'Internal',game.get('error') or 'Installed'))
            self.message.set(f'{len(games)} managed installations found. Missing SD cards must be mounted before uninstalling.')
        self.wizard.run_job('Reading installed Quest2Frame games…',work,done)
    def uninstall(self):
        if self.wizard.busy:return
        selection=self.tree.selection()
        if not selection:return
        game=self.games[selection[0]]
        if game.get('error'):messagebox.showerror('Cannot uninstall',game['error'],parent=self);return
        keep=self.keep.get();package=game['package']
        message=(f'Uninstall {package}?\n\nGame location: {game["base"]}\n\n'
                 'Removes game files, previous app copies, and its Steam shortcut. Steam will restart; finish all active games first.\n\n'+
                 ('Saves and per-game Lepton data will be moved to a recovery folder for manual restoration.' if keep else 'PERMANENTLY DELETE saves and per-game Lepton data, including previous baked snapshots.')+
                 '\n\nQuest originals and PC backups are not changed.')
        if not messagebox.askyesno('Confirm uninstall',message,parent=self,default='no'):return
        credentials=self.wizard.credentials()
        def work():
            with self.wizard.bridge.connect(**credentials) as client:return self.wizard.bridge.uninstall(client,package,keep,game)
        def done(result):
            ident=selection[0];self.tree.delete(ident);self.games.pop(ident,None)
            self.message.set('Uninstalled. '+('Saves retained at '+result['saves'] if result['saves'] else 'No save recovery folder was created.'))
        self.wizard.run_job('Uninstalling '+package+'…',work,done)
    def close(self):
        if self.wizard.busy:return
        self.destroy()
