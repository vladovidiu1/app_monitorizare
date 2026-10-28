"""Forward recovery of one requirement plus typed relation and deterministic events."""
from pathlib import Path
from ..domain.models import Node, HistoryEvent
from ..domain.common import utcnow
from ..errors import StorageError, ExternalModificationError, NotFoundError
from .atomic import atomic_write_json, atomic_write_text, read_json
from .paths import physical_dirname, is_reparse_point
from .repository import NODE_SUBDIRS


def apply_followup(repo,op):
    repo._require_writable()
    if op.state=='done':return op.data['new_node_id']
    node=Node.model_validate(op.data['node'])
    current=node.continuation_of;seen={node.id}
    while current is not None:
        if current in seen:raise StorageError('Ciclu în relația cerințelor; recuperarea necesită corectarea relației.')
        if current not in repo.nodes:break
        seen.add(current);current=repo.nodes[current].continuation_of
    target=repo.nodes_dir/physical_dirname(node.title,node.id)
    if node.creation_operation_id!=op.id:raise StorageError('Identificator de operație neconcordant')
    repo.mark_index_dirty()
    if not target.exists():
        current=node.parent_id;seen=set()
        while current is not None:
            if current not in repo.nodes:raise StorageError('Destinația cerinței nu mai este disponibilă; restaurează containerul sau alege explicit altă destinație în dialog.')
            if current in seen or repo.nodes[current].archived_at is not None:raise StorageError('Destinația este arhivată sau invalidă; recuperarea așteaptă o destinație activă.')
            seen.add(current);current=repo.nodes[current].parent_id
        repo.create_node(node,op.data['description'])
    else:
        if is_reparse_point(target) or is_reparse_point(repo.nodes_dir):raise StorageError('Director de recuperare nesigur')
        path=target/'node.json'
        if path.exists():
            stored=Node.model_validate(read_json(path,allow_backup=False)[0])
            if stored.id!=node.id or stored.creation_operation_id!=op.id or stored.continuation_of!=node.continuation_of:
                raise ExternalModificationError('Identitatea sau relația taskului în curs de creare s-a schimbat; nu se suprascrie.')
        else:
            if 'node' in op.steps_done:raise ExternalModificationError('Taskul creat a fost șters extern; nu se recreează automat.')
            # A reserved, interrupted create may contain only empty setup directories.
            if any(p.name not in NODE_SUBDIRS or not p.is_dir() or any(p.iterdir()) for p in target.iterdir()):
                raise StorageError('Directorul rezervat conține date neașteptate; nu se suprascrie.')
            atomic_write_json(path,node.model_dump(mode='json'))
        description=target/'description.md'
        if description.exists():
            if description.read_text(encoding='utf-8-sig')!=op.data['description']:
                raise ExternalModificationError('Descrierea cerinței a fost modificată extern; ciorna nu se suprascrie.')
        elif 'node' in op.steps_done:
            raise ExternalModificationError('Descrierea cerinței a fost ștearsă extern.')
        else:atomic_write_text(description,op.data['description'])
        for name in NODE_SUBDIRS:(target/name).mkdir(exist_ok=True)
        if node.id not in repo.nodes:repo.load_node_dir(target)
        else:repo.reload_node(node.id)
    if 'node' not in op.steps_done:
        op.steps_done.append('node');op.updated_at=utcnow();repo.operations.save(op)
    for event_data in op.data['events']:
        event=HistoryEvent.model_validate(event_data)
        try:existing=repo.history.get(event.id)
        except NotFoundError:repo.history.save(event)
        else:
            if existing.model_dump(mode='json')!=event.model_dump(mode='json'):
                raise ExternalModificationError('Evenimentul operației a fost modificat; nu se suprascrie.')
    # Durable compact receipt: no second permanent copy of description/checklist.
    op.data={'fingerprint':op.data['fingerprint'],'new_node_id':node.id,'source_id':node.continuation_of}
    op.state='done';op.updated_at=utcnow();repo.operations.save(op)
    return node.id


def recover_followups(repo):
    if repo.read_only:return []
    messages=[]
    for op in repo.operations.select(predicate=lambda row:row.get('type')=='followup_create' and row.get('state')=='pending'):
        try:
            apply_followup(repo,op)
            messages.append('Cerința nouă întreruptă a fost recuperată, fără duplicate.')
        except Exception as exc:
            messages.append(f'Cerință nouă în așteptarea recuperării: {exc}')
    return messages
