"""Calendar subpage and a generous local notes space; no automatic COM or work timer."""

from ..i18n import date_text, datetime_text

from ..i18n import tr
import tkinter as tk
from tkinter import ttk
from datetime import datetime,timedelta
from urllib.parse import urlparse
import webbrowser
from ..domain.common import new_id,utcnow
from ..domain.models import Kind,Priority
from ..domain.labels import PRIORITY_LABELS,PRIORITY_FROM_LABEL
from ..services.meetings import meeting_state
from ..domain.timeutil import local_day_bounds_utc
from .common import ModalDialog,make_tree,show_error,show_info,ask_choice
from .dialogs import NodePickerDialog,location_choices
from .formats import parse_date,format_date
from .session_ui import parse_local_stamp
from .tree_rows import sync_rows

MODES={tr('ui.meetings.urmatoare'):'upcoming',tr('ui.meetings.trecute'):'past',tr('ui.meetings.cu_notite'):'notes',tr('ui.meetings.cu_actiuni_neconvertite'):'actions',tr('ui.meetings.toate'):'all'}
ACTION_STATES={tr('ui.meetings.de_clarificat'):'clarify',tr('ui.meetings.de_facut'):'todo',tr('ui.meetings.inchisa'):'closed'}

class CalendarHub(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True)
        from .calendar_page import CalendarPage
        self.agenda=CalendarPage(self.nb,app);self.meetings=MeetingPage(self.nb,app)
        self.nb.add(self.agenda,text=tr('ui.meetings.agenda'));self.nb.add(self.meetings,text=tr('ui.meetings.intalniri'))
        self.nb.bind('<<NotebookTabChanged>>',self.changed)
        self._previous=0

    def __getattr__(self,name):
        agenda=self.__dict__.get('agenda')
        if agenda is not None:return getattr(agenda,name)
        raise AttributeError(name)

    def changed(self,event=None):
        index=self.nb.index(self.nb.select())
        if self._previous==1 and index!=1 and not self.meetings.resolve():
            self.nb.select(self.meetings);return
        self._previous=index
        if index==1 and self.app.ws:self.meetings.refresh()

    def refresh(self,*args,**kwargs):
        if self.nb.index(self.nb.select())==1:self.meetings.refresh()
        else:self.agenda.refresh(*args,**kwargs)

    def open_meeting(self,mid):
        self.nb.select(self.meetings);return self.meetings.open(mid)


