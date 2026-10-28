"""Real Tk guided description drafts, shared peers and nested modal boundaries."""
import tkinter as tk
import pytest

from focusdesk.domain.models import Kind
from focusdesk.ui.description_guide import guided_text, append_description, APPLIED_MESSAGE


@pytest.mark.parametrize('goal,steps,result,expected',[
    ('Scop șță',['Primul','Al doilea'],'Rezultat','Scop\nScop șță\n\nPasul 1\nPrimul\n\nPasul 2\nAl doilea\n\nRezultat așteptat\nRezultat'),
    ('',['  \n\t','Un pas','','Alt pas'],'','Pasul 1\nUn pas\n\nPasul 2\nAlt pas'),
    ('  indentat\n\tșț\n',['\n  cod\n    subpas\n'],'\n  rezultat','Scop\n  indentat\n\tșț\n\n\nPasul 1\n\n  cod\n    subpas\n\n\nRezultat așteptat\n\n  rezultat'),
    ('',[],'Numai rezultat','Rezultat așteptat\nNumai rezultat'),
])
def test_plain_generation_and_empty_step_numbering(goal,steps,result,expected):
    assert guided_text(goal,steps,result)==expected


def test_no_completed_section_rejected():
    with pytest.raises(ValueError,match='cel puțin'):guided_text(' \n',['','\t\n'],' ')


@pytest.mark.parametrize('before',['Text vechi','Text vechi\n','Text vechi\n\n','  \t\n'])
def test_append_keeps_every_existing_character(before):
    generated='Scop\nNou'
    assert append_description(before,generated).startswith(before)
    assert append_description(before,generated).endswith(generated)
    assert append_description('',generated)==generated


def details(ui,text=''):
    tab=ui.inspector.tab_by_title('Detalii')
    ui.ws.set_description(ui.selected_id,text);tab.load(ui.ws.get(ui.selected_id))
    ui.root.deiconify();ui.root.update()
    return tab


def opened(ui,tab=None):
    tab=tab or details(ui)
    dialog=tab.editor.open_guide();ui.root.update()
    assert dialog is not None and dialog.grab_current() is dialog
    return tab,dialog


def type_text(field,text):field.insert('1.0',text)


def test_private_draft_cancel_preserves_buffer_dirty_disk_and_undo(ui):
    tab=details(ui,'Text pe disc')
    tab.editor.replace('end-1c','end-1c','\nCiornă anterioară');ui.root.update()
    before=tab.editor.get();dirty=tab.is_dirty();cursor=tab.desc.index('insert')
    tab,dialog=opened(ui,tab)
    type_text(dialog.goal,'Ghid neaplicat');type_text(dialog.steps[0].text,'Pași nesalvați');ui.root.update()
    assert tab.editor.get()==before and tab.is_dirty()==dirty
    assert ui.ws.get_description(tab.node_id)=='Text pe disc'
    dialog.cancel();ui.root.update()
    assert tab.editor.get()==before and tab.is_dirty()==dirty
    assert tab.desc.index('insert')==cursor
    tab.editor.undo();assert tab.editor.get()=='Text pe disc'


def test_clean_cancel_does_not_mark_dirty_or_persist(ui):
    tab,dialog=opened(ui)
    type_text(dialog.goal,'Renunț');dialog.cancel();ui.root.update()
    assert tab.editor.get()=='' and not tab.is_dirty()
    assert ui.ws.get_description(tab.node_id)==''


def test_apply_is_one_undo_and_waits_for_existing_ctrl_s(ui):
    tab,dialog=opened(ui)
    original_title=ui.ws.get(tab.node_id).title
    tab.vars['title'].set('Titlu editat, încă nesalvat')
    type_text(dialog.goal,'Scop nou');type_text(dialog.steps[0].text,'  Întâi\n    apoi')
    assert dialog.apply();ui.root.update()
    value='Scop\nScop nou\n\nPasul 1\n  Întâi\n    apoi'
    assert tab.editor.get()==value and tab.is_dirty()
    assert tab.editor.guide_notice.cget('text')==APPLIED_MESSAGE
    assert ui.ws.get_description(tab.node_id)==''
    assert ui.ws.get(tab.node_id).title==original_title
    tab.editor.undo();assert tab.editor.get()==''
    tab.editor.redo();assert tab.editor.get()==value
    tab.desc.focus_force();ui.root.update();tab.desc.event_generate('<Control-s>');ui.root.update()
    assert ui.ws.get_description(tab.node_id)==value
    assert ui.ws.get(tab.node_id).title=='Titlu editat, încă nesalvat'
    assert not tab.is_dirty()


