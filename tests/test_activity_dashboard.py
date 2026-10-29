"""Shared activity arithmetic, offline export and real Tk dashboard regressions."""
import csv
import io
from dataclasses import replace
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

import pytest
from focusdesk.domain.models import Kind, Status
from focusdesk.domain.session import SessionRecord
from focusdesk.services.activity import (ActivityFilters, LiveWork, activity_model, csv_text,
    export_csv, period_bounds, safe_csv)
from focusdesk.storage.repository import WorkspaceRepository

NOW=datetime(2026,10,28,12,tzinfo=timezone.utc)


def save_session(ws,node,start,*,seconds=600,status='done',actual=None,end=None):
    s=SessionRecord(node_id=node.id if hasattr(node,'id') else node,start_at=start,
                    end_at=end or start+timedelta(hours=1),started_actual_at=actual,
                    actual_seconds=seconds,status=status)
    ws.repo.sessions.save(s);return s


def report(ws,first=date(2026,10,1),last=date(2026,10,31),**kwargs):
    return activity_model(ws).report(ActivityFilters(first,last),now=NOW,**kwargs)


def assert_equal_views(data):
    assert sum(r.worked for r in data.rows)==data.worked
    assert sum(r.planned for r in data.rows)==data.planned
    assert sum(d['worked'] for d in data.days.values())==data.worked
    assert sum(d['planned'] for d in data.days.values())==data.planned
    assert sum(p['worked'] for p in data.projects.values())==data.worked
    assert sum(p['planned'] for p in data.projects.values())==data.planned
    assert sum(bucket['worked'] for bucket in data.time_buckets()[1])==data.worked
    assert sum(bucket['planned'] for bucket in data.time_buckets()[1])==data.planned
    assert sum(seconds for name,ids,seconds in data.top_projects(2))==data.worked
    exported=list(csv.DictReader(io.StringIO(csv_text(data).lstrip('\ufeff')),delimiter=';'))
    sessions=[r for r in exported if r['Tip']=='Sesiune']
    assert sum(int(r['Lucrat înregistrat (secunde)']) for r in sessions)==data.worked
    assert sum(int(r['Programat eligibil (secunde)']) for r in sessions)==data.planned
    assert sum(int(r['Live nesalvat (secunde)']) for r in sessions)==data.live
    indicators={r['Indicator']:int(r['Valoare indicator']) for r in exported if r['Tip']=='Indicator'}
    assert indicators['Lucrat înregistrat']==data.worked
    assert indicators['Taskuri finalizate distincte']==len(data.completed_ids)


def test_parent_child_closed_archived_moved_and_missing(ws):
    a=ws.create_node(Kind.PROJECT,'A');b=ws.create_node(Kind.PROJECT,'B')
    parent=ws.create_node(Kind.TASK,'Părinte',a.id);child=ws.create_node(Kind.TASK,'Copil',parent.id)
    save_session(ws,parent,NOW,seconds=120);save_session(ws,child,NOW,seconds=240)
    ws.update_node(child.id,status=Status.DONE);ws.archive(child.id)
    data=report(ws);assert data.worked==360;assert_equal_views(data)
    ws.add_related(parent.id,b.id)
    assert report(ws).projects[a.id]['worked']==360
    ws.move(parent.id,b.id)
    assert report(ws).projects[b.id]['worked']==360
    ws.trash(parent.id)
    data=report(ws);assert data.worked==360
    assert all(row.task=='Task indisponibil' and row.project_id is None for row in data.rows)
    assert_equal_views(data)


def test_cancelled_missed_reservations_and_actual_day(ws):
    task=ws.create_node(Kind.TASK,'T')
    for status in ('done','planned','cancelled','missed'):
        save_session(ws,task,NOW,status=status,seconds=100)
    data=report(ws);assert data.worked==400;assert data.planned==7200
    assert all(r.planned==0 for r in data.rows if r.status in ('cancelled','missed'))
    save_session(ws,task,NOW-timedelta(days=40),actual=NOW,seconds=900)
    data=report(ws);assert data.worked==1300;assert data.planned==7200
    assert_equal_views(data)


