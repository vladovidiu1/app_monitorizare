"""Later requirements are independent tasks, not reminders, children or recurrences."""

from ..i18n import tr
from uuid import UUID, uuid5
from ..domain.common import is_uuid, utcnow
from ..domain.models import Node, Kind, Status, Priority, ChecklistItem, SourceWorkspace, HistoryEvent
from ..domain.session import OperationRecord
from ..errors import ValidationError, StorageError, NotFoundError, CycleError
from ..storage.atomic import dump_json, sha256_bytes
from ..storage.paths import physical_dirname, ensure_path_fits
from ..storage.followup_operations import apply_followup


class FollowupService:
    def __init__(self,ws):self.ws=ws;self._index_key=-1;self._reverse={}

    def validate_relation(self,node_id,source_id):
        if source_id is None:return
        source=self.ws.get(source_id)
        if source.kind!=Kind.TASK:raise ValidationError(tr('services.followups.o_cerinta_ulterioara_trebuie_sa_continue_un_task'))
        seen={node_id};current=source_id
        while current is not None:
            if current in seen:raise CycleError(tr('services.followups.relatia_cerintelor_ar_crea_un_ciclu'))
            if current not in self.ws.nodes:break
            seen.add(current);current=self.ws.nodes[current].continuation_of

    def children(self,node_id):
        if self._index_key!=self.ws.repo.generation:
            result={}
            for node in self.ws.nodes.values():
                if node.continuation_of:result.setdefault(node.continuation_of,[]).append(node.id)
            self._reverse=result;self._index_key=self.ws.repo.generation
        return sorted((self.ws.nodes[nid] for nid in self._reverse.get(node_id,[])),key=lambda n:(n.created_at,n.id))

    def lineage(self,node_id):
        out=[];seen=set();current=node_id
        while current is not None:
            if current in seen:raise CycleError(tr('storage.repository.ciclu_in_lantul_cerintelor'))
            seen.add(current);out.append(current)
            node=self.ws.nodes.get(current)
            if node is None:break
            current=node.continuation_of
        return out

    def family_ids(self,node_id):
        root=self.lineage(node_id)[-1];out=set();stack=[root]
        while stack:
            nid=stack.pop()
            if nid in out:continue
            out.add(nid);stack.extend(n.id for n in self.children(nid))
        return out

    def own_seconds(self,node_id):return self.ws.repo.sessions.worked_for_node(node_id)

    def validate_destination(self,parent_id):
        self.ws.check_parent(Kind.TASK,parent_id)
        if parent_id is not None and any(n.archived_at is not None for n in (*self.ws.ancestors(parent_id),self.ws.get(parent_id))):
            raise ValidationError(tr('services.followups.destinatia_este_arhivata_alege_explicit_un_container_activ_sau_radacin'))
        if parent_id is not None:self.ws.repo._check_unmodified(parent_id,'node.json',self.ws.node_dir(parent_id)/'node.json')
        if parent_id is not None and not (self.ws.node_dir(parent_id)/'node.json').is_file():
            raise ValidationError(tr('services.followups.destinatia_nu_mai_este_disponibila_alege_alt_container'))

    def create(self,source_id,*,title,description='',requested_by=None,priority=None,due_date=None,
               parent_id=...,copy_description=False,copy_checklist=False,code_access='none',code_folder=None,request_id,meeting_ids=()):
        self.ws._check_writable()
        if not is_uuid(request_id):raise ValidationError(tr('services.followups.identificator_de_operatie_invalid'))
        # Normalize user data before hashing, independently of later source edits.
        candidate=self.ws._build_node(dict(kind=Kind.TASK,title=title,status=Status.TODO,priority=priority or Priority.NORMAL,
            requested_by=requested_by,due_date=due_date,meeting_ids=list(meeting_ids)))
        payload=dict(source_id=source_id,title=candidate.title,description=description,requested_by=candidate.model_dump(mode='json')['requested_by'],
            priority=candidate.priority.value,due_date=candidate.due_date.isoformat() if candidate.due_date else None,
            parent_id='same' if parent_id is ... else parent_id,copy_description=copy_description,copy_checklist=copy_checklist,
            code_access=code_access,code_folder=str(code_folder) if code_folder else None)
        if candidate.meeting_ids:payload['meeting_ids']=candidate.meeting_ids
        fingerprint=sha256_bytes(dump_json(payload))
        try:old=self.ws.repo.operations.get(request_id)
        except NotFoundError:old=None
        if old is not None:
            same=old.type=='followup_create' and old.data.get('fingerprint')==fingerprint
            if not same:
                old_node=Node.model_validate(old.data['node']) if old.type=='followup_create' and old.state=='pending' else None
                reserved=self.ws.repo.nodes_dir/physical_dirname(old_node.title,old_node.id) if old_node else None
                if old_node is None or reserved.exists() or old_node.id in self.ws.nodes:
                    raise ValidationError(tr('services.followups.operatia_a_fost_deja_inceputa_cu_alte_date_reincearca_datele_initiale'))
                # No authoritative task has been written: the same stable request may be corrected.
            elif old.state=='done':
                nid=old.data['new_node_id']
                if nid not in self.ws.nodes:raise ValidationError(tr('services.followups.cerinta_creata_este_in_cos_sau_indisponibila_nu_se_recreeaza_automat'))
                return self.ws.get(nid)
            else:
                nid=apply_followup(self.ws.repo,old)
                self.ws.emit('node_created',node_id=nid);return self.ws.get(nid)
        source=self.ws.get(source_id)
        if source.kind!=Kind.TASK:raise ValidationError(tr('services.followups.selecteaza_un_task_sursa'))
        if not (self.ws.node_dir(source_id)/'node.json').is_file():raise ValidationError(tr('services.followups.taskul_sursa_nu_mai_este_disponibil'))
        self.ws.repo._check_unmodified(source_id,'node.json',self.ws.node_dir(source_id)/'node.json')
        destination=source.parent_id if parent_id is ... else parent_id
        self.validate_destination(destination)
        if destination==source_id:raise ValidationError(tr('services.followups.alege_un_container_separat_de_taskul_sursa'))
        if code_access not in ('none','shared','folder'):raise ValidationError(tr('services.followups.alegere_necunoscuta_pentru_accesul_la_cod'))
        from .files import FileService
        files=FileService(self.ws)
        sw=SourceWorkspace(mode='disabled')
        if code_access=='shared':sw=files.shared_access(source_id)
        elif code_access=='folder':
            from pathlib import Path
            folder=Path(code_folder or '')
            if not folder.is_absolute() or not folder.is_dir():raise ValidationError(tr('services.followups.alege_un_folder_de_cod_existent_cu_cale_absoluta'))
            sw=SourceWorkspace(mode='external',path=str(folder))
        text=description
        if copy_description:
            original=self.ws.get_description(source_id)
            separator='' if not original or original.endswith('\n\n') else '\n' if original.endswith('\n') else '\n\n'
            text=original+separator+description if description else original
        nid=str(uuid5(UUID(request_id),'requirement'))
        self.validate_relation(nid,source_id)
        data=candidate.model_dump(mode='python')
        data.update(id=nid,parent_id=destination,continuation_of=source_id,creation_operation_id=request_id,source_workspace=sw,
            sort_order=max((n.sort_order for n in self.ws.nodes.values() if n.parent_id==destination),default=0)+10,
            checklist=[ChecklistItem(text=item.text,done=False) for item in source.checklist] if copy_checklist else [])
        node=Node.model_validate(data)
        path=self.ws.repo.nodes_dir/physical_dirname(node.title,nid);ensure_path_fits(path)
        if path.exists():raise StorageError(tr('services.followups.directorul_rezervat_exista_deja_nu_se_suprascrie'))
        now=utcnow();events=[]
        for key,kind,node_id,event_data in (
            ('created','created',nid,{'title':node.title,'kind':'task','continuation_of':source_id}),
            ('source','followup_created',source_id,{'new_node_id':nid,'title':node.title}),
            ('link','followup_linked',nid,{'source_id':source_id,'title':source.title})):
            events.append(HistoryEvent(id=str(uuid5(UUID(request_id),key)),at=now,type=kind,node_id=node_id,data=event_data).model_dump(mode='json'))
        op=OperationRecord(id=request_id,type='followup_create',data=dict(fingerprint=fingerprint,node=node.model_dump(mode='json'),description=text,events=events))
        self.ws.repo.operations.save(op)
        try:nid=apply_followup(self.ws.repo,op)
        except Exception as exc:
            self.ws.emit('node_created',node_id=nid)
            raise StorageError(tr('services.followups.crearea_nu_este_confirmata_ciorna_se_pastreaza_reincearca_aceleasi_dat', exc=exc)) from exc
        self.ws.emit('node_created',node_id=nid)
        return self.ws.get(nid)
