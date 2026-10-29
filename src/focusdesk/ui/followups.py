"""Compact requirement context and explicit, draft-preserving later-request dialogs."""

from ..i18n import tr
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from ..domain.common import new_id
from ..domain.models import Kind, CLOSED_STATUSES
from ..domain.labels import PRIORITY_LABELS, PRIORITY_FROM_LABEL, STATUS_LABELS, format_seconds
from ..errors import FocusDeskError, CycleError
from .description_guide import NestedModal
from .common import ScrollFrame, make_tree, Tooltip
from .colleagues_ui import ColleagueField
from .design import C, px
from .formats import parse_date, format_date
from .tree_rows import sync_rows


class FollowupContext(ttk.Frame):
    """Two compact rows; the native menu exposes dated, keyboard-navigable requests."""
    def __init__(self,parent,app):
        super().__init__(parent,padding=(6,2));self.app=app;self.node_id=None
        self.columnconfigure(0,weight=1)
        self.source_btn=ttk.Button(self,style='Quiet.TButton');self.source_tip=Tooltip(self.source_btn,'');self.source_btn.grid(row=0,column=0,columnspan=3,sticky='w')
        self.root_btn=ttk.Button(self,style='Quiet.TButton');self.root_tip=Tooltip(self.root_btn,'');self.root_btn.grid(row=1,column=0,columnspan=3,sticky='w')
        self.time_lbl=ttk.Label(self,style='Muted.TLabel');self.time_lbl.grid(row=2,column=0,sticky='w')
        self.children_btn=ttk.Menubutton(self,text=tr('ui.followups.cerinte_ulterioare'))
        self.children_btn.grid(row=2,column=1,sticky='e')
        self.children_menu=tk.Menu(self.children_btn,tearoff=False);self.children_btn.configure(menu=self.children_menu)
        self.total_btn=ttk.Button(self,text=tr('ui.followups.total_lant'),style='Quiet.TButton',command=self.show_total)
        self.total_btn.grid(row=2,column=2,sticky='e')
        self.total_lbl=ttk.Label(self,text='',style='Muted.TLabel',wraplength=400);self.total_lbl.grid(row=3,column=0,columnspan=3,sticky='ew')
        self.total_lbl.grid_remove()
        self.bind('<Configure>',self.layout)

    def layout(self,event=None):
        compact=self.winfo_width()<self.time_lbl.winfo_reqwidth()+self.children_btn.winfo_reqwidth()+self.total_btn.winfo_reqwidth()+20
        self.time_lbl.grid_configure(row=2,column=0,columnspan=3 if compact else 1)
        self.children_btn.grid_configure(row=3 if compact else 2,column=0 if compact else 1,columnspan=2 if compact else 1,sticky='w' if compact else 'e')
        self.total_btn.grid_configure(row=3 if compact else 2)
        if self.total_lbl.cget('text'):self.total_lbl.grid_configure(row=4 if compact else 3)

    def load(self,node):
        self.node_id=node.id;ws=self.app.ws
        children=ws.followups.children(node.id)
        if node.kind!=Kind.TASK or not (children or node.continuation_of):self.pack_forget();return
        source=ws.nodes.get(node.continuation_of)
        if node.continuation_of:
            title=source.title if source else tr('ui.followups.task_indisponibil', node_continuation_of_8=node.continuation_of[:8])
            self.source_tip.text=title
            self.source_btn.configure(text=tr('ui.tab_journal.continuare_a')+(title[:28]+'…' if len(title)>28 else title),command=lambda:self.open_node(node.continuation_of))
            self.source_btn.state(['!disabled'] if source else ['disabled']);self.source_btn.grid()
        else:self.source_btn.grid_remove()
        try:lineage=ws.followups.lineage(node.id)
        except CycleError:lineage=[node.id]
        if len(lineage)>2:
            root_id=lineage[-1];root=ws.nodes.get(root_id)
            self.root_btn.configure(text=tr('ui.followups.task_initial')+(root.title[:28] if root else tr('common.unavailable')),command=lambda:self.open_node(root_id))
            self.root_btn.state(['!disabled'] if root else ['disabled']);self.root_btn.grid()
        else:self.root_btn.grid_remove()
        self.time_lbl.configure(text=tr('ui.followups.saved_own_time',duration=format_seconds(ws.followups.own_seconds(node.id))))
        self.children_btn.configure(text=tr('ui.followups.cerinte_ulterioare_2', len_children=len(children)))
        self.children_menu.delete(0,'end')
        for child in children:
            title=child.title[:55]+('…' if len(child.title)>55 else '')
            self.children_menu.add_command(label=title+' · '+format_date(child.created_at.astimezone(self.app.q.tz()).date())+' · '+STATUS_LABELS[child.status],command=lambda nid=child.id:self.open_node(nid))
        if children:self.children_menu.add_separator()
        self.children_menu.add_command(label=tr('ui.app.adauga_cerinta_noua'),command=lambda:self.app.add_followup(self.node_id),state='disabled' if ws.read_only else 'normal')
        self.total_lbl.configure(text='');self.total_lbl.grid_remove()
        self.layout()

    def open_node(self,nid):
        if self.app.ws and nid in self.app.ws.nodes:self.app.select_node(nid,reveal=True)

    def show_total(self):
        try:
            ids=self.app.ws.followups.family_ids(self.node_id);totals=self.app.ws.repo.sessions.worked_totals()
            self.total_lbl.configure(text=tr('ui.followups.total_lant_salvat_sesiuni_numarate_o_data')+format_seconds(sum(totals.get(nid,0) for nid in ids)))
        except FocusDeskError as exc:self.total_lbl.configure(text=str(exc))
        self.total_lbl.grid()


