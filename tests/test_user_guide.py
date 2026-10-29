"""Packaged manual, offline-only search, real Tk navigation and modal grab safety."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import time
import tkinter as tk

import pytest

from focusdesk.config import resource_path
from focusdesk.services.user_guide import GuideError, GuideHistory, GuideLibrary, blocks


def pump(app, condition=lambda: True, seconds=3):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.root.update()
        if condition():return True
        time.sleep(.01)
    return False


def test_all_chapters_and_internal_links_are_available():
    from focusdesk.ui.user_guide import TOPICS
    library=GuideLibrary()
    assert len(library.chapters)==19
    assert {'astazi','organizare','descriere','sesiuni','calendar','intalniri','activitate','fisiere','email','cerinte'} <= library.chapters.keys()
    library.validate_links()
    for target in TOPICS.values():library.target('guide:'+target)
    assert all(chapter.anchors and len(chapter.content)>1000 for chapter in library.chapters.values())
    assert all('##' in chapter.content for chapter in library.chapters.values())
    for heading in ('Tutorial A:', 'Tutorial B:', 'Tutorial C:', 'Tutorial D:', 'Tutorial E:', 'Tutorial F:',
                    'Tutorial G:', 'Tutorial H:', 'Tutorial I:', 'Tutorial J:', 'Tutorial K:'):
        assert any(heading in c.content for c in library.chapters.values())


@pytest.mark.parametrize('query,accented', [('intalniri','ÎNTÂLNIRI'),('descriere ghidata','descriere GHIDATĂ'),
                                         ('cerinta noua','cerință nouă'),('fisiere','fișiere')])
def test_search_ignores_case_and_diacritics(query,accented):
    library=GuideLibrary()
    assert library.search(query)==library.search(accented)
    assert library.search(query)
    assert all(hit.title and hit.fragment and hit.anchor for hit in library.search(query))
    assert not library.search('zzzzzz-document-inexistent') and not library.search('   ')


def test_manual_search_never_opens_personal_data(monkeypatch):
    from focusdesk.services.workspace import Workspace
    def forbidden(*a,**k):raise AssertionError('Personal data accessed by manual')
    monkeypatch.setattr(Workspace,'get_description',forbidden)
    monkeypatch.setattr(Workspace,'list_notes',forbidden)
    library=GuideLibrary()
    assert library.search('notite')
    hit=library.search('intalniri')[0]
    assert hit.fragment != hit.title and len(hit.fragment)>len(hit.title)


@pytest.mark.parametrize('manifest', [[], {}, {'version':2,'chapters':[]},
    {'version':1,'chapters':[{'id':'introducere','file':'../../private.md'}]},
    {'version':1,'chapters':[{'id':'introducere','file':'missing.md'}]}])
def test_missing_corrupt_or_unsafe_resources_have_clear_errors(tmp_path,manifest):
    (tmp_path/'index.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(GuideError):GuideLibrary(tmp_path)


def test_broken_internal_link_is_reported_and_no_external_link_is_followed(tmp_path):
    (tmp_path/'index.json').write_text(json.dumps({'version':1,'chapters':[{'id':'introducere','file':'introducere.md'}]}))
    for text in ('# Titlu\n[Greșit](guide:missing)', '# Titlu\n[Extern](https://example.com)'):
        (tmp_path/'introducere.md').write_text(text,encoding='utf-8')
        with pytest.raises(GuideError):GuideLibrary(tmp_path)


def test_markdown_subset_displays_literal_html_and_code():
    parsed=blocks('# Titlu\n\n## Întrebări\n\n1. Pas **important**\n- Alt pas\n> Observație\n```python\nraise RuntimeError("not executed")\n```\n<script>not executed</script>')
    assert any(p.kind=='code' and 'raise RuntimeError' in p.text for p in parsed)
    assert any('<script>' in p.text for p in parsed)
    assert 'intrebari' in {p.anchor for p in parsed}


def test_history_tracks_reading_positions_and_truncates_forward_branch():
    history=GuideHistory()
    history.current.scroll=.4
    history.visit('fisiere');history.current.scroll=.7
    assert history.move(-1) and history.current.scroll==.4
    assert history.move(1) and history.current.scroll==.7
    history.move(-1);history.visit('email')
    assert not history.move(1) and not history.visit('email')


def test_frozen_resources_load_without_source_checkout(tmp_path,monkeypatch):
    destination=tmp_path/'focusdesk'/'resources'
    destination.mkdir(parents=True)
    shutil.copytree(resource_path('guide'),destination/'guide')
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    library=GuideLibrary()
    assert len(library.chapters)==19 and library.search('intalniri')


def test_pyinstaller_data_collection_contains_manual_and_icon():
    from PyInstaller.utils.hooks import collect_data_files
    collected=collect_data_files('focusdesk')
    destinations={str(Path(destination)/Path(source).name).replace('\\','/') for source,destination in collected}
    assert 'focusdesk/resources/guide/index.json' in destinations
    assert 'focusdesk/resources/guide/intalniri.md' in destinations
    assert 'focusdesk/resources/icons/help-20.png' in destinations
    import ast
    spec=ast.parse(Path('focusdesk.spec').read_text())
    assert any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='collect_data_files'
               and node.args[0].value=='focusdesk' for node in ast.walk(spec))


@pytest.fixture
def guide(ui):
    ui.root.deiconify();ui.root.update()
    errors=[]
    ui.root.report_callback_exception=lambda exc,value,tb: errors.append(f'{exc.__name__}: {value}')
    window=ui.show_guide();ui.root.update()
    yield ui,window
    ui.root.update()
    assert not errors, errors


def test_header_menu_and_f1_reuse_one_nonmodal_window(guide):
    app,window=guide
    assert app.root.grab_current() is None and app.guide_btn.cget('text')=='Ghid de utilizare'
    app.guide_btn.invoke();app.root.update()
    assert app.user_guide.window is window
    app.help_menu.invoke(0);app.root.update()
    assert app.user_guide.window is window
    app.current_view='activity';app.root.focus_force();app.root.event_generate('<F1>');app.root.update()
    assert app.user_guide.window is window and app.user_guide.history.current.chapter_id=='activitate'
    assert app.root.grab_current() is None


@pytest.mark.parametrize('view,expected',[('today','astazi'),('tasks','organizare'),('tree:any','organizare'),
                                         ('activity','activitate'),('archive','siguranta')])
def test_contextual_main_pages(guide,view,expected):
    app,_=guide
    app.current_view=view;app.root.focus_force();app.root.update()
    app.show_guide(contextual=True)
    assert app.user_guide.history.current.chapter_id==expected


def test_contextual_calendar_agenda_and_meetings(guide):
    app,_=guide
    app.current_view='calendar';app.root.focus_force();app.root.update()
    app.calendar_page.nb.select(app.calendar_page.agenda)
    assert app.user_guide.context_topic()=='calendar'
    app.calendar_page.nb.select(app.calendar_page.meetings)
    app.root.focus_force()
    assert app.user_guide.context_topic()=='intalniri'


@pytest.mark.parametrize('section,expected',[('Pași','organizare'),('Fișiere','fisiere'),('Activitate','sesiuni'),
                                             ('Planificare','calendar'),('Versiuni','versiuni')])
def test_contextual_task_workspace_sections(ui,section,expected):
    ui.root.deiconify();ui.root.update();assert ui.open_task_space(ui.selected_id)
    space=ui.task_space;space.nb.select(space.scrolls[section]);ui.root.update();ui.root.focus_force()
    ui.show_guide(contextual=True)
    assert ui.user_guide.history.current.chapter_id==expected


def test_history_internal_links_keyboard_and_scroll_restore(guide):
    app,window=guide
    window.navigate('fisiere');app.root.update()
    window.article.yview_moveto(.4);app.root.update();fraction=window.article.yview()[0]
    window.navigate('email');app.root.update()
    window.back_btn.invoke();app.root.update()
    assert app.user_guide.history.current.chapter_id=='fisiere'
    assert abs(window.article.yview()[0]-fraction)<.02
    window.forward_btn.invoke();app.root.update()
    assert app.user_guide.history.current.chapter_id=='email'
    window.open_link('#atasamente');app.root.update()
    anchor_fraction=window.article.yview()[0]
    window.article.yview_moveto(0);app.root.update()
    window.open_link('#atasamente');app.root.update()
    assert abs(window.article.yview()[0]-anchor_fraction)<.02
    window.link_combo.current(0);window.link_btn.invoke();app.root.update()
    assert app.user_guide.history.current.chapter_id in app.user_guide.library.chapters
    window.close();app.root.update()
    current=app.user_guide.history.current.chapter_id;position=window.article.yview()[0]
    assert app.show_guide() is window
    app.root.update();assert current==app.user_guide.history.current.chapter_id
    assert abs(window.article.yview()[0]-position)<.02


def test_search_results_include_fragment_and_can_open_by_enter(guide):
    app,window=guide
    window.query.set('intalniri');window.search();app.root.update()
    first=window.toc.get_children()[0]
    window.toc.selection_set(first);window.toc.focus(first);app.root.update()
    assert window.preview.cget('text') and window._hits[first].title
    window.toc.focus_force();window.toc.event_generate('<Return>');app.root.update()
    assert app.user_guide.history.current.chapter_id==first
    window.query.set('xyz-fara-rezultat');window.search();app.root.update()
    assert not window.toc.get_children() and 'Nu există rezultate' in window.preview.cget('text')


def test_open_read_close_does_not_save_drafts_or_change_timer(ui):
    from test_stage3 import FakeClock
    ui.root.deiconify();ui.root.update()
    details=ui.inspector.tab_by_title('Detalii');nid=ui.selected_id
    original=ui.ws.get_description(nid)
    details.editor.replace('1.0','end-1c','Ciornă nesalvată\n  șț')
    details.vars['title'].set('Titlu nesalvat')
    clock=FakeClock();ui.timer._mono=clock
    ui.timer.start(nid)
    timer=ui.timer.state.session_id
    window=ui.show_guide('descriere');ui.root.update()
    window.navigate('sesiuni');window.close();ui.root.update()
    assert details.editor.get()=='Ciornă nesalvată\n  șț' and details.is_dirty()
    assert details.vars['title'].get()=='Titlu nesalvat'
    assert ui.ws.get_description(nid,observe=False)==original
    assert ui.ws.get(nid).title!='Titlu nesalvat'
    assert ui.timer.state.session_id==timer and ui.timer.running


def test_modal_editor_grab_focus_draft_and_cancel_remain_intact(ui):
    ui.root.deiconify();ui.root.update()
    details=ui.inspector.tab_by_title('Detalii');initial=details.editor.get()
    details.expand_description();editor=details.expanded;ui.root.update()
    editor.editor.replace('1.0','end-1c','În editorul extins')
    editor.editor.text.focus_force();ui.root.update()
    grab=ui.root.grab_current();focus=ui.root.tk.call('focus')
    window=ui.show_guide(contextual=True);ui.root.update()
    assert window.master is editor and ui.root.grab_current() is grab
    assert ui.user_guide.history.current.chapter_id=='descriere'
    window.close();ui.root.update()
    assert ui.root.grab_current() is grab and ui.root.tk.call('focus')==focus
    assert editor.editor.get()=='În editorul extins'
    editor.cancel();ui.root.update()
    assert details.editor.get()==initial


def test_existing_general_window_is_rehosted_under_nested_modal_without_changing_grab(guide):
    from focusdesk.ui.description_guide import DescriptionGuide
    app,old=guide
    old.navigate('email');app.root.update()
    details=app.inspector.tab_by_title('Detalii')
    nested=details.editor.open_guide();app.root.update();nested.goal.insert('1.0','Ciornă proprie')
    nested.goal.focus_force();app.root.update()
    grabbed=app.root.grab_current()
    window=app.show_guide(contextual=True);app.root.update()
    assert not old.winfo_exists() and window.master is nested
    assert app.root.grab_current() is grabbed
    window.close();app.root.update()
    assert nested.goal.get('1.0','end-1c')=='Ciornă proprie' and app.root.grab_current() is grabbed
    nested.cancel();app.root.update()
    assert app.root.grab_current() is None
    assert app.show_guide().master is app.root


def test_native_tcl_modal_keeps_its_grab_and_can_host_help(guide):
    app,_=guide
    before={suffix:len(app.root.tk.call('info','commands','*'+suffix)) for suffix in ('_query_changed','_toc_selected')}
    app.root.tk.call('toplevel','.nativeGuideTest')
    app.root.tk.call('grab','set','.nativeGuideTest')
    window=app.show_guide('probleme');app.root.update()
    assert str(window.master)=='.nativeGuideTest'
    assert str(app.root.tk.call('grab','current','.'))=='.nativeGuideTest'
    window.close();app.root.update()
    assert str(app.root.tk.call('grab','current','.'))=='.nativeGuideTest'
    app.root.tk.call('destroy','.nativeGuideTest');app.root.update()
    assert app.root.grab_current() is None
    assert app.show_guide().winfo_exists()
    assert {suffix:len(app.root.tk.call('info','commands','*'+suffix)) for suffix in before}==before


def test_general_manual_survives_workspace_release(guide):
    app,window=guide
    window.navigate('siguranta');app.root.update()
    assert pump(app,lambda:not app._pending_workspace_jobs())
    assert app._release_current();app.root.update()
    assert app.ws is None and window.winfo_exists() and app.show_guide() is window
    window.query.set('backup');window.search();app.root.update()
    assert window.toc.get_children()


def test_without_workspace_and_offline(tmp_path,monkeypatch):
    from focusdesk.ui.app import FocusDeskApp
    monkeypatch.setenv('APPDATA',str(tmp_path/'config'))
    app=FocusDeskApp();app.root.withdraw()
    try:
        window=app.show_guide();app.root.update()
        assert app.ws is None and window.article.get('1.0','end-1c')
        app.root.deiconify();app.root.focus_force();app.root.update()
        assert app.user_guide.context_topic()=='primii-pasi'
        assert app.show_guide('email') is window
        assert app.ws is None and app.timer is None
    finally:app.on_close()


def test_resource_error_is_contained_and_retry_works(ui,monkeypatch):
    real=GuideLibrary
    monkeypatch.setattr('focusdesk.ui.user_guide.GuideLibrary',lambda: (_ for _ in ()).throw(GuideError('Resurse lipsă demonstrative')))
    window=ui.show_guide();ui.root.update()
    assert 'Resurse lipsă' in window.article.get('1.0','end') and ui.ws is not None
    monkeypatch.setattr('focusdesk.ui.user_guide.GuideLibrary',real)
    window.retry_btn.invoke();ui.root.update()
    assert ui.user_guide.library and ui.user_guide.window.winfo_exists()


def test_read_only_article_and_ctrl_s_do_not_save_task_or_block_editing(guide,monkeypatch):
    app,window=guide
    saves=[];monkeypatch.setattr(app,'save_current',lambda:saves.append(True))
    window.article.focus_force();window.article.event_generate('<Control-s>');app.root.update()
    assert not saves and str(window.article.cget('state'))=='disabled'
    details=app.inspector.tab_by_title('Detalii')
    before=app.ws.get_description(app.selected_id,observe=False)
    app.root.focus_force();details.desc.focus_force()
    details.desc.insert('end-1c','\nLucru în aplicația din spate');app.root.update()
    assert details.is_dirty() and app.ws.get_description(app.selected_id,observe=False)==before
    assert app.root.grab_current() is None


def test_f1_from_mail_dialog_does_not_submit_or_lose_form(ui,monkeypatch):
    from focusdesk.ui.mail_ui import MailDialog
    ui.root.deiconify();ui.root.update()
    dialog=MailDialog(ui.root,ui,ui.ws.get(ui.selected_id))
    dialog.to_var.set('ana@exemplu.ro');dialog.text.insert('end','Ciornă proprie')
    submitted=[];monkeypatch.setattr(ui.outlook,'send_mail',lambda *a,**k:submitted.append(True))
    try:
        dialog.grab_set();dialog.to_entry.focus_force();ui.root.update()
        before=dialog.text.get('1.0','end-1c')
        dialog.to_entry.event_generate('<F1>');ui.root.update()
        window=ui.user_guide.window
        assert window is not None and window.master is dialog
        assert ui.user_guide.history.current.chapter_id=='email'
        window.close();ui.root.update()
        assert ui.root.grab_current() is dialog and dialog.text.get('1.0','end-1c')==before
        assert dialog.to_var.get()=='ana@exemplu.ro' and not submitted
    finally:dialog.destroy()


def test_package_data_declares_the_complete_manual():
    import tomllib
    settings=tomllib.loads(Path('pyproject.toml').read_text('utf-8'))
    patterns=settings['tool']['setuptools']['package-data']['focusdesk']
    assert 'resources/guide/*.md' in patterns and 'resources/guide/*.json' in patterns
    assert 'resources/icons/*.png' in patterns
