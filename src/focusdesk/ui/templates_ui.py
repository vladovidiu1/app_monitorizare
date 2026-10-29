"""Local template dialogs: no background services, network, or content execution."""
from __future__ import annotations

from ..i18n import tr
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ..domain.common import new_id
from ..domain.models import Kind, Priority
from ..domain.labels import KIND_LABELS, PRIORITY_LABELS
from ..domain.templates import StructureTemplate, TemplateItem, EXCLUDED
from ..services.templates import digest
from .common import ScrollFrame
from .markdown_editor import MarkdownEditor
from .design import icon

class TemplateWindow(tk.Toplevel):
    def __init__(self,app,title):
        super().__init__(app.root);self.app=app;self.ws=app.ws
        self.title(title);self.geometry('1060x780');self.minsize(850,620)
        self.transient(app.root)
        self.error=tk.StringVar()
        ttk.Label(self,textvariable=self.error,style='Muted.TLabel',wraplength=950).pack(side='bottom',fill='x',padx=12,pady=6)
    def current(self):
        if self.app.ws is not self.ws or self.ws is None:raise ValueError(tr('ui.templates_ui.workspace_ul_s_a_schimbat_inchide_si_redeschide_dialogul'))
    def attempt(self,action):
        try:self.current();self.error.set('');return action()
        except Exception as exc:self.error.set(str(exc));return None

class TemplatePreview(ttk.PanedWindow):
    def __init__(self,parent):
        super().__init__(parent,orient='horizontal')
        left=ttk.Frame(self);self.add(left,weight=1)
        self.tree=ttk.Treeview(left,show='tree',selectmode='browse')
        self.tree.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview);bar.pack(side='right',fill='y');self.tree.configure(yscrollcommand=bar.set)
        detail=ttk.Frame(self);self.add(detail,weight=2)
        self.text=tk.Text(detail,wrap='word',state='disabled',width=45,padx=10,pady=8)
        self.text.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(detail,orient='vertical',command=self.text.yview);scrollbar.pack(side='right',fill='y')
        self.text.configure(yscrollcommand=scrollbar.set);self.tree.bind('<<TreeviewSelect>>',self.show_item)
        self.template=None
    def load(self,template):
        self.template=template;self.tree.delete(*self.tree.get_children())
        for item in template.ordered():
            self.tree.insert(item.parent or '', 'end',iid=item.key,text=item.title,open=True,image=icon(self,'status-todo' if item.kind==Kind.TASK else item.kind.value))
        self.tree.selection_set(template.root.key);self.show_item()
    def show_item(self,event=None):
        if not self.template or not self.tree.selection():return
        item=next(i for i in self.template.items if i.key==self.tree.selection()[0])
        text=(tr('ui.templates_ui.tip_cheie_prioritate_estimare_etichete_urmatorul_pas_depinde_de_legatu', item_title=item.title, item_kind_value=KIND_LABELS[item.kind], item_key=item.key, item_priority_or_normal=PRIORITY_LABELS[item.priority or Priority.NORMAL], _estimated_minutes_is_not_none_else_neestimat=item.estimated_minutes if item.estimated_minutes is not None else tr("ui.planning.neestimat"), join_item_tags=", ".join(item.tags), item_next_action_or=item.next_action or "—", join_item_depends_on_or=", ".join(item.depends_on) or "—", join_item_related_or=", ".join(item.related) or "—", item_description=item.description)+ '\n'.join('☐ '+c for c in item.checklist))
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',text);self.text.configure(state='disabled')

def exclusion(parent):
    ttk.Label(parent,text=tr('ui.templates_ui.nu_se_copiaza')+EXCLUDED,style='Muted.TLabel',wraplength=980,justify='left').pack(fill='x',padx=12,pady=8)

