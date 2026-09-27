# SPDX-License-Identifier: GPL-3.0-only
"""Native icon list with stable index-based selection for the transfer workflow."""
import tkinter as tk
from tkinter import ttk


class GameList(ttk.Treeview):
    def __init__(self,parent):
        super().__init__(parent,show='tree',selectmode='extended',height=4,style='Games.Treeview')
        self.column('#0',stretch=True,width=500,minwidth=200)
        self.images={}
        self.fallback=tk.PhotoImage(master=self,width=48,height=48)
        self.fallback.put('#e0eee9',to=(0,0,48,48))
        self.fallback.put('#147d70',to=(10,14,38,31))
        self.fallback.put('#e0eee9',to=(14,18,34,27))

    def delete(self,first,last=None):
        if first==0 and last=='end':
            children=self.get_children()
            if children:super().delete(*children)
            self.images.clear()
        else:super().delete(first)

    def insert(self,index,text,icon=None):
        image=self.fallback
        if icon:
            try:
                candidate=tk.PhotoImage(master=self,data=icon,format='png')
                if candidate.width()<=96 and candidate.height()<=96:image=candidate
            except tk.TclError:pass
        ident=super().insert('','end',text='  '+text,image=image)
        self.images[ident]=image
        return ident

    def size(self):return len(self.get_children())

    def curselection(self):
        selected=set(self.selection())
        return tuple(i for i,ident in enumerate(self.get_children()) if ident in selected)

    def selection_set(self,first,last=None):
        children=self.get_children()
        if not children:return
        end=len(children)-1 if last=='end' else first if last is None else last
        super().selection_set(children[int(first):int(end)+1])
