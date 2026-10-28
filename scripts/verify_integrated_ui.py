"""Real Linux/Tk layout and keyboard review, in a temporary demo workspace. Optional Pillow for captures."""
import argparse,json,os,tempfile,time
from pathlib import Path
from datetime import timedelta


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scale',type=float,default=1.0);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    from focusdesk.services.workspace import Workspace
    from focusdesk.domain.models import Kind,Status
    from focusdesk.domain.common import utcnow
    with tempfile.TemporaryDirectory(prefix='focusdesk-ui-integration-') as folder:
        base=Path(folder);os.environ['APPDATA']=str(base/'profile')
        ws=Workspace.open(base/'workspace',create=True)
        source=None
        for i in range(70):
            p=ws.create_node(Kind.PROJECT,f'Proiect {i:02d} · descriere lungă pentru verificarea navigării și a contextului')
            task=ws.create_node(Kind.TASK,'Script cu titlu lung · validarea diferențelor, raportare și păstrarea contextului',p.id,
                status=Status.TODO if i<15 else Status.DONE)
            if i==0:source=task
        now=utcnow();m=ws.meetings.manual(title='Întâlnire cu titlu foarte lung · decizii pentru rapoarte și validări, clarificări și următorii pași',start=now,end=now+timedelta(hours=1))
        ws.meetings.save_notes(m.id,'Subiecte discutate\n\nText liber cu diacritice și indentare.\n    Detalii care rămân în notițe.\n\nDecizii\n\nCrearea taskurilor se face numai explicit.\n')
        ws.meetings.save_action(m.id,text='Acțiune cu un text lung, care trebuie să rămână lizibilă și accesibilă prin tastatură',responsible='Colega responsabilă',state='todo')
        ws.close()
        import focusdesk.ui.app as module
        apply=module.apply_theme
        def scaled(root,theme):root.tk.call('tk','scaling',args.scale*96/72);apply(root,theme)
        module.apply_theme=scaled
        app=module.FocusDeskApp();app._post_open_checks=lambda:None
        app.open_workspace(base/'workspace');app.root.geometry(f'{round(1100*args.scale)}x{round(700*args.scale)}+0+0')
        def settle():
            deadline=time.monotonic()+8
            while True:
                app.root.update()
                job=app.activity_page._job
                if not job or job.done:break
                if time.monotonic()>deadline:raise RuntimeError('UI work did not complete')
                time.sleep(.01)
            app.root.update()
        checks=[]
        def fit(name,widget,parent=None):
            parent=parent or app.root;app.root.update()
            a=(widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_rootx()+widget.winfo_width(),widget.winfo_rooty()+widget.winfo_height())
            b=(parent.winfo_rootx(),parent.winfo_rooty(),parent.winfo_rootx()+parent.winfo_width(),parent.winfo_rooty()+parent.winfo_height())
            ok=bool(widget.winfo_ismapped()) and a[0]>=b[0]-2 and a[1]>=b[1]-2 and a[2]<=b[2]+2 and a[3]<=b[3]+2
            checks.append(dict(name=name,ok=ok,widget=a,container=b));return ok
        def shot(name,window=None):
            from PIL import ImageGrab
            w=window or app.root;app.root.update()
            ImageGrab.grab(bbox=(w.winfo_rootx(),w.winfo_rooty(),w.winfo_rootx()+w.winfo_width(),w.winfo_rooty()+w.winfo_height())).save(args.output/f'{name}-{round(args.scale*100)}.png')
        app.select_node(source.id,reveal=True);settle()
        tab=app.inspector.tab_by_title('Detalii');guide=tab.editor.open_guide();app.root.update()
        guide.goal.insert('1.0','Scop verificat în interfață')
        guide.steps[0].text.insert('1.0','Primul pas')
        fit('guide_apply',guide.apply_btn,guide)
        guide.apply();app.root.update();app.save_current()
        description=tab.editor.get()
        app.open_task_space(source.id);app.root.update()
        fit('task_save',app.task_space.save_btn);fit('task_description',app.task_space.editor.text)
        assert app.task_space.editor.get()==description
        tab.expand_description();expanded=tab.expanded;app.root.update()
        expanded.editor.replace('end-1c','end-1c','\nTemporar');expanded.cancel();app.root.update()
        assert app.task_space.editor.get()==description
        app.timer.start(source.id);app.timer_indicator.update_state()
        app.task_space.toggle_focus();app.root.update();fit('timer_in_focus',app.timer_indicator)
        for name,button in [('timer_pause',app.timer_indicator.pause),('timer_stop',app.timer_indicator.stop),('timer_open',app.timer_indicator.open)]:fit(name,button)
        shot('integrare-task');app.timer.stop();app.timer_indicator.update_state()
        app.task_space.exit_focus();app.task_space.back();app.show_view('activity');settle()
        for name,w in [('dashboard_export',app.activity_page.export_btn),('dashboard_cards',app.activity_page.cards),('dashboard_filters',app.activity_page.filters_frame)]:fit(name,w)
        shot('integrare-activitate')
        app.show_view('calendar');page=app.calendar_page.meetings;app.calendar_page.nb.select(page);app.root.update()
        for name,w in [('meetings_import',page.import_btn),('meetings_manual',page.manual_btn),('meetings_open',page.more)]:fit(name,w)
        page.tv.selection_set(m.id);page.tv.focus(m.id);page.tv.focus_force();app.root.update();page.tv.event_generate('<Return>');app.root.update()
        assert page.mid==m.id
        fit('meeting_editor',page.notes);fit('meeting_actions',page.actions_menu);shot('integrare-intalnire')
        save=app.ws.meetings.save_notes
        app.ws.meetings.save_notes=lambda *a:(_ for _ in ()).throw(OSError('Eroare demonstrativă de salvare, ciorna este păstrată'))
        page.notes.insert('end','Ciornă la eroare');app.root.update();assert not page.save() and page.dirty
        assert 'Ciornă la eroare' in page.notes.get('1.0','end-1c')
        app.ws.meetings.save_notes=save;assert page.save();page.back();page.query.set('fără rezultate imposibile');page.filter_changed();app.root.update()
        assert not page.tv.get_children()
        report=dict(platform='Linux/Xvfb, not Windows',scale=args.scale,geometry=app.root.geometry(),checks=checks)
        (args.output/f'ui-{round(args.scale*100)}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        app.on_close()
        failed=[r['name'] for r in checks if not r['ok']]
        if failed:raise AssertionError('Controls outside supported window: '+', '.join(failed))
        print(f'Scale {args.scale}: {len(checks)} geometry checks, keyboard Enter, expanded cancel, empty state, save error passed.')
if __name__=='__main__':main()