def test_distinct_done_transitions_reopening_and_legacy(ws,monkeypatch):
    task=ws.create_node(Kind.TASK,'T')
    from focusdesk.domain.models import HistoryEvent
    for to in ('done','todo','done'):
        ws.repo.history.save(HistoryEvent(type='status_changed',node_id=task.id,at=NOW,data={'to':to}))
    ws.repo.history.save(HistoryEvent(type='status_changed',node_id=task.id,at=NOW-timedelta(days=90),data={'to':'done'}))
    legacy=ws.create_node(Kind.TASK,'Vechi',status=Status.DONE,completed_at=NOW,updated_at=NOW)
    project=ws.create_node(Kind.PROJECT,'Proiect')
    ws.repo.history.save(HistoryEvent(type='status_changed',node_id=project.id,at=NOW,data={'to':'done'}))
    data=report(ws)
    assert data.completed_ids=={task.id};assert data.legacy_done==1
    assert task.id not in report(ws,date(2026,9,1),date(2026,9,30)).completed_ids
    assert legacy.id not in data.completed_ids
    assert_equal_views(data)


def test_live_delta_is_separate_and_not_double_counted(ws):
    task=ws.create_node(Kind.TASK,'T');s=save_session(ws,task,NOW,seconds=100,status='active')
    live=LiveWork(s.id,task.id,160,NOW)
    data=report(ws,live=live)
    assert data.worked==100 and data.live==60
    assert_equal_views(data)
    from focusdesk.services.queries import Queries
    assert Queries(ws).worked_map((task.id,160))[task.id]==100
    assert activity_model(ws).live_delta(live)==60
    assert Queries(ws).worked_by_day(date(2026,10,28),date(2026,10,28),live)[date(2026,10,28)][task.id]==100
    older=report(ws,date(2026,9,1),date(2026,9,30),live=live)
    assert older.worked==older.live==0
    assert report(ws,live=replace(live,seconds=90)).live==0


@pytest.mark.parametrize('start,end,expected_day,seconds',[
    (datetime(2026,10,27,21,30,tzinfo=timezone.utc),datetime(2026,10,28,1,tzinfo=timezone.utc),date(2026,10,27),12600),
    (datetime(2026,3,29,0,30,tzinfo=timezone.utc),datetime(2026,3,29,2,30,tzinfo=timezone.utc),date(2026,3,29),7200),
    (datetime(2026,10,25,0,30,tzinfo=timezone.utc),datetime(2026,10,25,2,30,tzinfo=timezone.utc),date(2026,10,25),7200),
])
def test_midnight_and_dst_use_workspace_start_day(ws,start,end,expected_day,seconds):
    ws.settings.timezone='Europe/Bucharest'
    task=ws.create_node(Kind.TASK,'T');save_session(ws,task,start,end=end,seconds=seconds,actual=start)
    data=report(ws,expected_day,expected_day)
    assert data.worked==data.planned==seconds
    assert set(data.days)=={expected_day};assert_equal_views(data)
    next_day=report(ws,expected_day+timedelta(days=1),expected_day+timedelta(days=1))
    assert next_day.worked==next_day.planned==0


def test_empty_interval_current_status_and_overdue_are_explicit(ws):
    task=ws.create_node(Kind.TASK,'Restant',due_date=date(2026,1,1))
    data=report(ws,date(2025,1,1),date(2025,1,7))
    assert not data.rows and data.worked==data.planned==0
    assert data.overdue_ids=={task.id};assert data.statuses[Status.TODO]==1
    ws.archive(task.id)
    assert not report(ws).overdue_ids
    assert_equal_views(data)


