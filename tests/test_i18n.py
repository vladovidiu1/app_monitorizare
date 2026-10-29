"""Offline catalogs, stable data and real Tk in fresh language-specific processes."""
from __future__ import annotations
import ast
from datetime import date,datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import pytest

from focusdesk import i18n
from focusdesk.config import AppConfig,resource_path
from focusdesk.services.user_guide import GuideLibrary
from focusdesk.services.templates import parse_template

ROOT=Path(__file__).resolve().parents[1]


def test_complete_catalogs_named_parameters_and_all_code_keys():
    assert i18n.validate_catalogs()==[]
    source=json.loads(resource_path('locales/ro.json').read_text())
    assert len(source)>1500
    for file in (ROOT/'src/focusdesk').rglob('*.py'):
        tree=ast.parse(file.read_text())
        for call in ast.walk(tree):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='tr' or not call.args:continue
            key=call.args[0]
            if isinstance(key,ast.Constant):assert key.value in source,(file,key.value)
    # Real translations, not placeholder copies of Romanian text.
    for code in ('en','de','fr','es'):
        target=json.loads(resource_path(f'locales/{code}.json').read_text())
        untranslated=[k for k,v in source.items() if isinstance(v,str) and re.search('[ăâîșțĂÂÎȘȚ]',v) and target[k]==v]
        assert untranslated==[],(code,untranslated)


@pytest.mark.parametrize('code',['ro','en','de','fr','es'])
def test_localized_guide_has_all_common_anchors_and_tutorials(code):
    original=GuideLibrary(resource_path('guide'))
    library=GuideLibrary(resource_path('guide')/code if code!='ro' else resource_path('guide'))
    assert library.chapters.keys()==original.chapters.keys()
    for key,chapter in library.chapters.items():
        assert chapter.anchors==original.chapters[key].anchors
        assert len(chapter.content)>650
    if code!='ro':
        assert library.chapters['introducere'].title!=original.chapters['introducere'].title
        assert library.chapters['sesiuni'].content!=original.chapters['sesiuni'].content
    assert library.search({'ro':'întâlniri','en':'meetings','de':'Besprechungen','fr':'réunions','es':'reuniones'}[code])


@pytest.mark.parametrize('code',['en','de','fr','es'])
def test_bundled_templates_localize_text_not_internal_structure(code):
    for original_path in resource_path('templates').glob('*.json'):
        original=parse_template(original_path.read_bytes())
        translated=parse_template((resource_path('templates')/code/original_path.name).read_bytes())
        assert translated.id==original.id and translated.name!=original.name
        assert translated.variables==original.variables
        for before,after in zip(original.items,translated.items):
            a,b=before.model_dump(),after.model_dump()
            for field in ('title','description','checklist'):a.pop(field);b.pop(field)
            assert a==b
        assert not re.search('[ășțĂȘȚ]',translated.model_dump_json())


@pytest.mark.parametrize('code,categories',[
    ('ro',['few','one','few','few','other','few','few']),
    ('en',['other','one','other','other','other','other','other']),
    ('de',['other','one','other','other','other','other','other']),
    ('fr',['one','one','other','other','other','other','one']),
    ('es',['other','one','other','other','other','other','other']),
])
def test_plural_categories_and_actual_translations(monkeypatch,code,categories):
    monkeypatch.setattr(i18n,'_language',code)
    assert [i18n.plural_category(n) for n in (0,1,2,19,20,101,1.5)]==categories
    assert '1' in i18n.tr('items.tasks',count=1)
    assert '2' in i18n.tr('items.tasks',count=2)
    assert i18n.tr('items.tasks',count=1)!=i18n.tr('items.tasks',count=2)
    with pytest.raises(ValueError,match='count required'):i18n.tr('items.tasks')


def test_missing_key_controlled_fallback_and_bad_parameters(monkeypatch,caplog):
    monkeypatch.setattr(i18n,'_language','en')
    monkeypatch.setattr(i18n,'_catalogs',{'ro':{'example':'Valoare {value}'},'en':{}})
    monkeypatch.setattr(i18n,'_missing',set())
    assert i18n.tr('example',value='User text îäéñ')=='Valoare User text îäéñ'
    assert i18n.tr('example',value='unchanged')=='Valoare unchanged'
    assert caplog.text.count('Missing translation: en:example')==1
    assert i18n.tr('unknown')=='[unknown]'
    with pytest.raises(KeyError):i18n.tr('example')