class MeetingPage(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.workspace=None;self.mid=None;self.dirty=False;self._loading=False
        self._save_job=None;self._search_job=None;self._import_job=None;self._request_generation=0;self._limit=100
        self._apply_iter=None;self._apply_job=None
        self.active_dialog=None;self.node_filter=None
        self.list_frame=ttk.Frame(self,padding=12);self.list_frame.pack(fill='both',expand=True)
        header=ttk.Frame(self.list_frame);header.pack(fill='x')
        ttk.Label(header,text=tr('ui.meetings.intalniri'),style='Title.TLabel').pack(side='left')
        self.import_btn=ttk.Button(header,text=tr('ui.meetings.actualizeaza_intalnirile'),command=self.import_meetings);self.import_btn.pack(side='right')
        self.choose_btn=ttk.Button(header,text=tr('ui.meetings.alege_calendarul'),command=self.choose_source);self.choose_btn.pack(side='right',padx=6)
        self.manual_btn=ttk.Button(header,text=tr('ui.meetings.intalnire_manuala_2'),command=self.manual);self.manual_btn.pack(side='right')
        self.source_label=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.source_label.pack(fill='x',pady=6)
        self.period_label=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.period_label.pack(fill='x')
        filters=ttk.Frame(self.list_frame);filters.pack(fill='x',pady=6)
        self.mode=tk.StringVar(value=tr('ui.meetings.urmatoare'));self.query=tk.StringVar();self.first=tk.StringVar();self.last=tk.StringVar()
        combo=ttk.Combobox(filters,textvariable=self.mode,values=list(MODES),state='readonly',width=23);combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda e:self.filter_changed())
        entry=ttk.Entry(filters,textvariable=self.query,width=25);entry.pack(side='left',fill='x',expand=True,padx=6)
        self.query.trace_add('write',self.search_changed)
        dates=ttk.Frame(self.list_frame);dates.pack(fill='x',pady=4)
        for text,var in [(tr('ui.meetings.de_la'),self.first),(tr('ui.meetings.pana_la'),self.last)]:
            ttk.Label(dates,text=text).pack(side='left',padx=(0,4));ttk.Entry(dates,textvariable=var,width=12).pack(side='left',padx=(0,8))
        ttk.Button(dates,text=tr('ui.meetings.filtreaza_interval'),command=self.filter_changed).pack(side='left')
        ttk.Button(dates,text=tr('ui.meetings.incarca_interval_din_outlook'),command=lambda:self.import_meetings(custom=True)).pack(side='left',padx=6)
        ttk.Button(dates,text=tr('ui.meetings.resetare'),command=self.reset).pack(side='left')
        ttk.Button(self.list_frame,text=tr('ui.meetings.verifica_integritatea_locala'),command=self.check_integrity).pack(anchor='e')
        self.filter_label=ttk.Label(self.list_frame,style='Muted.TLabel');self.filter_label.pack(fill='x')
        self.tv,wrap=make_tree(self.list_frame,[('when',tr('ui.meetings.data_si_ora'),170),('title',tr('ui.meetings.titlu'),360),('state',tr('ui.meetings.stare_calendaristica'),170),('notes',tr('ui.meetings.notite'),90),('actions',tr('ui.meetings.actiuni_neconvertite'),120)],height=14)
        wrap.pack(fill='both',expand=True,pady=6)
        self.tv.bind('<Double-1>',lambda e:self.open_selected());self.tv.bind('<Return>',lambda e:self.open_selected())
        bottom=ttk.Frame(self.list_frame);bottom.pack(fill='x')
        ttk.Button(bottom,text=tr('ui.meetings.deschide_notitele'),command=self.open_selected).pack(side='left')
        self.more=ttk.Button(bottom,text=tr('ui.meetings.mai_multe'),command=self.load_more);self.more.pack(side='right')
        self.message=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.message.pack(side='bottom',fill='x',pady=4,before=wrap)
        bottom.pack_configure(side='bottom',before=wrap)
        self.space=ttk.Frame(self,padding=12)
        nav=ttk.Frame(self.space);nav.pack(fill='x')
        ttk.Button(nav,text=tr('ui.meetings.inapoi'),command=self.back).pack(side='left')
        ttk.Button(nav,text=tr('ui.meetings.salveaza_ctrl_s'),command=self.save).pack(side='right')
        ttk.Button(nav,text=tr('ui.meetings.reincearca_salvarea'),command=self.save).pack(side='right',padx=6)
        self.reload_btn=ttk.Button(nav,text=tr('ui.meetings.reincarca_notitele'),command=self.reload_notes);self.reload_btn.pack(side='right')
        self.context=ttk.Label(self.space,style='Section.TLabel',wraplength=900);self.context.pack(fill='x',pady=8)
        self.save_state=ttk.Label(self.space,text='',style='Muted.TLabel',wraplength=900);self.save_state.pack(fill='x')
        self.split=ttk.PanedWindow(self.space,orient='vertical');self.split.pack(fill='both',expand=True,pady=6)
        edit=ttk.Frame(self.split);edit.rowconfigure(1,weight=1);edit.columnconfigure(0,weight=1)
        tools=ttk.Frame(edit);tools.grid(row=0,column=0,sticky='ew')
        ttk.Button(tools,text=tr('ui.meetings.sablon_optional'),command=self.template).pack(side='left')
        self.create_task_btn=ttk.Button(tools,text=tr('ui.meetings.creeaza_task_din_selectie'),command=self.from_selection);self.create_task_btn.pack(side='left',padx=6)
        self.join_btn=ttk.Button(tools,text=tr('ui.meetings.participa_link'),command=self.join);self.join_btn.pack(side='right')
        self.notes=tk.Text(edit,wrap='word',undo=True,font='TkTextFont',height=16)
        self.notes.grid(row=1,column=0,sticky='nsew',pady=(6,0));sb=ttk.Scrollbar(edit,command=self.notes.yview);sb.grid(row=1,column=1,sticky='ns');self.notes.configure(yscrollcommand=sb.set)
        self.notes.bind('<<Modified>>',self.modified)
        self.split.add(edit,weight=3)
        actions=ttk.Frame(self.split);self.split.add(actions,weight=1)
        bar=ttk.Frame(actions);bar.pack(fill='x')
        ttk.Label(bar,text=tr('ui.meetings.actiuni_rezultate'),style='Section.TLabel').pack(side='left')
        self.actions_menu=ttk.Menubutton(bar,text=tr('ui.meetings.actiuni'));self.actions_menu.pack(side='right')
        menu=tk.Menu(self.actions_menu,tearoff=False);self.actions_menu.configure(menu=menu)
        for text,fn in [(tr('ui.meetings.adauga_actiune'),self.add_action),(tr('ui.meetings.modifica_actiunea'),self.edit_action),(tr('ui.meetings.creeaza_task'),lambda:self.convert_action(Kind.TASK)),(tr('ui.meetings.creeaza_proiect'),lambda:self.convert_action(Kind.PROJECT)),(tr('ui.meetings.cerinta_noua_pentru_un_task_existent'),self.new_requirement),(tr('ui.meetings.leaga_task_proiect_existent'),self.link),(tr('ui.meetings.deschide_taskul_proiectul'),self.open_link)]:menu.add_command(label=text,command=fn)
        self.actions,awrap=make_tree(actions,[('text',tr('ui.meetings.actiune_legatura'),340),('person',tr('ui.meetings.responsabil'),120),('due',tr('ui.meetings.termen'),100),('state',tr('ui.meetings.stare'),160)],height=5);awrap.pack(fill='both',expand=True)
        self.actions.bind('<Double-1>',lambda e:self.open_link());self.actions.bind('<Return>',lambda e:self.open_link())
        self._actions={};self._links={};self._current_source=None
        self.space.bind('<Configure>',lambda e:self.context.configure(wraplength=max(250,e.width-24)))
        self.list_frame.bind('<Configure>',self.resize_labels)

    def resize_labels(self,event):
        for label in (self.source_label,self.period_label,self.message):label.configure(wraplength=max(250,event.width-24))

    @property
    def service(self):return self.app.ws.meetings

    def attach(self):
        if self.workspace is self.app.ws:return
        if self._save_job:self.after_cancel(self._save_job);self._save_job=None
        self.cancel_import()
        self._request_generation+=1;self._import_job=None;self.workspace=self.app.ws;self.mid=None;self.dirty=False
        self.node_filter=None;self.mode.set(tr('ui.meetings.urmatoare'));self.query.set('');self.first.set('');self.last.set('');self._limit=100
        self.space.pack_forget();self.list_frame.pack(fill='both',expand=True)

    def refresh(self):
        if not self.app.ws:return
        self.attach()
        if self.mid:
            try:self._current_source=self.service.store.source(self.mid);self.render_context();self.render_actions()
            except Exception as exc:self.save_state.configure(text=str(exc))
            return
        scroll=self.tv.yview()[0];selected=self.tv.selection()
        try:
            first,last=self.bounds(optional=True)
            rows,total=self.service.list(mode=MODES[self.mode.get()],text=self.query.get(),first=first,last=last,node_id=self.node_filter,limit=self._limit)
            data=[];tz=self.app.q.tz()
            for row in rows:
                start=datetime.fromisoformat(row['start_at']).astimezone(tz)
                end=datetime.fromisoformat(row['end_at']).astimezone(tz)
                when=(date_text(datetime.fromisoformat(row['all_day_start'])) if row.get('all_day_start') else date_text(start))+tr('ui.meetings.toata_ziua') if row['all_day'] else f'{datetime_text(start)}–{end:%H:%M}'
                data.append(('',row['id'],dict(values=(when,row['title'],meeting_state(row),tr('ui.meetings.are_notite') if row['has_notes'] else '—',row['unconverted']))))
            sync_rows(self.tv,data);self.tv.selection_set([i for i in selected if self.tv.exists(i)]);self.tv.yview_moveto(scroll)
            self.more.configure(state='normal' if len(rows)<total else 'disabled')
            self.message.configure(text=tr('ui.meetings.din_intalniri_in_desfasurare_descrie_intervalul_nu_prezenta_sau_un_tim', len_rows=len(rows), total=total) if rows else tr('ui.meetings.nicio_intalnire_pentru_filtrele_alese_poti_importa_sau_crea_manual_inc'))
            config=self.service.config()
            self.source_label.configure(text=tr('ui.meetings.sursa_import')+config.get('label',tr('ui.meetings.nealeasa_outlook_classic_com_necesar_pentru_import_new_outlook_nu_supo')))
            self.period_label.configure(text=tr('ui.meetings.import_implicit_ultimele_14_zile_si_urmatoarele_60_ultima_actualizare')+config.get('last_update',tr('ui.meetings.niciodata'))+(tr('ui.meetings.rezultat_partial') if config.get('complete') is False and config.get('last_update') else '')+ (' · Eroare: '+config['last_error'] if config.get('last_error') else '')+(' · '+str(config['last_warnings'][0]) if config.get('last_warnings') else ''))
            self.filter_label.configure(text=tr('ui.meetings.filtru_intalniri_legate_de_task_proiect') if self.node_filter else tr('ui.meetings.cautare_dupa_titlu_notitele_se_incarca_numai_la_deschidere'))
            ro=self.app.ws.read_only
            for button in (self.import_btn,self.choose_btn,self.manual_btn):button.configure(state='disabled' if ro or self._import_job else 'normal')
        except Exception as exc:self.message.configure(text=tr('ui.meetings.eroare')+str(exc))

    def bounds(self,optional=False):
        first=parse_date(self.first.get(),self.app.q.today());last=parse_date(self.last.get(),self.app.q.today())
        if first and last and first>last:raise ValueError(tr('ui.meetings.interval_inversat'))
        tz=self.app.ws.settings.timezone
        return (local_day_bounds_utc(first,tz)[0] if first else None,local_day_bounds_utc(last,tz)[1] if last else None)

    def search_changed(self,*args):
        if self._search_job:self.after_cancel(self._search_job)
        self._search_job=self.after(250,self.filter_changed)

    def filter_changed(self):self._search_job=None;self._limit=100;self.refresh()
    def load_more(self):self._limit+=100;self.refresh()
    def reset(self):self.node_filter=None;self.mode.set(tr('ui.meetings.urmatoare'));self.query.set('');self.first.set('');self.last.set('');self.filter_changed()

    def open_selected(self):
        selected=self.tv.selection()
        if selected:self.open(selected[0])

    def open(self,mid):
        if not self.resolve():return False
        self.attach()
        try:
            source=self.service.store.source(mid);text=self.service.store.notes(mid)
        except Exception as exc:show_error(self,str(exc));return False
        self.mid=mid;self._current_source=source;self._loading=True
        self.notes.configure(state='normal');self.notes.delete('1.0','end');self.notes.insert('1.0',text);self.notes.edit_reset();self.notes.edit_modified(False)
        self._loading=False;self.dirty=False
        self.notes.configure(state='disabled' if self.app.ws.read_only else 'normal')
        self.save_state.configure(text=tr('ui.meetings.doar_citire') if self.app.ws.read_only else tr('ui.meetings.salvat_notite_locale_fara_sincronizare_in_outlook'))
        self.list_frame.pack_forget();self.space.pack(fill='both',expand=True)
        self.render_context();self.render_actions();self.notes.focus_set();return True

    def render_context(self):
        s=self._current_source;tz=self.app.q.tz()
        self.context.configure(text=tr('ui.meetings.timed_context', s_title=s.title, s_start_at_astimezone_tz=s.start_at.astimezone(tz), s_end_at_astimezone_tz=s.end_at.astimezone(tz))+(tr('ui.meetings.toata_ziua_2') if s.all_day else '')+meeting_state(s.model_dump(mode='json'))+tr('ui.meetings.context_calendaristic_fara_timp_lucrat_presupus', s_location=s.location, s_organizer=s.organizer))
        if s.all_day and s.all_day_start and s.all_day_end:
            end=s.all_day_end-timedelta(days=1)
            self.context.configure(text=tr('ui.meetings.toata_ziua_3', s_title=s.title, s_all_day_start=s.all_day_start)+(f'–{date_text(end)}' if end!=s.all_day_start else '')+
                ' · '+meeting_state(s.model_dump(mode='json'))+tr('ui.meetings.context_calendaristic_fara_timp_lucrat_presupus', s_location=s.location, s_organizer=s.organizer))
        self.join_btn.configure(state='normal' if urlparse(s.join_url).scheme in ('http','https') else 'disabled')
        self.actions_menu.configure(state='disabled' if self.app.ws.read_only else 'normal')
        self.create_task_btn.configure(state='disabled' if self.app.ws.read_only else 'normal')

    def modified(self,event=None):
        if not self.notes.edit_modified():return
        self.notes.edit_modified(False)
        if self._loading or not self.mid or not self.app.ws or self.app.ws.read_only:return
        self.dirty=True;self.save_state.configure(text=tr('ui.meetings.se_salveaza'))
        if self._save_job:self.after_cancel(self._save_job)
        ws=self.app.ws;mid=self.mid
        self._save_job=self.after(900,lambda:self.save() if self.app.ws is ws and self.mid==mid else None)

    def save(self):
        if self._save_job:self.after_cancel(self._save_job);self._save_job=None
        if not self.dirty:return True
        try:
            if self.app.ws is not self.workspace:raise ValueError(tr('ui.meetings.workspace_schimbat_ciorna_este_pastrata_in_editor'))
            self.service.save_notes(self.mid,self.notes.get('1.0','end-1c'))
            self.dirty=False;self.save_state.configure(text=tr('ui.meetings.salvat_numai_local'));return True
        except Exception as exc:
            self.save_state.configure(text=tr('ui.meetings.salvarea_a_esuat')+str(exc)+tr('ui.meetings.textul_ramane_in_editor'));return False

    def resolve(self):
        if self.active_dialog is not None and self.active_dialog.winfo_exists():self.active_dialog.lift();return False
        if not self.dirty:return True
        if self.save():return True
        choice=ask_choice(self,tr('ui.meetings.notite_nesalvate'),tr('ui.meetings.salvarea_nu_a_reusit_pastreaza_ciorna_sau_renunta_explicit'), [('retry',tr('ui.meetings.reincearca')),('stay',tr('ui.meetings.ramai_aici')),('discard',tr('ui.meetings.renunta_la_ciorna'))])
        if choice=='retry':return self.save()
        if choice=='discard':
            self.dirty=False;self.open(self.mid);return True
        return False

    def back(self):
        if not self.resolve():return
        self.mid=None;self.space.pack_forget();self.list_frame.pack(fill='both',expand=True);self.refresh()

    def reload_notes(self):
        if self.dirty and ask_choice(self,tr('ui.meetings.reincarca_notitele_2'),tr('ui.meetings.inlocuiesti_explicit_ciorna_cu_textul_de_pe_disc'), [('stay',tr('ui.meetings.pastreaza_ciorna')),('reload',tr('ui.meetings.reincarca_de_pe_disc'))])!='reload':return
        self.dirty=False;self.open(self.mid)

    def template(self):
        if self.app.ws.read_only:return
        self.notes.insert('end',tr('ui.meetings.subiecte_discutate_decizii_de_clarificat'))

    def join(self):
        link=self._current_source.join_url
        if urlparse(link).scheme in ('http','https'):webbrowser.open(link)

    def render_actions(self):
        local=self.service.store.local(self.mid);rows=[];self._actions={};self._links={}
        for a in local.actions:
            self._actions[a.id]=a
            status=tr('ui.meetings.deschide_taskul_proiectul') if a.node_id and a.node_id in self.app.ws.nodes else tr('ui.meetings.task_indisponibil') if a.node_id else next((k for k,v in ACTION_STATES.items() if v==a.state),tr('ui.meetings.transformata_referinta_indisponibila'))
            rows.append(('',a.id,dict(values=(a.text,a.responsible,format_date(a.due_date),status))))
            if a.node_id:self._links[a.id]=a.node_id
        converted={a.node_id for a in local.actions}
        for nid in local.linked_node_ids:
            if nid in converted:continue
            n=self.app.ws.nodes.get(nid);iid='link:'+nid;self._links[iid]=nid
            rows.append(('',iid,dict(values=(n.title if n else tr('common.missing_node'),'','',tr('ui.meetings.legatura')))))
        sync_rows(self.actions,rows)

    def selected_action(self):
        selected=self.actions.selection();return self._actions.get(selected[0]) if selected else None

    def modal(self,dialog):
        self.active_dialog=dialog
        try:return dialog.run()
        finally:self.active_dialog=None

    def add_action(self):
        if self.mid and not self.app.ws.read_only:
            if self.modal(ActionDialog(self,self.app,self.mid)):self.render_actions()

    def edit_action(self):
        action=self.selected_action()
        if action and not action.node_id and not self.app.ws.read_only:
            if self.modal(ActionDialog(self,self.app,self.mid,action)):self.render_actions()

    def from_selection(self):
        try:text=self.notes.get('sel.first','sel.last')
        except tk.TclError:show_info(self,tr('ui.meetings.selecteaza_fragmentul_din_notite_pentru_contextul_taskului'));return
        self.create(Kind.TASK,text)

    def create(self,kind,text,action=None,followup=False):
        if not self.resolve():return
        dialog=MeetingNodeDialog(self,self.app,self.mid,kind=kind,text=text,action=action,followup=followup)
        result=self.modal(dialog)
        if result:self.render_actions()
        return result

    def convert_action(self,kind):
        action=self.selected_action()
        if action and action.node_id:self.open_link();return
        if action:self.create(kind,action.text,action)
        else:self.create(kind,'')

    def new_requirement(self):
        action=self.selected_action()
        if action and action.node_id:self.open_link();return
        self.create(Kind.TASK,action.text if action else '',action,True)

    def link(self):
        if not self.resolve():return
        nid=self.modal(NodePickerDialog(self,self.app.ws,tr('ui.meetings.leaga_un_task_proiect_existent')))
        if nid and self.app.run_write(lambda:self.service.link(self.mid,nid)):self.render_actions()

    def open_link(self):
        selected=self.actions.selection();nid=self._links.get(selected[0]) if selected else None
        if nid and nid in self.app.ws.nodes and self.resolve():self.app.select_node(nid,reveal=True)
        elif nid:show_info(self,tr('ui.meetings.taskul_proiectul_este_indisponibil_sau_in_cos_legatura_este_pastrata'))

    def manual(self):
        if self.app.ws.read_only:return
        result=self.modal(ManualMeetingDialog(self,self.app))
        if result:self.refresh();self.open(result.id)

    def check_integrity(self):
        if not self.resolve():return
        issues=self.service.integrity(include_notes=True)
        show_info(self,tr('ui.meetings.verificare_locala_incheiata')+(tr('ui.meetings.nicio_problema') if not issues else '\n'+'\n'.join(f'{path}: {text}' for path,text in issues[:30])))

    def cancel_import(self):
        self._request_generation+=1
        if self._apply_job:self.after_cancel(self._apply_job);self._apply_job=None
        if self._apply_iter is not None:
            self._apply_iter.close();self._apply_iter=None
            if self.workspace is self.app.ws and self.app.ws and not self.app.ws.read_only:
                try:self.service.record_import(error=tr('ui.meetings.actualizare_intrerupta_metadatele_deja_salvate_sunt_pastrate'))
                except Exception:pass
        self._import_job=None

    def choose_source(self):
        if self.app.ws.read_only or self._import_job:return
        ws=self.app.ws;generation=self._request_generation;self.message.configure(text=tr('ui.meetings.se_citesc_calendarele_din_outlook_classic'))
        def done(calendars):
            if self.app.ws is not ws or generation!=self._request_generation:return
            self._import_job=None
            dialog=CalendarSourceDialog(self,calendars);chosen=self.modal(dialog)
            if chosen is not None:
                c=calendars[chosen]
                self.app.run_write(lambda:ws.meetings.configure(c.store_id,c.folder_id,c.label))
            self.refresh()
        def error(exc):
            if self.app.ws is ws and generation==self._request_generation:
                self._import_job=None;self.message.configure(text=tr('ui.meetings.import_indisponibil')+str(exc)+tr('ui.meetings.datele_locale_raman_disponibile_poti_crea_manual_new_outlook_nu_suport'))
        self._import_job=True
        self.app.outlook.worker.submit(lambda backend:backend.list_calendars(),done,error,name='meeting-calendars',timeout_s=40)

    def import_meetings(self,custom=False):
        if self.app.ws.read_only or self._import_job:return
        config=self.service.config()
        if not config.get('store_id'):show_info(self,tr('ui.meetings.alege_explicit_calendarul_pentru_intalniri'));return
        ws=self.app.ws;generation=self._request_generation;source=(config['store_id'],config['folder_id'])
        try:
            if custom:
                first,last=self.bounds()
                if first is None or last is None:raise ValueError(tr('ui.meetings.completeaza_ambele_date_pentru_incarcarea_explicita'))
            else:
                today=self.app.q.today();tz=ws.settings.timezone
                first=local_day_bounds_utc(today-timedelta(days=14),tz)[0];last=local_day_bounds_utc(today+timedelta(days=60),tz)[1]
            if (last-first).days>370:raise ValueError(tr('ui.meetings.incarca_cel_mult_un_an_per_comanda_istoricul_local_ramane_accesibil'))
        except ValueError as exc:show_error(self,str(exc));return
        choice=ask_choice(self,tr('ui.meetings.previzualizare_import'),tr('ui.meetings.sursa_interval_utc_doar_metadate_fara_corpuri_atasamente_participanti', config_label=config["label"], first_isoformat=first.isoformat(), last_isoformat=last.isoformat()), [('import',tr('ui.meetings.actualizeaza_intalnirile')),('cancel',tr('ui.meetings.anuleaza'))])
        if choice!='import':return
        self._import_job=True;self.message.configure(text=tr('ui.meetings.se_incarca_metadatele_intalnirilor'));self.import_btn.configure(state='disabled')
        def valid():
            current=ws.meetings.config() if self.app.ws is ws else {}
            return self.app.ws is ws and generation==self._request_generation and source==(current.get('store_id'),current.get('folder_id'))
        def done(batch):
            if not valid():
                if self.app.ws is ws:self._import_job=None;self.refresh()
                return
            self._import_job=True
            iterator=ws.meetings.iter_import_batch(*source,batch,first,last)
            self._apply_iter=iterator
            def step():
                self._apply_job=None
                if not valid():
                    iterator.close();self._apply_iter=None
                    if self.app.ws is ws:self._import_job=None;self.refresh()
                    return
                try:
                    progress=next(iterator)
                    self.message.configure(text=tr('ui.meetings.se_salveaza_metadatele_locale', progress_applied=progress["applied"], progress_total=progress["total"]))
                    self._apply_job=self.after(1,step)
                except StopIteration as completed:
                    self._apply_iter=None;self._import_job=None;result=completed.value
                    self.refresh();self.message.configure(text=tr('ui.meetings.intalniri_actualizate', count=result["count"], result_count=result["count"])+(tr('ui.meetings.rezultat_partial_2') if not result['complete'] else ' ')+ ' · '.join(result['warnings'][:4]))
                except Exception as exc:
                    self._apply_iter=None;self._import_job=None;error(exc)
            self._apply_job=self.after(1,step)
        def error(exc):
            if not valid():
                if self.app.ws is ws:self._import_job=None;self.refresh()
                return
            self._import_job=None
            try:ws.meetings.record_import(error=str(exc))
            except Exception:pass
            self.refresh();self.message.configure(text=tr('ui.meetings.actualizarea_a_esuat')+str(exc)+tr('ui.meetings.datele_locale_sunt_pastrate_outlook_classic_com_este_necesar_new_outlo'))
        self.app.outlook.worker.submit(lambda backend:backend.read_meetings(*source,first,last),done,error,name='meeting-import',timeout_s=40)

