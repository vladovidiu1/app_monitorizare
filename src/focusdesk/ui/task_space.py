"""Nonmodal central task workspace. Editors are views of the inspector's state."""
from __future__ import annotations

from ..i18n import tr

import tkinter as tk
from tkinter import ttk
from ..domain.models import Kind, CLOSED_STATUSES
from ..domain.labels import PRIORITY_LABELS, format_seconds
from .common import SessionButton, ScrollFrame, heading_width
from .markdown_editor import MarkdownEditor
from .status_visuals import node_icon, node_label
from .formats import format_date
from .navigation_controls import AdaptiveNotebook
from .identifiers import tab_id, tab_label, TabMap
from .design import C
from .tab_subtasks import SubtasksTab
from .tab_files import FilesTab
from .tab_journal import JournalTab
from .calendar_page import PlanTab
from .tab_versions import VersionsTab


def viewport(tree):
    return {'selected': tree.selection(), 'x': tree.xview()[0], 'y': tree.yview()[0]}


def restore_viewport(tree, value):
    tree.selection_set([i for i in value['selected'] if tree.exists(i)])
    tree.xview_moveto(value['x']);tree.yview_moveto(value['y'])


class TaskSpace(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(12,8))
        self.app=app;self.node_id=None;self.history=[];self.focus_layout=None
        self.positions={};self._missing_discarded=False
        self.details=app.inspector.tab_by_id('details')
        self.journal_source=app.inspector.tab_by_id('journal')
        nav=ttk.Frame(self);nav.pack(fill='x')
        ttk.Button(nav,text=tr('ui.meetings.inapoi'),command=self.back).pack(side='left')
        self.focus_btn=ttk.Button(nav,text=tr('ui.task_space.concentrare_f11'),command=self.toggle_focus)
        self.focus_btn.pack(side='right')
        self.panel_btn=ttk.Button(nav,text=tr('ui.task_space.ascunde_panoul_taskului'),command=self.toggle_panel)
        self.panel_btn.pack(side='right',padx=6)
        self.breadcrumb=ttk.Label(self,style='Crumb.TLabel',wraplength=900)
        self.breadcrumb.pack(fill='x',pady=(6,2))
        self.title=ttk.Label(self,style='Title.TLabel',wraplength=900,justify='left')
        self.title.pack(fill='x')
        self.summary=ttk.Label(self,compound='left',style='Muted.TLabel')
        self.summary.pack(fill='x',pady=(2,4))
        actions=ttk.Frame(self);actions.pack(fill='x')
        self.start_btn=SessionButton(actions,app,lambda:self.node_id);self.start_btn.pack(side='left')
        self.stop_btn=ttk.Button(actions,text=tr('ui.task_space.incheie_sesiunea'),command=app.stop_session)
        self.stop_btn.pack(side='left',padx=4)
        self.done_btn=ttk.Button(actions,command=app.toggle_done_selected);self.done_btn.pack(side='left')
        self.save_btn=ttk.Button(actions,text=tr('ui.meetings.salveaza_ctrl_s'),command=self.save)
        self.save_btn.pack(side='left',padx=4)
        more=ttk.Menubutton(actions,text=tr('ui.meetings.mai_multe'));more.pack(side='left')
        self.menu=tk.Menu(more,tearoff=False)
        for label,command in [(tr('ui.inspector.compune_e_mail'),app.compose_mail),(tr('ui.task_space.muta_proiect'),app.move_selected),
                              (tr('ui.inspector.arhiveaza_restaureaza'),app.toggle_archive_selected),
                              (tr('ui.task_space.cod_in_vs_code'),lambda:app.open_code_in_vscode(self.node_id)),
                              (tr('ui.task_space.copiaza_descrierea'),self.copy_description)]:
            self.menu.add_command(label=label,command=command)
        self.menu.add_command(label=tr('ui.app.adauga_cerinta_noua'),command=lambda:app.add_followup(self.node_id))
        self.menu.add_command(label=tr('ui.app.redeschide_cu_motiv'),command=lambda:app.reopen_with_reason(self.node_id))
        more.configure(menu=self.menu)
        from .design import wrap_actions
        wrap_actions(actions)
        self.timer_lbl=ttk.Label(self,style='Muted.TLabel');self.timer_lbl.pack(fill='x',pady=(4,0))
        self.state=ttk.Label(self,style='Muted.TLabel',wraplength=900);self.state.pack(fill='x',pady=(2,5))
        from .meetings import MeetingLinks
        self.meeting_links=MeetingLinks(self,app)
        from .followups import FollowupContext
        self.followup_context=FollowupContext(self,app);self.followup_context.pack(fill='x')
        self.body=ttk.PanedWindow(self,orient='horizontal');self.body.pack(fill='both',expand=True)
        self.editor=MarkdownEditor(self.body,source=self.details.desc,on_change=self.changed,on_save=self.save,guide_context=self.details.description_context,on_guide_applied=self.guide_applied)
        self.body.add(self.editor,weight=3)
        self.secondary=ttk.Frame(self.body,padding=(6,0))
        ttk.Label(self.secondary,text=tr('ui.tab_details.urmatorul_pas'),style='Section.TLabel').pack(anchor='w')
        self.next_entry=ttk.Entry(self.secondary,textvariable=self.details.vars['next'])
        self.next_entry.pack(fill='x',pady=(4,8))
        self.nb=AdaptiveNotebook(self.secondary);self.nb.pack(fill='both',expand=True)
        self.sections=TabMap();self.scrolls=TabMap()
        specs=[('steps',SubtasksTab,dict(drafts_from=app.inspector.tab_by_id('subtasks'),on_open=app.open_task_space,checklist_first=True)),
               ('files',FilesTab,dict(on_expand=self.widen_files)),('journal',JournalTab,dict(source_entry=self.journal_source.entry,source_kind=self.journal_source.kind_var)),
               ('planning',PlanTab,{}),('versions',VersionsTab,{})]
        for label,cls,options in specs:
            scroll=ttk.Frame(self.nb) if label=='files' else ScrollFrame(self.nb)
            self.nb.add(scroll,text=tab_label(label))
            tab=cls(scroll if label=='files' else scroll.inner,app,**options);tab.pack(fill='both',expand=True)
            if label=='steps':
                tab.check_frame.configure(text=tr('ui.task_space.checklist'))
                tab.tv.configure(displaycolumns=('title','status','progress'))
                tab.tv.column('#0',width=42,minwidth=42,stretch=False)
                tab.tv.column('title',width=180,minwidth=120,stretch=True)
                tab.tv.column('status',width=90,minwidth=80,stretch=False)
                tab.tv.column('progress',width=max(76,heading_width(tab.tv,tab.tv.heading('progress','text'))),minwidth=heading_width(tab.tv,tab.tv.heading('progress','text')),stretch=False)
            self.sections[label]=tab;self.scrolls[label]=scroll
        self.nb.bind("<<NotebookTabChanged>>",lambda event:self._load_section(),add="+")
        self.body.add(self.secondary,weight=2)
        self._split=False
        self.body.bind('<Configure>',self._size_body)
        self.bind('<Configure>',lambda e:(self.title.configure(wraplength=max(300,e.width-32)),self.breadcrumb.configure(wraplength=max(300,e.width-32)),self.state.configure(wraplength=max(300,e.width-32))))
        self.details.desc.bind('<<Modified>>',lambda e:self.update_state(),add='+')
        self.journal_source.entry.bind('<<Modified>>',lambda e:self.update_state(),add='+')
        self.details.vars['next'].trace_add('write',lambda *_:self.update_state())
        drafts=app.inspector.tab_by_id('subtasks')
        for value in (drafts.add_var,drafts.check_var): value.trace_add('write',lambda *_:self.update_state())
        self.missing_help=ttk.Label(self.secondary,text=tr('ui.task_space.task_indisponibil_foloseste_inapoi_sau_copiaza_descrierea'),style='Muted.TLabel',wraplength=300)

    @property
    def active(self):return self.app.current_view=='task_space'

    def _size_body(self,event):
        if not self._split and event.width>650:
            self._split=True;self.body.sashpos(0,max(330,event.width-365))

    def changed(self):
        self.details._desc_changed();self.update_state()

    def guide_applied(self):
        self.details._mark_dirty();self.update_state()

    def is_dirty(self):
        if self.node_id not in self.app.ws.nodes:
            return not self._missing_discarded and (self.details.is_dirty() or self.journal_source.is_dirty())
        return self.app.inspector.is_dirty()

    def save(self):
        if not self.app.ws or self.node_id not in self.app.ws.nodes:
            self.state.configure(text=tr('ui.task_space.taskul_nu_mai_exista_copiaza_descrierea_inainte_de_a_renunta_la_ciorna'),foreground=C.danger)
            return False
        if self.app.ws.read_only:return False
        self.remember_position()
        ok=self.app.inspector.save()
        if ok:
            self.state.configure(text=tr('ui.tab_details.salvat'),foreground=C.success)
            self.refresh()
            self.restore_position()
        else:self.state.configure(text=tr('ui.task_space.salvarea_a_esuat_ciorna_este_pastrata'),foreground=C.danger)
        return ok

    def update_state(self):
        if not self.node_id or not self.app.ws:return
        if self.node_id not in self.app.ws.nodes:return
        if self.app.ws.read_only:text=tr('ui.meetings.doar_citire');color=C.muted
        elif self.is_dirty():text=tr('ui.task_space.modificari_nesalvate_ctrl_s');color=C.warning
        else:text=tr('ui.tab_details.salvat');color=C.muted
        self.state.configure(text=text,foreground=color)

    def copy_description(self):
        self.clipboard_clear();self.clipboard_append(self.editor.get())
        self.state.configure(text=tr('ui.task_space.descriere_copiata'),foreground=C.success)

    def discard_missing(self):
        self._missing_discarded=True
        self.details._dirty=False;self.details._orig_desc=self.editor.get()
        self.journal_source.entry.configure(state='normal')
        self.journal_source.entry.delete('1.0','end')

    def remember_position(self):
        if self.node_id:
            self.positions[self.node_id]={'edit':self.editor.text.yview()[0],
                'insert':self.editor.text.index('insert'),
                'section':self.nb.index(self.nb.select())}

    def restore_position(self):
        value=self.positions.get(self.node_id)
        if value:
            self.nb.select(value['section'])
            self.editor.text.yview_moveto(value['edit'])
            self.editor.text.mark_set('insert',value['insert'])

    def layout(self):
        p=self.app.paned
        return {'panes':p.panes(),'sashes':[p.sashpos(i) for i in range(len(p.panes())-1)],
                'show':self.app.config.show_inspector,'left':self.app.config.sash_left,'right':self.app.config.sash_right}

    def restore_layout(self,value):
        self.app._layout_generation += 1
        p=self.app.paned;widgets={str(w):w for w in (self.app.sidebar,self.app.center,self.app.inspector)}
        for item in p.panes():p.forget(item)
        for item in value['panes']:p.add(widgets[item],weight=1 if widgets[item] is self.app.center else 0)
        p.update_idletasks()
        for i,pos in enumerate(value['sashes']):p.sashpos(i,pos)
        p.update_idletasks()
        self.app.config.show_inspector=value['show'];self.app.inspector_var.set(value['show'])
        self.app.config.sash_left=value['left'];self.app.config.sash_right=value['right']

    def toggle_panel(self):
        if str(self.secondary) in self.body.panes():self.body.forget(self.secondary)
        else:
            self.body.add(self.secondary,weight=2)
            self._load_section()
            self.body.sashpos(0,max(330,self.body.winfo_width()-365))
        self.panel_btn.configure(text=tr('ui.task_space.ascunde_panoul_taskului') if str(self.secondary) in self.body.panes() else tr('ui.task_space.arata_panoul_taskului'))

    def widen_files(self):
        if str(self.secondary) not in self.body.panes(): self.toggle_panel()
        if len(self.body.panes()) > 1:
            self.body.sashpos(0, max(280, int(self.body.winfo_width() * .35)))

    def toggle_focus(self):
        if self.focus_layout is not None:
            self.exit_focus();return
        self.focus_layout={**self.layout(),'panel':str(self.secondary) in self.body.panes(),
                           'split':self.body.sashpos(0) if len(self.body.panes())>1 else None,
                           'section':self.nb.index(self.nb.select())}
        for widget in (self.app.sidebar,self.app.inspector):
            if str(widget) in self.app.paned.panes():self.app.paned.forget(widget)
        if str(self.secondary) not in self.body.panes():self.toggle_panel()
        self.nb.select(0)
        self.focus_btn.configure(text=tr('ui.task_space.iesi_din_concentrare_f11'))

    def exit_focus(self):
        value=self.focus_layout
        if value is None:return
        self.focus_layout=None;self.restore_layout(value)
        if value['panel'] != (str(self.secondary) in self.body.panes()):self.toggle_panel()
        if value['split'] is not None and len(self.body.panes())>1:self.body.sashpos(0,value['split'])
        self.nb.select(value['section']);self.focus_btn.configure(text=tr('ui.task_space.concentrare_f11'))

    def snapshot(self):
        app=self.app
        return {'view':app.current_view,'scope':app.current_scope,'selected':app.selected_id,'layout':self.layout(),
            'task_list':viewport(app.tasklist.tv),'sidebar':viewport(app.sidebar.tree),
            'calendar':viewport(app.calendar_page.tv),'today':app.today.sf.canvas.yview()[0],
            'filters':{name:getattr(app.tasklist,name).get() for name in ('status_var','prio_var','due_var','proj_var','requester_var','text_var','closed_var')},
            'focus':dict(self.focus_layout) if self.focus_layout is not None else None,
            'inspector_tab':app.inspector.current_tab_id()}

    def open(self,node_id):
        app=self.app
        if not app.ws or node_id not in app.ws.nodes or app.ws.get(node_id).kind!=Kind.TASK:return False
        if self.details.expanded is not None and self.details.expanded.winfo_exists():
            self.details.expanded.lift();return False
        same=app.inspector.node_id==node_id
        if not same and not app.confirm_leave():return False
        if self.active and self.node_id==node_id:return True
        if self.active:self.remember_position()
        self.history.append(self.snapshot())
        app.current_view='task_space';app.current_scope=None;app.selected_id=node_id
        app.inspector.load(node_id,keep_dirty=same)
        self.node_id=node_id;self._missing_discarded=False
        app.config.last_view='tasks'
        app.sidebar.select_view('task_space')
        app._show_center(self);self.refresh();self.restore_position()
        return True

    def back(self):
        target=self.history[-1] if self.history else None
        same=target is not None and target['selected']==self.node_id and target['view']!='task_space' and self.node_id in self.app.ws.nodes
        if not same and not self.app.confirm_leave():return False
        self.remember_position();self.exit_focus()
        value=self.history.pop() if self.history else None
        if value is None:
            self.app.show_view('tasks');return True
        app=self.app
        app.current_view=value['view'];app.current_scope=value['scope'] if value['scope'] in app.ws.nodes else None
        app.selected_id=value['selected'] if value['selected'] in app.ws.nodes else None
        if (app.current_view.startswith('tree:') and app.current_scope is None) or (app.current_view=='task_space' and app.selected_id is None):
            app.current_view='tasks'
        for name,setting in value['filters'].items():getattr(app.tasklist,name).set(setting)
        app.inspector.load(app.selected_id,keep_dirty=same)
        if app.current_view=='task_space':
            self.node_id=value['selected']
        else:self.node_id=None
        app._reload_center()
        app.sidebar.select_view(app.current_view)
        restore_viewport(app.tasklist.tv,value['task_list']);restore_viewport(app.sidebar.tree,value['sidebar'])
        restore_viewport(app.calendar_page.tv,value['calendar']);app.today.sf.canvas.yview_moveto(value['today'])
        app.inspector.show_tab(value['inspector_tab']);self.restore_layout(value['layout'])
        if self.active:
            self.focus_layout=value['focus']
            self.focus_btn.configure(text=tr('ui.task_space.iesi_din_concentrare_f11') if self.focus_layout is not None else tr('ui.task_space.concentrare_f11'))
            self.restore_position()
        return True

    def leave_route(self):
        self.remember_position();self.exit_focus();self.history.clear();self.node_id=None

    def refresh(self):
        if not self.active or not self.node_id:return
        app=self.app;node=app.ws.nodes.get(self.node_id)
        if node is None:
            self.title.configure(text=tr('ui.meetings.task_indisponibil'))
            self.state.configure(text=tr('ui.task_space.taskul_a_fost_sters_sau_mutat_in_cos_ciorna_ramane_disponibila_in_mai'),foreground=C.danger)
            self.editor.set_read_only(True);self.next_entry.configure(state='disabled')
            for b in (self.start_btn,self.stop_btn,self.done_btn,self.save_btn):b.state(['disabled'])
            self.meeting_links.pack_forget()
            self.followup_context.pack_forget()
            self.menu.entryconfigure(5,state='disabled');self.menu.entryconfigure(6,state='disabled')
            self.nb.pack_forget();self.missing_help.pack(fill='x',pady=12)
            for i in range(4):self.menu.entryconfigure(i,state='disabled')
            return
        self.missing_help.pack_forget();self.nb.pack(fill='both',expand=True)
        if app.inspector.node_id != node.id:
            # Restore a task that reappeared without losing its retained draft.
            if self.details.node_id == node.id:app.inspector.node_id=node.id
            app.inspector.load(node.id,keep_dirty=True)
            app.selected_id=node.id
        self.menu.entryconfigure(0,state='normal');self.menu.entryconfigure(3,state='normal')
        self.title.configure(text=node.title)
        self.breadcrumb.configure(text=' › '.join(n.title for n in [*app.ws.ancestors(node.id),node]))
        self.summary.configure(text=tr('ui.task_space.task_summary', node_label_node=node_label(node), priority_labels_get_node_priority=PRIORITY_LABELS.get(node.priority, ""), format_date_app_q_due_day_node_or_fara_termen=format_date(app.q.due_day(node)) or tr('ui.inspector.fara_termen'))+(tr('extra.ui.task_space.arhivat') if app.q.is_archived(node) else ''),image=node_icon(self,node))
        ro=app.ws.read_only
        self.meeting_links.load(node,self.body)
        self.followup_context.pack(fill='x',before=self.body);self.followup_context.load(node)
        self.menu.entryconfigure(5,state='disabled' if ro else 'normal')
        self.menu.entryconfigure(6,state='normal' if not ro and node.status in CLOSED_STATUSES else 'disabled')
        self.editor.set_read_only(ro);self.next_entry.configure(state='disabled' if ro else 'normal')
        self.save_btn.state(['disabled'] if ro else ['!disabled']);self.done_btn.state(['disabled'] if ro else ['!disabled'])
        self.done_btn.configure(text=tr('ui.task_space.redeschide') if node.status in CLOSED_STATUSES else tr('ui.inspector.finalizeaza'))
        self.menu.entryconfigure(1,state='disabled' if ro else 'normal');self.menu.entryconfigure(2,state='disabled' if ro else 'normal')
        if not self.details.is_dirty():self.editor.clear_guide_notice()
        self._load_section()
        self.update_state();self.update_timer()

    def _load_section(self):
        if not self.active or not self.node_id or self.node_id not in self.app.ws.nodes: return
        selected = self.nb.select()
        for label, tab in self.sections.items():
            if str(self.scrolls[label]) != selected: continue
            if tab.node_id == self.node_id and tab.is_dirty(): return
            node = self.app.ws.get(self.node_id)
            tab.load(node)
            if label == 'steps': tab.check_tv.configure(height=max(1,min(5,len(node.checklist))))

    def update_timer(self):
        if not self.active or not self.app.ws:return
        t=self.app.timer
        self.start_btn.update_state()
        if self.node_id not in self.app.ws.nodes:self.start_btn.state(['disabled'])
        active=bool(t and t.active)
        self.stop_btn.state(['!disabled'] if active and not self.app.ws.read_only else ['disabled'])
        if active:
            node=self.app.ws.nodes.get(t.node_id)
            self.timer_lbl.configure(text=tr('ui.task_space.timer_summary', in_lucru_if_t_running_else_in_pauza=tr('ui.session_ui.in_lucru') if t.running else tr('ui.session_ui.in_pauza'), node_title_if_node_else_task=node.title if node else tr('ui.outlook_ui.task'), format_seconds_t_seconds=format_seconds(t.seconds)))
        else:self.timer_lbl.configure(text=tr('ui.session_ui.nicio_sesiune_de_lucru_pornita'))