@pytest.mark.parametrize('code,date_output,decimal',[
    ('ro','29.10.2026','1.234,50'),('en','29/10/2026','1,234.50'),
    ('de','29.10.2026','1.234,50'),('fr','29/10/2026','1\u202f234,50'),('es','29/10/2026','1.234,50'),
])
def test_formats_and_unambiguous_input(monkeypatch,code,date_output,decimal):
    from focusdesk.ui.formats import parse_date,parse_time,parse_duration
    monkeypatch.setattr(i18n,'_language',code)
    value=datetime(2026,10,29,17,42,tzinfo=timezone.utc)
    assert i18n.date_text(value)==date_output
    assert i18n.datetime_text(value)==date_output+' 17:42'
    assert i18n.date_text(value.date(),iso=True)=='2026-10-29'
    assert i18n.number(1234.5,2)==decimal
    assert i18n.month_name(10) and i18n.weekday_name(3)
    for text in (date_output,'2026-10-29','29.10.2026'):assert parse_date(text)==value.date()
    assert parse_time('17:42').hour==17 and parse_duration('1,5h')==90
    with pytest.raises(ValueError):parse_date('10/29/2026')


def test_profile_migration_persistence_and_bad_language(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    assert AppConfig.load().language=='ro' and i18n.profile_language()=='ro'
    for code in i18n.LANGUAGES:
        config=AppConfig(language=code,inspector_tab='Jurnal');config.save()
        assert AppConfig.load().language==i18n.profile_language()==code
        assert config.inspector_tab=='journal'
    assert AppConfig(language='unknown').language=='ro'
    AppConfig.path().write_text('{broken')
    assert i18n.profile_language()=='ro'


def test_frozen_catalogs_and_all_guides_do_not_need_checkout(tmp_path,monkeypatch):
    import shutil
    for resource in ('locales','guide'):
        shutil.copytree(resource_path(resource),tmp_path/'focusdesk/resources'/resource)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    monkeypatch.setattr(i18n,'_catalogs',{})
    for code in i18n.LANGUAGES:
        monkeypatch.setattr(i18n,'_language',code)
        assert i18n.tr('ui.app.ghid_de_utilizare')
        assert len(GuideLibrary().chapters)==19


def test_pyinstaller_collects_every_language_guide_and_template():
    from PyInstaller.utils.hooks import collect_data_files
    collected={Path(source).resolve() for source,_destination in collect_data_files('focusdesk')}
    for folder in ('locales','guide','templates'):
        for resource in resource_path(folder).rglob('*'):
            if resource.is_file():assert resource.resolve() in collected


@pytest.mark.parametrize('code',['ro','en','de','fr','es'])
def test_fresh_language_real_ui_drafts_timer_and_navigation(code,tmp_path):
    if not os.environ.get('DISPLAY') and sys.platform!='win32':pytest.skip('Tk display unavailable')
    process=subprocess.run([sys.executable,str(ROOT/'scripts/i18n_smoke.py'),'--language',code,
                            '--report',str(tmp_path/'report.json')],cwd=ROOT,text=True,capture_output=True,timeout=50)
    assert process.returncode==0,process.stdout+'\n'+process.stderr
    report=json.loads((tmp_path/'report.json').read_text())
    assert len(report['checks'])>=44


def test_failed_profile_write_keeps_preference_and_draft(ui,monkeypatch):
    from focusdesk.ui.settings_dialog import SettingsDialog
    from focusdesk.storage import atomic
    import focusdesk.ui.settings_dialog as settings_ui
    details=ui.inspector.tab_by_id('details')
    details.editor.replace('end-1c','end-1c','\nUser draft îäéñ')
    draft=details.editor.get();previous=ui.config.language;errors=[]
    dialog=SettingsDialog(ui.root,ui)
    dialog.language_var.set(i18n.LANGUAGES['en'])
    monkeypatch.setattr(settings_ui,'show_error',lambda *a:errors.append(a))
    def fail(*a,**k):raise OSError('technical detail unchanged')
    monkeypatch.setattr(atomic,'atomic_write_json',fail)
    try:
        assert not dialog.save_language()
        assert ui.config.language==previous and details.editor.get()==draft and details.is_dirty()
        assert errors and 'technical detail unchanged' in errors[0][1]
    finally:dialog.destroy()


def test_readonly_workspace_allows_profile_language_only(ui):
    from focusdesk.ui.settings_dialog import SettingsDialog
    before=ui.ws.node_dir(ui.selected_id).joinpath('node.json').read_bytes()
    ui.ws.repo.read_only=True
    dialog=SettingsDialog(ui.root,ui)
    try:
        assert dialog.ok_btn.instate(['disabled'])
        dialog.language_var.set('Deutsch')
        assert dialog.save_language() and AppConfig.load().language=='de'
        assert ui.ws.node_dir(ui.selected_id).joinpath('node.json').read_bytes()==before
    finally:dialog.destroy();ui.ws.repo.read_only=False


@pytest.mark.parametrize('code',['ro','en','de','fr','es'])
def test_real_restart_does_not_translate_personal_data(code,tmp_path,monkeypatch):
    from focusdesk.services.workspace import Workspace
    from focusdesk.domain.models import Kind,Status
    from focusdesk.domain.session import SessionRecord
    from focusdesk.domain.common import new_id
    from datetime import timedelta
    root=tmp_path/'data';ws=Workspace.open(root,create=True)
    task=ws.create_node(Kind.TASK,'De făcut — User title îäéñ',description='Scop\nUser text {value}\n    indentation')
    ws.add_note(task.id,'Notiță personală îäéñ {name}')
    now=datetime.now(timezone.utc)
    session=SessionRecord(node_id=task.id,start_at=now-timedelta(hours=1),end_at=now,status='done',actual_seconds=600,summary='Rezumat personal')
    ws.repo.sessions.save(session)
    meeting=ws.meetings.manual(title='Titlu întâlnire îäéñ',start=now,end=now+timedelta(hours=1))
    ws.meetings.save_notes(meeting.id,'Minute personale îäéñ {title}')
    template=ws.templates.capture(task.id,'Șablon personal îäéñ')
    ws.templates.save(template)
    ws.update_node(task.id,status=Status.DONE)
    ws.close()
    # Include authoritative nodes, notes, sessions, history, meetings and templates;
    # exclude reconstructible indexes, locks and operation bookkeeping.
    def authoritative():
        return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()
                and (p.is_relative_to(root/'nodes') or any(part in p.parts for part in ('sessions','history','meetings','templates')))
                and not p.name.endswith(('.bak','.lock')) and 'index' not in p.stem}
    before=authoritative()
    profile=tmp_path/'profile';monkeypatch.setenv('APPDATA',str(profile));AppConfig(language=code).save()
    script='''
import sys
from focusdesk.i18n import language
from focusdesk.services.workspace import Workspace
assert language()==sys.argv[2]
w=Workspace.open(sys.argv[1])
try:
 assert any(n.title=='De făcut — User title îäéñ' for n in w.nodes.values())
 assert any(t.name=='Șablon personal îäéñ' for t,builtin in w.templates.catalog() if not builtin)
finally:w.close()
'''
    process=subprocess.run([sys.executable,'-c',script,str(root),code],cwd=ROOT,text=True,capture_output=True,timeout=15)
    assert process.returncode==0,process.stderr
    assert authoritative()==before


