"""Calendar subpage and a generous local notes space; no automatic COM or work timer."""
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

MODES={'Următoare':'upcoming','Trecute':'past','Cu notițe':'notes','Cu acțiuni neconvertite':'actions','Toate':'all'}
ACTION_STATES={'De clarificat':'clarify','De făcut':'todo','Închisă':'closed'}

class CalendarHub(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True)
        from .calendar_page import CalendarPage
        self.agenda=CalendarPage(self.nb,app);self.meetings=MeetingPage(self.nb,app)
        self.nb.add(self.agenda,text='Agenda');self.nb.add(self.meetings,text='Întâlniri')
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
        ttk.Label(header,text='Întâlniri',style='Title.TLabel').pack(side='left')
        self.import_btn=ttk.Button(header,text='Actualizează întâlnirile',command=self.import_meetings);self.import_btn.pack(side='right')
        self.choose_btn=ttk.Button(header,text='Alege calendarul…',command=self.choose_source);self.choose_btn.pack(side='right',padx=6)
        self.manual_btn=ttk.Button(header,text='Întâlnire manuală…',command=self.manual);self.manual_btn.pack(side='right')
        self.source_label=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.source_label.pack(fill='x',pady=6)
        self.period_label=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.period_label.pack(fill='x')
        filters=ttk.Frame(self.list_frame);filters.pack(fill='x',pady=6)
        self.mode=tk.StringVar(value='Următoare');self.query=tk.StringVar();self.first=tk.StringVar();self.last=tk.StringVar()
        combo=ttk.Combobox(filters,textvariable=self.mode,values=list(MODES),state='readonly',width=23);combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>',lambda e:self.filter_changed())
        entry=ttk.Entry(filters,textvariable=self.query,width=25);entry.pack(side='left',fill='x',expand=True,padx=6)
        self.query.trace_add('write',self.search_changed)
        dates=ttk.Frame(self.list_frame);dates.pack(fill='x',pady=4)
        for text,var in [('De la',self.first),('Până la',self.last)]:
            ttk.Label(dates,text=text).pack(side='left',padx=(0,4));ttk.Entry(dates,textvariable=var,width=12).pack(side='left',padx=(0,8))
        ttk.Button(dates,text='Filtrează interval',command=self.filter_changed).pack(side='left')
        ttk.Button(dates,text='Încarcă interval din Outlook…',command=lambda:self.import_meetings(custom=True)).pack(side='left',padx=6)
        ttk.Button(dates,text='Resetare',command=self.reset).pack(side='left')
        ttk.Button(self.list_frame,text='Verifică integritatea locală…',command=self.check_integrity).pack(anchor='e')
        self.filter_label=ttk.Label(self.list_frame,style='Muted.TLabel');self.filter_label.pack(fill='x')
        self.tv,wrap=make_tree(self.list_frame,[('when','Data și ora',170),('title','Titlu',360),('state','Stare calendaristică',170),('notes','Notițe',90),('actions','Acțiuni neconvertite',120)],height=14)
        wrap.pack(fill='both',expand=True,pady=6)
        self.tv.bind('<Double-1>',lambda e:self.open_selected());self.tv.bind('<Return>',lambda e:self.open_selected())
        bottom=ttk.Frame(self.list_frame);bottom.pack(fill='x')
        ttk.Button(bottom,text='Deschide notițele',command=self.open_selected).pack(side='left')
        self.more=ttk.Button(bottom,text='Mai multe',command=self.load_more);self.more.pack(side='right')
        self.message=ttk.Label(self.list_frame,style='Muted.TLabel',wraplength=900);self.message.pack(side='bottom',fill='x',pady=4,before=wrap)
        bottom.pack_configure(side='bottom',before=wrap)
        self.space=ttk.Frame(self,padding=12)
        nav=ttk.Frame(self.space);nav.pack(fill='x')
        ttk.Button(nav,text='Înapoi',command=self.back).pack(side='left')
        ttk.Button(nav,text='Salvează · Ctrl+S',command=self.save).pack(side='right')
        ttk.Button(nav,text='Reîncearcă salvarea',command=self.save).pack(side='right',padx=6)
        self.reload_btn=ttk.Button(nav,text='Reîncarcă notițele…',command=self.reload_notes);self.reload_btn.pack(side='right')
        self.context=ttk.Label(self.space,style='Section.TLabel',wraplength=900);self.context.pack(fill='x',pady=8)
        self.save_state=ttk.Label(self.space,text='',style='Muted.TLabel',wraplength=900);self.save_state.pack(fill='x')
        self.split=ttk.PanedWindow(self.space,orient='vertical');self.split.pack(fill='both',expand=True,pady=6)
        edit=ttk.Frame(self.split);edit.rowconfigure(1,weight=1);edit.columnconfigure(0,weight=1)
        tools=ttk.Frame(edit);tools.grid(row=0,column=0,sticky='ew')
        ttk.Button(tools,text='Șablon opțional',command=self.template).pack(side='left')
        self.create_task_btn=ttk.Button(tools,text='Creează task din selecție…',command=self.from_selection);self.create_task_btn.pack(side='left',padx=6)
        self.join_btn=ttk.Button(tools,text='Participă (link)',command=self.join);self.join_btn.pack(side='right')
        self.notes=tk.Text(edit,wrap='word',undo=True,font='TkTextFont',height=16)
        self.notes.grid(row=1,column=0,sticky='nsew',pady=(6,0));sb=ttk.Scrollbar(edit,command=self.notes.yview);sb.grid(row=1,column=1,sticky='ns');self.notes.configure(yscrollcommand=sb.set)
        self.notes.bind('<<Modified>>',self.modified)
        self.split.add(edit,weight=3)
        actions=ttk.Frame(self.split);self.split.add(actions,weight=1)
        bar=ttk.Frame(actions);bar.pack(fill='x')
        ttk.Label(bar,text='Acțiuni rezultate',style='Section.TLabel').pack(side='left')
        self.actions_menu=ttk.Menubutton(bar,text='Acțiuni');self.actions_menu.pack(side='right')
        menu=tk.Menu(self.actions_menu,tearoff=False);self.actions_menu.configure(menu=menu)
        for text,fn in [('Adaugă acțiune…',self.add_action),('Modifică acțiunea…',self.edit_action),('Creează task…',lambda:self.convert_action(Kind.TASK)),('Creează proiect…',lambda:self.convert_action(Kind.PROJECT)),('Cerință nouă pentru un task existent…',self.new_requirement),('Leagă task/proiect existent…',self.link),('Deschide taskul/proiectul',self.open_link)]:menu.add_command(label=text,command=fn)
        self.actions,awrap=make_tree(actions,[('text','Acțiune / legătură',340),('person','Responsabil',120),('due','Termen',100),('state','Stare',160)],height=5);awrap.pack(fill='both',expand=True)
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
        self.node_filter=None;self.mode.set('Următoare');self.query.set('');self.first.set('');self.last.set('');self._limit=100
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
                when=(datetime.fromisoformat(row['all_day_start']).strftime('%d.%m.%Y') if row.get('all_day_start') else start.strftime('%d.%m.%Y'))+' · Toată ziua' if row['all_day'] else f'{start:%d.%m.%Y %H:%M}–{end:%H:%M}'
                data.append(('',row['id'],dict(values=(when,row['title'],meeting_state(row),'Are notițe' if row['has_notes'] else '—',row['unconverted']))))
            sync_rows(self.tv,data);self.tv.selection_set([i for i in selected if self.tv.exists(i)]);self.tv.yview_moveto(scroll)
            self.more.configure(state='normal' if len(rows)<total else 'disabled')
            self.message.configure(text=f'{len(rows)} din {total} întâlniri. În desfășurare descrie intervalul, nu prezența sau un timer.' if rows else 'Nicio întâlnire pentru filtrele alese. Poți importa sau crea manual, inclusiv offline.')
            config=self.service.config()
            self.source_label.configure(text='Sursă import: '+config.get('label','nealeasă · Outlook Classic/COM necesar pentru import; New Outlook nu suportă COM.'))
            self.period_label.configure(text='Import implicit: ultimele 14 zile și următoarele 60 · ultima actualizare: '+config.get('last_update','niciodată')+(' · rezultat parțial' if config.get('complete') is False and config.get('last_update') else '')+ (' · Eroare: '+config['last_error'] if config.get('last_error') else '')+(' · '+str(config['last_warnings'][0]) if config.get('last_warnings') else ''))
            self.filter_label.configure(text='Filtru: întâlniri legate de task/proiect' if self.node_filter else 'Căutare după titlu; notițele se încarcă numai la deschidere.')
            ro=self.app.ws.read_only
            for button in (self.import_btn,self.choose_btn,self.manual_btn):button.configure(state='disabled' if ro or self._import_job else 'normal')
        except Exception as exc:self.message.configure(text='Eroare: '+str(exc))

    def bounds(self,optional=False):
        first=parse_date(self.first.get(),self.app.q.today());last=parse_date(self.last.get(),self.app.q.today())
        if first and last and first>last:raise ValueError('Interval inversat')
        tz=self.app.ws.settings.timezone
        return (local_day_bounds_utc(first,tz)[0] if first else None,local_day_bounds_utc(last,tz)[1] if last else None)

    def search_changed(self,*args):
        if self._search_job:self.after_cancel(self._search_job)
        self._search_job=self.after(250,self.filter_changed)

    def filter_changed(self):self._search_job=None;self._limit=100;self.refresh()
    def load_more(self):self._limit+=100;self.refresh()
    def reset(self):self.node_filter=None;self.mode.set('Următoare');self.query.set('');self.first.set('');self.last.set('');self.filter_changed()

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
        self.save_state.configure(text='Doar citire' if self.app.ws.read_only else 'Salvat · notițe locale, fără sincronizare în Outlook')
        self.list_frame.pack_forget();self.space.pack(fill='both',expand=True)
        self.render_context();self.render_actions();self.notes.focus_set();return True

    def render_context(self):
        s=self._current_source;tz=self.app.q.tz()
        self.context.configure(text=f'{s.title}\n{s.start_at.astimezone(tz):%d.%m.%Y %H:%M}–{s.end_at.astimezone(tz):%d.%m.%Y %H:%M} · '+('Toată ziua · ' if s.all_day else '')+meeting_state(s.model_dump(mode='json'))+f'\n{s.location} · {s.organizer}\nContext calendaristic, fără timp lucrat presupus.')
        if s.all_day and s.all_day_start and s.all_day_end:
            end=s.all_day_end-timedelta(days=1)
            self.context.configure(text=f'{s.title}\nToată ziua · {s.all_day_start:%d.%m.%Y}'+(f'–{end:%d.%m.%Y}' if end!=s.all_day_start else '')+
                ' · '+meeting_state(s.model_dump(mode='json'))+f'\n{s.location} · {s.organizer}\nContext calendaristic, fără timp lucrat presupus.')
        self.join_btn.configure(state='normal' if urlparse(s.join_url).scheme in ('http','https') else 'disabled')
        self.actions_menu.configure(state='disabled' if self.app.ws.read_only else 'normal')
        self.create_task_btn.configure(state='disabled' if self.app.ws.read_only else 'normal')

    def modified(self,event=None):
        if not self.notes.edit_modified():return
        self.notes.edit_modified(False)
        if self._loading or not self.mid or not self.app.ws or self.app.ws.read_only:return
        self.dirty=True;self.save_state.configure(text='Se salvează…')
        if self._save_job:self.after_cancel(self._save_job)
        ws=self.app.ws;mid=self.mid
        self._save_job=self.after(900,lambda:self.save() if self.app.ws is ws and self.mid==mid else None)

    def save(self):
        if self._save_job:self.after_cancel(self._save_job);self._save_job=None
        if not self.dirty:return True
        try:
            if self.app.ws is not self.workspace:raise ValueError('Workspace schimbat. Ciorna este păstrată în editor.')
            self.service.save_notes(self.mid,self.notes.get('1.0','end-1c'))
            self.dirty=False;self.save_state.configure(text='Salvat · numai local');return True
        except Exception as exc:
            self.save_state.configure(text='Salvarea a eșuat: '+str(exc)+' · Textul rămâne în editor.');return False

    def resolve(self):
        if self.active_dialog is not None and self.active_dialog.winfo_exists():self.active_dialog.lift();return False
        if not self.dirty:return True
        if self.save():return True
        choice=ask_choice(self,'Notițe nesalvate','Salvarea nu a reușit. Păstrează ciorna sau renunță explicit?', [('retry','Reîncearcă'),('stay','Rămâi aici'),('discard','Renunță la ciornă')])
        if choice=='retry':return self.save()
        if choice=='discard':
            self.dirty=False;self.open(self.mid);return True
        return False

    def back(self):
        if not self.resolve():return
        self.mid=None;self.space.pack_forget();self.list_frame.pack(fill='both',expand=True);self.refresh()

    def reload_notes(self):
        if self.dirty and ask_choice(self,'Reîncarcă notițele','Înlocuiești explicit ciorna cu textul de pe disc?', [('stay','Păstrează ciorna'),('reload','Reîncarcă de pe disc')])!='reload':return
        self.dirty=False;self.open(self.mid)

    def template(self):
        if self.app.ws.read_only:return
        self.notes.insert('end','\n\nSubiecte discutate\n\nDecizii\n\nDe clarificat\n')

    def join(self):
        link=self._current_source.join_url
        if urlparse(link).scheme in ('http','https'):webbrowser.open(link)

    def render_actions(self):
        local=self.service.store.local(self.mid);rows=[];self._actions={};self._links={}
        for a in local.actions:
            self._actions[a.id]=a
            status='Deschide taskul/proiectul' if a.node_id and a.node_id in self.app.ws.nodes else 'Task indisponibil' if a.node_id else next((k for k,v in ACTION_STATES.items() if v==a.state),'Transformată · referință indisponibilă')
            rows.append(('',a.id,dict(values=(a.text,a.responsible,format_date(a.due_date),status))))
            if a.node_id:self._links[a.id]=a.node_id
        converted={a.node_id for a in local.actions}
        for nid in local.linked_node_ids:
            if nid in converted:continue
            n=self.app.ws.nodes.get(nid);iid='link:'+nid;self._links[iid]=nid
            rows.append(('',iid,dict(values=(n.title if n else 'Task/proiect indisponibil','','','Legătură'))))
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
        except tk.TclError:show_info(self,'Selectează fragmentul din notițe pentru contextul taskului.');return
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
        nid=self.modal(NodePickerDialog(self,self.app.ws,'Leagă un task/proiect existent'))
        if nid and self.app.run_write(lambda:self.service.link(self.mid,nid)):self.render_actions()

    def open_link(self):
        selected=self.actions.selection();nid=self._links.get(selected[0]) if selected else None
        if nid and nid in self.app.ws.nodes and self.resolve():self.app.select_node(nid,reveal=True)
        elif nid:show_info(self,'Taskul/proiectul este indisponibil sau în coș. Legătura este păstrată.')

    def manual(self):
        if self.app.ws.read_only:return
        result=self.modal(ManualMeetingDialog(self,self.app))
        if result:self.refresh();self.open(result.id)

    def check_integrity(self):
        if not self.resolve():return
        issues=self.service.integrity(include_notes=True)
        show_info(self,'Verificare locală încheiată. '+('Nicio problemă.' if not issues else '\n'+'\n'.join(f'{path}: {text}' for path,text in issues[:30])))

    def cancel_import(self):
        self._request_generation+=1
        if self._apply_job:self.after_cancel(self._apply_job);self._apply_job=None
        if self._apply_iter is not None:
            self._apply_iter.close();self._apply_iter=None
            if self.workspace is self.app.ws and self.app.ws and not self.app.ws.read_only:
                try:self.service.record_import(error='Actualizare întreruptă; metadatele deja salvate sunt păstrate.')
                except Exception:pass
        self._import_job=None

    def choose_source(self):
        if self.app.ws.read_only or self._import_job:return
        ws=self.app.ws;generation=self._request_generation;self.message.configure(text='Se citesc calendarele din Outlook Classic…')
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
                self._import_job=None;self.message.configure(text='Import indisponibil: '+str(exc)+' · Datele locale rămân disponibile; poți crea manual. New Outlook nu suportă COM.')
        self._import_job=True
        self.app.outlook.worker.submit(lambda backend:backend.list_calendars(),done,error,name='meeting-calendars',timeout_s=40)

    def import_meetings(self,custom=False):
        if self.app.ws.read_only or self._import_job:return
        config=self.service.config()
        if not config.get('store_id'):show_info(self,'Alege explicit calendarul pentru întâlniri.');return
        ws=self.app.ws;generation=self._request_generation;source=(config['store_id'],config['folder_id'])
        try:
            if custom:
                first,last=self.bounds()
                if first is None or last is None:raise ValueError('Completează ambele date pentru încărcarea explicită.')
            else:
                today=self.app.q.today();tz=ws.settings.timezone
                first=local_day_bounds_utc(today-timedelta(days=14),tz)[0];last=local_day_bounds_utc(today+timedelta(days=60),tz)[1]
            if (last-first).days>370:raise ValueError('Încarcă cel mult un an per comandă; istoricul local rămâne accesibil.')
        except ValueError as exc:show_error(self,str(exc));return
        choice=ask_choice(self,'Previzualizare import',f'Sursă: {config["label"]}\nInterval UTC: {first.isoformat()} → {last.isoformat()}\nDoar metadate, fără corpuri/atașamente/participanți. Nu se scrie în Outlook.', [('import','Actualizează întâlnirile'),('cancel','Anulează')])
        if choice!='import':return
        self._import_job=True;self.message.configure(text='Se încarcă metadatele întâlnirilor…');self.import_btn.configure(state='disabled')
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
                    self.message.configure(text=f'Se salvează metadatele locale: {progress["applied"]}/{progress["total"]}…')
                    self._apply_job=self.after(1,step)
                except StopIteration as completed:
                    self._apply_iter=None;self._import_job=None;result=completed.value
                    self.refresh();self.message.configure(text=f'{result["count"]} întâlniri actualizate.'+(' Rezultat parțial. ' if not result['complete'] else ' ')+ ' · '.join(result['warnings'][:4]))
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
            self.refresh();self.message.configure(text='Actualizarea a eșuat: '+str(exc)+' · Datele locale sunt păstrate. Outlook Classic/COM este necesar; New Outlook nu suportă COM.')
        self.app.outlook.worker.submit(lambda backend:backend.read_meetings(*source,first,last),done,error,name='meeting-import',timeout_s=40)