@pytest.mark.parametrize('mode',['append','replace'])
def test_existing_text_requires_explicit_choice_and_single_undo(ui,mode):
    tab=details(ui,'Descriere veche\n  păstrată')
    tab.editor.replace('end-1c','end-1c','\nCiornă proprie')
    before=tab.editor.get()
    tab,dialog=opened(ui,tab);type_text(dialog.goal,'Nou')
    assert not dialog.apply()
    assert tab.editor.get()==before and dialog.choice is not None
    choice=dialog.choice
    assert choice.append_btn.cget('text')=='Adaugă la final'
    choice.choose(mode);ui.root.update()
    expected=append_description(before,'Scop\nNou') if mode=='append' else 'Scop\nNou'
    assert tab.editor.get()==expected
    tab.editor.undo();assert tab.editor.get()==before
    tab.editor.undo();assert tab.editor.get()=='Descriere veche\n  păstrată'
    tab.editor.redo();assert tab.editor.get()==before
    tab.editor.redo();assert tab.editor.get()==expected


def test_choice_cancel_restores_guide_and_keeps_its_draft(ui):
    tab=details(ui,'Vechi');tab,dialog=opened(ui,tab)
    type_text(dialog.goal,'Ciorna ghidului');dialog.apply();choice=dialog.choice
    assert dialog.grab_current() is choice
    choice.cancel();ui.root.update()
    assert dialog.grab_current() is dialog
    assert dialog.goal.get('1.0','end-1c')=='Ciorna ghidului'
    assert tab.editor.get()=='Vechi' and not tab.is_dirty()
    dialog.cancel();ui.root.update();assert tab.desc.grab_current() is None


def test_reorder_delete_and_many_steps_keep_footer_accessible(ui):
    tab,dialog=opened(ui)
    first,second=dialog.steps;type_text(first.text,'Unu');type_text(second.text,'Doi')
    dialog.move_step(second,-1)
    assert dialog.steps==[second,first]
    assert [step.label.cget('text') for step in dialog.steps]==['Pasul 1','Pasul 2']
    assert second.text.get('1.0','end-1c')=='Doi'
    dialog.remove_step(second)
    assert dialog.steps==[first] and first.label.cget('text')=='Pasul 1'
    for _ in range(18):dialog.add_step(focus=False)
    dialog.geometry('560x430');ui.root.update()
    assert dialog.apply_btn.winfo_ismapped()
    assert dialog.apply_btn.winfo_rooty()+dialog.apply_btn.winfo_height()<=dialog.winfo_rooty()+dialog.winfo_height()
    assert dialog.sf.inner.winfo_height()>dialog.sf.canvas.winfo_height()
    dialog.cancel()


def test_empty_guide_validation_keeps_dialog_open(ui):
    tab,dialog=opened(ui)
    type_text(dialog.goal,'  ');type_text(dialog.steps[0].text,'\t')
    assert not dialog.apply()
    assert 'cel puțin' in dialog.error.cget('text') and dialog.winfo_exists()
    assert not tab.is_dirty()
    dialog.cancel()


def test_ctrl_s_inside_guide_is_not_task_save(ui):
    tab,dialog=opened(ui)
    type_text(dialog.goal,'Ciornă proprie');dialog.goal.focus_force();ui.root.update()
    dialog.goal.event_generate('<Control-s>');ui.root.update()
    assert dialog.winfo_exists() and ui.ws.get_description(tab.node_id)==''
    assert not tab.is_dirty()
    dialog.cancel()


def test_shared_task_space_buffer_and_no_automatic_checklist_or_subtasks(ui):
    tab=details(ui,'')
    assert ui.open_task_space(tab.node_id)
    editor=ui.task_space.editor;dialog=editor.open_guide();type_text(dialog.steps[1].text,'Pas documentat')
    count=len(ui.ws.nodes);dialog.apply();ui.root.update()
    assert editor.get()==tab.editor.get()=='Pasul 1\nPas documentat'
    assert ui.task_space.is_dirty()
    assert editor.guide_notice.cget('text')==APPLIED_MESSAGE
    assert ui.ws.get_description(tab.node_id)==''
    assert not ui.ws.get(tab.node_id).checklist and len(ui.ws.nodes)==count
    tab.editor.undo();assert editor.get()==''
    editor.redo();assert tab.editor.get()=='Pasul 1\nPas documentat'
    assert ui.task_space.save()
    assert ui.ws.get_description(tab.node_id)=='Pasul 1\nPas documentat'