class CreateTemplateDialog(TemplateWindow):
    def __init__(self,app,selected=None):
        super().__init__(app,tr('ui.templates_ui.creeaza_din_sablon'))
        self.request_id=new_id();self.created=None;self.preview_signature=None
        self.catalog=self.ws.templates.catalog();self.by_name={tr('ui.templates_ui.template_choice', t_name=t.name, implicit_if_builtin_else_personal=tr('template.builtin') if builtin else tr('template.personal'), t_id_8=t.id[:8]):t for t,builtin in self.catalog}
        top=ttk.Frame(self,padding=12);top.pack(fill='x')
        self.choice=tk.StringVar();self.title_var=tk.StringVar();self.dest=tk.StringVar(value=tr('ui.followups.radacina_workspace_ului'))
        ttk.Label(top,text=tr('ui.planning.sablon')).grid(row=0,column=0,sticky='w')
        self.combo=ttk.Combobox(top,textvariable=self.choice,values=list(self.by_name),state='readonly');self.combo.grid(row=0,column=1,sticky='ew',pady=4)
        self.combo.bind('<<ComboboxSelected>>',lambda e:self.choose())
        ttk.Label(top,text=tr('ui.templates_ui.titlu_nou')).grid(row=1,column=0,sticky='w');self.title_entry=ttk.Entry(top,textvariable=self.title_var);self.title_entry.grid(row=1,column=1,sticky='ew',pady=4)
        ttk.Label(top,text=tr('ui.templates_ui.destinatie')).grid(row=2,column=0,sticky='w');self.dest_combo=ttk.Combobox(top,textvariable=self.dest,state='readonly');self.dest_combo.grid(row=2,column=1,sticky='ew',pady=4);top.columnconfigure(1,weight=1)
        self.variable_scroll=ScrollFrame(self);self.variable_scroll.pack(fill='x',padx=12)
        self.variable_scroll.pack_propagate(False);self.fields=self.variable_scroll.inner;self.values={}
        actions=ttk.Frame(self,padding=(12,6));self.actions=actions;actions.pack(fill='x')
        self.preview_btn=ttk.Button(actions,text=tr('ui.templates_ui.actualizeaza_previzualizarea'),command=lambda:self.attempt(self.preview));self.preview_btn.pack(side='left')
        self.create_btn=ttk.Button(actions,text=tr('ui.templates_ui.creeaza_structura'),command=lambda:self.attempt(self.create));self.create_btn.pack(side='right');self.create_btn.state(['disabled'])
        exclusion(self)
        self.preview_widget=TemplatePreview(self);self.preview_widget.pack(fill='both',expand=True,padx=12,pady=6)
        name=next((name for name,t in self.by_name.items() if selected and t.id==selected.id),next(iter(self.by_name),''))
        self.choice.set(name);self.choose()
    def choose(self):
        template=self.by_name[self.choice.get()];self.title_var.set(template.root.title)
        for child in self.fields.winfo_children():child.destroy()
        self.values={}
        for index,name in enumerate(template.variables):
            var=tk.StringVar();self.values[name]=var
            ttk.Label(self.fields,text=tr('template.variable.'+name) if any(t.id==template.id and builtin for t,builtin in self.catalog) else name).grid(row=index,column=0,sticky='w',padx=(0,12))
            ttk.Entry(self.fields,textvariable=var).grid(row=index,column=1,sticky='ew',pady=2)
        self.fields.columnconfigure(1,weight=1)
        self.variable_scroll.configure(height=min(5,len(template.variables))*36+4)
        if template.variables:self.variable_scroll.pack(fill='x',padx=12,before=self.actions)
        else:self.variable_scroll.pack_forget()
        self.destinations={tr('ui.followups.radacina_workspace_ului'):None}
        for node in self.ws.nodes.values():
            try:self.ws.check_parent(template.root.kind,node.id)
            except Exception:continue
            self.destinations[tr('ui.templates_ui.destination_choice', self_ws_breadcrumb_node_id=self.ws.breadcrumb(node.id), node_id_8=node.id[:8])]=node.id
        self.dest_combo.configure(values=list(self.destinations));self.dest.set(tr('ui.followups.radacina_workspace_ului'))
        preferred=self.app.selected_id
        for label,value in self.destinations.items():
            if preferred and value==preferred:self.dest.set(label)
        self.preview_widget.load(template);self.preview_signature=None;self.create_btn.state(['disabled'])
        self.error.set(tr('ui.templates_ui.completeaza_variabilele_apoi_actualizeaza_previzualizarea') if template.variables else tr('ui.templates_ui.previzualizeaza_inainte_de_creare'))
    def options(self):
        return {'title':self.title_var.get(),'parent_id':self.destinations[self.dest.get()],'values':{name:v.get() for name,v in self.values.items()}}
    def signature(self,expanded):return (digest(expanded.model_copy(update={'id':self.by_name[self.choice.get()].id})),self.options()['parent_id'])
    def preview(self):
        template=self.by_name[self.choice.get()];expanded=self.ws.templates.preview(template,**self.options())
        self.preview_widget.load(expanded);self.preview_signature=self.signature(expanded)
        if not self.ws.read_only:
            self.create_btn.state(['!disabled']);self.error.set(tr('ui.templates_ui.previzualizare_actualizata_taskurile_vor_porni_de_facut_checklisturile'))
        else:self.error.set(tr('ui.templates_ui.workspace_doar_pentru_citire_crearea_nu_este_permisa'))
        return expanded
    def create(self):
        if self.created is not None:return self.created
        self.current()
        template=self.by_name[self.choice.get()];expanded=self.ws.templates.preview(template,**self.options())
        if self.signature(expanded)!=self.preview_signature:raise ValueError(tr('ui.templates_ui.datele_s_au_schimbat_actualizeaza_previzualizarea_inainte_de_creare'))
        self.create_btn.state(['disabled'])
        try:self.created=self.ws.create_from_template(template,**self.options(),request_id=self.request_id)
        except Exception: self.error.set(tr('ui.templates_ui.crearea_a_esuat_consulta_mesajul_de_eroare_redeschide_dialogul_pentru'));raise
        self.app.refresh_all()
        # Stay in the dialog with an explicit successful result; no surprise navigation or second creation.
        self.error.set(tr('ui.templates_ui.creat_structura_a_fost_salvata_integral', self_created_title=self.created.title))
        self.create_btn.configure(text=tr('ui.templates_ui.creat'),command=lambda:None)
        for widget in (self.combo,self.title_entry,self.dest_combo,self.preview_btn):widget.state(['disabled'])
        for widget in self.fields.winfo_children():
            if isinstance(widget,ttk.Entry):widget.state(['disabled'])
        ttk.Button(self,text=tr('ui.templates_ui.deschide_elementul_creat'),command=self.open_created).pack(side='bottom',pady=4)
        return self.created
    def open_created(self):
        self.current()
        if not self.app.confirm_leave():return
        self.app.select_node(self.created.id,reveal=True);self.destroy()

