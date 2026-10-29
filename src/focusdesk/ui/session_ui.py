"""Persistent timer controls and explicit time reconciliation, entirely on Tk's thread."""

from ..i18n import short_datetime_text

from ..i18n import tr
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
        self.label=ttk.Label(self,text=tr('ui.session_ui.nicio_sesiune_de_lucru_pornita'),style='Section.TLabel',width=36)
        self.label.grid(row=0,column=0,sticky='ew')
        controls=ttk.Frame(self);controls.grid(row=0,column=1,sticky='e')
        self.pause=ttk.Button(controls,text=tr('ui.session_ui.pauza'),command=app.toggle_pause);self.pause.pack(side='left')
        self.stop=ttk.Button(controls,text=tr('ui.session_ui.incheie'),command=app.stop_session);self.stop.pack(side='left',padx=6)
        self.open=ttk.Button(controls,text=tr('ui.session_ui.deschide_taskul'),command=self.open_task);self.open.pack(side='left')
        self.recover=ttk.Button(controls,text=tr('ui.session_ui.recupereaza'),command=app._handle_recovered_timer)
        ttk.Button(controls,text=tr('common.warning'),style='Quiet.TButton',command=self.configure_warning).pack(side='left',padx=6)
        from .common import Tooltip
        self.tip=Tooltip(self.label,'')

    def open_task(self):
        t=self.app.timer
        if t and t.node_id in self.app.ws.nodes:self.app.select_node(t.node_id,reveal=True)

    def configure_warning(self):
        value=ask_string(self,tr('ui.session_ui.avertizare_sesiune_lunga'),tr('ui.session_ui.dupa_cate_minute_de_lucru_0_dezactiveaza'),str(self.app.config.long_session_minutes),tr('ui.session_ui.aplica'))
        if value is None:return
        try:
            minutes=int(value)
            if minutes<0:raise ValueError()
        except ValueError:
            show_error(self,tr('ui.session_ui.introdu_un_numar_de_minute_pozitiv_sau_zero'));return
        self.app.config.long_session_minutes=minutes;self.app.config.save()

    def update_state(self):
        t=self.app.timer;st=t.state if t else None
        writable=bool(self.app.ws and not self.app.ws.read_only)
        current=bool(st and not t.recovered)
        if st:
            node=self.app.ws.nodes.get(st.node_id)
            state=tr('ui.session_ui.incheiere_de_recuperat') if st.finalization else (tr('ui.session_ui.in_lucru') if t.running else tr('ui.session_ui.in_pauza'))
            if t.recovered:state=tr('ui.session_ui.sesiune_de_recuperat_ultima_stare')+(tr('ui.session_ui.in_pauza') if st.state=='paused' else tr('ui.session_ui.in_lucru'))
            started=short_datetime_text(st.started_at.astimezone(self.app.q.tz()))
            limit=self.app.config.long_session_minutes
            warning=tr('ui.session_ui.sesiune_lunga_verifica_timpul') if limit and t.seconds>=limit*60 else ''
            title=node.title if node else tr('ui.meetings.task_indisponibil')
            self.label.configure(text=tr('ui.session_ui.state_duration', state=state, format_seconds_t_seconds=format_seconds(t.seconds)) + (' · ⚠' if warning else '') + '\n' + title[:24] + ' · ' + started[-5:])
            detail=tr('ui.session_ui.inceput', state=state, title=title, format_seconds_t_seconds=format_seconds(t.seconds), started=started, warning=warning)
        else:self.label.configure(text=tr('ui.session_ui.timer_salvat_nevalid_verifica_fisierul') if t and t.recovery_error else tr('ui.session_ui.nicio_sesiune_de_lucru_pornita'))
        self.tip.text=detail if st else self.label.cget('text')
        if st:
            for button in (self.pause,self.stop,self.open):button.pack(side='left',padx=2)
        else:
            for button in (self.pause,self.stop,self.open):button.pack_forget()
        self.pause.configure(text=tr('ui.session_ui.pauza') if t and t.running else tr('ui.session_ui.continua'),state='normal' if current and writable and not st.finalization else 'disabled')
        self.stop.configure(state='normal' if current and writable else 'disabled')
        self.open.configure(state='normal' if st and st.node_id in self.app.ws.nodes else 'disabled')
        if t and t.recovered:
            self.recover.pack(side='left',padx=6);self.recover.configure(state='normal' if writable else 'disabled')
        else:self.recover.pack_forget()


class CorrectTimeDialog(ModalDialog):
    def __init__(self,parent,app,session):
        super().__init__(parent,tr('ui.session_ui.corecteaza_timpul'),resizable=True,ok_text=tr('ui.session_ui.salveaza_corectia'))
        self.app=app;self.session=session
        ttk.Label(self.body,text=tr('ui.session_ui.se_corecteaza_munca_efectiva_rezervarea_programata_ramane_neschimbata'),wraplength=520).pack(fill='x')
        self.seconds=tk.StringVar(value=str(session.actual_seconds))
        self.start=tk.StringVar(value=session.started_actual_at.astimezone(app.q.tz()).isoformat(timespec='seconds') if session.started_actual_at else '')
        self.end=tk.StringVar(value=session.stopped_actual_at.astimezone(app.q.tz()).isoformat(timespec='seconds') if session.stopped_actual_at else '')
        self.reason=tk.StringVar()
        for text,var in [(tr('ui.session_ui.durata_efectiva_secunde'),self.seconds),(tr('ui.session_ui.inceput_efectiv_iso_optional'),self.start),(tr('ui.session_ui.sfarsit_efectiv_iso_optional'),self.end),(tr('ui.session_ui.motiv_optional'),self.reason)]:
            ttk.Label(self.body,text=text).pack(anchor='w',pady=(8,0));ttk.Entry(self.body,textvariable=var,width=58).pack(fill='x')
        ttk.Label(self.body,text=tr('ui.session_ui.pentru_ora_repetata_la_schimbarea_orei_pastreaza_offsetul_explicit_02'),wraplength=520,style='Muted.TLabel').pack(fill='x',pady=8)

    def collect(self):
        try:
            if self.app.ws.read_only:raise ValueError(tr('ui.session_ui.workspace_doar_pentru_citire'))
            kwargs={}
            if bool(self.start.get().strip()) != bool(self.end.get().strip()):raise ValueError(tr('ui.session_ui.completeaza_ambele_capete_ale_intervalului'))
            if self.start.get().strip():
                kwargs=dict(started_at=parse_local_stamp(self.start.get(),self.app.ws.settings.timezone),stopped_at=parse_local_stamp(self.end.get(),self.app.ws.settings.timezone))
            self.app.sessions.correct_time(self.session.id,int(self.seconds.get()),reason=self.reason.get(),expected=self.session,**kwargs)
            self.app.on_sessions_changed()
            return True
        except Exception as exc:show_error(self,str(exc));return False


def correct_selected(parent,app,session):
    if session is None or session.status!='done':
        show_error(parent,tr('ui.session_ui.selecteaza_o_sesiune_incheiata'));return
    if app.ws.read_only:
        show_error(parent,tr('ui.session_ui.workspace_doar_pentru_citire'));return
    CorrectTimeDialog(parent,app,session).run()
