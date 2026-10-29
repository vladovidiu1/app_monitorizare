"""One local activity calculation model for cards, charts, calendar, tables and CSV."""
from __future__ import annotations

from ..i18n import tr

from bisect import bisect_left
from collections import OrderedDict, Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace, MappingProxyType
from zoneinfo import ZoneInfo
import csv
import io
import calendar
from threading import RLock

from ..domain.common import utcnow
from ..domain.models import Kind, Status, CLOSED_STATUSES
from ..domain.labels import STATUS_LABELS, SESSION_STATUS_LABELS, display_status
from ..storage.atomic import atomic_write_text

ALL_PROJECTS = '*'
DEFINITIONS = {
    'worked': tr('services.activity.actual_seconds_salvat_o_singura_data_pe_sesiune_fara_rollup_parinte_co'),
    'planned': tr('services.activity.durata_rezervata_la_data_start_at_fara_cancelled_missed_si_fara_timer'),
    'completed': tr('services.activity.taskuri_distincte_cu_tranzitie_la_done_in_perioada_aleasa_redeschidere'),
    'overdue': tr('services.activity.situatie_curenta_taskuri_deschise_nearhivate_cu_termen_depasit_acum_nu'),
    'live': tr('services.activity.separat_de_lucrat_inregistrat_max_0_secunde_timer_actual_seconds_deja'),
}


@dataclass(frozen=True)
class ActivityFilters:
    first: date | None = None
    last: date | None = None
    project_id: str | None = ALL_PROJECTS  # None = Fără proiect, * = toate
    focus_first: date | None = None
    focus_last: date | None = None
    focus_projects: tuple[str | None, ...] | None = None

    def bounds(self):
        first = max(d for d in (self.first,self.focus_first) if d) if self.first or self.focus_first else None
        last = min(d for d in (self.last,self.focus_last) if d) if self.last or self.focus_last else None
        return first,last


@dataclass(frozen=True)
class LiveWork:
    session_id: str
    node_id: str
    seconds: int
    started_at: datetime


@dataclass(frozen=True)
class ActivityRow:
    id: str
    node_id: str
    task: str
    project_id: str | None
    project: str
    status: str
    start_at: datetime
    end_at: datetime
    worked_day: date
    planned_day: date
    worked: int
    planned: int
    live: int = 0


@dataclass(frozen=True)
class ActivityReport:
    filters: ActivityFilters
    timezone: str
    rows: tuple[ActivityRow, ...]
    completed_ids: frozenset[str]
    overdue_ids: frozenset[str]
    statuses: dict
    legacy_done: int
    issues: tuple[str, ...] = ()
    project_filter_label: str = tr('ui.activity_page.toate_proiectele')

    @property
    def worked(self): return sum(r.worked for r in self.rows)
    @property
    def planned(self): return sum(r.planned for r in self.rows)
    @property
    def live(self): return sum(r.live for r in self.rows)
    @property
    def days(self):
        out = {}
        for row in self.rows:
            for day,field,amount in ((row.worked_day,'worked',row.worked),(row.planned_day,'planned',row.planned),(row.worked_day,'live',row.live)):
                if amount: out.setdefault(day,dict(worked=0,planned=0,live=0))[field] += amount
        return out
    @property
    def projects(self):
        out = {}
        for row in self.rows:
            bucket = out.setdefault(row.project_id,dict(name=row.project,worked=0,planned=0,live=0))
            for key in ('worked','planned','live'): bucket[key] += getattr(row,key)
        return out

    def time_buckets(self):
        days = self.days
        first,last = self.filters.bounds()
        first = first or min(days,default=date.today())
        last = last or max(days,default=first)
        span = (last-first).days+1
        mode = 'days' if span <= 45 else 'weeks' if span <= 180 else 'months'
        groups = {}
        for day,totals in sorted(days.items()):
            start = day if mode == 'days' else day-timedelta(days=day.weekday()) if mode == 'weeks' else day.replace(day=1)
            end = start if mode == 'days' else start+timedelta(days=6) if mode == 'weeks' else start.replace(day=calendar.monthrange(start.year,start.month)[1])
            item = groups.setdefault(start,dict(first=max(first,start),last=min(last,end),worked=0,planned=0,live=0))
            for key in ('worked','planned','live'): item[key]+=totals[key]
        return mode,tuple(groups.values())

    def top_projects(self,n=5):
        projects = sorted(self.projects.items(),key=lambda pair:(-pair[1]['worked'],pair[1]['name'].casefold(),pair[0] or ''))
        rows = [(data['name'],(pid,),data['worked']) for pid,data in projects[:n]]
        if len(projects)>n: rows.append((tr('activity.others'),tuple(pid for pid,data in projects[n:]),sum(data['worked'] for pid,data in projects[n:])))
        return tuple(rows)

    def with_live(self,live,delta):
        first,last=self.filters.bounds()
        def value(row):
            eligible=(first is None or row.worked_day>=first) and (last is None or row.worked_day<=last)
            return delta if live and row.id==live.session_id and eligible else 0
        return replace(self,rows=tuple(replace(row,live=value(row)) if row.live!=value(row) else row for row in self.rows))

    def saved_by_day(self):
        out = {}
        for row in self.rows:
            if row.worked:
                bucket = out.setdefault(row.worked_day,{})
                bucket[row.node_id] = bucket.get(row.node_id,0)+row.worked
        return out


