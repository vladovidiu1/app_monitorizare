"""Persistent timer controls and explicit time reconciliation, entirely on Tk's thread."""
from datetime import datetime
from tkinter import ttk
import tkinter as tk
from .common import ModalDialog, show_error, ask_string
from ..domain.labels import format_seconds
from ..domain.timeutil import local_to_utc


def parse_local_stamp(text, tz):
    """Reject ambiguous/nonexistent local times; allow explicit ISO offsets for DST."""
    value=datetime.fromisoformat(text.strip())
    if value.tzinfo is not None:return value
    return local_to_utc(value.date(),value.time(),tz)


class TimerIndicator(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(3,0));self.app=app
        self.columnconfigure(0,weight=1)
        self.label=ttk.Label(self,text='Nicio sesiune de lucru pornită',style='Section.TLabel',width=36)
        self.label.grid(row=0,column=0,sticky='ew')
        controls=ttk.Frame(self);controls.grid(row=0,column=1,sticky='e')
        self.pause=ttk.Button(controls,text='Pauză',command=app.toggle_pause);self.pause.pack(side='left')
        self.stop=ttk.Button(controls,text='Încheie',command=app.stop_session);self.stop.pack(side='left',padx=6)
        self.open=ttk.Button(controls,text='Deschide taskul',command=self.open_task);self.open.pack(side='left')
        self.recover=ttk.Button(controls,text='Recuperează…',command=app._handle_recovered_timer)
        ttk.Button(controls,text='Avertizare…',style='Quiet.TButton',command=self.configure_warning).pack(side='left',padx=6)
        from .common import Tooltip
        self.tip=Tooltip(self.label,'')

    def open_task(self):
        t=self.app.timer
        if t and t.node_id in self.app.ws.nodes:self.app.select_node(t.node_id,reveal=True)

    def configure_warning(self):
        value=ask_string(self,'Avertizare sesiune lungă','După câte minute de lucru? 0 dezactivează.',str(self.app.config.long_session_minutes),'Aplică')
        if value is None:return
        try:
            minutes=int(value)
            if minutes<0:raise ValueError()
        except ValueError:
            show_error(self,'Introdu un număr de minute pozitiv sau zero.');return
        self.app.config.long_session_minutes=minutes;self.app.config.save()

    def update_state(self):
        t=self.app.timer;st=t.state if t else None
        writable=bool(self.app.ws and not self.app.ws.read_only)
        current=bool(st and not t.recovered)
        if st:
            node=self.app.ws.nodes.get(st.node_id)
            state='Încheiere de recuperat' if st.finalization else ('În lucru' if t.running else 'În pauză')
            if t.recovered:state='Sesiune de recuperat · ultima stare: '+('În pauză' if st.state=='paused' else 'În lucru')
            started=st.started_at.astimezone(self.app.q.tz()).strftime('%d.%m %H:%M')
            limit=self.app.config.long_session_minutes
            warning=' · ⚠ Sesiune lungă — verifică timpul' if limit and t.seconds>=limit*60 else ''
            title=node.title if node else 'Task indisponibil'
            self.label.configure(text=f'{state} · {format_seconds(t.seconds)}' + (' · ⚠' if warning else '') + '\n' + title[:24] + ' · ' + started[-5:])
            detail=f'{state} · {title} · {format_seconds(t.seconds)} · început {started}{warning}'
        else:self.label.configure(text='Timer salvat nevalid — verifică fișierul' if t and t.recovery_error else 'Nicio sesiune de lucru pornită')
        self.tip.text=detail if st else self.label.cget('text')
        if st:
            for button in (self.pause,self.stop,self.open):button.pack(side='left',padx=2)
        else:
            for button in (self.pause,self.stop,self.open):button.pack_forget()
        self.pause.configure(text='Pauză' if t and t.running else 'Continuă',state='normal' if current and writable and not st.finalization else 'disabled')
        self.stop.configure(state='normal' if current and writable else 'disabled')
        self.open.configure(state='normal' if st and st.node_id in self.app.ws.nodes else 'disabled')
        if t and t.recovered:
            self.recover.pack(side='left',padx=6);self.recover.configure(state='normal' if writable else 'disabled')
        else:self.recover.pack_forget()


class CorrectTimeDialog(ModalDialog):
    def __init__(self,parent,app,session):
        super().__init__(parent,'Corectează timpul',resizable=True,ok_text='Salvează corecția')
        self.app=app;self.session=session
        ttk.Label(self.body,text='Se corectează munca efectivă; rezervarea programată rămâne neschimbată.',wraplength=520).pack(fill='x')
        self.seconds=tk.StringVar(value=str(session.actual_seconds))
        self.start=tk.StringVar(value=session.started_actual_at.astimezone(app.q.tz()).isoformat(timespec='seconds') if session.started_actual_at else '')
        self.end=tk.StringVar(value=session.stopped_actual_at.astimezone(app.q.tz()).isoformat(timespec='seconds') if session.stopped_actual_at else '')
        self.reason=tk.StringVar()
        for text,var in [('Durată efectivă (secunde)',self.seconds),('Început efectiv (ISO, opțional)',self.start),('Sfârșit efectiv (ISO, opțional)',self.end),('Motiv (opțional)',self.reason)]:
            ttk.Label(self.body,text=text).pack(anchor='w',pady=(8,0));ttk.Entry(self.body,textvariable=var,width=58).pack(fill='x')
        ttk.Label(self.body,text='Pentru ora repetată la schimbarea orei, păstrează offsetul explicit (+02:00 / +03:00).',wraplength=520,style='Muted.TLabel').pack(fill='x',pady=8)

    def collect(self):
        try:
            if self.app.ws.read_only:raise ValueError('Workspace doar pentru citire.')
            kwargs={}
            if bool(self.start.get().strip()) != bool(self.end.get().strip()):raise ValueError('Completează ambele capete ale intervalului.')
            if self.start.get().strip():
                kwargs=dict(started_at=parse_local_stamp(self.start.get(),self.app.ws.settings.timezone),stopped_at=parse_local_stamp(self.end.get(),self.app.ws.settings.timezone))
            self.app.sessions.correct_time(self.session.id,int(self.seconds.get()),reason=self.reason.get(),expected=self.session,**kwargs)
            self.app.on_sessions_changed()
            return True
        except Exception as exc:show_error(self,str(exc));return False


def correct_selected(parent,app,session):
    if session is None or session.status!='done':
        show_error(parent,'Selectează o sesiune încheiată.');return
    if app.ws.read_only:
        show_error(parent,'Workspace doar pentru citire.');return
    CorrectTimeDialog(parent,app,session).run()
