import pytest
from focusdesk.ui.templates_ui import TemplateManager,CreateTemplateDialog,TemplateEditor
from focusdesk.domain.models import Kind
from focusdesk.domain.templates import StructureTemplate,TemplateItem


def test_creation_requires_current_preview_and_double_click_is_safe(ui):
    dialog=CreateTemplateDialog(ui)
    try:
        assert dialog.grab_current() is None
        assert dialog.create_btn.instate(['disabled'])
        for name,var in dialog.values.items():var.set('Exemplu '+name)
        dialog.title_var.set('Proiect șablon');dialog.preview()
        dialog.title_var.set('Alt titlu')
        with pytest.raises(ValueError,match='previzualizarea'):dialog.create()
        assert len(ui.ws.nodes)==1
        dialog.preview();created=dialog.create();size=len(ui.ws.nodes)
        assert dialog.create().id==created.id and len(ui.ws.nodes)==size
        assert dialog.create_btn.instate(['disabled'])
        assert ui.ws.get(created.id).title=='Alt titlu'
    finally:dialog.destroy()


def test_template_editor_edit_add_and_reuse(ui):
    source=ui.ws.create_node(Kind.PROJECT,'Proiect')
    ui.ws.create_node(Kind.TASK,'Pas unu',source.id)
    template=ui.ws.templates.capture(source.id,'Personal')
    editor=TemplateEditor(ui,template)
    try:
        editor.fields['title'].set('{{nume_proiect}}');editor.variables.set('nume_proiect')
        editor.editor.text.insert('end','\n## Context\nText **{{nume_proiect}}**')
        editor.add_item();editor.fields['title'].set('Pas nou');editor.checklist.insert('1.0','Validare\nLivrare')
        editor.save()
        saved=next(t for t,b in ui.ws.templates.catalog() if not b)
        assert len(saved.items)==3 and saved.variables==['nume_proiect']
        made=ui.ws.create_from_template(saved,title='{{nume_proiect}}',values={'nume_proiect':'Nou'},request_id=__import__('uuid').uuid4().__str__())
        assert made.title=='Nou' and '**Nou**' in ui.ws.get_description(made.id)
        added=next(n for n in ui.ws.children(made.id) if n.title=='Pas nou')
        assert [c.text for c in added.checklist]==['Validare','Livrare']
    finally:
        if editor.winfo_exists():editor.destroy()


def test_manager_default_copy_edit_and_readonly(ui):
    manager=TemplateManager(ui)
    try:
        assert len(manager.entries)==4
        with pytest.raises(ValueError,match='Duplică'):manager.edit()
        manager.duplicate();assert len(manager.entries)==5
        assert len(ui.ws.nodes)==1 # no demonstration project or task was created
    finally:manager.destroy()
    ui.ws.repo.read_only=True
    manager=TemplateManager(ui)
    try:
        buttons=[w for f in manager.winfo_children() for w in f.winfo_children() if w.winfo_class()=='TButton']
        assert next(b for b in buttons if b.cget('text')=='Șablon nou').instate(['disabled'])
    finally:manager.destroy();ui.ws.repo.read_only=False


def test_dialog_rejects_workspace_change(ui):
    dialog=CreateTemplateDialog(ui)
    current=ui.ws
    try:
        ui.ws=None
        with pytest.raises(ValueError,match='schimbat'):dialog.current()
    finally:ui.ws=current;dialog.destroy()


def test_editor_conflict_preserves_unsaved_text(ui):
    original=ui.ws.save_template(StructureTemplate(name='T',items=[TemplateItem(key='root',title='Task')]))
    a=TemplateEditor(ui,original,existing=True);b=TemplateEditor(ui,original,existing=True)
    try:
        a.name.set('Primul');a.save()
        b.fields['title'].set('Ciornă păstrată')
        result=b.attempt(b.save)
        assert result is None and b.winfo_exists() and b.fields['title'].get()=='Ciornă păstrată'
        assert 'schimbat' in b.error.get()
    finally:
        for editor in (a,b):
            if editor.winfo_exists():editor.destroy()


def test_new_menu_and_tools_are_accessible(ui):
    labels=lambda menu:[menu.entrycget(i,'label') for i in range(menu.index('end')+1) if menu.type(i)!='separator']
    assert 'Din șablon…' in labels(ui.new_menu)
    assert 'Gestionare șabloane…' in labels(ui.tools_menu)