@pytest.mark.parametrize('initial_dirty',[False,True])
def test_nested_guide_then_expanded_cancel_restores_original_session(ui,initial_dirty):
    tab=details(ui,'Pe disc')
    if initial_dirty:tab.editor.replace('end-1c','end-1c','\nCiornă anterioară')
    before=tab.editor.get();was_dirty=tab.is_dirty()
    tab.expand_description();expanded=tab.expanded;ui.root.update()
    dialog=expanded.editor.open_guide();ui.root.update();type_text(dialog.goal,'Text din ghid')
    dialog.apply();choice=dialog.choice;choice.choose('replace');ui.root.update()
    assert tab.editor.get()=='Scop\nText din ghid'
    assert expanded.grab_current() is expanded
    assert expanded.focus_get() is expanded.editor.text
    expanded.cancel();ui.root.update()
    assert tab.editor.get()==before and tab.is_dirty()==was_dirty
    assert tab.desc.grab_current() is None
    assert ui.ws.get_description(tab.node_id)=='Pe disc'
    tab.editor.undo();assert tab.editor.get()==before


def test_nested_escape_cancels_only_current_dialog(ui):
    tab=details(ui,'Vechi');tab.expand_description();expanded=tab.expanded;ui.root.update()
    dialog=expanded.editor.open_guide();ui.root.update();type_text(dialog.goal,'Nou');dialog.apply();ui.root.update()
    choice=dialog.choice;choice.append_btn.focus_force();ui.root.update();choice.append_btn.event_generate('<Escape>');ui.root.update()
    assert dialog.winfo_exists() and dialog.grab_current() is dialog
    dialog.goal.focus_force();ui.root.update();dialog.goal.event_generate('<Escape>');ui.root.update()
    assert expanded.winfo_exists() and expanded.grab_current() is expanded
    assert tab.editor.get()=='Vechi' and not tab.is_dirty()
    expanded.cancel()


@pytest.mark.parametrize('change',['read_only','missing','workspace'])
def test_unavailable_context_cannot_apply(ui,change):
    tab,dialog=opened(ui);type_text(dialog.goal,'Nu aplica')
    if change=='read_only':ui.ws.repo.read_only=True
    elif change=='missing':ui.ws.trash(tab.node_id)
    else:
        original=ui.ws;ui.ws=None
    assert not dialog.apply()
    assert 'nu mai este disponibil' in dialog.error.cget('text')
    assert tab.editor.get()==''
    if change=='read_only':ui.ws.repo.read_only=False
    if change=='workspace':ui.ws=original
    dialog.cancel()


def test_choice_revalidates_changed_buffer(ui):
    tab=details(ui,'Vechi');tab,dialog=opened(ui,tab);type_text(dialog.goal,'Nou');dialog.apply()
    tab.desc.insert('end-1c','\nAltă modificare')
    dialog.choice.choose('replace');ui.root.update()
    assert dialog.winfo_exists() and 'Altă modificare' in tab.editor.get()
    assert 's-a schimbat' in dialog.error.cget('text')
    dialog.cancel()


def test_read_only_hides_effect_and_guide_blocks_navigation(ui):
    tab=details(ui)
    ui.ws.repo.read_only=True;tab.load(ui.ws.get(tab.node_id))
    assert tab.editor.guide_btn.instate(['disabled']) and tab.editor.open_guide() is None
    ui.ws.repo.read_only=False;tab.load(ui.ws.get(tab.node_id))
    tab,dialog=opened(ui,tab)
    assert not ui.confirm_leave()
    dialog.cancel()


def test_explicit_apply_marks_unsaved_even_if_generated_text_matches(ui):
    tab=details(ui,'Scop\nAcelași conținut')
    tab,dialog=opened(ui,tab);type_text(dialog.goal,'Același conținut');dialog.apply()
    dialog.choice.choose('replace');ui.root.update()
    assert tab.editor.get()=='Scop\nAcelași conținut' and tab.is_dirty()
    assert ui.ws.get_description(tab.node_id)=='Scop\nAcelași conținut'


def test_external_node_disappearance_is_guarded_without_reload(ui):
    tab,dialog=opened(ui);type_text(dialog.goal,'Nu aplica')
    path=ui.ws.node_dir(tab.node_id)/'node.json';moved=path.with_suffix('.temporarily-missing')
    path.rename(moved)
    try:
        assert not dialog.apply() and tab.editor.get()==''
        assert 'nu mai este disponibil' in dialog.error.cget('text')
    finally:moved.rename(path);dialog.cancel()


def test_choice_rechecks_read_only_after_explicit_selection(ui):
    tab=details(ui,'Vechi');tab,dialog=opened(ui,tab);type_text(dialog.goal,'Nou');dialog.apply()
    ui.ws.repo.read_only=True
    try:
        dialog.choice.choose('replace');ui.root.update()
        assert dialog.winfo_exists() and tab.editor.get()=='Vechi'
        assert not tab.is_dirty()
    finally:ui.ws.repo.read_only=False;dialog.cancel()
