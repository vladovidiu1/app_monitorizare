"""A native notebook with a full-label keyboard selector when tabs do not fit."""
from tkinter import ttk, StringVar
import tkinter.font as tkfont
from ..i18n import tr
from .design import px


class AdaptiveNotebook(ttk.Notebook):
    def __init__(self,parent,**options):
        super().__init__(parent,**options)
        self._normal_style=options.get('style','TNotebook')
        self._compact_style='Compact.'+self._normal_style
        ttk.Style(self).layout(self._compact_style+'.Tab',[])
        self.selector=ttk.Frame(parent)
        ttk.Label(self.selector,text=tr('nav.section')).pack(side='left',padx=(0,6))
        self.selection_label=StringVar(master=self)
        self.section_box=ttk.Combobox(self.selector,textvariable=self.selection_label,state='readonly',width=15)
        self.section_box.pack(side='left',fill='x',expand=True)
        self.section_box.bind('<<ComboboxSelected>>',self._choose)
        self.bind('<Configure>',self._adapt,add='+')
        self.bind('<Map>',self._adapt,add='+')
        self.bind('<Unmap>',self._hide_selector,add='+')
        self.bind('<<NotebookTabChanged>>',self._sync,add='+')
        self._compact=False

    def _hide_selector(self,event=None):
        self.selector.pack_forget()
        self._compact=False
        if self.cget('style') != self._normal_style:self.configure(style=self._normal_style)

    def _ids(self):
        return [tab for tab in self.tabs() if self.tab(tab,'state')!='hidden']

    def _sync(self,event=None):
        ids=self._ids()
        self.section_box.configure(values=[self.tab(tab,'text') for tab in ids])
        selected=self.select()
        if selected:self.selection_label.set(self.tab(selected,'text'))

    def _choose(self,event=None):
        ids=self._ids();index=self.section_box.current()
        if 0<=index<len(ids):self.select(ids[index])

    def _adapt(self,event=None):
        if not self.winfo_ismapped() or self.winfo_manager()!='pack':
            self._hide_selector();return
        style=ttk.Style(self)
        font=tkfont.Font(self,font=style.lookup(self._normal_style+'.Tab','font') or 'TkDefaultFont')
        needed=sum(font.measure(self.tab(tab,'text'))+px(self,24) for tab in self._ids())
        compact=self.winfo_width()<needed
        if compact!=self._compact:
            self._compact=compact
            if compact:
                self.selector.pack(fill='x',padx=6,pady=0,before=self)
                self.configure(style=self._compact_style)
            else:
                self.selector.pack_forget();self.configure(style=self._normal_style)
        self._sync()