def period_bounds(label,today,custom_first=None,custom_last=None):
    days={'7d':7,'30d':30,'90d':90,'7 zile':7,'30 zile':30,'30 de zile':30,'90 zile':90,'90 de zile':90}.get(label)
    if days: return today-timedelta(days=days-1),today
    if label in ('month','Luna curentă'): return today.replace(day=1),today.replace(day=calendar.monthrange(today.year,today.month)[1])
    if label in ('custom','Interval personalizat'):
        if not custom_first or not custom_last or custom_first>custom_last:
            raise ValueError(tr('services.activity.alege_un_interval_valid_inceputul_nu_poate_fi_dupa_sfarsit'))
        return custom_first,custom_last
    return None,None


def project_filter_title(filters,nodes):
    chosen=filters.focus_projects if filters.focus_projects is not None else (None if filters.project_id==ALL_PROJECTS else (filters.project_id,))
    return tr('ui.activity_page.toate_proiectele') if chosen is None else ', '.join(nodes[pid].title if pid in nodes else tr('ui.activity_page.fara_proiect') if pid is None else tr('common.project_unavailable') for pid in chosen)


class ActivityModel:
    def __init__(self,ws):
        self.ws=ws
        self._mutex=RLock()
        self._session_key=None;self._history_key=None
        self._facts={};self._times={};self._events=[]
        self._cache=OrderedDict()

    def _prepare(self, *, sessions_only=False):
        store=self.ws.repo.sessions
        key=(store.revision,self.ws.repo.reload_generation)
        if key!=self._session_key:
            facts={};times={'worked':[],'planned':[]}
            for item in store.summaries():
                row=dict(item)
                for field in ('start_at','end_at','started_actual_at','stopped_actual_at'):
                    row[field]=datetime.fromisoformat(row[field]) if row.get(field) else None
                facts[row['id']]=row
                times['worked'].append((row['started_actual_at'] or row['start_at'],row['id']))
                times['planned'].append((row['start_at'],row['id']))
            self._facts=facts;self._times={k:sorted(v) for k,v in times.items()}
            self._session_key=key
        if sessions_only: return
        store=self.ws.repo.history
        key=(store.revision,self.ws.repo.reload_generation)
        if key!=self._history_key:
            self._events=sorted((datetime.fromisoformat(r['at']),r['node_id']) for r in store.summaries()
                                if r.get('type')=='status_changed' and r.get('transition_to')=='done' and r.get('node_id'))
            self._done_ever={nid for at,nid in self._events}
            self._history_key=key

    def coerce_live(self,live):
        if live is None or isinstance(live,LiveWork):return live
        # Legacy callers pass (node_id, accumulated seconds); match the active session.
        self._prepare(sessions_only=True)
        nid,seconds=live
        matches=[r for r in self._facts.values() if r['node_id']==nid and r['status']=='active']
        row=max(matches,key=lambda r:r['start_at']) if matches else None
        return LiveWork(row['id'] if row else 'live',nid,int(seconds),
                        row['started_actual_at'] or row['start_at'] if row else utcnow())

    def live_delta(self,live):
        with self._mutex:return self._live_delta(live)

    def _live_delta(self,live):
        self._prepare(sessions_only=True);live=self.coerce_live(live)
        if live is None:return 0
        return max(0,int(live.seconds)-self._facts.get(live.session_id,{}).get('actual_seconds',0))

    def report(self,filters=ActivityFilters(),*,live=None,now=None):
        with self._mutex:
            return self._report(filters,live=live,now=now)

    def _report(self,filters,*,live=None,now=None):
        self._prepare()
        now=now or utcnow();tz=ZoneInfo(self.ws.settings.timezone)
        live=self.coerce_live(live)
        key=(filters,live,now.replace(second=0,microsecond=0),self._session_key,self._history_key,self.ws.repo.generation,self.ws.settings.timezone)
        if key in self._cache:
            self._cache.move_to_end(key);return self._cache[key]
        nodes=dict(self.ws.nodes)
        task_ids=tuple(self.ws.repo.task_ids)
        memberships={}
        first,last=filters.bounds()
        if filters.first and filters.last and filters.first>filters.last:raise ValueError('Interval invalid.')
        def in_day(day):return (first is None or day>=first) and (last is None or day<=last)
        def project_for(nid):
            if nid in memberships:return memberships[nid]
            current=nodes[nid].parent_id if nid in nodes else None
            seen={nid}
            while current in nodes and current not in seen:
                seen.add(current)
                if nodes[current].kind==Kind.PROJECT:
                    memberships[nid]=current;return current
                current=nodes[current].parent_id
            memberships[nid]=None
            return None
        def matches(pid):
            return (filters.project_id==ALL_PROJECTS or pid==filters.project_id) and (filters.focus_projects is None or pid in filters.focus_projects)
        ids=set()
        for values in self._times.values():
            lo=bisect_left(values,(datetime.combine(first,time.min,tz),'')) if first else 0
            hi=bisect_left(values,(datetime.combine(last+timedelta(days=1),time.min,tz),'')) if last else len(values)
            ids.update(rid for at,rid in values[lo:hi])
        if live: ids.add(live.session_id)
        rows=[]
        for rid in ids:
            fact=self._facts.get(rid)
            if fact is None:
                if not live or rid!=live.session_id:continue
                fact=dict(id=rid,node_id=live.node_id,start_at=live.started_at,end_at=live.started_at,
                          started_actual_at=live.started_at,status='active',actual_seconds=0)
            nid=fact['node_id'];pid=project_for(nid)
            if not matches(pid):continue
            wd=(fact['started_actual_at'] or fact['start_at']).astimezone(tz).date()
            pd=fact['start_at'].astimezone(tz).date()
            worked=max(0,fact['actual_seconds']) if in_day(wd) else 0
            # elapsed UTC seconds preserves reserved duration across DST transitions.
            planned=max(0,int((fact['end_at']-fact['start_at']).total_seconds()//60)*60) if in_day(pd) and fact['status'] not in ('cancelled','missed') and fact.get('origin')!='timer' else 0
            extra=self.live_delta(live) if live and rid==live.session_id and in_day(wd) else 0
            if not (in_day(wd) or in_day(pd)):continue
            node=nodes.get(nid);project=nodes.get(pid)
            rows.append(ActivityRow(rid,nid,node.title if node else tr('ui.meetings.task_indisponibil'),pid,
                project.title if project else tr('ui.activity_page.fara_proiect'),fact['status'],fact['start_at'],fact['end_at'],wd,pd,worked,planned,extra))
        complete=set()
        lo=bisect_left(self._events,(datetime.combine(first,time.min,tz),'')) if first else 0
        hi=bisect_left(self._events,(datetime.combine(last+timedelta(days=1),time.min,tz),'')) if last else len(self._events)
        for at,nid in self._events[lo:hi]:
            node=nodes.get(nid)
            if node and node.kind==Kind.TASK and matches(project_for(nid)):complete.add(nid)
        counts=Counter();overdue=set();legacy=0
        for nid in task_ids:
            if nid not in nodes:continue
            node=nodes[nid]
            if not matches(project_for(nid)):continue
            counts[display_status(node.status)]+=1
            if node.status==Status.DONE and nid not in self._done_ever:legacy+=1
            current=nid;seen=set();archived=False
            while current in nodes and current not in seen:
                seen.add(current);archived=archived or nodes[current].archived_at is not None;current=nodes[current].parent_id
            if node.status not in CLOSED_STATUSES and not archived:
                late=(node.due_date is not None and node.due_date<now.astimezone(tz).date()) or (node.due_date is None and node.due_at is not None and node.due_at<now)
                if late:overdue.add(nid)
        project_label=project_filter_title(filters,nodes)
        report=ActivityReport(filters,self.ws.settings.timezone,tuple(sorted(rows,key=lambda r:(r.start_at,r.id),reverse=True)),frozenset(complete),frozenset(overdue),MappingProxyType(dict(counts)),legacy,tuple(tr('services.activity.inregistrari_necitibile_omise', store_directory_name=store.directory.name, len_store_errors=len(store.errors)) for store in (self.ws.repo.sessions,self.ws.repo.history) if store.errors),project_filter_label=project_label)
        self._cache[key]=report
        while len(self._cache)>12 or (len(self._cache)>1 and sum(len(r.rows) for r in self._cache.values())>20000):self._cache.popitem(last=False)
        return report

    def relabel(self,report):
        # Title-only events update text; numerical totals and membership remain unchanged.
        def label(row):
            node=self.ws.nodes.get(row.node_id);project=self.ws.nodes.get(row.project_id)
            return replace(row,task=node.title if node else tr('ui.meetings.task_indisponibil'),project=project.title if project else tr('ui.activity_page.fara_proiect'))
        return replace(report,rows=tuple(label(row) for row in report.rows),project_filter_label=project_filter_title(report.filters,self.ws.nodes))


def activity_model(ws):
    if not hasattr(ws,'_activity_model'):ws._activity_model=ActivityModel(ws)
    return ws._activity_model


def live_snapshot(app):
    timer=app.timer
    if timer and timer.state and not timer.recovered:
        state=timer.state
        return LiveWork(state.session_id,state.node_id,int(timer.seconds),state.started_at)
    return None


def activity_ledger(ws,days=30):
    """Compatibility adapter; all arithmetic is delegated to the shared report."""
    today=datetime.now(ZoneInfo(ws.settings.timezone)).date()
    report=activity_model(ws).report(ActivityFilters(today-timedelta(days=days-1) if days else None,today if days else None))
    rows=[]
    for row in report.rows:
        fact=activity_model(ws)._facts[row.id]
        session=SimpleNamespace(**fact,planned_minutes=int((fact['end_at']-fact['start_at']).total_seconds()//60))
        rows.append((session,ws.nodes.get(row.node_id),row.project))
    return dict(days=report.days,projects=report.projects,sessions=rows,worked=report.worked,planned=report.planned)


CSV_COLUMNS=(tr('ui.dialogs.tip'),tr('activity.csv.session_id'),tr('activity.csv.task_id'),tr('ui.outlook_ui.task'),tr('ui.app.proiect'),tr('activity.csv.status'),tr('ui.activity_page.inceput_programat'),tr('services.activity.zi_lucrata'),
             tr('services.activity.lucrat_inregistrat_secunde'),tr('extra.services.activity.programat_eligibil_secunde'),tr('extra.services.activity.live_nesalvat_secunde'),
             tr('activity.csv.indicator'),tr('activity.csv.value'),tr('services.activity.definitie_filtre'))

def safe_csv(value):
    if not isinstance(value,str):return value
    if value.startswith(('\t','\r','\n')) or value.lstrip().startswith(('=','+','-','@')):return "'"+value
    return value


def csv_text(report):
    out=io.StringIO(newline='');writer=csv.writer(out,delimiter=';',lineterminator='\r\n')
    writer.writerow(CSV_COLUMNS)
    def write(values):writer.writerow([safe_csv(v) for v in values])
    tz=ZoneInfo(report.timezone)
    first,last=report.filters.bounds()
    interval=(first.strftime('%d.%m.%Y') if first else tr('services.activity.inceputul_istoricului'))+' — '+(last.strftime('%d.%m.%Y') if last else tr('ui.activity_page.tot_istoricul'))
    context=tr('services.activity.fus_perioada_proiecte_finalizari_distincte_restante_si_statusuri_situa', report_timezone=report.timezone, interval=interval, report_project_filter_label=report.project_filter_label)
    for row in report.rows:
        write((tr('ui.tab_journal.sesiune'),row.id,row.node_id,row.task,row.project,SESSION_STATUS_LABELS[row.status],row.start_at.astimezone(tz).isoformat(),row.worked_day.isoformat(),row.worked,row.planned,row.live,'','',context))
    for key,label,value in [('worked',tr('ui.activity_page.lucrat_inregistrat'),report.worked),('planned',tr('ui.tab_versions.programat'),report.planned),('completed',tr('extra.services.activity.taskuri_finalizate_distincte'),len(report.completed_ids)),('overdue',tr('ui.activity_page.restante_acum'),len(report.overdue_ids)),('live',tr('ui.activity_page.live_nesalvat'),report.live)]:
        write((tr('activity.csv.indicator'),'','','','','','','','','','',label,value,DEFINITIONS[key]+' '+context))
    write((tr('services.activity.definitie'),'','','','','','','','','','','','',tr('services.activity.istoric_incomplet_taskuri_finalizate_curent_nu_au_tranzitie_done_in_is', report_legacy_done=report.legacy_done)))
    if report.issues:write((tr('services.activity.definitie'),*('',)*12,tr('activity.csv.warnings',details='; '.join(report.issues))))
    return '\ufeff'+out.getvalue()


def export_csv(report,path):
    atomic_write_text(path,csv_text(report))