class TemplateEditor(TemplateWindow):
    def __init__(self,app,template,*,on_saved=lambda:None,existing=False):
        super().__init__(app,tr('ui.templates_ui.editeaza_sablonul'))
        self.template=template.model_copy(deep=True);self.on_saved=on_saved
        self.expected_hash=digest(template) if existing else None;self.active_key=None;self.loading=False
        top=ttk.Frame(self,padding=10);top.pack(fill='x')
        self.name=tk.StringVar(value=template.name);self.variables=tk.StringVar(value=', '.join(template.variables))
        ttk.Label(top,text=tr('ui.templates_ui.nume_sablon')).grid(row=0,column=0,sticky='w');ttk.Entry(top,textvariable=self.name).grid(row=0,column=1,sticky='ew')
        ttk.Label(top,text=tr('ui.templates_ui.variabile_declarate_virgula')).grid(row=1,column=0,sticky='w');ttk.Entry(top,textvariable=self.variables).grid(row=1,column=1,sticky='ew',pady=4);top.columnconfigure(1,weight=1)
        ttk.Label(self,text=tr('extra.ui.templates_ui.variabile_in_titlu_descriere_fara_expresii_selecteaza_un_element_'),style='Muted.TLabel').pack(fill='x',padx=10)
        buttons=ttk.Frame(self,padding=8);buttons.pack(fill='x')
        for text,command in [(tr('ui.tab_subtasks.adauga_subtask'),self.add_item),(tr('ui.templates_ui.elimina_ramura'),self.remove_item),(tr('ui.templates_ui.valideaza_previzualizeaza'),self.preview),(tr('ui.templates_ui.salveaza_sablonul'),self.save)]:
            ttk.Button(buttons,text=text,command=lambda cmd=command:self.attempt(cmd)).pack(side='left',padx=3)
        body=ttk.PanedWindow(self,orient='horizontal');body.pack(fill='both',expand=True,padx=10)
        left=ttk.Frame(body);body.add(left,weight=1)
        self.tree=ttk.Treeview(left,show='tree');self.tree.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview);bar.pack(side='right',fill='y');self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind('<<TreeviewSelect>>',self.select_item)
        tabs=ttk.Notebook(body);body.add(tabs,weight=3)
        content=ScrollFrame(tabs);advanced=ScrollFrame(tabs)
        tabs.add(content,text=tr('ui.templates_ui.continut'));tabs.add(advanced,text=tr('ui.templates_ui.structura_si_optiuni'))
        form=content.inner;self.fields={}
        for row,(name,label) in enumerate([('title',tr('ui.meetings.titlu')),('kind',tr('ui.templates_ui.tip_project_task_folder')),('parent',tr('ui.templates_ui.cheie_parinte_gol_radacina')),('priority',tr('ui.templates_ui.prioritate_normal_high_low_urgent')),('estimated_minutes',tr('ui.templates_ui.estimare_minute_optional')),('tags',tr('ui.templates_ui.etichete_separate_prin_virgula')),('next_action',tr('ui.tab_details.urmatorul_pas')),('depends_on',tr('ui.templates_ui.dependente_chei_separate_prin_virgula')),('related',tr('ui.templates_ui.legaturi_chei_separate_prin_virgula'))]):
            target=form if name in ('title','next_action') else advanced.inner
            ttk.Label(target,text=label).pack(anchor='w',pady=(5,0));value=tk.StringVar();self.fields[name]=value
            if name in ('kind','priority'):
                values=['task','project','folder'] if name=='kind' else ['', 'normal','high','low','urgent']
                ttk.Combobox(target,textvariable=value,values=values,state='readonly').pack(fill='x')
            else:ttk.Entry(target,textvariable=value).pack(fill='x')
        ttk.Label(form,text=tr('ui.templates_ui.checklist_un_element_pe_rand_porneste_nebifat')).pack(anchor='w',pady=(6,0))
        self.checklist=tk.Text(form,height=4,wrap='word');self.checklist.pack(fill='x')
        self.editor=MarkdownEditor(form,on_save=lambda:self.attempt(self.save));self.editor.pack(fill='both',expand=True);self.editor.text.configure(height=12)
        exclusion(self)
        self.bind('<Control-s>',lambda e:(self.attempt(self.save),'break')[1])
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.rebuild();self.load_item(template.root.key)
        self.initial=self.snapshot()
    def snapshot(self):
        return (self.name.get(),self.variables.get(),self.template.model_dump_json(),tuple(v.get() for v in self.fields.values()),self.editor.get(),self.checklist.get('1.0','end-1c'))
    def close(self):
        if self.snapshot()!=self.initial and not messagebox.askyesno(tr('ui.meetings.renunta_la_ciorna'),tr('ui.templates_ui.inchizi_fara_sa_salvezi_sablonul'),parent=self):return
        self.destroy()
    def rebuild(self):
        self.loading=True;self.tree.delete(*self.tree.get_children())
        for item in self.template.ordered():self.tree.insert(item.parent or '', 'end',iid=item.key,text=f'{item.title} [{item.key}]',open=True,image=icon(self,'status-todo' if item.kind==Kind.TASK else item.kind.value))
        self.loading=False
    def load_item(self,key):
        self.loading=True;self.active_key=key;item=next(i for i in self.template.items if i.key==key)
        for name,var in self.fields.items():
            value=getattr(item,name);var.set(', '.join(value) if isinstance(value,list) else (value if value is not None else ''))
        self.editor.text.delete('1.0','end');self.editor.text.insert('1.0',item.description)
        self.checklist.delete('1.0','end');self.checklist.insert('1.0','\n'.join(item.checklist))
        self.tree.selection_set(key);self.loading=False
    def apply_item(self):
        if not self.active_key:return
        original=next(i for i in self.template.items if i.key==self.active_key)
        data=original.model_dump(mode='json')
        for name,var in self.fields.items():
            value=var.get()
            if name in ('tags','depends_on','related'):value=[v.strip() for v in value.split(',') if v.strip()]
            elif name=='estimated_minutes':value=int(value) if value.strip() else None
            elif name in ('parent','priority','next_action'):value=value.strip() or None
            data[name]=value
        data['description']=self.editor.get();data['checklist']=[line for line in self.checklist.get('1.0','end-1c').splitlines() if line.strip()]
        updated=TemplateItem.model_validate(data)
        items=[updated if i.key==updated.key else i for i in self.template.items]
        self.template=StructureTemplate(**{**self.template.model_dump(mode='json'),'items':items})
    def select_item(self,event=None):
        if self.loading or not self.tree.selection():return
        target=self.tree.selection()[0]
        if target==self.active_key:return
        try:self.apply_item();self.load_item(target)
        except Exception as exc:
            self.error.set(str(exc));self.tree.selection_set(self.active_key)
    def collect(self):
        self.apply_item()
        return StructureTemplate(**{**self.template.model_dump(mode='json'),'name':self.name.get().strip(),'variables':[v.strip() for v in self.variables.get().split(',') if v.strip()]})
    def add_item(self):
        self.apply_item();key='n'+new_id().replace('-','')[:12]
        self.template.items.append(TemplateItem(key=key,parent=self.active_key,title=tr('ui.app.subtask_nou')))
        self.rebuild();self.load_item(key)
    def remove_item(self):
        self.apply_item()
        if self.active_key==self.template.root.key:raise ValueError(tr('ui.templates_ui.radacina_nu_poate_fi_eliminata'))
        removed={self.active_key}
        while True:
            more={i.key for i in self.template.items if i.parent in removed}-removed
            if not more:break
            removed|=more
        if not messagebox.askyesno(tr('ui.templates_ui.elimina_ramura'),tr('ui.templates_ui.elimini_elemente_doar_din_sablon', len_removed=len(removed)),parent=self):return
        items=[i.model_copy(update={'depends_on':[k for k in i.depends_on if k not in removed],'related':[k for k in i.related if k not in removed]}) for i in self.template.items if i.key not in removed]
        self.template=StructureTemplate(**{**self.template.model_dump(mode='json'),'items':items});self.rebuild();self.load_item(self.template.root.key)
    def preview(self):
        template=self.collect();window=tk.Toplevel(self);window.title(tr('ui.templates_ui.previzualizare_sablon'));window.geometry('900x650')
        exclusion(window);view=TemplatePreview(window);view.pack(fill='both',expand=True);view.load(template)
    def save(self):
        self.current();template=self.collect();self.ws.save_template(template,expected_hash=self.expected_hash)
        self.on_saved();self.destroy()