class FollowupDialog(NestedModal):
    def __init__(self,app,source_id):
        super().__init__(app.root)
        self.app=app;self.ws=app.ws;self.source_id=source_id;self.request_id=new_id();self.created=None;self._creating=False
        source=self.ws.get(source_id)
        self.title(tr('ui.followups.adauga_cerinta_noua'));self._focusdesk_sized=True
        self.geometry(f'{min(px(self,780),self.winfo_screenwidth()-40)}x{min(px(self,740),self.winfo_screenheight()-80)}')
        self.minsize(px(self,520),px(self,400));self.resizable(True,True)
        ttk.Label(self,text=tr('ui.meetings.cerinta_noua_pentru')+source.title,style='Section.TLabel',wraplength=px(self,700),padding=12).pack(fill='x')
        footer=ttk.Frame(self,padding=10);footer.pack(side='bottom',fill='x');footer.columnconfigure(0,weight=1)
        self.message=ttk.Label(footer,text=tr('ui.followups.task_independent_sursa_si_munca_ei_raman_intacte'),style='Muted.TLabel',wraplength=px(self,700));self.message.grid(row=0,column=0,columnspan=2,sticky='ew',pady=6)
        self.create_btn=ttk.Button(footer,text=tr('ui.followups.creeaza_cerinta'),style='Primary.TButton',command=self.create);self.create_btn.grid(row=1,column=0,sticky='e',padx=6)
        ttk.Button(footer,text=tr('ui.outlook_ui.inchide'),command=self.close).grid(row=1,column=1)
        self.sf=ScrollFrame(self);self.sf.pack(fill='both',expand=True,padx=12)
        form=self.sf.inner;form.columnconfigure(0,weight=1)
        self.title_var=tk.StringVar();self.priority=tk.StringVar(value=tr('ui.followups.nespecificata'));self.due=tk.StringVar()
        self.dest=tk.StringVar();self.code_access=tk.StringVar(value='none');self.code_folder=tk.StringVar()
        self.copy_description=tk.BooleanVar(value=False);self.copy_checklist=tk.BooleanVar(value=False)
        ttk.Label(form,text=tr('ui.followups.titlul_cerintei_noi')).pack(anchor='w');self.title_entry=ttk.Entry(form,textvariable=self.title_var);self.title_entry.pack(fill='x')
        ttk.Label(form,text=tr('ui.followups.descrierea_solicitarii')).pack(anchor='w',pady=(8,0));self.description=tk.Text(form,height=6,wrap='word',undo=True);self.description.pack(fill='x')
        ttk.Label(form,text=tr('ui.followups.solicitant')).pack(anchor='w',pady=(8,0));self.requester=ColleagueField(form,lambda:self.ws);self.requester.pack(fill='x')
        row=ttk.Frame(form);row.pack(fill='x',pady=8)
        ttk.Label(row,text=tr('ui.meetings.prioritate')).grid(row=0,column=0,sticky='w');ttk.Combobox(row,textvariable=self.priority,values=[tr('ui.followups.nespecificata'),*PRIORITY_LABELS.values()],state='readonly',width=18).grid(row=1,column=0,padx=(0,12))
        ttk.Label(row,text=tr('ui.followups.termen_optional_zz_ll_aaaa')).grid(row=0,column=1,sticky='w');ttk.Entry(row,textvariable=self.due,width=16).grid(row=1,column=1)
        ttk.Label(form,text=tr('ui.followups.destinatie_langa_taskul_sursa_implicit')).pack(anchor='w')
        self.destinations={tr('ui.followups.radacina_workspace_ului'):None}
        for node in sorted(self.ws.nodes.values(),key=lambda n:n.title.casefold()):
            if node.id==source_id:continue
            try:self.ws.followups.validate_destination(node.id)
            except FocusDeskError:continue
            self.destinations[node.title+' · '+node.id[:8]]=node.id
        default=next((label for label,nid in self.destinations.items() if nid==source.parent_id),tr('ui.meetings.alege_o_destinatie_activa'))
        self.dest.set(default)
        ttk.Combobox(form,textvariable=self.dest,values=list(self.destinations),state='readonly').pack(fill='x')
        ttk.Label(form,text=tr('ui.followups.preluare_explicita_din_datele_salvate_ale_sursei'),style='Section.TLabel').pack(anchor='w',pady=(10,2))
        ttk.Checkbutton(form,text=tr('ui.followups.preia_descrierea_sursei_inaintea_noii_solicitari'),variable=self.copy_description).pack(anchor='w')
        ttk.Checkbutton(form,text=tr('ui.followups.preia_checklistul_cu_toate_elementele_nebifate'),variable=self.copy_checklist).pack(anchor='w')
        for value,label in [('none',tr('ui.followups.nu_prelua_accesul_la_cod')),('shared',tr('ui.followups.acelasi_folder_de_cod_folder_de_cod_comun')),('folder',tr('ui.followups.alege_alt_folder_de_cod'))]:
            ttk.Radiobutton(form,text=label,variable=self.code_access,value=value).pack(anchor='w',pady=2)
        pick=ttk.Frame(form);pick.pack(fill='x');ttk.Entry(pick,textvariable=self.code_folder).pack(side='left',fill='x',expand=True)
        ttk.Button(pick,text=tr('ui.followups.alege_folder'),command=self.choose_folder).pack(side='left')
        self.source_note=ttk.Label(form,style='Muted.TLabel',wraplength=px(self,690));self.source_note.pack(fill='x',pady=8)
        try:
            src=app.files.effective_source(source_id)
            text=(tr('ui.followups.cod_asociat_sursei')+str(src.path)+(tr('ui.followups.folderul_nu_mai_exista_alege_alt_folder_sau_creeaza_fara_acces') if not src.path.is_dir() else tr('ui.followups.scripturile_nu_se_copiaza'))) if src else tr('ui.followups.sursa_nu_are_folder_de_cod_poti_alege_un_folder_nou_sau_crea_fara_acce')
        except FocusDeskError as exc:text=str(exc)+tr('ui.followups.poti_alege_alt_folder_fara_sa_pierzi_cerinta')
        self.source_note.configure(text=text)
        self.bind('<Escape>',self.close);self.protocol('WM_DELETE_WINDOW',self.close)
        self.grab_set();self.title_entry.focus_set()

    def choose_folder(self):
        try:folder=filedialog.askdirectory(parent=self,title=tr('ui.followups.alege_folderul_de_cod'))
        finally:self.grab_set()
        if folder:self.code_folder.set(folder);self.code_access.set('folder')

    def create(self):
        if self._creating:return None
        if self.created is not None:return self.created
        self._creating=True;self.create_btn.state(['disabled'])
        try:
            if self.app.ws is not self.ws or self.ws.read_only:raise ValueError(tr('ui.followups.workspace_schimbat_sau_doar_pentru_citire_ciorna_ramane_aici'))
            if self.dest.get() not in self.destinations:raise ValueError(tr('ui.followups.alege_explicit_o_destinatie_activa'))
            task=self.ws.create_followup(self.source_id,title=self.title_var.get(),description=self.description.get('1.0','end-1c'),
                requested_by=self.requester.person,priority=PRIORITY_FROM_LABEL.get(self.priority.get()),due_date=parse_date(self.due.get(),self.app.q.today()),
                parent_id=self.destinations[self.dest.get()],copy_description=self.copy_description.get(),copy_checklist=self.copy_checklist.get(),
                code_access=self.code_access.get(),code_folder=self.code_folder.get() or None,request_id=self.request_id)
            self.created=task
            self.freeze_form(self.sf.inner)
            self.message.configure(text=tr('ui.followups.cerinta_creata_taskul_sursa_nu_a_fost_redeschis_sau_modificat'),foreground=C.success)
            self.create_btn.configure(text=tr('ui.followups.deschide_cerinta'),command=self.open_created)
            return task
        except Exception as exc:
            self.message.configure(text=str(exc),foreground=C.danger)
            return None
        finally:self._creating=False;self.create_btn.state(['!disabled'])

    def freeze_form(self,widget):
        if isinstance(widget,tk.Text):widget.configure(state='disabled')
        elif isinstance(widget,(ttk.Entry,ttk.Combobox,ttk.Checkbutton,ttk.Radiobutton,ttk.Button)):widget.state(['disabled'])
        for child in widget.winfo_children():self.freeze_form(child)

    def open_created(self):
        nid=self.created.id;self.close();self.app.select_node(nid,reveal=True)

    def close(self,event=None):
        self.app.followup_dialog=None;self.close_modal();return 'break'