class CalendarSourceDialog(ModalDialog):
    def __init__(self,parent,calendars):
        super().__init__(parent,tr('ui.meetings.alege_sursa_intalnirilor'),resizable=True,ok_text=tr('ui.meetings.foloseste_calendarul'))
        self.calendars=calendars
        ttk.Label(self.body,text=tr('ui.meetings.selectare_explicita_separata_de_calendarul_rezervarilor_focusdesk_impo'),wraplength=680).pack(fill='x')
        self.tv,wrap=make_tree(self.body,[('calendar',tr('ui.meetings.calendar_si_sursa'),680)],height=10);wrap.pack(fill='both',expand=True,pady=8)
        for i,c in enumerate(calendars):self.tv.insert('','end',iid=str(i),values=(c.label,))
        if not calendars:ttk.Label(self.body,text=tr('ui.meetings.niciun_calendar_disponibil_datele_locale_si_intalnirile_manuale_functi')).pack()
    def validate(self):return bool(self.tv.selection())
    def collect(self):return int(self.tv.selection()[0])

class ManualMeetingDialog(ModalDialog):
    def __init__(self,parent,app):
        super().__init__(parent,tr('ui.meetings.intalnire_manuala'),resizable=True,ok_text=tr('ui.meetings.creeaza_intalnirea'))
        self.app=app;self.ws=app.ws;self.request_id=new_id()
        now=utcnow().astimezone(app.q.tz()).replace(second=0,microsecond=0)
        self.title_var=tk.StringVar();self.start=tk.StringVar(value=now.isoformat());self.end=tk.StringVar(value=(now+timedelta(hours=1)).isoformat());self.location=tk.StringVar()
        for text,var in [(tr('ui.meetings.titlu'),self.title_var),(tr('ui.meetings.inceput_iso_cu_fus_offset'),self.start),(tr('ui.meetings.sfarsit_iso_cu_fus_offset'),self.end),(tr('ui.meetings.locatie_optional'),self.location)]:
            ttk.Label(self.body,text=text).pack(anchor='w',pady=(6,0));ttk.Entry(self.body,textvariable=var,width=65).pack(fill='x')
        ttk.Label(self.body,text=tr('ui.meetings.context_calendaristic_local_nu_creeaza_sesiune_de_lucru_si_nu_exporta'),wraplength=500,style='Muted.TLabel').pack(fill='x',pady=8)
    def collect(self):
        try:
            if self.app.ws is not self.ws:raise ValueError(tr('ui.meetings.workspace_schimbat'))
            return self.ws.meetings.manual(title=self.title_var.get(),start=parse_local_stamp(self.start.get(),self.ws.settings.timezone),
                end=parse_local_stamp(self.end.get(),self.ws.settings.timezone),location=self.location.get(),request_id=self.request_id)
        except Exception as exc:show_error(self,str(exc));return False

