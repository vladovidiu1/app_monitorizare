"""Read-only calendar imports, local drafts/actions and recoverable explicit node creation."""

from ..i18n import tr
from datetime import datetime
from uuid import UUID, uuid5
from ..domain.common import utcnow, new_id, is_uuid
from ..domain.meeting import MeetingSource, MeetingLocal, MeetingAction
from ..domain.models import Node, Kind, Priority, Status, HistoryEvent
from ..domain.session import OperationRecord
from ..errors import ValidationError, NotFoundError, ExternalModificationError
from ..storage.meetings import MeetingStore
from ..storage.atomic import read_json, atomic_write_json
from ..storage.records import checksum
from ..storage.followup_operations import apply_followup

class MeetingService:
    def __init__(self,ws):
        self.ws=ws;self.store=MeetingStore(ws.repo);self._importing=False
        self.config_path=ws.repo.system_dir/'meeting-source.json'

    def config(self):
        if not self.config_path.exists():return {}
        return read_json(self.config_path,allow_backup=False)[0]

    def configure(self,store_id,folder_id,label):
        self.ws.repo._require_writable()
        if not store_id or not folder_id:raise ValidationError(tr('extra.services.meetings.alege_explicit_un_calendar'))
        data=self.config();data.update(store_id=store_id,folder_id=folder_id,label=label,last_error=None)
        atomic_write_json(self.config_path,data)
        self.ws.emit('meetings_changed')

    def record_import(self,*,error=None,first=None,last=None,complete=False,warnings=()):
        self.ws.repo._require_writable();data=self.config()
        data.update(last_attempt=utcnow().isoformat(),last_error=error)
        if error is None:data.update(last_update=utcnow().isoformat(),first=first.isoformat(),last=last.isoformat(),complete=complete,last_warnings=list(warnings)[:30])
        atomic_write_json(self.config_path,data)

    @staticmethod
    def source_key(store_id,folder_id,event_uid,occurrence_key=''):
        if occurrence_key:
            try:
                from datetime import timezone
                occurrence_key=datetime.fromisoformat(occurrence_key).astimezone(timezone.utc).isoformat()
            except ValueError:pass
        if not event_uid:raise ValidationError(tr('services.meetings.eveniment_fara_identificator_stabil_nu_se_importa_dupa_titlu'))
        return checksum(['outlook',store_id,folder_id,event_uid,occurrence_key])

    def import_batch(self,store_id,folder_id,batch,first,last):
        iterator=self.iter_import_batch(store_id,folder_id,batch,first,last)
        while True:
            try:next(iterator)
            except StopIteration as result:return result.value

    def iter_import_batch(self,store_id,folder_id,batch,first,last):
        """No notes reads, no removals. A partial result never implies absence."""
        self.ws.repo._require_writable()
        if first>=last:raise ValidationError(tr('extra.services.meetings.interval_de_import_invalid'))
        config=self.config()
        if (store_id,folder_id)!=(config.get('store_id'),config.get('folder_id')):
            raise ValidationError(tr('services.meetings.sursa_selectata_s_a_schimbat_rezultatul_intarziat_este_ignorat'))
        if self._importing:raise ValidationError(tr('services.meetings.un_import_se_aplica_deja'))
        self._importing=True
        try:
            known={row['source_key']:row['id'] for row in self.store.summaries() if row['provider']=='outlook'}
            known_ids=set(known.values())
            seen=set();count=0;processed=0;warnings=list(batch.warnings);complete=batch.complete
            for index,event in enumerate(batch.events,1):
                if event.end<=first or event.start>=last:continue
                if event.session_id:continue # FocusDesk marker, never subject text
                try:
                    key=self.source_key(store_id,folder_id,event.uid,event.occurrence_key)
                    mid=known.get(key,str(uuid5(UUID(self.ws.id),'meeting:'+key)))
                    if key in seen:continue
                    if mid in known_ids:self.store.source(mid)
                    record=MeetingSource(id=mid,provider='outlook',source_key=key,store_id=store_id,folder_id=folder_id,
                        event_uid=event.uid,occurrence_key=event.occurrence_key,entry_id=event.entry_id,
                        title=event.title or tr('services.meetings.fara_titlu'),start_at=event.start,end_at=event.end,timezone=self.ws.settings.timezone,
                        source_timezone=event.timezone,location=event.location,organizer=event.organizer,join_url=event.join_url,
                        all_day=event.all_day,all_day_start=event.all_day_start,all_day_end=event.all_day_end,state='cancelled' if event.cancelled else 'present')
                    self.store.save_source(record);seen.add(key);known[key]=mid;known_ids.add(mid);count+=1
                except Exception as exc:
                    complete=False;warnings.append(str(exc))
                processed+=1
                if processed%8==0:yield dict(applied=count,total=len(batch.events))
            if complete:
                absent=0
                for index,row in enumerate(self.store.summaries(),1):
                    if row['provider']!='outlook' or (row['store_id'],row['folder_id'])!=(store_id,folder_id):continue
                    if datetime.fromisoformat(row['end_at'])<=first or datetime.fromisoformat(row['start_at'])>=last:continue
                    if row['source_key'] in seen or row['state']=='cancelled':continue
                    source=self.store.source(row['id']);source.state='not_seen';self.store.save_source(source)
                    absent+=1
                    if absent%8==0:yield dict(applied=count,total=len(batch.events))
            self.record_import(first=first,last=last,complete=complete,error=None,warnings=warnings)
            self.store.flush();self.ws.emit('meetings_changed')
            return dict(count=count,complete=complete,warnings=warnings)
        finally:self._importing=False

    def manual(self,*,title,start,end,location='',request_id=None):
        self.ws.repo._require_writable();mid=request_id or new_id()
        record=MeetingSource(id=mid,title=title,start_at=start,end_at=end,location=location,timezone=self.ws.settings.timezone)
        try:existing=self.store.source(mid)
        except NotFoundError:existing=None
        if existing is not None:
            if (existing.title,existing.start_at,existing.end_at,existing.location)!=(record.title,record.start_at,record.end_at,record.location):
                raise ValidationError(tr('services.meetings.aceasta_intalnire_a_fost_deja_creata_cu_alte_date_nu_se_suprascrie_la'))
            return existing
        self.store.save_source(record);self.ws.emit('meetings_changed');return record

    def save_notes(self,mid,text):
        self.store.save_notes(mid,text);self.ws.emit('meeting_notes_changed',meeting_id=mid)

    def save_action(self,mid,*,text,responsible='',due_date=None,state='clarify',action_id=None,expected=None):
        self.ws.repo._require_writable();self.store.source(mid);local=self.store.local(mid)
        action=MeetingAction(id=action_id or new_id(),text=text,responsible=responsible,due_date=due_date,state=state)
        old=next((a for a in local.actions if a.id==action.id),None)
        if expected is not None and old!=expected:raise ExternalModificationError(tr('services.meetings.actiunea_s_a_modificat_dupa_deschiderea_dialogului_reincarca_inainte_d'))
        if old and old.node_id:raise ValidationError(tr('services.meetings.actiunea_este_deja_transformata_deschide_taskul_legat'))
        if state=='converted':raise ValidationError(tr('services.meetings.foloseste_crearea_explicita_a_unui_task_proiect'))
        local.actions=[action if a.id==action.id else a for a in local.actions] if old else [*local.actions,action]
        self.store.save_local(mid,local);self.ws.emit('meetings_changed',meeting_id=mid);return action

    def list(self,*,mode='upcoming',text='',first=None,last=None,node_id=None,offset=0,limit=100,now=None):
        now=now or utcnow();rows=[]
        for row in self.store.summaries():
            start=datetime.fromisoformat(row['start_at']);end=datetime.fromisoformat(row['end_at'])
            if mode=='upcoming' and end<now:continue
            if mode=='past' and end>=now:continue
            if mode=='notes' and not row['has_notes']:continue
            if mode=='actions' and not row['unconverted']:continue
            if node_id and node_id not in row['links'] and not (node_id in self.ws.nodes and row['id'] in self.ws.nodes[node_id].meeting_ids):continue
            if text.casefold() not in row['title'].casefold():continue
            if first and end<=first:continue
            if last and start>=last:continue
            rows.append(row)
        rows.sort(key=lambda r:(r['start_at'],r['id']),reverse=mode=='past')
        return rows[offset:offset+limit],len(rows)

    def search_notes(self,text):
        """Explicit operation; never called by the ordinary title search trace."""
        return [r['id'] for r in self.store.summaries() if r['has_notes'] and text.casefold() in self.store.notes(r['id'],observe=False).casefold()]

    def _destination(self,kind,parent_id):
        self.ws.check_parent(kind,parent_id)
        self.ws.followups.validate_destination(parent_id)

    def create_node(self,mid,*,request_id,title,description='',kind=Kind.TASK,parent_id=None,priority=Priority.NORMAL,
                    due_date=None,action_id=None,followup_source=None,code_access='none'):
        self.ws.repo._require_writable()
        if not is_uuid(request_id):raise ValidationError(tr('services.meetings.identificator_de_operatie_invalid'))
        payload=dict(meeting_id=mid,title=title,description=description,kind=Kind(kind).value,parent_id=parent_id,
            priority=Priority(priority).value,due_date=due_date.isoformat() if due_date else None,action_id=action_id,
            followup_source=followup_source,code_access=code_access)
        fingerprint=checksum(payload)
        try:op=self.ws.repo.operations.get(request_id)
        except NotFoundError:op=None
        if op:
            if op.type!='meeting_convert' or op.data['fingerprint']!=fingerprint:raise ValidationError(tr('services.meetings.operatia_exista_cu_alte_date_reincearca_datele_initiale'))
            return self._apply(op)
        self.store.source(mid);local=self.store.local(mid)
        if action_id:
            for pending in self.ws.repo.operations.select(predicate=lambda r:r.get('type')=='meeting_convert' and r.get('state')=='pending'):
                pp=pending.data.get('payload',{})
                if pending.data.get('meeting_id')==mid and pp.get('action_id')==action_id:
                    if pending.data['fingerprint']!=fingerprint:
                        raise ValidationError(tr('services.meetings.actiunea_are_deja_o_creare_in_curs_reincearca_datele_initiale_sau_recu'))
                    return self._apply(pending)
        action=next((a for a in local.actions if a.id==action_id),None)
        if action_id and action is None:raise ValidationError(tr('services.meetings.actiunea_nu_mai_exista'))
        if action and action.node_id:
            if action.node_id not in self.ws.nodes:raise NotFoundError(tr('services.meetings.taskul_creat_este_indisponibil_sau_in_cos_nu_il_recreez'))
            return self.ws.get(action.node_id)
        kind=Kind(kind)
        if followup_source and kind!=Kind.TASK:raise ValidationError(tr('services.meetings.o_cerinta_ulterioara_este_un_task_nu_un_proiect'))
        if kind not in (Kind.TASK,Kind.PROJECT):raise ValidationError(tr('services.meetings.creeaza_un_task_sau_un_proiect'))
        self._destination(kind,parent_id)
        seed_id=str(uuid5(UUID(request_id),'node'))
        nid=str(uuid5(UUID(seed_id),'requirement'))
        # Validate before journalling; followup creation uses the same existing service.
        node=Node(id=nid,kind=kind,title=title,parent_id=parent_id,priority=priority,status=Status.TODO,
            due_date=due_date,meeting_ids=[mid],creation_operation_id=seed_id)
        op=OperationRecord(id=request_id,type='meeting_convert',data=dict(fingerprint=fingerprint,payload=payload,node=node.model_dump(mode='json'),
            seed_id=seed_id,new_node_id=nid,meeting_id=mid,action_before=action.model_dump(mode='json') if action else None))
        self.ws.repo.operations.save(op)
        return self._apply(op)

    def _apply(self,op):
        self.ws.repo._require_writable()
        if op.state=='done':
            if op.data['new_node_id'] not in self.ws.nodes:raise NotFoundError(tr('extra.services.meetings.taskul_creat_nu_mai_este_disponibil_nu_creez_un_duplicat'))
            return self.ws.get(op.data['new_node_id'])
        p=op.data['payload'];mid=op.data['meeting_id'];self.store.source(mid)
        if p['followup_source']:
            from datetime import date
            node=self.ws.followups.create(p['followup_source'],title=p['title'],description=p['description'],parent_id=p['parent_id'],
                priority=p['priority'],due_date=date.fromisoformat(p['due_date']) if p['due_date'] else None,
                code_access=p['code_access'],request_id=op.data['seed_id'],meeting_ids=[mid])
        else:
            try:seed=self.ws.repo.operations.get(op.data['seed_id'])
            except NotFoundError:
                event=HistoryEvent(id=str(uuid5(UUID(op.id),'created')),node_id=op.data['new_node_id'],type='created',data=dict(meeting_id=mid))
                seed=OperationRecord(id=op.data['seed_id'],type='meeting_node_seed',data=dict(fingerprint=op.data['fingerprint'],node=op.data['node'],
                    description=p['description'],events=[event.model_dump(mode='json')]))
                self.ws.repo.operations.save(seed)
            if 'node' in seed.steps_done and op.data['new_node_id'] not in self.ws.nodes:
                raise NotFoundError(tr('services.meetings.taskul_creat_a_devenit_indisponibil_restaureaza_l_nu_se_recreeaza_auto'))
            nid=apply_followup(self.ws.repo,seed)
            if nid not in self.ws.nodes:raise NotFoundError(tr('services.meetings.taskul_creat_este_in_cos_nu_il_recreez'))
            node=self.ws.get(nid)
        self._finish_link(mid,node.id,p['action_id'],op.data.get('action_before'))
        op.data=dict(fingerprint=op.data['fingerprint'],new_node_id=node.id,meeting_id=mid)
        op.state='done';op.updated_at=utcnow();self.ws.repo.operations.save(op)
        self.ws.emit('node_created',node_id=node.id);self.ws.emit('meetings_changed',meeting_id=mid)
        return node

    def _finish_link(self,mid,nid,action_id=None,action_before=None):
        local=self.store.local(mid)
        if action_id:
            action=next((a for a in local.actions if a.id==action_id),None)
            if action is None:raise ExternalModificationError(tr('services.meetings.actiunea_a_fost_eliminata_legatura_nu_este_confirmata'))
            if action.node_id and action.node_id!=nid:raise ExternalModificationError(tr('services.meetings.actiunea_este_legata_de_alt_task'))
            if not action.node_id and action.model_dump(mode='json')!=action_before:
                raise ExternalModificationError(tr('services.meetings.actiunea_a_fost_modificata_nu_o_suprascriu'))
            action.node_id=nid;action.state='converted'
        if nid not in local.linked_node_ids:local.linked_node_ids.append(nid)
        self.store.save_local(mid,local)

    def link(self,mid,nid):
        self.ws.repo._require_writable();self.store.source(mid);node=self.ws.get(nid)
        if node.kind not in (Kind.TASK,Kind.PROJECT):raise ValidationError(tr('services.meetings.leaga_un_task_sau_un_proiect'))
        oid=str(uuid5(UUID(self.ws.id),'meeting-link:'+mid+':'+nid))
        try:op=self.ws.repo.operations.get(oid)
        except NotFoundError:
            op=OperationRecord(id=oid,type='meeting_link',data=dict(meeting_id=mid,node_id=nid));self.ws.repo.operations.save(op)
        self._apply_link(op)

    def _apply_link(self,op):
        mid=op.data['meeting_id'];nid=op.data['node_id'];self.store.source(mid);node=self.ws.get(nid)
        if mid not in node.meeting_ids:self.ws.update_node(nid,meeting_ids=[*node.meeting_ids,mid])
        self._finish_link(mid,nid)
        op.state='done';self.ws.repo.operations.save(op)
        self.ws.emit('meetings_changed',meeting_id=mid)

    def recover(self):
        if self.ws.read_only:return []
        messages=[]
        for op in self.ws.repo.operations.select(predicate=lambda r:r.get('state')=='pending' and r.get('type') in ('meeting_convert','meeting_link')):
            try:
                self._apply(op) if op.type=='meeting_convert' else self._apply_link(op)
                messages.append(tr('services.meetings.operatia_intalnirii_a_fost_recuperata_fara_duplicate'))
            except Exception as exc:messages.append(tr('services.meetings.operatie_intalnire_in_asteptare')+str(exc))
        return messages

    def integrity(self,*,include_notes=False):
        self.store.invalidate();rows=self.store.summaries();issues=list(self.store.issues)
        for row in rows:
            mid=row['id']
            try:
                local=self.store.local(mid)
                if include_notes:self.store.notes(mid,observe=False)
                for nid in local.linked_node_ids:
                    if nid not in self.ws.nodes:issues.append((mid,tr('services.meetings.referinta_la_task_proiect_indisponibil')+nid))
                    elif mid not in self.ws.nodes[nid].meeting_ids:issues.append((mid,tr('services.meetings.legatura_inversa_lipsa_pentru')+nid))
            except Exception as exc:issues.append((mid,str(exc)))
        known={r['id'] for r in rows}
        for node in self.ws.nodes.values():
            for mid in node.meeting_ids:
                if mid not in known:issues.append((node.id,tr('services.meetings.intalnire_indisponibila')+mid))
        return issues


def meeting_state(row,now=None):
    now=now or utcnow()
    if row['state']=='cancelled':return tr('domain.labels.anulata')
    if row['state']=='not_seen':return tr('services.meetings.sursa_neconfirmata')
    start=datetime.fromisoformat(row['start_at']);end=datetime.fromisoformat(row['end_at'])
    return tr('services.meetings.urmeaza') if now<start else tr('services.meetings.in_desfasurare') if now<end else tr('domain.labels.incheiata')