def test_project_and_day_filters_top_rest_granularity(ws):
    for i in range(8):
        project=ws.create_node(Kind.PROJECT,f'P{i}')
        task=ws.create_node(Kind.TASK,f'T{i}',project.id)
        save_session(ws,task,NOW-timedelta(days=i),seconds=100*(i+1))
    independent=ws.create_node(Kind.TASK,'Independent');save_session(ws,independent,NOW)
    model=activity_model(ws);data=report(ws)
    top=data.top_projects(3);assert top[-1][0]=='Restul'
    focus=ActivityFilters(date(2026,10,1),date(2026,10,31),focus_projects=top[-1][1])
    subset=model.report(focus,now=NOW)
    assert subset.worked==top[-1][2];assert_equal_views(subset)
    assert model.report(ActivityFilters(project_id=None),now=NOW).worked==600
    assert data.time_buckets()[0]=='days'
    assert report(ws,date(2026,8,1),date(2026,10,31)).time_buckets()[0]=='weeks'
    assert report(ws,date(2025,1,1),date(2026,10,31)).time_buckets()[0]=='months'


def test_period_bounds_and_formula_safe_utf8_export(ws,tmp_path):
    assert period_bounds('Luna curentă',date(2024,2,15))==(date(2024,2,1),date(2024,2,29))
    with pytest.raises(ValueError):period_bounds('Interval personalizat',date.today(),date(2026,2,2),date(2026,1,1))
    task=ws.create_node(Kind.TASK,'=HYPERLINK("evil") șță');save_session(ws,task,NOW)
    data=report(ws);dest=tmp_path/'activitate.csv';export_csv(data,dest)
    assert dest.read_bytes().startswith(b'\xef\xbb\xbf')
    assert "'=HYPERLINK" in dest.read_text('utf-8-sig') and 'șță' in dest.read_text('utf-8-sig')
    for value in ('=1+1',' +cmd','@SUM(A1)','-2+4','\tformula','\rtext','\ntext'):
        assert safe_csv(value).startswith("'")
    assert_equal_views(data)


def test_repeated_filters_read_no_authoritative_payloads(ws,monkeypatch):
    project=ws.create_node(Kind.PROJECT,'P');task=ws.create_node(Kind.TASK,'T',project.id)
    save_session(ws,task,NOW)
    model=activity_model(ws);data=report(ws)
    def forbidden(*a,**kw):raise AssertionError('Unnecessary filesystem read')
    monkeypatch.setattr('focusdesk.storage.records.read_json',forbidden)
    for i in range(12):
        data=model.report(ActivityFilters(date(2026,10,1)+timedelta(days=i),date(2026,10,31),project.id),now=NOW)
        assert_equal_views(data)


def settle(ui):
    import time
    deadline=time.monotonic()+5
    page=ui.activity_page
    while True:
        ui.root.update()
        pending=page._job and not page._job.done
        pending=pending or any(getattr(tv,'_rows_job',None) for tv in page.tables.values())
        if not pending:break
        assert time.monotonic()<deadline,'dashboard did not settle'
        time.sleep(.01)


def test_real_dashboard_filters_keyboard_return_and_export(ui,tmp_path,monkeypatch):
    page=ui.activity_page;task=ui.ws.get(ui.selected_id)
    save_session(ui.ws,task,datetime.now(timezone.utc)-timedelta(hours=1),seconds=3600)
    ui.show_view('activity');settle(ui)
    assert page.report.worked==3600
    assert page.metrics['worked'].cget('text')=='1:00:00'
    assert_equal_views(page.report)
    page.time_chart.activate();settle(ui)
    assert page._focus_first is not None and page.clear_btn.instate(['!disabled'])
    page.clear_focus();settle(ui)
    tv=page.tables['sessions'];tv.selection_set(page.report.rows[0].id)
    page.sf.canvas.yview_moveto(.4);ui.root.update();scroll=page.sf.canvas.yview()[0]
    filters=page.current_filters();page.open_task();ui.show_view('activity');settle(ui)
    assert page.current_filters()==filters
    assert abs(page.sf.canvas.yview()[0]-scroll)<.1
    dest=tmp_path/'raport.csv'
    monkeypatch.setattr('focusdesk.ui.activity_page.filedialog.asksaveasfilename',lambda **kw:str(dest))
    page.export();assert dest.exists();assert_equal_views(page.report)
    ui.open_dashboard();ui.root.update()
    assert ui.dashboard.report.worked==page.report.worked
    ui.dashboard.destroy()