class ActionDialog(ModalDialog):
    def __init__(self,parent,app,mid,action=None):
        super().__init__(parent,tr('ui.meetings.actiune_rezultata'),resizable=True,ok_text=tr('ui.meetings.salveaza_actiunea'))
        self.app=app;self.ws=app.ws;self.mid=mid;self.original=action;self.aid=action.id if action else new_id()
        ttk.Label(self.body,text=tr('ui.meetings.textul_actiunii')).pack(anchor='w')
        self.text=tk.Text(self.body,height=5,width=62,wrap='word');self.text.pack(fill='both',expand=True)
        if action:self.text.insert('1.0',action.text)
        self.person=tk.StringVar(value=action.responsible if action else '')
        self.due=tk.StringVar(value=format_date(action.due_date) if action else '')
        self.state=tk.StringVar(value=next((k for k,v in ACTION_STATES.items() if action and v==action.state),tr('ui.meetings.de_clarificat')))
        for label,var in [(tr('ui.meetings.responsabil_optional_nu_creeaza_automat_un_task_personal'),self.person),(tr('ui.meetings.termen_optional'),self.due)]:
            ttk.Label(self.body,text=label).pack(anchor='w',pady=(6,0));ttk.Entry(self.body,textvariable=var).pack(fill='x')
        ttk.Combobox(self.body,textvariable=self.state,values=list(ACTION_STATES),state='readonly').pack(fill='x',pady=8)
    def collect(self):
        try:
            if self.app.ws is not self.ws:raise ValueError(tr('ui.meetings.workspace_schimbat'))
            return self.ws.meetings.save_action(self.mid,text=self.text.get('1.0','end-1c'),responsible=self.person.get(),
                due_date=parse_date(self.due.get(),self.app.q.today()),state=ACTION_STATES[self.state.get()],action_id=self.aid,expected=self.original)
        except Exception as exc:show_error(self,str(exc));return False

