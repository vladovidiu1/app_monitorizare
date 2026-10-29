"""Persistent local activity dashboard with one shared report and native charts."""

from ..i18n import datetime_text, month_year_text, short_date_text

from ..i18n import tr
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog
import tkinter as tk
import logging

from ..domain.labels import format_seconds, STATUS_LABELS, SESSION_STATUS_LABELS, session_status_text
from ..services.activity import (ActivityFilters, ALL_PROJECTS, activity_model, period_bounds,
                                 live_snapshot, DEFINITIONS, export_csv)
from .common import heading_width, make_tree, ScrollFrame, Tooltip, show_info, show_error
from .tree_rows import sync_rows
from .design import C, px
from .formats import parse_date, format_date
from .activity_charts import BarChart

log=logging.getLogger(__name__)
PERIOD_IDS=('7d','30d','90d','month','custom','all')
PERIODS=tuple(tr('activity.period.'+key) for key in PERIOD_IDS)


class ActivityPage(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.report=None;self._workspace=None;self._job=None
        self._focus_first=None;self._focus_last=None;self._focus_projects=None;self._session_nodes={}
        self._project_options={tr('ui.activity_page.toate_proiectele'):ALL_PROJECTS,tr('ui.activity_page.fara_proiect'):None}
        self.sf=ScrollFrame(self);self.sf.pack(fill='both',expand=True)
        self.sf.canvas.configure(background=C.canvas)
        body=self.sf.inner;body.configure(style='Page.TFrame');body.columnconfigure(0,weight=1)
        top=ttk.Frame(body,style='Page.TFrame',padding=(16,14));top.grid(row=0,column=0,sticky='ew');top.columnconfigure(0,weight=1)
        ttk.Label(top,text=tr('ui.activity_page.activitate'),style='Page.Title.TLabel').grid(row=0,column=0,sticky='w')
        self.header=top
        actions=ttk.Frame(top,style='Page.TFrame');self.header_actions=actions;actions.grid(row=0,column=1,sticky='e')
        ttk.Button(actions,text=tr('ui.activity_page.calendar_lunar_ctrl_d'),command=app.open_dashboard).grid(row=0,column=0,padx=(0,6))
        ttk.Button(actions,text=tr('ui.calendar_page.corecteaza_timpul'),command=self.correct_time).grid(row=0,column=2,padx=6)
        self.export_btn=ttk.Button(actions,text=tr('ui.activity_page.export_csv'),style='Primary.TButton',command=self.export)
        self.export_btn.grid(row=0,column=1)
        self.summary=ttk.Label(body,style='Page.Muted.TLabel');self.summary.grid(row=1,column=0,sticky='w',padx=16)
        filters=ttk.Frame(body,style='Card.TFrame',padding=12);filters.grid(row=2,column=0,sticky='ew',padx=16,pady=(10,8));filters.columnconfigure(1,weight=1);filters.columnconfigure(3,weight=1)
        self.period=tk.StringVar(value=tr('activity.period.30d'));self.project=tk.StringVar(value=tr('ui.activity_page.toate_proiectele'))
        ttk.Label(filters,text=tr('ui.activity_page.perioada')).grid(row=0,column=0,sticky='w',padx=(0,8))
        self.period_box=ttk.Combobox(filters,textvariable=self.period,values=PERIODS,state='readonly',width=21)
        self.period_box.grid(row=0,column=1,sticky='ew',padx=(0,16))
        self.filters_frame=filters
        self.project_label=ttk.Label(filters,text=tr('ui.app.proiect'));self.project_label.grid(row=0,column=2,sticky='w',padx=(0,8))
        self.project_box=ttk.Combobox(filters,textvariable=self.project,state='readonly',width=22)
        self.project_box.grid(row=0,column=3,sticky='ew')
        self.period_box.bind('<<ComboboxSelected>>',self.filters_changed);self.project_box.bind('<<ComboboxSelected>>',self.filters_changed)
        self.custom=ttk.Frame(filters);self.custom.grid(row=1,column=0,columnspan=4,sticky='ew',pady=(8,0))
        self.first=tk.StringVar();self.last=tk.StringVar()
        for label,var in [(tr('ui.meetings.de_la'),self.first),(tr('ui.meetings.pana_la'),self.last)]:
            ttk.Label(self.custom,text=label).pack(side='left',padx=(0,6))
            entry=ttk.Entry(self.custom,textvariable=var,width=12);entry.pack(side='left',padx=(0,10));entry.bind('<Return>',lambda event:self.refresh())
        ttk.Button(self.custom,text=tr('ui.activity_page.aplica_interval'),command=self.refresh).pack(side='left')
        self.custom.grid_remove()
        tools=ttk.Frame(filters);self.filter_tools=tools;tools.grid(row=2,column=0,columnspan=4,sticky='ew',pady=(8,0));tools.columnconfigure(0,weight=1)
        self.focus_label=ttk.Label(tools,text=tr('ui.activity_page.fara_filtru_de_detaliu'),style='Muted.TLabel',wraplength=480);self.focus_label.grid(row=0,column=0,sticky='w')
        self.clear_btn=ttk.Button(tools,text=tr('ui.activity_page.elimina_detaliul'),command=self.clear_focus);self.clear_btn.grid(row=0,column=1,padx=6)
        ttk.Button(tools,text=tr('ui.activity_page.resetare_filtre'),command=self.reset_filters).grid(row=0,column=2)
        self.state=ttk.Label(body,style='Page.Muted.TLabel',wraplength=900);self.state.grid(row=3,column=0,sticky='ew',padx=16,pady=(0,6))
        self.cards=ttk.Frame(body,style='Page.TFrame');self.cards.grid(row=4,column=0,sticky='ew',padx=16)
        self.metrics={};self._cards=[]
        for key,title,subtitle in [('worked',tr('ui.activity_page.lucrat_inregistrat'),tr('ui.activity_page.timp_salvat_fara_timerul_live')),('planned',tr('ui.tab_versions.programat'),tr('ui.activity_page.rezervari_nu_munca_efectuata')),('completed',tr('ui.activity_page.taskuri_finalizate'),tr('ui.activity_page.distincte_din_istoricul_perioadei')),('overdue',tr('ui.activity_page.restante_acum'),tr('ui.activity_page.situatie_curenta_nu_istorica'))]:
            card=ttk.Frame(self.cards,style='Card.TFrame',padding=14);card.columnconfigure(0,weight=1)
            ttk.Label(card,text=title,style='Eyebrow.TLabel').grid(row=0,column=0,sticky='w')
            help_btn=ttk.Button(card,text='?',width=2,command=lambda k=key:show_info(self,DEFINITIONS[k],tr('ui.activity_page.definitia_indicatorului')))
            help_btn.grid(row=0,column=1,sticky='e');tip=Tooltip(help_btn,DEFINITIONS[key]);help_btn.bind('<FocusIn>',tip._show);help_btn.bind('<FocusOut>',tip._hide)
            value=ttk.Label(card,text='—',style='Metric.TLabel');value.grid(row=1,column=0,columnspan=2,sticky='w',pady=(8,4));self.metrics[key]=value
            ttk.Label(card,text=subtitle,style='Muted.TLabel',wraplength=240).grid(row=2,column=0,columnspan=2,sticky='w')
            self._cards.append(card)
        self.live_label=ttk.Label(body,style='Page.Muted.TLabel',wraplength=900);self.live_label.grid(row=5,column=0,sticky='ew',padx=16,pady=(8,8))
        self.charts=ttk.Frame(body,style='Page.TFrame');self.charts.grid(row=6,column=0,sticky='ew',padx=16)
        self.time_chart=BarChart(self.charts,tr('ui.activity_page.lucrat_si_programat'),on_select=self.focus_period)
        self.project_chart=BarChart(self.charts,tr('ui.activity_page.timp_lucrat_pe_proiecte'),horizontal=True,on_select=self.focus_projects)
        self.status_frame=ttk.Frame(body,style='Card.TFrame',padding=12);self.status_frame.grid(row=7,column=0,sticky='ew',padx=16,pady=10)
        ttk.Label(self.status_frame,text=tr('ui.activity_page.statusuri_situatie_curenta'),style='Section.TLabel').pack(anchor='w')
        self.status_canvas=tk.Canvas(self.status_frame,height=px(self,22),background=C.surface,highlightthickness=0);self.status_canvas.pack(fill='x',pady=6)
        self.status_text=ttk.Label(self.status_frame,style='Muted.TLabel',wraplength=900);self.status_text.pack(anchor='w')
        self.status_canvas.bind('<Configure>',lambda event:self.draw_status())
        details=ttk.Frame(body,style='Card.TFrame',padding=12);details.grid(row=8,column=0,sticky='nsew',padx=16,pady=(0,14))
        ttk.Label(details,text=tr('ui.activity_page.detalii_verificabile'),style='Section.TLabel').pack(anchor='w')
        ttk.Label(details,text=tr('ui.activity_page.enter_sau_dublu_clic_deschide_taskul_in_tabelele_de_zile_proiecte_ente'),style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(4,8))
        self.nb=ttk.Notebook(details);self.nb.pack(fill='both',expand=True);self.tables={}
        specs=[('sessions',[('date',tr('ui.activity_page.inceput_programat'),145),('task',tr('ui.outlook_ui.task'),210),('project',tr('ui.app.proiect'),180),('status',tr('ui.activity_page.stare_sesiune'),110),('worked',tr('ui.activity_page.lucrat_salvat'),110),('planned',tr('ui.activity_page.programat_eligibil'),125),('live',tr('ui.activity_page.live_nesalvat'),110)]),
               ('days',[('date',tr('ui.activity_page.zi_lucrata_programata'),180),('worked',tr('ui.activity_page.lucrat_salvat'),140),('planned',tr('ui.activity_page.programat_eligibil'),145),('live',tr('ui.activity_page.live_nesalvat'),130)]),
               ('projects',[('project',tr('ui.app.proiect'),260),('worked',tr('ui.activity_page.lucrat_salvat'),140),('planned',tr('ui.activity_page.programat_eligibil'),145),('live',tr('ui.activity_page.live_nesalvat'),130)]),
               ('statuses',[('status',tr('ui.activity_page.status_actual'),220),('count',tr('ui.activity_page.taskuri'),100)])]
        for title,columns in specs:
            tv,wrap=make_tree(self.nb,columns,height=9);self.nb.add(wrap,text=tr({'sessions':'ui.activity_page.sesiuni','days':'ui.activity_page.pe_zile','projects':'ui.activity_page.pe_proiecte','statuses':'ui.activity_page.statusuri_actuale'}[title]));self.tables[title]=tv;tv.configure(style='Dense.Treeview')
            for cid,label,width in columns:tv.column(cid,width=max(px(self,width),heading_width(tv,label)),minwidth=max(px(self,75),heading_width(tv,label)),stretch=(cid=='task' or (title!='sessions' and cid==columns[0][0])))
        for key,command in [('sessions',self.open_task),('days',self.table_day),('projects',self.table_project)]:
            self.tables[key].bind('<Double-1>',command);self.tables[key].bind('<Return>',command)
        self.empty=ttk.Label(details,style='Muted.TLabel',wraplength=850);self.empty.pack(fill='x',pady=(8,0))
        self.limit_label=ttk.Label(body,style='Page.Muted.TLabel',wraplength=900);self.limit_label.grid(row=9,column=0,sticky='ew',padx=16,pady=(0,16))
        self.sf.canvas.bind('<Configure>',self.layout,add='+');self.layout()

    def layout(self,event=None):
        width=event.width if event else max(700,self.winfo_width())
        compact=width<px(self,850)
        if compact:
            self.header_actions.grid(row=1,column=0,columnspan=2,sticky='w',pady=(8,0))
            self.project_label.grid(row=1,column=0,sticky='w',pady=(8,0))
            self.project_box.grid(row=1,column=1,columnspan=3,sticky='ew',pady=(8,0))
            self.period_box.grid(columnspan=3,padx=0)
        else:
            self.header_actions.grid(row=0,column=1,columnspan=1,sticky='e',pady=0)
            self.project_label.grid(row=0,column=2,pady=0)
            self.project_box.grid(row=0,column=3,columnspan=1,pady=0)
            self.period_box.grid(columnspan=1,padx=(0,16))
        self.custom.grid_configure(row=2 if compact else 1)
        if self.period_id()!='custom':self.custom.grid_remove()
        self.filter_tools.grid_configure(row=3 if compact else 2)
        for label in (self.state,self.live_label,self.limit_label,self.status_text):label.configure(wraplength=max(280,width-60))
        columns=4 if width>=px(self,1000) else 2
        for col in range(4):self.cards.columnconfigure(col,weight=1 if col<columns else 0)
        for i,card in enumerate(self._cards):card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=(0,8) if i%columns<columns-1 else 0,pady=(0,8))
        wide=width>=px(self,940)
        self.charts.columnconfigure(0,weight=3);self.charts.columnconfigure(1,weight=2 if wide else 0)
        self.time_chart.grid(row=0,column=0,sticky='nsew',padx=(0,8) if wide else 0,pady=(0,8))
        self.project_chart.grid(row=0 if wide else 1,column=1 if wide else 0,sticky='nsew',pady=(0,8))

    def period_id(self):
        index=self.period_box.current()
        if index>=0:return PERIOD_IDS[index]
        return {'7 zile':'7d','30 zile':'30d','90 zile':'90d','Luna curentă':'month','Interval personalizat':'custom','Tot istoricul':'all'}.get(self.period.get(),'30d')

    def current_filters(self):
        today=self.app.q.today()
        custom=self.period_id()=='custom'
        first,last=period_bounds(self.period_id(),today,parse_date(self.first.get(),today) if custom else None,parse_date(self.last.get(),today) if custom else None)
        return ActivityFilters(first,last,self._project_options.get(self.project.get(),ALL_PROJECTS),self._focus_first,self._focus_last,self._focus_projects)

    def filters_changed(self,event=None):
        self._focus_first=self._focus_last=self._focus_projects=None
        self.refresh()

    def clear_focus(self):
        self._focus_first=self._focus_last=self._focus_projects=None;self.refresh()

    def focus_period(self,bounds):
        self._focus_first,self._focus_last=bounds;self.refresh()

    def focus_projects(self,ids):self._focus_projects=tuple(ids);self.refresh()

    def reset_filters(self):
        self.period.set(tr('activity.period.30d'));self.project.set(tr('ui.activity_page.toate_proiectele'));self.first.set('');self.last.set('');self.clear_focus()

    def refresh(self):
        if not self.app.ws:return
        if self._workspace is not self.app.ws:
            self._workspace=self.app.ws;self.report=None;self._focus_first=self._focus_last=self._focus_projects=None
            self.period.set(tr('activity.period.30d'));self.project.set(tr('ui.activity_page.toate_proiectele'));self.first.set('');self.last.set('')
        selected_project=self._project_options.get(self.project.get(),ALL_PROJECTS)
        projects=[self.app.ws.nodes[nid] for nid in self.app.ws.repo.project_ids]
        self._project_options={tr('ui.activity_page.toate_proiectele'):ALL_PROJECTS,tr('ui.activity_page.fara_proiect'):None}
        for project in sorted(projects,key=lambda n:(n.title.casefold(),n.id)):
            self._project_options[tr('ui.activity_page.project_choice', project_title=project.title, project_id_6=project.id[:6])]=project.id
        self.project_box.configure(values=list(self._project_options))
        if self.project.get() not in self._project_options:
            self.project.set(next((label for label,pid in self._project_options.items() if pid==selected_project),tr('ui.activity_page.toate_proiectele')))
        self.custom.grid() if self.period_id()=='custom' else self.custom.grid_remove()
        self.state.configure(text=tr('ui.activity_page.se_incarca_raportul_local'),foreground=C.muted);self.export_btn.state(['disabled'])
        if self._job and not self._job.done:self._job.token.cancel()
        self._request=getattr(self,'_request',0)+1
        request=self._request
        try:
            filters=self.current_filters()
            ws=self.app.ws;model=activity_model(ws);live=live_snapshot(self.app)
            version=(ws.repo.generation,ws.repo.sessions.revision,ws.repo.history.revision,ws.settings.timezone)
            def apply(report):
                if request!=self._request or ws is not self.app.ws:return
                if version!=(ws.repo.generation,ws.repo.sessions.revision,ws.repo.history.revision,ws.settings.timezone):
                    self.refresh();return
                self.render(report)
            def failed(exc):
                if request==self._request and ws is self.app.ws:self.show_error(exc)
            stores=(ws.repo.sessions,ws.repo.history)
            large=any(store._entries is None or len(store._entries)>2000 for store in stores)
            if large:
                self._job=self.app.bridge.submit(lambda token:model.report(filters,live=live),apply,failed,name='activity-report')
            else:apply(model.report(filters,live=live))
        except Exception as exc:
            log.exception(tr('extra.ui.activity_page.raport_activitate_indisponibil'))
            self.show_error(exc)

    def show_error(self,exc):
        self.state.configure(text=tr('ui.activity_page.raport_indisponibil_corecteaza_filtrele_sau_reincarca_prin_f5', exc=exc),foreground=C.danger)
        self.report=None
        self.time_chart.set_rows([]);self.project_chart.set_rows([])
        self.status_canvas.delete('all');self.status_text.configure(text='')
        for tv in self.tables.values():sync_rows(tv,[])
        self.live_label.configure(text='')
        for metric in self.metrics.values():metric.configure(text='—')

    def render(self,report):
        self.report=report
        self._has_live=bool(report.live)
        self._live_signature=object()
        first,last=report.filters.bounds()
        self.summary.configure(text=tr('ui.activity_page.period_summary', format_date_first_or_inceputul_istoricului=format_date(first) or tr('services.activity.inceputul_istoricului'), format_date_last_or_tot_istoricul=format_date(last) or tr('activity.period.all'), report_timezone=report.timezone))
        self.metrics['worked'].configure(text=format_seconds(report.worked));self.metrics['planned'].configure(text=format_seconds(report.planned))
        self.metrics['completed'].configure(text=str(len(report.completed_ids)));self.metrics['overdue'].configure(text=str(len(report.overdue_ids)))
        self.live_label.configure(text=tr('ui.activity_page.live_nesalvat_separat_nu_intra_in_lucrat_inregistrat_sau_in_barele_sal', format_seconds_report_live=format_seconds(report.live)))
        mode,buckets=report.time_buckets()
        self.time_chart.set_rows([dict(label=short_date_text(item['first']) if mode!='months' else month_year_text(item['first']),value=item['worked'],secondary=item['planned'],token=(item['first'],item['last'])) for item in buckets],tr('ui.activity_page.violet_lucrat_salvat_contur_programat', mode=tr('activity.granularity.'+mode)))
        self.project_chart.set_rows([dict(label=name,value=value,token=ids) for name,ids,value in report.top_projects() if value>0], tr('ui.activity_page.top_5_restul_apartenenta_actuala'))
        self.draw_status()
        rows={name:[] for name in self.tables};self._session_nodes={}
        from zoneinfo import ZoneInfo
        tz=ZoneInfo(report.timezone)
        for row in report.rows:
            rows['sessions'].append(('',row.id,dict(values=(datetime_text(row.start_at.astimezone(tz)),row.task,row.project,session_status_text(row,self.app.timer),format_seconds(row.worked),format_seconds(row.planned),format_seconds(row.live)))))
            self._session_nodes[row.id]=row.node_id
        for day,data in sorted(report.days.items(),reverse=True):rows['days'].append(('',day.isoformat(),dict(values=(format_date(day),*(format_seconds(data[k]) for k in ('worked','planned','live'))))))
        for pid,data in sorted(report.projects.items(),key=lambda p:p[1]['name'].casefold()):rows['projects'].append(('',pid or 'independent',dict(values=(data['name'],*(format_seconds(data[k]) for k in ('worked','planned','live'))))))
        for status,count in sorted(report.statuses.items(),key=lambda p:STATUS_LABELS[p[0]]):rows['statuses'].append(('',status.value,dict(values=(STATUS_LABELS[status],count))))
        for name,tv in self.tables.items():sync_rows(tv,rows[name])
        focus=[]
        if self._focus_first:focus.append(tr('ui.activity_page.detaliu', format_date_self_focus_first=format_date(self._focus_first), format_date_self_focus_last=format_date(self._focus_last)))
        if self._focus_projects:focus.append(tr('ui.activity_page.proiecte')+', '.join(self.app.ws.nodes[pid].title if pid in self.app.ws.nodes else tr('ui.activity_page.fara_proiect') for pid in self._focus_projects))
        self.focus_label.configure(text=' · '.join(focus) or tr('ui.activity_page.fara_filtru_de_detaliu_selecteaza_o_bara_o_zi_sau_un_proiect'))
        self.clear_btn.state(['!disabled'] if focus else ['disabled'])
        self.empty.configure(text='' if report.rows else tr('ui.activity_page.nu_exista_sesiuni_in_perioada_si_proiectul_alese_indicatorii_de_situat'))
        self.limit_label.configure(text=tr('ui.activity_page.finalizari_taskuri_distincte_cu_tranzitie_done_redeschiderea_nu_sterge', report_legacy_done=report.legacy_done))
        self.state.configure(text=(tr('ui.activity_page.sesiuni_actualizat_la', count=len(report.rows), len_report_rows=len(report.rows), datetime_now_tz=datetime.now(tz))+(tr('ui.activity_page.atentie')+'; '.join(report.issues) if report.issues else '')),foreground=C.warning if report.issues else C.muted);self.export_btn.state(['!disabled'])

    def draw_status(self):
        c=self.status_canvas;c.delete('all')
        if not self.report:return
        total=sum(self.report.statuses.values());width=max(1,c.winfo_width());x=0
        colors={'done':C.success,'cancelled':C.muted,'waiting':C.warning,'todo':C.border,'in_progress':C.accent,'testing':C.accent}
        parts=[]
        for status,count in sorted(self.report.statuses.items(),key=lambda p:STATUS_LABELS[p[0]]):
            right=x+width*count/max(1,total)
            c.create_rectangle(x,0,right,px(self,21),fill=colors.get(status.value,C.accent),outline=C.surface)
            x=right;parts.append(f'{STATUS_LABELS[status]}: {count}')
        self.status_text.configure(text=' · '.join(parts) or tr('ui.activity_page.niciun_task_in_proiectul_ales'))

    def refresh_labels(self):
        if self._job and not self._job.done:
            self.refresh();return
        if self.report and self.app.ws is self._workspace:self.render(activity_model(self.app.ws).relabel(self.report))
        else:self.refresh()

    def update_live(self):
        if self.app.current_view!='activity' or not self.report or (self._job and not self._job.done):return
        live=live_snapshot(self.app)
        # A changing live timer never rescans files or refreshes the large tables.
        if live is None and not self._has_live:return
        signature=(live.session_id,live.seconds) if live else None
        if signature==self._live_signature:return
        self._live_signature=signature
        value=activity_model(self.app.ws).live_delta(live) if live else 0
        before=self.report
        self.report=before.with_live(live,value)
        self._has_live=bool(self.report.live)
        self.live_label.configure(text=tr('ui.activity_page.live_nesalvat_separat_nu_intra_in_lucrat_inregistrat_sau_in_barele_sal_2', format_seconds_self_report_live=format_seconds(self.report.live)))
        changed=[new for old,new in zip(before.rows,self.report.rows) if old.live!=new.live]
        active=next((row for row in self.report.rows if row.live),None)
        for row in changed:
            tv=self.tables['sessions']
            if tv.exists(row.id):tv.set(row.id,'live',format_seconds(row.live))
            tv=self.tables['days']
            if tv.exists(row.worked_day.isoformat()):tv.set(row.worked_day.isoformat(),'live',format_seconds(active.live if active and active.worked_day==row.worked_day else 0))
            tv=self.tables['projects'];iid=row.project_id or 'independent'
            if tv.exists(iid):tv.set(iid,'live',format_seconds(active.live if active and active.project_id==row.project_id else 0))

    def table_day(self,event=None):
        selected=self.tables['days'].selection()
        if selected:
            from datetime import date
            day=date.fromisoformat(selected[0]);self.focus_period((day,day))
        return 'break'

    def table_project(self,event=None):
        selected=self.tables['projects'].selection()
        if selected:self.focus_projects((None if selected[0]=='independent' else selected[0],))
        return 'break'

    def open_task(self,event=None):
        selected=self.tables['sessions'].selection()
        if selected:
            nid=self._session_nodes.get(selected[0])
            if nid in self.app.ws.nodes:self.app.select_node(nid,reveal=True)
        return 'break'

    def export(self):
        if not self.report:return
        path=filedialog.asksaveasfilename(parent=self,title=tr('ui.activity_page.export_activitate'),defaultextension='.csv',filetypes=[('CSV UTF-8','*.csv')],initialfile='FocusDesk-Activitate.csv')
        if not path:return
        try:
            report=activity_model(self.app.ws).report(self.current_filters(),live=live_snapshot(self.app))
            export_csv(report,Path(path));self.render(report)
            self.state.configure(text=tr('ui.activity_page.exportat', path=path),foreground=C.success)
        except Exception as exc:self.state.configure(text=tr('ui.activity_page.export_nereusit', exc=exc),foreground=C.danger)


    def correct_time(self):
        selected=self.tables['sessions'].selection()
        if not selected:return
        from .session_ui import correct_selected
        try:session=self.app.ws.repo.sessions.get(selected[0])
        except Exception as exc:
            show_error(self,str(exc));return
        correct_selected(self,self.app,session)
