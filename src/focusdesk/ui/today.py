"""Compact persistent daily cockpit; timer controls reflect real timer state."""
from datetime import date
from tkinter import ttk
from ..domain.labels import STATUS_LABELS, format_seconds, session_status_text
from .common import ScrollFrame, SessionButton, make_tree
from .dialogs import NodePickerDialog
from .design import C, icon
from .formats import format_date

_DAYS=['luni','marți','miercuri','joi','vineri','sâmbătă','duminică']
_MONTHS=['ianuarie','februarie','martie','aprilie','mai','iunie','iulie','august','septembrie','octombrie','noiembrie','decembrie']
def long_date(day:date):
    return f'{_DAYS[day.weekday()].capitalize()}, {day.day} {_MONTHS[day.month-1]} {day.year}'


class TodayPage(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app
        self.sf=ScrollFrame(self);self.sf.pack(fill='both',expand=True)
        f=self.sf.inner;f.configure(style='Page.TFrame');self.sf.canvas.configure(background=C.canvas)
        self.heading=ttk.Label(f,text='Astăzi',style='Page.Title.TLabel');self.heading.pack(anchor='w',padx=16,pady=(14,2))
        self.day_label=ttk.Label(f,style='Page.Muted.TLabel');self.day_label.pack(anchor='w',padx=16)
        active=ttk.Frame(f,padding=10);active.pack(fill='x',padx=16,pady=10)
        self.timer_label=ttk.Label(active,style='Section.TLabel',wraplength=700);self.timer_label.pack(anchor='w')
        actions=ttk.Frame(active);actions.pack(fill='x',pady=(6,0));self.timer_actions=actions
        self.timer_toggle=ttk.Button(actions,command=app.toggle_pause);self.timer_toggle.pack(side='left')
        self.stop_btn=ttk.Button(actions,text='Încheie sesiunea…',image=icon(self,'stop'),compound='left',command=app.stop_session);self.stop_btn.pack(side='left',padx=6)
        self.open_timer=ttk.Button(actions,text='Deschide taskul activ',command=app.resume_work);self.open_timer.pack(side='left')
        row=ttk.Frame(f,style='Page.TFrame');row.pack(fill='x',padx=16,pady=(6,4))
        self.priorities_label=ttk.Label(row,text='Prioritățile zilei',style='Section.TLabel');self.priorities_label.pack(side='left')
        ttk.Button(row,text='Alege priorități…',command=self._pick_priority).pack(side='right')
        self.priorities,pwrap=make_tree(f,[('title','Task',240),('status','Status',120),('due','Termen',100),('next','Următorul pas',300)],show_tree=True,height=3)
        self.priorities.configure(style='Dense.Treeview')
        self.priorities.column('#0',width=28,minwidth=28,stretch=False)
        pwrap.pack(fill='x',padx=16)
        self.priorities.bind('<<TreeviewSelect>>',lambda e:self.update_timer())
        self.priorities.bind('<Double-1>',lambda e:self._open(self.priorities))
        self.priority_empty=ttk.Label(f,style='Page.Muted.TLabel');self.priority_empty.pack(fill='x',padx=16)
        pbuttons=ttk.Frame(f,style='Page.TFrame');pbuttons.pack(fill='x',padx=16,pady=4)
        self.priority_start=SessionButton(pbuttons,app,lambda:self._selected(self.priorities));self.priority_start.pack(side='left')
        ttk.Button(pbuttons,text='Deschide',command=lambda:self._open(self.priorities)).pack(side='left',padx=6)
        ttk.Button(pbuttons,text='Scoate din priorități',command=self._unpin).pack(side='left')
        ttk.Label(f,text='Rezervări și lucru azi',style='Section.TLabel').pack(anchor='w',padx=16,pady=(12,4))
        self.sessions,swrap=make_tree(f,[('time','Interval',120),('title','Task',300),('status','Stare rezervare / lucru',120)],show_tree=True,height=5)
        self.sessions.configure(style='Dense.Treeview')
        self.sessions.column('#0',width=28,minwidth=28,stretch=False)
        swrap.pack(fill='x',padx=16)
        self.sessions.bind('<Double-1>',lambda e:self._open_session())
        self.sessions.bind('<<TreeviewSelect>>',lambda e:self.update_timer())
        self.session_empty=ttk.Label(f,style='Page.Muted.TLabel');self.session_empty.pack(fill='x',padx=16)
        sbuttons=ttk.Frame(f,style='Page.TFrame');sbuttons.pack(fill='x',padx=16,pady=4)
        self.start_session_btn=ttk.Button(sbuttons,text='Începe rezervarea selectată',command=self._start_planned);self.start_session_btn.pack(side='left')
        ttk.Button(sbuttons,text='Deschide Calendar',command=lambda:app.show_view('calendar')).pack(side='left',padx=6)
        self.overdue_btn=ttk.Button(f,command=lambda:app.quick_tasks('overdue'));self.overdue_btn.pack(anchor='w',padx=16,pady=(12,10))
        ttk.Button(f,text='Toate proiectele și taskurile',command=lambda:app.show_view('tasks')).pack(anchor='w',padx=16,pady=(0,12))
        self._session_nodes={};self._planned_ids=set()

    def _selected(self,tv):
        selected=tv.selection();return selected[0] if selected else None

    def _open(self,tv):
        nid=self._selected(tv)
        if nid:self.app.select_node(nid,reveal=True)

    def _open_session(self):
        nid=self._session_nodes.get(self._selected(self.sessions))
        if nid:self.app.select_node(nid,reveal=True)

    def _unpin(self):
        nid=self._selected(self.priorities)
        if nid:self.app.set_pinned(nid,False)

    def _start_planned(self):
        sid=self._selected(self.sessions);nid=self._session_nodes.get(sid)
        if nid and sid in self._planned_ids:self.app.start_session(nid,sid)

    def refresh(self):
        from .status_visuals import node_icon
        app=self.app;q=app.q;self.day_label.configure(text=long_date(q.today()))
        scroll=self.sf.canvas.yview()[0]
        selected=self.priorities.selection();self.priorities.delete(*self.priorities.get_children())
        nodes=q.pinned_today()
        self.priorities.configure(height=max(1,min(3,len(nodes))))
        self.priorities_label.configure(text=f'Prioritățile zilei · {len(nodes)}/{app.ws.settings.max_today_priorities}')
        for n in nodes:self.priorities.insert('','end',iid=n.id,image=node_icon(self,n),values=(n.title,STATUS_LABELS[n.status],format_date(q.due_day(n)),n.next_action or 'Adaugă următorul pas în Detalii'))
        keep=[s for s in selected if self.priorities.exists(s)]
        if keep or nodes:self.priorities.selection_set(keep or nodes[0].id)
        self.priority_empty.configure(text='' if nodes else 'Nicio prioritate aleasă. Folosește „Alege priorități…” sau deschide lista de taskuri.')
        selected=self.sessions.selection();self.sessions.delete(*self.sessions.get_children());self._session_nodes={};self._planned_ids=set()
        planned=q.sessions_on(q.today())
        self.sessions.configure(height=max(1,min(6,len(planned))))
        for s in planned:
            n=app.ws.nodes.get(s.node_id)
            if not n:continue
            self._session_nodes[s.id]=n.id
            if s.status=='planned':self._planned_ids.add(s.id)
            self.sessions.insert('','end',iid=s.id,image=node_icon(self,n),values=(f'{s.start_at.astimezone(q.tz()):%H:%M}–{s.end_at.astimezone(q.tz()):%H:%M}',n.title,session_status_text(s,app.timer)))
        keep=[s for s in selected if self.sessions.exists(s)]
        if keep or self._session_nodes:self.sessions.selection_set(keep or next(iter(self._session_nodes)))
        self.session_empty.configure(text='' if planned else 'Nicio rezervare azi. Programează timp din Calendar.')
        self.overdue_btn.configure(text=f'{len(q.view_overdue())} taskuri restante · vezi și filtrează')
        self.update_timer();self.sf.canvas.yview_moveto(scroll)

    def update_timer(self):
        app=self.app;t=app.timer
        active=bool(t and t.active)
        if active:
            self.timer_actions.pack(fill='x',pady=(6,0))
            n=app.ws.nodes.get(t.node_id)
            self.timer_label.configure(text=f'{"În lucru" if t.running else "În pauză"} · {n.title if n else "Task"} · {format_seconds(t.seconds)}')
        else:
            self.timer_actions.pack_forget()
            self.timer_label.configure(text='Nicio sesiune de lucru pornită. Alege o prioritate și apasă Începe.')
        self.timer_toggle.configure(image=icon(self,'pause' if active and t.running else 'play'),compound='left',text='Pauză' if active and t.running else 'Continuă',state='normal' if active and not t.recovered else 'disabled')
        self.stop_btn.configure(state='normal' if active and not t.recovered else 'disabled')
        self.open_timer.configure(state='normal' if active else 'disabled')
        self.start_session_btn.configure(state='disabled' if self._selected(self.sessions) not in self._planned_ids or app.ws.read_only else 'normal')
        self.priority_start.update_state()

    def _pick_priority(self):
        ws=self.app.ws
        if ws.read_only:return
        picked=NodePickerDialog(self,ws,'Alege prioritate pentru azi',exclude={n.id for n in self.app.q.pinned_today()},only_tasks=True).run()
        if picked:self.app.set_pinned(picked,True)