def test_plural_fallback_uses_source_language_rules(monkeypatch):
    monkeypatch.setattr(i18n,'_language','en')
    monkeypatch.setattr(i18n,'_catalogs',{'ro':{'example':{'one':'{count} task','few':'{count} taskuri','other':'{count} de taskuri'}},'en':{}})
    monkeypatch.setattr(i18n,'_missing',set())
    assert i18n.tr('example',count=0)=='0 taskuri'
    assert i18n.tr('example',count=20)=='20 de taskuri'


def test_catalog_validator_rejects_missing_keys_parameters_and_plural_forms(tmp_path):
    source={'sample':'Hello {name}','plural':{'one':'{count} item','other':'{count} items'}}
    for code in i18n.LANGUAGES:(tmp_path/f'{code}.json').write_text(json.dumps(source))
    broken={'sample':'Bonjour {other}','plural':{'one':'{count} élément'},'unexpected':'extra'}
    (tmp_path/'fr.json').write_text(json.dumps(broken))
    errors=i18n.validate_catalogs(tmp_path)
    assert any('unexpected' in error for error in errors)
    assert any('parameters' in error for error in errors)
    assert any('plural forms' in error for error in errors)


def test_no_new_hardcoded_widget_labels():
    allowed={'FocusDesk','  FocusDesk','Code.exe'}
    for p in (ROOT/'src/focusdesk/ui').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node,ast.keyword) and node.arg in ('text','title','label','ok_text','success_text'):
                if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) and re.search('[A-Za-z]',node.value.value):
                    assert node.value.value in allowed,(p,node.value.lineno,node.value.value)


def test_adaptive_tabs_keep_context_and_hide_when_task_is_unselected(ui):
    task_id=ui.selected_id
    ui.root.deiconify();ui.show_view('tasks');ui.select_node(task_id,reveal=True);ui.root.update()
    notebook=ui.inspector.nb
    for tab in notebook.tabs():notebook.tab(tab,text='Long translated section — '+notebook.tab(tab,'text')*3)
    notebook._adapt();ui.root.update()
    assert notebook.selector.winfo_ismapped()
    selected=notebook.select()
    ui.inspector.load(None);ui.root.update()
    assert not notebook.selector.winfo_ismapped()
    ui.inspector.load(task_id);ui.root.update()
    assert notebook.selector.winfo_ismapped() and notebook.select()==selected
    notebook.section_box.current(1);notebook.section_box.event_generate('<<ComboboxSelected>>');ui.root.update()
    assert ui.inspector.current_tab_id()=='subtasks'