class CalendarSourceDialog(ModalDialog):
    def __init__(self,parent,calendars):
        super().__init__(parent,'Alege sursa întâlnirilor',resizable=True,ok_text='Folosește calendarul')
        self.calendars=calendars
        ttk.Label(self.body,text='Selectare explicită, separată de calendarul rezervărilor FocusDesk. Importul este doar pentru citire.',wraplength=680).pack(fill='x')
        self.tv,wrap=make_tree(self.body,[('calendar','Calendar și sursă',680)],height=10);wrap.pack(fill='both',expand=True,pady=8)
        for i,c in enumerate(calendars):self.tv.insert('','end',iid=str(i),values=(c.label,))
        if not calendars:ttk.Label(self.body,text='Niciun calendar disponibil. Datele locale și întâlnirile manuale funcționează offline.').pack()
    def validate(self):return bool(self.tv.selection())
    def collect(self):return int(self.tv.selection()[0])

class ManualMeetingDialog(ModalDialog):
    def __init__(self,parent,app):
        super().__init__(parent,'Întâlnire manuală',resizable=True,ok_text='Creează întâlnirea')
        self.app=app;self.ws=app.ws;self.request_id=new_id()
        now=utcnow().astimezone(app.q.tz()).replace(second=0,microsecond=0)
        self.title_var=tk.StringVar();self.start=tk.StringVar(value=now.isoformat());self.end=tk.StringVar(value=(now+timedelta(hours=1)).isoformat());self.location=tk.StringVar()
        for text,var in [('Titlu',self.title_var),('Început (ISO cu fus/offset)',self.start),('Sfârșit (ISO cu fus/offset)',self.end),('Locație (opțional)',self.location)]:
            ttk.Label(self.body,text=text).pack(anchor='w',pady=(6,0));ttk.Entry(self.body,textvariable=var,width=65).pack(fill='x')
        ttk.Label(self.body,text='Context calendaristic local. Nu creează sesiune de lucru și nu exportă evenimente.',wraplength=500,style='Muted.TLabel').pack(fill='x',pady=8)
    def collect(self):
        try:
            if self.app.ws is not self.ws:raise ValueError('Workspace schimbat')
            return self.ws.meetings.manual(title=self.title_var.get(),start=parse_local_stamp(self.start.get(),self.ws.settings.timezone),
                end=parse_local_stamp(self.end.get(),self.ws.settings.timezone),location=self.location.get(),request_id=self.request_id)
        except Exception as exc:show_error(self,str(exc));return False