def test_invalid_custom_range_has_error_state_and_recovers(ui):
    ui.show_view('activity');page=ui.activity_page
    page.period.set('Interval personalizat');page.first.set('28.10.2026');page.last.set('01.10.2026');page.refresh()
    assert page.report is None and 'Raport indisponibil' in page.state.cget('text')
    assert page.export_btn.instate(['disabled'])
    page.reset_filters();settle(ui);assert page.report is not None


def test_history_v1_index_rebuilt_to_transition_summary(tmp_path):
    from focusdesk.services.workspace import Workspace
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    task=ws.create_node(Kind.TASK,'T');ws.update_node(task.id,status=Status.DONE)
    ws.close()
    cache=root/'_system/history/.cache/index.json'
    import json
    data=json.loads(cache.read_text());data['version']=1;cache.write_text(json.dumps(data))
    ws=Workspace.open(root)
    try:
        data=activity_model(ws).report(ActivityFilters())
        assert task.id in data.completed_ids
        assert json.loads(cache.read_text())['version']==2
    finally:ws.close()


def test_async_filter_results_apply_only_latest_and_on_tk_thread(ui,monkeypatch):
    import threading
    page=ui.activity_page
    project=ui.ws.create_node(Kind.PROJECT,'P')
    task=ui.ws.create_node(Kind.TASK,'T',project.id)
    save_session(ui.ws,task,datetime.now(timezone.utc)-timedelta(hours=1))
    # Force initial catalog reconciliation through the existing worker bridge.
    ui.ws.repo.history.invalidate()
    main=threading.get_ident();workers=[];renders=[]
    model=activity_model(ui.ws);original=model.report;render=page.render
    def observed(*a,**kw):workers.append(threading.get_ident());return original(*a,**kw)
    def painted(data):renders.append(threading.get_ident());return render(data)
    monkeypatch.setattr(model,'report',observed);monkeypatch.setattr(page,'render',painted)
    ui.show_view('activity')
    page.project.set('Fără proiect');page.filters_changed()
    settle(ui)
    assert page.report.filters.project_id is None and page.report.worked==0
    assert any(thread!=main for thread in workers)
    assert renders and set(renders)=={main}


def test_project_rename_keeps_selected_id(ui):
    project=ui.ws.create_node(Kind.PROJECT,'Nume vechi')
    ui.show_view('activity');settle(ui);page=ui.activity_page
    label=next(label for label,pid in page._project_options.items() if pid==project.id)
    page.project.set(label);page.filters_changed();settle(ui)
    ui.ws.rename(project.id,'Nume nou');page.refresh();settle(ui)
    assert page.report.filters.project_id==project.id
    assert 'Nume nou' in page.project.get()


def test_corrupt_source_is_reported_without_inventing_duration(ws):
    task=ws.create_node(Kind.TASK,'T');s=save_session(ws,task,NOW)
    ws.repo.sessions._path(s.id).write_text('{bad')
    ws.repo.sessions.invalidate()
    data=report(ws)
    assert data.worked==0 and data.issues


def test_live_refresh_keeps_actual_start_outside_period_excluded(ws):
    task=ws.create_node(Kind.TASK,'T')
    s=save_session(ws,task,NOW,actual=NOW-timedelta(days=2),status='active')
    live=LiveWork(s.id,task.id,900,NOW-timedelta(days=2))
    data=report(ws,date(2026,10,28),date(2026,10,28),live=live)
    assert data.rows and data.live==0
    refreshed=data.with_live(replace(live,seconds=1000),400)
    assert refreshed.live==0 and refreshed.planned==data.planned
    assert_equal_views(refreshed)
