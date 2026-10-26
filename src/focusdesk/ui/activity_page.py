"""Persistent activity destination with saved work, schedules and dashboard access."""
import tkinter as tk
from tkinter import ttk
from ..domain.labels import format_seconds, SESSION_STATUS_LABELS
from ..services.activity import activity_ledger
from .common import make_tree


class ActivityPage(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=14)
        self.app=app
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Label(top,text='Activitate',style='Title.TLabel').pack(side='left')
        ttk.Button(top,text='Dashboard lunar',command=app.open_dashboard).pack(side='right')
        self.period=tk.StringVar(value='30 de zile')
        period=ttk.Combobox(top,textvariable=self.period,values=['7 zile','30 de zile','90 de zile','Tot istoricul'],width=15,state='readonly')
        period.pack(side='right',padx=10);period.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        self.summary=ttk.Label(self,style='Section.TLabel');self.summary.pack(fill='x',pady=(12,6))
        ttk.Label(self,text='Lucrat: timpul înregistrat în sesiuni. Programat: durata rezervată, inclusiv pentru sesiuni realizate. Timerul în curs apare în Astăzi.',style='Muted.TLabel',wraplength=800).pack(fill='x',pady=(0,8))
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True)
        self.tables={}
        for title,columns in [('Pe zile',[('date','Zi',150),('worked','Lucrat',120),('planned','Programat',120)]),
                              ('Pe proiecte',[('project','Proiect',220),('worked','Lucrat',120),('planned','Programat',120)]),
                              ('Sesiuni',[('date','Data / ora',140),('task','Task',220),('project','Proiect',180),('status','Stare sesiune',120),('worked','Lucrat',100),('planned','Durată',100)])]:
            tv,wrap=make_tree(self.nb,columns);self.nb.add(wrap,text=title);self.tables[title]=tv;tv.configure(style='Dense.Treeview')
        self.tables['Sesiuni'].bind('<Double-1>',self.open_task)
        self.empty=ttk.Label(self,text='Nu există sesiuni în perioada aleasă. Începe un task din Astăzi sau Proiecte și taskuri.',style='Muted.TLabel')
        self.empty.pack(fill='x',pady=8)
        ttk.Button(self,text='Alege un task',command=lambda:app.show_view('tasks')).pack(anchor='w')
        self._session_nodes={}

    def refresh(self):
        value=self.period.get();days={'7 zile':7,'30 de zile':30,'90 de zile':90}.get(value)
        data=activity_ledger(self.app.ws,days)
        self.summary.configure(text=f"Lucrat înregistrat: {format_seconds(data['worked'])}    ·    Programat: {format_seconds(data['planned'])}")
        for tv in self.tables.values():
            tv._keep=(tv.selection(),tv.yview()[0],tv.xview()[0]);tv.delete(*tv.get_children())
        for day,item in sorted(data['days'].items(),reverse=True):
            self.tables['Pe zile'].insert('', 'end',iid=day.isoformat(),values=(day.strftime('%d.%m.%Y'),format_seconds(item['worked']),format_seconds(item['planned'])))
        for pid,item in sorted(data['projects'].items(),key=lambda r:r[1]['name']):
            self.tables['Pe proiecte'].insert('','end',iid=pid or 'independent',values=(item['name'],format_seconds(item['worked']),format_seconds(item['planned'])))
        self._session_nodes={}
        for s,node,project in data['sessions']:
            self.tables['Sesiuni'].insert('','end',iid=s.id,values=(s.start_at.astimezone(self.app.q.tz()).strftime('%d.%m.%Y %H:%M'),node.title if node else 'Task indisponibil',project,SESSION_STATUS_LABELS[s.status],format_seconds(s.actual_seconds),format_seconds(s.planned_minutes*60)))
            self._session_nodes[s.id]=s.node_id
        for tv in self.tables.values():
            selected,scroll,horizontal=tv._keep
            tv.selection_set([s for s in selected if tv.exists(s)]);tv.yview_moveto(scroll);tv.xview_moveto(horizontal)
        self.empty.configure(text='' if data['sessions'] else 'Nu există sesiuni în perioada aleasă. Alege un task pentru a începe.')

    def open_task(self,event=None):
        selected=self.tables['Sesiuni'].selection()
        if selected:
            nid=self._session_nodes.get(selected[0])
            if nid in self.app.ws.nodes:self.app.select_node(nid,reveal=True)