class ActionDialog(ModalDialog):
    def __init__(self,parent,app,mid,action=None):
        super().__init__(parent,'Acțiune rezultată',resizable=True,ok_text='Salvează acțiunea')
        self.app=app;self.ws=app.ws;self.mid=mid;self.original=action;self.aid=action.id if action else new_id()
        ttk.Label(self.body,text='Textul acțiunii').pack(anchor='w')
        self.text=tk.Text(self.body,height=5,width=62,wrap='word');self.text.pack(fill='both',expand=True)
        if action:self.text.insert('1.0',action.text)
        self.person=tk.StringVar(value=action.responsible if action else '')
        self.due=tk.StringVar(value=format_date(action.due_date) if action else '')
        self.state=tk.StringVar(value=next((k for k,v in ACTION_STATES.items() if action and v==action.state),'De clarificat'))
        for label,var in [('Responsabil (opțional; nu creează automat un task personal)',self.person),('Termen opțional',self.due)]:
            ttk.Label(self.body,text=label).pack(anchor='w',pady=(6,0));ttk.Entry(self.body,textvariable=var).pack(fill='x')
        ttk.Combobox(self.body,textvariable=self.state,values=list(ACTION_STATES),state='readonly').pack(fill='x',pady=8)
    def collect(self):
        try:
            if self.app.ws is not self.ws:raise ValueError('Workspace schimbat')
            return self.ws.meetings.save_action(self.mid,text=self.text.get('1.0','end-1c'),responsible=self.person.get(),
                due_date=parse_date(self.due.get(),self.app.q.today()),state=ACTION_STATES[self.state.get()],action_id=self.aid,expected=self.original)
        except Exception as exc:show_error(self,str(exc));return False

