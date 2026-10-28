"""Real Tk screenshots on isolated demo data; no user profile or workspace touched."""
import argparse
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime,timedelta,timezone


def demo(root):
    from focusdesk.services.workspace import Workspace
    from focusdesk.domain.models import Kind,Status,HistoryEvent
    from focusdesk.domain.session import SessionRecord
    ws=Workspace.open(root,create=True,name='Demo · Activitate')
    settings=ws.settings.model_copy(deep=True);settings.backup.daily=False;ws.update_settings(settings)
    now=datetime.now(timezone.utc).replace(hour=8,minute=0,second=0,microsecond=0)
    titles=['Automatizări SAP','Validări și raportare','Calitatea datelor','Integrări interne','Documentare','Operațiuni','Cerințe noi']
    for i,title in enumerate(titles):
        project=ws.create_node(Kind.PROJECT,title)
        for j in range(4):
            task=ws.create_node(Kind.TASK,['Verificare date','Automatizare raport','Analiză diferențe','Actualizare script'][j],project.id,
                due_date=(now-timedelta(days=2)).date() if j==0 else None,status=(Status.TODO,Status.IN_PROGRESS,Status.DONE,Status.WAITING)[j])
            if j==2:
                ws.repo.history.save(HistoryEvent(node_id=task.id,type='status_changed',at=now-timedelta(days=i+2),data={'to':'done'}))
            for k in range(3):
                start=now-timedelta(days=2*i+3*k+j)
                seconds=(70-i*5+j*8+k*3)*60
                ws.repo.sessions.save(SessionRecord(node_id=task.id,start_at=start,end_at=start+timedelta(minutes=90),started_actual_at=start,
                    actual_seconds=seconds,status='done',origin='manual'))
    task=ws.create_node(Kind.TASK,'Verificare punctuală, fără proiect')
    ws.repo.sessions.save(SessionRecord(node_id=task.id,start_at=now-timedelta(days=1),end_at=now-timedelta(days=1)+timedelta(minutes=40),actual_seconds=1800,status='done'))
    ws.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('docs/capturi-ui'));parser.add_argument('--scale',type=float,default=1);parser.add_argument('--minimum',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='focusdesk-dashboard-capture-') as directory:
        base=Path(directory);os.environ['APPDATA']=str(base/'profile')
        demo(base/'workspace')
        import focusdesk.ui.app as module
        apply=module.apply_theme
        def scaled(root,theme):
            root.tk.call('tk','scaling',args.scale*96/72);apply(root,theme)
        module.apply_theme=scaled
        app=module.FocusDeskApp();app._post_open_checks=lambda:None
        app.open_workspace(base/'workspace');app.show_view('activity')
        w,h=(1100,700) if args.minimum else (1640,1120)
        app.root.geometry(f'{round(w*args.scale)}x{round(h*args.scale)}+0+0')
        deadline=time.monotonic()+10
        while True:
            app.root.update()
            page=app.activity_page
            pending=page._job and not page._job.done
            pending=pending or any(getattr(tv,'_rows_job',None) for tv in page.tables.values())
            if not pending and page.report:break
            if time.monotonic()>deadline:raise RuntimeError('Dashboard did not load')
            time.sleep(.02)
        for _ in range(4):app.root.update();time.sleep(.05)
        from PIL import ImageGrab
        root=app.root
        def shot(name):
            root.update()
            ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(args.output/name)
        tag=f'{round(args.scale*100)}'
        shot(f'activitate-dashboard-{tag}.png')
        if not args.minimum:
            page.sf.canvas.yview_moveto(1);root.update();shot(f'activitate-detalii-{tag}.png')
            app.open_dashboard();root.update();time.sleep(.1);root.update()
            window=app.dashboard
            ImageGrab.grab(bbox=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())).save(args.output/'activitate-calendar-lunar.png')
            window.destroy()
        # Horizontal fit at the supported minimum; vertical overflow is scrollable.
        for widget in (page.cards,page.filters_frame,page.charts):
            assert widget.winfo_x()+widget.winfo_width()<=page.sf.inner.winfo_width()+2
        print(f'Captured actual Tk at scaling {args.scale}, {root.winfo_width()}x{root.winfo_height()}; horizontal layout fits.')
        app.on_close()
if __name__=='__main__':main()
