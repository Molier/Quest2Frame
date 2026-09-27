# SPDX-License-Identifier: GPL-3.0-only
from tkinter import ttk

class StoragePicker(ttk.Frame):
    def __init__(self, master, wizard):
        super().__init__(master);self.wizard=wizard
        self.choices=[{'id':'internal'}]
        ttk.Label(self,text='Install location:').pack(side='left',padx=(0,8))
        self.combo=ttk.Combobox(self,state='readonly',width=48,values=['Internal storage (refresh for SD cards)'])
        self.combo.current(0);self.combo.pack(side='left',fill='x',expand=True)
        ttk.Button(self,text='Refresh storage',command=self.refresh).pack(side='left',padx=8)
    def selected_id(self):
        index=self.combo.current()
        if not 0<=index<len(self.choices):raise ValueError('Refresh storage and choose a destination')
        return self.choices[index]['id']
    def refresh(self):
        if self.wizard.busy:return
        credentials=self.wizard.credentials()
        try:previous=self.selected_id()
        except ValueError:previous=None
        def work():
            with self.wizard.bridge.connect(**credentials) as client:
                return self.wizard.bridge.storage_locations(client)
        def done(choices):
            self.choices=choices
            self.combo.configure(values=[f"{c['label']} — {c['free']/1024**3:.1f} GiB free"+(f" — {c['mount']}" if c['uuid'] else '') for c in choices])
            match=next((i for i,c in enumerate(choices) if c['id']==previous),None)
            if match is None:
                self.combo.set('Previous destination missing — choose storage')
            else:self.combo.current(match)
            self.wizard.status.set('Storage refreshed. SD cards must be mounted, writable ext4/btrfs (not noexec).')
        self.wizard.run_job('Detecting Frame storage…',work,done)
