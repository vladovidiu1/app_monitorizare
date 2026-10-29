"""Real Tk language/navigation checks on disposable data; optional Linux screenshots.

Run one fresh process per language so module-level UI choices use the saved profile.
This never opens Outlook, external documents, network resources or a real workspace.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language',choices=['ro','en','de','fr','es'],required=True)
    parser.add_argument('--scale',type=float,default=1)
    parser.add_argument('--capture-dir',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result={'language':args.language,'scale_simulated':args.scale,'platform':sys.platform,
            'windows_executable_verified':False,'native_windows_dpi_verified':False,'checks':[],'captures':[]}
    with tempfile.TemporaryDirectory(prefix='focusdesk-i18n-') as tmp:
        base=Path(tmp);os.environ['APPDATA']=str(base/'profile')
        config_path=base/'profile/FocusDesk/app.json';config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({'language':args.language}),encoding='utf-8')
        from focusdesk.i18n import tr,language,LANGUAGES,validate_catalogs
        from focusdesk.domain.models import Kind,Status
        from focusdesk.ui.app import FocusDeskApp
        from focusdesk.ui.design import px
        from focusdesk.ui.common import apply_theme, heading_width
        from focusdesk.ui.description_guide import guided_text
        from focusdesk.ui.settings_dialog import SettingsDialog
        from focusdesk.services.mail import default_subject,default_body
        from focusdesk.services.activity import activity_model,ActivityFilters,csv_text
        from focusdesk.domain.session import SessionRecord
        from datetime import datetime,timedelta,timezone
        from focusdesk.config import AppConfig
        app=FocusDeskApp();errors=[]
        app.root.report_callback_exception=lambda cls,value,tb:errors.append(f'{cls.__name__}: {value}')
        app.root.tk.call('tk','scaling',args.scale*96/72);apply_theme(app.root)
        app.root.minsize(px(app.root,1100),px(app.root,700))
        app.root.geometry(f'{px(app.root,1100)}x{px(app.root,700)}+0+0')
        def pump():
            for _ in range(5):app.root.update();time.sleep(.015)
        def check(name,condition):
            assert condition,name
            result['checks'].append(name)
        def shot(name,window):
            if args.capture_dir:
                from PIL import ImageGrab
                args.capture_dir.mkdir(parents=True,exist_ok=True);window.lift();pump()
                x,y=window.winfo_rootx(),window.winfo_rooty();w,h=window.winfo_width(),window.winfo_height()
                file=args.capture_dir/f'{name}.png';ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(file)
                result['captures'].append(file.name)
        def within(widget,owner):
            x,y=widget.winfo_rootx()-owner.winfo_rootx(),widget.winfo_rooty()-owner.winfo_rooty()
            return widget.winfo_viewable() and x>=0 and y>=0 and x+widget.winfo_width()<=owner.winfo_width() and y+widget.winfo_height()<=owner.winfo_height()
        def disk_snapshot():
            return {str(p.relative_to(app.ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in app.ws.root.rglob('*') if p.is_file() and not p.name.endswith('.lock')}
        try:
            check('profile language loaded',language()==args.language==app.config.language)
            check('all catalog keys/parameters match',not validate_catalogs())
            preferences=SettingsDialog(app.root,app)
            check('language settings without workspace',preferences._language_only and preferences.validate() and preferences.save_language())
            preferences.destroy()
            pump();app.show_guide('introducere');pump()
            check('guide without workspace',app.user_guide.library is not None)
            app.user_guide.window.close()
            check('create disposable workspace',app.open_workspace(base/'data',create=True))
            project=app.ws.create_node(Kind.PROJECT,'User project îäéñ')
            task=app.ws.create_node(Kind.TASK,'User task — Straße é ñ',project.id,description='')
            app.refresh_all();app.select_node(task.id,reveal=True);pump()
            check('localized header',app.guide_btn.cget('text')==tr('ui.app.ghid_de_utilizare'))
            check('header at minimum',all(within(w,app.root) for w in (app.guide_btn,app.new_btn,app.search_entry)))
            check('header no overlap',app.guide_btn.winfo_rootx()+app.guide_btn.winfo_width()<=app.search_entry.winfo_rootx())
            for view in ('today','tasks','calendar','activity'):
                app.show_view(view);pump();check('navigate '+view,app.current_view==view)
                if view=='tasks':
                    check('complete table headings',all(app.tasklist.tv.column(cid,'width')>=heading_width(app.tasklist.tv,app.tasklist.tv.heading(cid,'text')) for cid in app.tasklist.tv['columns']))
            deadline=time.monotonic()+6
            while app.activity_page._job and not app.activity_page._job.done and time.monotonic()<deadline:pump()
            check('activity uses stable table IDs',set(app.activity_page.tables)=={'sessions','days','projects','statuses'})
            app.activity_page.period_box.current(4)
            check('custom period ID',app.activity_page.period_id()=='custom')
            app.activity_page.period_box.current(1)
            check('30-day filter',app.activity_page.current_filters().first is not None)
            app.show_view('tasks');app.select_node(task.id,reveal=True);app.inspector.show_tab('details');pump()
            details=app.inspector.tab_by_id('details')
            form=details.editor.open_guide();pump();form.goal.insert('1.0','User goal îäéñ')
            form.steps[0].text.insert('1.0','  Preserve indentation\n    nested')
            expected=guided_text('User goal îäéñ',['  Preserve indentation\n    nested'],'')
            check('apply guided text',form.apply());pump()
            check('generated language/shared draft',details.editor.get()==expected and details.is_dirty())
            details.editor.undo();check('single Undo',details.editor.get()=='')
            details.editor.redo();check('Redo',details.editor.get()==expected)
            check('existing save',details.save());pump()
            check('description on disk',app.ws.get_description(task.id)==expected)
            app.open_task_space(task.id);pump()
            check('PeerText buffer',app.task_space.editor.get()==expected)
            check('journal/subtask draft ownership',app.inspector.tab_by_id('journal').node_id==task.id and app.inspector.tab_by_id('subtasks').node_id==task.id)
            for key,tab in app.task_space.sections.items():
                app.task_space.nb.select(app.task_space.scrolls[key]);app.root.focus_force();pump()
                check('task section '+key,app.user_guide.context_topic()=={'steps':'organizare','files':'fisiere','journal':'sesiuni#jurnalul-taskului','planning':'calendar','versions':'versiuni'}[key])
            app.task_space.back();pump();app.select_node(task.id,reveal=True);details=app.inspector.tab_by_id('details')
            details.expand_description();pump();expanded=details.expanded
            expanded.editor.text.insert('end-1c','\nUser expanded draft')
            help_window=app.show_guide('descriere');pump()
            check('modal help preserves grab',app.root.grab_current() is expanded)
            help_window.close();expanded.cancel();pump()
            check('expanded cancel preserves snapshot',details.editor.get()==expected)
            app.timer.start(task.id);timer_id=app.timer.state.session_id
            details.editor.replace('end-1c','end-1c','\nUser unsaved îäéñ');details.vars['title'].set('User title draft')
            draft=details.editor.get();pump()
            before=disk_snapshot();dialog=SettingsDialog(app.root,app);pump()
            other=next(code for code in LANGUAGES if code!=args.language);dialog.language_var.set(LANGUAGES[other])
            check('save profile preference',dialog.save_language());pump()
            check('preference persisted',AppConfig.load().language==other)
            check('language deferred',language()==args.language)
            check('preference does not write workspace',before==disk_snapshot())
            check('draft/timer retained',details.editor.get()==draft and details.vars['title'].get()=='User title draft' and app.timer.state.session_id==timer_id and app.timer.running)
            shot('settings-language',dialog);dialog.destroy();pump()
            window=app.show_guide('descriere');pump()
            window.geometry(f'{px(window,760)}x{px(window,500)}+5+5');pump()
            check('guide controls at minimum',all(within(getattr(window,name),window) for name in ('search_entry','toc','article','back_btn','forward_btn','close_btn','link_combo','link_btn')))
            check('all guide chapters',len(app.user_guide.library.chapters)==19)
            check('localized generated email',default_subject(task).endswith(task.title) and expected in default_body(app.ws,task))
            shot('guide-description',window);window.close();pump()
            details.revert();app.timer.stop(summary='User summary unchanged');pump()
            session=SessionRecord(node_id=task.id,start_at=datetime.now(timezone.utc)-timedelta(days=1,hours=1),end_at=datetime.now(timezone.utc)-timedelta(days=1),status='done',actual_seconds=3600)
            app.ws.repo.sessions.save(session)
            report=activity_model(app.ws).report(ActivityFilters())
            check('historical arithmetic',report.worked>=3600 and str(report.worked) in csv_text(report))
            app.ws.update_node(task.id,status=Status.DONE);app.refresh_all();pump()
            check('stable persisted done',app.ws.get(task.id).model_dump(mode='json')['status']=='done')
            app.ws.reopen_task(task.id);app.refresh_all();pump()
            check('reopen keeps own data',app.ws.get(task.id).status==Status.TODO and app.ws.get_description(task.id)==expected)
            templates=app.ws.templates.catalog();check('four bundled templates',len([t for t,b in templates if b])==4)
            check('user titles retained',app.ws.get(task.id).title==task.title)
            app.show_view('tasks');app.select_node(task.id,reveal=True);pump();shot('main-minimum',app.root)
            app.open_dashboard();pump();check('monthly calendar',app.dashboard.winfo_exists());app.dashboard.destroy()
            check('no Tk callback errors',not errors)
            check('no missing translation keys',not __import__('focusdesk.i18n',fromlist=['_missing'])._missing)
        finally:
            app.inspector.revert()
            if app.timer and app.timer.state:app.timer.discard()
            deadline=time.monotonic()+5
            while app._pending_workspace_jobs() and time.monotonic()<deadline:pump()
            app.on_close()
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'language':args.language,'scale':args.scale,'checks_passed':len(result['checks']),'captures':len(result['captures'])}))


if __name__=='__main__':main()