class MeetingNodeDialog(ModalDialog):
    def __init__(self,parent,app,mid,*,kind=Kind.TASK,text='',action=None,followup=False):
        super().__init__(parent,'Cerință nouă din întâlnire' if followup else ('Proiect din întâlnire' if kind==Kind.PROJECT else 'Task din întâlnire'),resizable=True,ok_text='Creează și leagă')
        self.app=app;self.ws=app.ws;self.mid=mid;self.kind=kind;self.action=action;self.followup=followup;self.request_id=new_id();self.source_id=None;self._creating=False
        source=self.ws.meetings.store.source(mid)
        ttk.Label(self.body,text='Întâlnire sursă: '+source.title,wraplength=620,style='Section.TLabel').pack(fill='x')
        self.title_var=tk.StringVar(value=(text.splitlines()[0] if text else '')[:300]);self.due=tk.StringVar(value=format_date(action.due_date) if action else '')
        self.priority=tk.StringVar(value=PRIORITY_LABELS[Priority.NORMAL]);self.destination=tk.StringVar();self.share=tk.BooleanVar(value=False)
        ttk.Label(self.body,text='Titlu').pack(anchor='w',pady=(8,0));self.title_entry=ttk.Entry(self.body,textvariable=self.title_var,width=70);self.title_entry.pack(fill='x')
        ttk.Label(self.body,text='Descriere · numai contextul selectat, editabil').pack(anchor='w',pady=(8,0))
        self.description=tk.Text(self.body,height=7,wrap='word',undo=True);self.description.pack(fill='both',expand=True);self.description.insert('1.0',text)
        self.choices=[]
        for label,nid in location_choices(self.ws,kind):
            try:self.ws.meetings._destination(kind,nid)
            except Exception:continue
            self.choices.append((label,nid))
        ttk.Label(self.body,text='Proiect / container').pack(anchor='w',pady=(8,0))
        self.dest_box=ttk.Combobox(self.body,textvariable=self.destination,values=[c[0] for c in self.choices],state='readonly');self.dest_box.pack(fill='x')
        if self.choices:self.destination.set(self.choices[0][0])
        ttk.Label(self.body,text='Prioritate').pack(anchor='w',pady=(8,0));ttk.Combobox(self.body,textvariable=self.priority,values=list(PRIORITY_LABELS.values()),state='readonly').pack(fill='x')
        ttk.Label(self.body,text='Termen opțional').pack(anchor='w',pady=(8,0));ttk.Entry(self.body,textvariable=self.due).pack(fill='x')
        if followup:
            self.source_label=ttk.Label(self.body,text='Alege taskul/scriptul sursă',wraplength=620);self.source_label.pack(fill='x',pady=8)
            ttk.Button(self.body,text='Task existent…',command=self.choose_task).pack(anchor='w')
            ttk.Checkbutton(self.body,text='Preia accesul la același folder de cod (Folder de cod comun)',variable=self.share).pack(anchor='w',pady=8)
        ttk.Label(self.body,text='Nu se copiază toate notițele, nu se pornește timerul și nu se creează rezervări.',wraplength=620,style='Muted.TLabel').pack(fill='x',pady=8)

    def choose_task(self):
        try:nid=NodePickerDialog(self,self.ws,'Cerință nouă pentru task/script existent',only_tasks=True).run()
        finally:self.grab_set()
        if nid:
            self.source_id=nid;source=self.ws.get(nid);self.source_label.configure(text='Cerință nouă pentru: '+source.title)
            label=next((label for label,pid in self.choices if pid==source.parent_id),None)
            self.destination.set(label or 'Alege o destinație activă')

    def collect(self):
        if self._creating:return False
        self._creating=True
        try:
            if self.app.ws is not self.ws:raise ValueError('Workspace schimbat. Ciorna rămâne în dialog.')
            if self.followup and self.source_id is None:raise ValueError('Alege explicit taskul sursă')
            destination=next((pid for label,pid in self.choices if label==self.destination.get()),...)
            if destination is ...:raise ValueError('Alege un container activ')
            return self.ws.meetings.create_node(self.mid,request_id=self.request_id,title=self.title_var.get(),description=self.description.get('1.0','end-1c'),
                kind=self.kind,parent_id=destination,priority=PRIORITY_FROM_LABEL[self.priority.get()],due_date=parse_date(self.due.get(),self.app.q.today()),
                action_id=self.action.id if self.action else None,followup_source=self.source_id,code_access='shared' if self.share.get() else 'none')
        except Exception as exc:show_error(self,str(exc));return False
        finally:self._creating=False


class MeetingLinks(ttk.Menubutton):
    """One compact contextual entry in a task/project, no fifth navigation destination."""
    def __init__(self,parent,app):
        super().__init__(parent,text='Întâlniri legate');self.app=app;self.menu=tk.Menu(self,tearoff=False);self.configure(menu=self.menu)

    def load(self,node,before):
        self.pack_forget();self.menu.delete(0,'end')
        if not node or not node.meeting_ids:return
        for mid in node.meeting_ids:
            row=self.app.ws.meetings.store.summary(mid);self.menu.add_command(label=(row['title'] if row else 'Întâlnire indisponibilă')[:90],
                command=lambda mid=mid:self.app.open_meeting(mid),state='normal' if row else 'disabled')
        self.configure(text=f'Întâlniri legate ({len(node.meeting_ids)})');self.pack(fill='x',before=before,padx=6,pady=2)