class ReopenReasonDialog(NestedModal):
    def __init__(self,app,node_id):
        super().__init__(app.root);self.app=app;self.ws=app.ws;self.node_id=node_id
        self.title(tr('ui.app.redeschide_taskul'));self.geometry('620x300');self.resizable(True,True)
        ttk.Label(self,text=tr('ui.followups.motivul_redeschiderii_optional_continui_cerinta_initiala_nu_creezi_un'),wraplength=560,padding=12).pack(fill='x')
        self.reason=tk.Text(self,height=5,wrap='word');self.reason.pack(fill='both',expand=True,padx=12)
        self.error=ttk.Label(self,foreground=C.danger,wraplength=560);self.error.pack(fill='x',padx=12)
        ttk.Button(self,text=tr('ui.app.redeschide_taskul'),command=self.apply).pack(side='right',padx=12,pady=8)
        ttk.Button(self,text=tr('ui.meetings.anuleaza'),command=self.close_modal).pack(side='right',padx=6)
        self.bind('<Escape>',lambda e:self.close_modal());self.protocol('WM_DELETE_WINDOW',self.close_modal)
        self.grab_set();self.reason.focus_set()

    def apply(self):
        try:
            if self.ws is not self.app.ws:raise ValueError(tr('ui.followups.workspace_schimbat'))
            self.ws.reopen_task(self.node_id,self.reason.get('1.0','end-1c'))
            self.close_modal();self.app.refresh_all()
        except Exception as exc:self.error.configure(text=str(exc))