class MeetingNodeDialog(ModalDialog):
    def __init__(self,parent,app,mid,*,kind=Kind.TASK,text='',action=None,followup=False):
        super().__init__(parent,tr('ui.meetings.cerinta_noua_din_intalnire') if followup else (tr('ui.meetings.proiect_din_intalnire') if kind==Kind.PROJECT else tr('ui.meetings.task_din_intalnire')),resizable=True,ok_text=tr('ui.meetings.creeaza_si_leaga'))
        self.app=app;self.ws=app.ws;self.mid=mid;self.kind=kind;self.action=action;self.followup=followup;self.request_id=new_id();self.source_id=None;self._creating=False
        source=self.ws.meetings.store.source(mid)
        ttk.Label(self.body,text=tr('ui.meetings.intalnire_sursa')+source.title,wraplength=620,style='Section.TLabel').pack(fill='x')
        self.title_var=tk.StringVar(value=(text.splitlines()[0] if text else '')[:300]);self.due=tk.StringVar(value=format_date(action.due_date) if action else '')
        self.priority=tk.StringVar(value=PRIORITY_LABELS[Priority.NORMAL]);self.destination=tk.StringVar();self.share=tk.BooleanVar(value=False)
        ttk.Label(self.body,text=tr('ui.meetings.titlu')).pack(anchor='w',pady=(8,0));self.title_entry=ttk.Entry(self.body,textvariable=self.title_var,width=70);self.title_entry.pack(fill='x')
        ttk.Label(self.body,text=tr('ui.meetings.descriere_numai_contextul_selectat_editabil')).pack(anchor='w',pady=(8,0))
        self.description=tk.Text(self.body,height=7,wrap='word',undo=True);self.description.pack(fill='both',expand=True);self.description.insert('1.0',text)
        self.choices=[]
        for label,nid in location_choices(self.ws,kind):
            try:self.ws.meetings._destination(kind,nid)
            except Exception:continue
            self.choices.append((label,nid))
        ttk.Label(self.body,text=tr('ui.meetings.proiect_container')).pack(anchor='w',pady=(8,0))
        self.dest_box=ttk.Combobox(self.body,textvariable=self.destination,values=[c[0] for c in self.choices],state='readonly');self.dest_box.pack(fill='x')
        if self.choices:self.destination.set(self.choices[0][0])
        ttk.Label(self.body,text=tr('ui.meetings.prioritate')).pack(anchor='w',pady=(8,0));ttk.Combobox(self.body,textvariable=self.priority,values=list(PRIORITY_LABELS.values()),state='readonly').pack(fill='x')
        ttk.Label(self.body,text=tr('ui.meetings.termen_optional')).pack(anchor='w',pady=(8,0));ttk.Entry(self.body,textvariable=self.due).pack(fill='x')
        if followup:
            self.source_label=ttk.Label(self.body,text=tr('ui.meetings.alege_taskul_scriptul_sursa'),wraplength=620);self.source_label.pack(fill='x',pady=8)
            ttk.Button(self.body,text=tr('ui.meetings.task_existent'),command=self.choose_task).pack(anchor='w')
            ttk.Checkbutton(self.body,text=tr('ui.meetings.preia_accesul_la_acelasi_folder_de_cod_folder_de_cod_comun'),variable=self.share).pack(anchor='w',pady=8)
        ttk.Label(self.body,text=tr('ui.meetings.nu_se_copiaza_toate_notitele_nu_se_porneste_timerul_si_nu_se_creeaza_r'),wraplength=620,style='Muted.TLabel').pack(fill='x',pady=8)

    def choose_task(self):
        try:nid=NodePickerDialog(self,self.ws,tr('ui.meetings.cerinta_noua_pentru_task_script_existent'),only_tasks=True).run()
        finally:self.grab_set()
        if nid:
            self.source_id=nid;source=self.ws.get(nid);self.source_label.configure(text=tr('ui.meetings.cerinta_noua_pentru')+source.title)
            label=next((label for label,pid in self.choices if pid==source.parent_id),None)
            self.destination.set(label or tr('ui.meetings.alege_o_destinatie_activa'))

    def collect(self):
        if self._creating:return False
        self._creating=True
        try:
            if self.app.ws is not self.ws:raise ValueError(tr('ui.meetings.workspace_schimbat_ciorna_ramane_in_dialog'))
            if self.followup and self.source_id is None:raise ValueError(tr('ui.meetings.alege_explicit_taskul_sursa'))
            destination=next((pid for label,pid in self.choices if label==self.destination.get()),...)
            if destination is ...:raise ValueError(tr('ui.meetings.alege_un_container_activ'))
            return self.ws.meetings.create_node(self.mid,request_id=self.request_id,title=self.title_var.get(),description=self.description.get('1.0','end-1c'),
                kind=self.kind,parent_id=destination,priority=PRIORITY_FROM_LABEL[self.priority.get()],due_date=parse_date(self.due.get(),self.app.q.today()),
                action_id=self.action.id if self.action else None,followup_source=self.source_id,code_access='shared' if self.share.get() else 'none')
        except Exception as exc:show_error(self,str(exc));return False
        finally:self._creating=False


class MeetingLinks(ttk.Menubutton):
    """One compact contextual entry in a task/project, no fifth navigation destination."""
    def __init__(self,parent,app):
        super().__init__(parent,text=tr('ui.meetings.intalniri_legate'));self.app=app;self.menu=tk.Menu(self,tearoff=False);self.configure(menu=self.menu)

    def load(self,node,before):
        self.pack_forget();self.menu.delete(0,'end')
        if not node or not node.meeting_ids:return
        for mid in node.meeting_ids:
            row=self.app.ws.meetings.store.summary(mid);self.menu.add_command(label=(row['title'] if row else tr('ui.meetings.intalnire_indisponibila'))[:90],
                command=lambda mid=mid:self.app.open_meeting(mid),state='normal' if row else 'disabled')
        self.configure(text=tr('ui.meetings.intalniri_legate_2', len_node_meeting_ids=len(node.meeting_ids)));self.pack(fill='x',before=before,padx=6,pady=2)
