"""Local template catalog and recoverable, idempotent instantiation through Workspace."""
from __future__ import annotations
from importlib.resources import files
from pathlib import Path
from ..domain.templates import StructureTemplate, TemplateItem, MAX_TEMPLATE_BYTES, substitute
from ..domain.models import Kind, Node, Status, Priority, ChecklistItem
from ..domain.common import new_id, is_uuid, utcnow
from ..domain.session import OperationRecord
from ..errors import ValidationError, ExternalModificationError, StorageError
from ..storage.atomic import atomic_write_json, dump_json, sha256_bytes
from ..storage.paths import physical_dirname, ensure_path_fits, is_reparse_point
from ..storage.template_operations import rollback_template


def parse_template(raw: bytes) -> StructureTemplate:
    if len(raw)>MAX_TEMPLATE_BYTES:raise ValidationError('Șablonul depășește limita de 2 MiB.')
    try:return StructureTemplate.model_validate_json(raw)
    except (ValueError,RecursionError) as exc:raise ValidationError(f'Șablon JSON invalid: {exc}') from exc


def digest(template):return sha256_bytes(dump_json(template.model_dump(mode='json')))

class TemplateService:
    def __init__(self,ws):self.ws=ws;self.issues=[]
    @property
    def directory(self):return self.ws.repo.system_dir/'templates'

    def _path(self,template_id):
        if not is_uuid(template_id):raise ValidationError('ID șablon invalid')
        path=self.directory/f'{template_id}.json'
        if is_reparse_point(self.directory) or is_reparse_point(path):raise StorageError('Calea șabloanelor nu poate fi o legătură')
        return path

    def catalog(self):
        self.issues=[];out=[]
        resource=files('focusdesk').joinpath('resources','templates')
        for file in sorted(resource.iterdir(),key=lambda p:p.name):
            if file.name.endswith('.json'):out.append((parse_template(file.read_bytes()),True))
        if self.directory.exists():
            if is_reparse_point(self.directory):raise StorageError('Director de șabloane nesigur')
            for path in sorted(self.directory.glob('*.json')):
                try:
                    t=self.read(path)
                    if self._path(t.id)!=path:raise ValidationError('Numele fișierului nu corespunde ID-ului')
                    out.append((t,False))
                except Exception as exc:self.issues.append(f'{path.name}: {exc}')
        return out

    @staticmethod
    def read(path):
        with Path(path).open('rb') as file:return parse_template(file.read(MAX_TEMPLATE_BYTES+1))

    def save(self,template,*,expected_hash=None):
        self.ws._check_writable();template=parse_template(dump_json(template.model_dump(mode='json')))
        path=self._path(template.id)
        if path.exists():
            current=self.read(path)
            if expected_hash is None or digest(current)!=expected_hash:raise ExternalModificationError('Șablonul a fost schimbat. Redeschide editorul.')
            template=template.model_copy(update={'revision':current.revision+1})
        elif expected_hash is not None:raise ExternalModificationError('Șablonul a fost șters între timp.')
        atomic_write_json(path,template.model_dump(mode='json'))
        self.ws.emit('templates_changed');return template

    def duplicate(self,template,name=None):
        return self.save(template.model_copy(update={'id':new_id(),'revision':1,'name':name or template.name+' — copie'}))

    def delete(self,template,expected_hash):
        self.ws._check_writable();path=self._path(template.id)
        if digest(self.read(path))!=expected_hash:raise ExternalModificationError('Șablonul a fost schimbat. Reîncarcă lista.')
        path.unlink();path.with_name(path.name+'.bak').unlink(missing_ok=True);self.ws.emit('templates_changed')

    def import_file(self,path):return self.duplicate(self.read(path))
    def export_file(self,template,path):
        # The path is chosen explicitly by the user; no path contained in JSON is ever interpreted.
        template=parse_template(dump_json(template.model_dump(mode='json')))
        atomic_write_json(Path(path),template.model_dump(mode='json'),keep_backup=False)

    def capture(self,node_id,name):
        self.ws._check_writable()
        if self.ws.get(node_id).kind not in (Kind.TASK,Kind.PROJECT):raise ValidationError('Selectează un proiect sau task.')
        ids=[];seen=set();stack=[node_id];children=self.ws.children_map()
        while stack:
            value=stack.pop()
            if value in seen:raise ValidationError('Structura sursă conține un ciclu.')
            seen.add(value);ids.append(value)
            if len(ids)>500:raise ValidationError('Maximum 500 elemente într-un șablon.')
            stack.extend(reversed([n.id for n in children.get(value,[])]))
        keys={value:f'n{i}' for i,value in enumerate(ids)}
        items=[]
        for value in ids:
            node=self.ws.get(value)
            items.append(TemplateItem(key=keys[value],parent=keys.get(node.parent_id),kind=node.kind,
                title=node.title,description=self.ws.get_description(value),checklist=[c.text for c in node.checklist],
                priority=node.priority,tags=list(node.tags),estimated_minutes=node.estimated_minutes,next_action=node.next_action,
                depends_on=[keys[i] for i in node.depends_on_ids if i in keys],related=[keys[i] for i in node.related_node_ids if i in keys]))
        return StructureTemplate(name=name,items=items)

    def preview(self,template,*,title,parent_id=None,values=None):
        template=parse_template(dump_json(template.model_dump(mode='json')))
        values=values or {}
        if set(values)!=set(template.variables) or any(not isinstance(v,str) or not v.strip() or len(v)>10_000 for v in values.values()):
            raise ValidationError('Completează toate variabilele declarate (text de maximum 10000 caractere).')
        self.ws.check_parent(template.root.kind,parent_id)
        result=[];expanded_bytes=0
        for item in template.ordered():
            data=item.model_dump(mode='json')
            data['title']=substitute(title if item.parent is None else item.title,values,limit=300)
            data['description']=substitute(item.description,values)
            expanded_bytes+=len(dump_json(data))
            if expanded_bytes>MAX_TEMPLATE_BYTES:raise ValidationError('Structura rezultată depășește 2 MiB.')
            result.append(TemplateItem.model_validate(data))
        expanded=StructureTemplate(name=template.name,items=result)
        return parse_template(dump_json(expanded.model_dump(mode='json')))

    def create(self,template,*,title,parent_id=None,values=None,request_id):
        self.ws._check_writable()
        if not is_uuid(request_id):raise ValidationError('ID cerere invalid')
        expanded=self.preview(template,title=title,parent_id=parent_id,values=values)
        fingerprint=sha256_bytes(dump_json({'template':expanded.model_dump(mode='json',exclude={'id'}),'parent':parent_id}))
        # preview creates a fresh identity, deliberately excluded from idempotency signature.
        old=next((o for o in self.ws.repo.operations.list_all() if o.id==request_id),None)
        if old:
            if old.type!='template_create' or old.data.get('fingerprint')!=fingerprint:raise ValidationError('Cererea a fost deja folosită cu alte date.')
            if old.state=='done':
                root_id=old.data['nodes'][0]['id']
                if root_id not in self.ws.nodes:raise ValidationError('Structura creată anterior nu mai este disponibilă. Nu se recreează automat.')
                return self.ws.get(root_id)
            raise StorageError('Cererea anterioară nu a fost finalizată. Verifică recuperarea, apoi deschide un dialog nou.')
        ids={i.key:new_id() for i in expanded.items};nodes=[]
        for i,item in enumerate(expanded.items):
            node=Node(id=ids[item.key],kind=item.kind,title=item.title,parent_id=ids[item.parent] if item.parent else parent_id,
                status=Status.TODO if item.kind!=Kind.FOLDER else None,priority=item.priority or Priority.NORMAL,
                checklist=[ChecklistItem(text=text,done=False) for text in item.checklist],tags=item.tags,
                estimated_minutes=item.estimated_minutes,remaining_minutes=item.estimated_minutes,next_action=item.next_action,
                related_node_ids=[ids[k] for k in item.related],depends_on_ids=[ids[k] for k in item.depends_on],
                sort_order=(max((n.sort_order for n in self.ws.nodes.values() if n.parent_id==parent_id),default=0)+10) if item.parent is None else (i+1)*10)
            path=self.ws.repo.nodes_dir/physical_dirname(node.title,node.id);ensure_path_fits(path)
            if path.exists():raise StorageError('Coliziune de director; nimic nu a fost creat.')
            nodes.append(node)
        op=OperationRecord(id=request_id,type='template_create',data={'fingerprint':fingerprint,'nodes':[n.model_dump(mode='json') for n in nodes]})
        self.ws.repo.operations.save(op)
        try:
            for node,item in zip(nodes,expanded.items):self.ws.repo.create_node(node,item.description)
            op.state='done';op.updated_at=utcnow();self.ws.repo.operations.save(op)
        except Exception as exc:
            try:rollback_template(self.ws.repo,op)
            except Exception as recovery:
                self.ws.reload();raise StorageError(f'Creare incompletă: {exc}. Recuperarea trebuie reluată la redeschidere: {recovery}') from exc
            self.ws.repo.write_index()
            raise StorageError(f'Crearea a eșuat; toate elementele noi au fost retrase: {exc}') from exc
        # Authoritative nodes and the committed operation are already durable; the index is only a cache.
        try:self.ws.repo.write_index()
        except Exception:pass
        self.ws.emit('node_created',node_id=nodes[0].id)
        return nodes[0]
