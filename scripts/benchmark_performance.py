"""Reproducible disposable workload; run under xvfb-run. Never uses user data."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta, timezone


def generate(root, count, meetings=0):
    from focusdesk.services.workspace import Workspace
    from focusdesk.domain.models import Node, Kind, Status, Priority, HistoryEvent
    from focusdesk.domain.session import SessionRecord
    from focusdesk.storage.atomic import atomic_write_json, atomic_write_text
    from focusdesk.storage.paths import physical_dirname
    ws = Workspace.open(root, create=True, name='Benchmark')
    settings = ws.settings.model_copy(deep=True); settings.backup.daily = False
    ws.update_settings(settings)
    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    project = Node(kind=Kind.PROJECT, title='Proiect benchmark')
    ws.repo.create_node(project)
    active = []
    groups = []
    for i in range(count):
        n = Node(kind=Kind.TASK, title=f'Task {i:06d}', parent_id=(groups[(i-10)%len(groups)] if i >= 10 else project.id),
                 status=Status.TODO if i < 50 else Status.DONE, priority=Priority.NORMAL,
                 sort_order=i, pinned_today=now.date() if i < 10 else None)
        # Fixture generation intentionally outside timed operations (no UI/service events).
        directory = root / 'nodes' / physical_dirname(n.title, n.id)
        atomic_write_json(directory/'node.json', n.model_dump(mode='json'))
        atomic_write_text(directory/'description.md', 'Documentare istorică șțâ\n' * 80)
        if i < 10: groups.append(n.id)
        if i < 50: active.append(n.id)
        for j in range(3):
            start = now - timedelta(days=(i % 365)+j+1)
            s = SessionRecord(node_id=n.id, start_at=start, end_at=start+timedelta(minutes=30),
                              status='done', actual_seconds=900, summary='Rezumat\n'*40)
            atomic_write_json(root/'_system/sessions'/f'{s.id}.json', s.model_dump(mode='json'))
            e = HistoryEvent(node_id=n.id, type='status_changed', data={'to':'done'})
            atomic_write_json(root/'_system/history'/f'{e.id}.json', e.model_dump(mode='json'))
    # Identical local meeting payloads even when the baseline does not implement this feature.
    for i in range(meetings):
        from uuid import uuid5, UUID
        mid=str(uuid5(UUID(project.id),f'meeting-{i}'))
        path=root/'_system'/'meetings'/mid
        start=now-timedelta(days=i%365)
        atomic_write_json(path/'source.json',dict(id=mid,provider='manual',title=f'Întâlnire istorică {i:06d}',
            start_at=start.isoformat(),end_at=(start+timedelta(hours=1)).isoformat(),timezone='Europe/Bucharest'))
        atomic_write_json(path/'local.json',dict(actions=[],linked_node_ids=[]))
        atomic_write_text(path/'notes.md','Notițe istorice · decizii și detalii care nu se încarcă în liste.\n'*160)
    ws.close()
    return active


def measure(root, active):
    from focusdesk.ui.app import FocusDeskApp
    from focusdesk.services.activity import activity_ledger
    reads = [0, 0]
    original = Path.open
    def tracked(path, mode='r', *a, **kw):
        if 'r' in mode and path.is_relative_to(root) and path.is_file():
            reads[0] += 1
            try: reads[1] += path.stat().st_size
            except OSError: pass
        return original(path, mode, *a, **kw)
    Path.open = tracked
    report = {}
    from focusdesk.config import AppConfig
    AppConfig(last_view='today',show_completed=False).save()
    FocusDeskApp._startup = lambda self: None
    tracemalloc.start()
    def phase(name, fn):
        before = reads.copy(); start = time.perf_counter()
        result = fn()
        report[name] = {'ms': round((time.perf_counter()-start)*1000, 2),
                        'reads': reads[0]-before[0], 'bytes': reads[1]-before[1]}
        return result
    app = phase('ui_construct', FocusDeskApp)
    app.root.withdraw()
    # Exclude optional startup maintenance/backups; measured separately from interactive work.
    app._post_open_checks = lambda: None
    phase('cold_open', lambda: app.open_workspace(root))
    def settle():
        deadline=time.perf_counter()+30
        def pending(widget):
            job=getattr(widget,'_job',None)
            return bool(getattr(widget,'_rows_job',None)) or bool(job and not job.done) or any(pending(w) for w in widget.winfo_children())
        app.root.update()
        while pending(app.root):
            if time.perf_counter()>deadline:raise RuntimeError('UI fill did not finish')
            time.sleep(.001);app.root.update()
    def navigate():
        for view in ('tasks','today','calendar','tasks'):
            app.show_view(view); settle()
    phase('navigation', navigate)
    phase('select', lambda: (app.select_node(active[0]), settle()))
    phase('save_title', lambda: app.ws.update_node(active[0], title='Task redenumit benchmark'))
    phase('refresh_after_save', lambda: (app.refresh_all(), settle()))
    phase('search', lambda: app.q.search('Task 000090'))
    phase('activity', lambda: (app.show_view('activity'), settle()))
    totals = activity_ledger(app.ws, 30)
    report['totals'] = {k:totals[k] for k in ('worked','planned')}
    if hasattr(app.ws,'meetings'):
        meetings=app.ws.meetings.store.summaries()
        if meetings:
            page=app.calendar_page.meetings
            def meeting_list():
                app.show_view('calendar');app.calendar_page.nb.select(page)
                page.mode.set('Cu notițe');page.filter_changed();settle()
            phase('meetings_list',meeting_list)
            phase('meeting_open',lambda:(page.open(meetings[0]['id']),settle()))
            page.back()
    report['memory'] = {'python_peak_mib':round(tracemalloc.get_traced_memory()[1]/2**20,2),
                        'rss_peak_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)}
    app.inspector.revert(); app.on_close()
    tracemalloc.stop()
    Path.open=original
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tasks',type=int,default=1000)
    p.add_argument('--meetings',type=int,default=0)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker-root',type=Path)
    p.add_argument('--ids',type=Path)
    args=p.parse_args()
    if args.tasks < 50: p.error('--tasks trebuie să fie cel puțin 50')
    if args.worker_root:
        args.output.write_text(json.dumps(measure(args.worker_root,json.loads(args.ids.read_text())),ensure_ascii=False,indent=2)+'\n')
        return
    with tempfile.TemporaryDirectory(prefix='focusdesk-benchmark-') as d:
        os.environ['APPDATA']=str(Path(d)/'profile')
        root=Path(d)/'workspace';active=generate(root,args.tasks,args.meetings)
        ids=Path(d)/'ids.json';ids.write_text(json.dumps(active))
        report={'meetings':args.meetings,'tasks':args.tasks,'active_tasks':50,'sessions':args.tasks*3,'history':args.tasks*3}
        for label in ('first_open','indexed_reopen'):
            out=Path(d)/(label+'.json')
            subprocess.run([sys.executable,__file__,'--worker-root',str(root),'--ids',str(ids),'--output',str(out)],check=True)
            report[label]=json.loads(out.read_text())
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