class TemplateManager(TemplateWindow):
    def __init__(self,app):
        super().__init__(app,tr('ui.templates_ui.gestionare_sabloane'))
        self.entries={}
        buttons=ttk.Frame(self,padding=10);buttons.pack(fill='x')
        for text,action,write in [(tr('ui.templates_ui.sablon_nou'),self.new,True),(tr('ui.templates_ui.editeaza'),self.edit,True),(tr('ui.templates_ui.duplica'),self.duplicate,True),(tr('ui.design.sterge'),self.delete,True),(tr('ui.templates_ui.importa_json'),self.import_file,True),(tr('ui.templates_ui.exporta_json'),self.export_file,False),(tr('ui.templates_ui.creeaza_din_sablon'),self.create,True)]:
            button=ttk.Button(buttons,text=text,command=lambda cmd=action:self.attempt(cmd));button.pack(side='left',padx=2)
            if write and self.ws.read_only:button.state(['disabled'])
        self.list=ttk.Treeview(self,columns=('name','source'),show='headings',height=6)
        self.list.heading('name',text=tr('ui.planning.sablon'));self.list.heading('source',text=tr('ui.templates_ui.origine'));self.list.pack(fill='x',padx=12)
        self.list.bind('<<TreeviewSelect>>',lambda e:self.show())
        exclusion(self);self.preview=TemplatePreview(self);self.preview.pack(fill='both',expand=True,padx=12,pady=6)
        self.refresh()
    def refresh(self):
        if not self.winfo_exists():return
        self.current();self.list.delete(*self.list.get_children());self.entries={}
        for t,builtin in self.ws.templates.catalog():
            key=('builtin:' if builtin else 'user:')+t.id;self.entries[key]=(t,builtin)
            self.list.insert('','end',iid=key,values=(t.name,tr('ui.templates_ui.implicit_doar_citire') if builtin else tr('ui.templates_ui.personal')))
        if self.entries:self.list.selection_set(next(iter(self.entries)));self.show()
        if self.ws.templates.issues:self.error.set(tr('ui.templates_ui.fisiere_ignorate')+'; '.join(self.ws.templates.issues))
    def selected(self):
        if not self.list.selection():raise ValueError(tr('ui.templates_ui.selecteaza_un_sablon'))
        return self.entries[self.list.selection()[0]]
    def show(self):
        if self.list.selection():self.preview.load(self.selected()[0])
    def new(self):TemplateEditor(self.app,StructureTemplate(name=tr('ui.templates_ui.sablon_nou'),items=[TemplateItem(key='root',title=tr('ui.app.task_nou'))]),on_saved=self.refresh)
    def edit(self):
        template,builtin=self.selected()
        if builtin:raise ValueError(tr('ui.templates_ui.sabloanele_implicite_sunt_resurse_foloseste_duplica_pentru_o_copie_edi'))
        TemplateEditor(self.app,template,on_saved=self.refresh,existing=True)
    def duplicate(self):self.ws.duplicate_template(self.selected()[0]);self.refresh()
    def delete(self):
        template,builtin=self.selected()
        if builtin:raise ValueError(tr('ui.templates_ui.sabloanele_implicite_nu_se_sterg_poti_modifica_o_copie_personala'))
        if messagebox.askyesno(tr('ui.planning.sterge_sablonul'),tr('ui.templates_ui.stergi_proiectele_si_taskurile_create_nu_se_modifica', template_name=template.name),parent=self):
            self.ws.delete_template(template,digest(template));self.refresh()
    def import_file(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[(tr('ui.templates_ui.sablon_json'),'*.json')])
        if path:self.ws.import_template(path);self.refresh()
    def export_file(self):
        template,_=self.selected();path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',filetypes=[(tr('ui.templates_ui.sablon_json'),'*.json')])
        if path:self.ws.templates.export_file(template,path);self.error.set(tr('ui.templates_ui.sablon_exportat'))
    def create(self):CreateTemplateDialog(self.app,self.selected()[0])
